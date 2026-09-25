<?php
/**
 * Safe, additive schema upgrades.
 *
 * - Every step is idempotent (checks before it changes anything).
 * - Before the first pending step runs, every existing table is copied to
 *   bak_<UTC stamp>_<table> inside the same database.
 * - Nothing is dropped, renamed or deleted. Existing rows keep working.
 * - A MySQL named lock makes sure only one request upgrades at a time.
 */
declare(strict_types=1);
require_once __DIR__ . '/helpers.php';
// step 6 seeds the plan rows using plan_seed_rows() from plans.php; include
// it here so the migration works from any entry point (installer, auto-run,
// or the Database page), not only when bootstrap.php happened to load it.
require_once __DIR__ . '/plans.php';

const SCHEMA_VERSION = 12;

function schema_version(): int
{
    $v = setting('schema_version');
    if ($v !== null) {
        return (int)$v;
    }
    // no marker: the original release (schema 1) or an empty database (0)
    return table_exists('licenses', true) ? 1 : 0;
}

function schema_pending(): bool
{
    return schema_version() < SCHEMA_VERSION;
}

function migrate_if_needed(): void
{
    static $checked = false;
    if ($checked || !cfg('AUTO_MIGRATE', true)) {
        return;
    }
    $checked = true;
    try {
        if (schema_pending()) {
            run_migrations(true, 'auto');
        }
    } catch (Throwable $e) {
        error_log('[mavelylink] schema upgrade failed: ' . $e->getMessage());
    }
}

function mig_add_column(PDO $pdo, string $table, string $column, string $definition): void
{
    if (!column_exists($table, $column)) {
        $pdo->exec("ALTER TABLE `$table` ADD COLUMN `$column` $definition");
    }
}

/** Copy every existing table to bak_<stamp>_<table>. Returns the names made. */
function backup_tables(): array
{
    $pdo = db();
    $made = [];
    $stamp = gmdate('Ymd_His');
    $rows = $pdo->query("SELECT TABLE_NAME FROM information_schema.TABLES
                          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
                            AND TABLE_NAME NOT LIKE 'bak\\_%' AND TABLE_NAME <> 'rate_limits'")->fetchAll();
    foreach ($rows as $r) {
        $t = $r['TABLE_NAME'];
        $b = substr('bak_' . $stamp . '_' . $t, 0, 64);
        $pdo->exec("CREATE TABLE IF NOT EXISTS `$b` LIKE `$t`");
        $pdo->exec("INSERT INTO `$b` SELECT * FROM `$t`");
        $made[] = $b;
    }
    return $made;
}

function backup_table_list(): array
{
    try {
        return db()->query("SELECT TABLE_NAME AS name, TABLE_ROWS AS approx_rows, CREATE_TIME AS created
                              FROM information_schema.TABLES
                             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE 'bak\\_%'
                             ORDER BY TABLE_NAME DESC")->fetchAll();
    } catch (PDOException $e) {
        return [];
    }
}

function run_migrations(bool $backup = true, string $trigger = 'admin'): array
{
    $pdo = db();
    $got = (int)$pdo->query("SELECT GET_LOCK('mavelylink_schema', 30)")->fetchColumn();
    if ($got !== 1) {
        throw new RuntimeException('Another upgrade is already running. Try again in a minute.');
    }
    try {
        settings_cache(true);
        $from = schema_version();
        $report = ['from' => $from, 'to' => $from, 'steps' => [], 'backups' => []];
        if ($from >= SCHEMA_VERSION) {
            return $report;
        }
        if ($backup && $from > 0) {
            $report['backups'] = backup_tables();
        }
        $pdo->exec('CREATE TABLE IF NOT EXISTS schema_migrations (
            version INT PRIMARY KEY, label VARCHAR(160) NOT NULL,
            applied_at DATETIME NOT NULL, trigger_src VARCHAR(16) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
        foreach (migration_steps() as $ver => [$label, $fn]) {
            if ($ver <= $from) {
                continue;
            }
            $fn($pdo);
            $pdo->prepare('INSERT INTO schema_migrations (version, label, applied_at, trigger_src)
                           VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE applied_at = VALUES(applied_at)')
                ->execute([$ver, $label, now(), $trigger]);
            set_setting('schema_version', (string)$ver);
            $report['steps'][] = 'v' . $ver . ': ' . $label;
            $report['to'] = $ver;
        }
        if ($report['backups']) {
            set_setting('schema_last_backup', implode(',', $report['backups']));
        }
        table_exists('licenses', true);
        audit('schema.upgraded', 'v' . $from . ' -> v' . $report['to'] . ' (' . $trigger . '), backups: '
            . count($report['backups']));
        return $report;
    } finally {
        $pdo->query("SELECT RELEASE_LOCK('mavelylink_schema')")->fetchColumn();
    }
}

function migration_steps(): array
{
    return [
        2 => ['core tables', static function (PDO $pdo): void {
            $pdo->exec("CREATE TABLE IF NOT EXISTS admins (
              id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(64) NOT NULL UNIQUE,
              password_hash VARCHAR(255) NOT NULL, last_login DATETIME NULL, created_at DATETIME NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("CREATE TABLE IF NOT EXISTS licenses (
              id INT AUTO_INCREMENT PRIMARY KEY, serial VARCHAR(32) NOT NULL UNIQUE,
              email VARCHAR(190) NOT NULL, tier ENUM('free','pro') NOT NULL DEFAULT 'free',
              status ENUM('active','blocked','revoked') NOT NULL DEFAULT 'active',
              expires_at DATETIME NOT NULL, device_hash VARCHAR(64) NULL, device_label VARCHAR(120) NULL,
              device_resets INT NOT NULL DEFAULT 0, app_version VARCHAR(32) NULL, last_seen DATETIME NULL,
              last_ip VARCHAR(45) NULL, profile_count INT NOT NULL DEFAULT 0,
              source VARCHAR(32) NOT NULL DEFAULT 'manual', external_id VARCHAR(190) NULL, notes TEXT NULL,
              created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
              UNIQUE KEY uq_external (external_id), KEY idx_email (email), KEY idx_device (device_hash),
              KEY idx_status (status, expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("CREATE TABLE IF NOT EXISTS scripts (
              id INT AUTO_INCREMENT PRIMARY KEY, slug VARCHAR(64) NOT NULL UNIQUE, name VARCHAR(120) NOT NULL,
              min_tier ENUM('free','pro') NOT NULL DEFAULT 'free', enabled TINYINT(1) NOT NULL DEFAULT 1,
              version INT NOT NULL DEFAULT 1, source MEDIUMTEXT NOT NULL, updated_at DATETIME NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("CREATE TABLE IF NOT EXISTS payments (
              id INT AUTO_INCREMENT PRIMARY KEY, provider VARCHAR(24) NOT NULL, external_id VARCHAR(190) NOT NULL,
              email VARCHAR(190) NULL, amount DECIMAL(12,2) NOT NULL DEFAULT 0,
              currency VARCHAR(12) NOT NULL DEFAULT 'USD', status VARCHAR(32) NOT NULL, license_id INT NULL,
              raw MEDIUMTEXT NULL, created_at DATETIME NOT NULL, UNIQUE KEY uq_provider_ext (provider, external_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("CREATE TABLE IF NOT EXISTS settings (k VARCHAR(64) PRIMARY KEY, v TEXT NOT NULL)
                        ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("CREATE TABLE IF NOT EXISTS rate_limits (k VARCHAR(64) PRIMARY KEY,
                        hits INT NOT NULL DEFAULT 0, window_start DATETIME NOT NULL)
                        ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("CREATE TABLE IF NOT EXISTS audit_log (
              id INT AUTO_INCREMENT PRIMARY KEY, action VARCHAR(64) NOT NULL, detail VARCHAR(500) NULL,
              license_id INT NULL, ip VARCHAR(45) NULL, created_at DATETIME NOT NULL, KEY idx_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("INSERT IGNORE INTO settings (k, v) VALUES
              ('kill_switch','0'),
              ('kill_message','The service is temporarily unavailable. Please try again later.'),
              ('paypal_enabled','1'),('paypal_client_id',''),('paypal_secret',''),('paypal_webhook_id',''),
              ('paypal_live','0'),('crypto_enabled','1'),('crypto_provider','manual'),('crypto_api_key',''),
              ('crypto_ipn_secret',''),('usdt_network','TRC20'),('usdt_address',''),('price_usd','29.00'),
              ('trial_enabled','1'),('latest_version','1.0.0'),('min_version','1.0.0'),('download_url',''),
              ('force_update','0'),('app_enabled','1'),
              ('blocked_message','The application is temporarily disabled by the administrator.')");
            $pdo->exec("INSERT IGNORE INTO scripts (slug, name, min_tier, enabled, version, source, updated_at) VALUES
              ('script1','Script 1','free',1,1,'',UTC_TIMESTAMP()),
              ('script2','Script 2','pro',1,1,'',UTC_TIMESTAMP())");
        }],
        3 => ['licence types, dates and customer fields', static function (PDO $pdo): void {
            $pdo->exec("ALTER TABLE licenses MODIFY tier ENUM('free','pro','team') NOT NULL DEFAULT 'free'");
            mig_add_column($pdo, 'licenses', 'max_devices', 'INT NOT NULL DEFAULT 1');
            mig_add_column($pdo, 'licenses', 'activated_at', 'DATETIME NULL');
            mig_add_column($pdo, 'licenses', 'last_validated_at', 'DATETIME NULL');
            mig_add_column($pdo, 'licenses', 'customer_name', 'VARCHAR(190) NULL');
            mig_add_column($pdo, 'licenses', 'order_id', 'INT NULL');
            mig_add_column($pdo, 'licenses', 'payment_id', 'INT NULL');
            mig_add_column($pdo, 'licenses', 'coupon_code', 'VARCHAR(40) NULL');
            mig_add_column($pdo, 'licenses', 'revoked_at', 'DATETIME NULL');
            mig_add_column($pdo, 'licenses', 'renewed_at', 'DATETIME NULL');
            $pdo->exec("UPDATE licenses SET activated_at = COALESCE(last_seen, updated_at)
                         WHERE activated_at IS NULL AND device_hash IS NOT NULL AND device_hash <> ''");
            $pdo->exec("UPDATE licenses SET revoked_at = updated_at WHERE status = 'revoked' AND revoked_at IS NULL");
            $pdo->exec("UPDATE licenses SET last_validated_at = last_seen WHERE last_validated_at IS NULL");
        }],
        4 => ['activated devices per licence', static function (PDO $pdo): void {
            $pdo->exec("CREATE TABLE IF NOT EXISTS license_devices (
              id INT AUTO_INCREMENT PRIMARY KEY, license_id INT NOT NULL, device_hash VARCHAR(64) NOT NULL,
              device_label VARCHAR(120) NULL, app_version VARCHAR(32) NULL,
              status ENUM('active','released','removed') NOT NULL DEFAULT 'active',
              activated_at DATETIME NOT NULL, last_seen DATETIME NULL, last_ip VARCHAR(45) NULL,
              released_at DATETIME NULL,
              UNIQUE KEY uq_license_device (license_id, device_hash), KEY idx_device (device_hash)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            // every existing single-device binding becomes the licence's first device
            $pdo->exec("INSERT IGNORE INTO license_devices
                (license_id, device_hash, device_label, app_version, status, activated_at, last_seen, last_ip)
                SELECT id, device_hash, device_label, app_version, 'active',
                       COALESCE(activated_at, updated_at), last_seen, last_ip
                  FROM licenses WHERE device_hash IS NOT NULL AND device_hash <> ''");
        }],
        5 => ['installations and client error log', static function (PDO $pdo): void {
            $pdo->exec("CREATE TABLE IF NOT EXISTS installations (
              id INT AUTO_INCREMENT PRIMARY KEY, device_hash VARCHAR(64) NOT NULL UNIQUE,
              plan VARCHAR(16) NOT NULL DEFAULT 'free', license_id INT NULL, app_version VARCHAR(32) NULL,
              profile_count INT NOT NULL DEFAULT 0, first_seen DATETIME NOT NULL, last_seen DATETIME NOT NULL,
              last_ip VARCHAR(45) NULL, last_state VARCHAR(24) NULL, checkins INT NOT NULL DEFAULT 0,
              KEY idx_seen (last_seen)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("CREATE TABLE IF NOT EXISTS client_errors (
              id INT AUTO_INCREMENT PRIMARY KEY, device_hash VARCHAR(64) NULL, license_id INT NULL,
              app_version VARCHAR(32) NULL, kind VARCHAR(48) NOT NULL, message VARCHAR(500) NOT NULL,
              created_at DATETIME NOT NULL, KEY idx_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
        }],
        6 => ['pricing plans, coupons, orders and payment details', static function (PDO $pdo): void {
            $pdo->exec("CREATE TABLE IF NOT EXISTS plans (
              code VARCHAR(16) PRIMARY KEY, name VARCHAR(80) NOT NULL, tagline VARCHAR(160) NULL,
              previous_price DECIMAL(10,2) NULL, current_price DECIMAL(10,2) NOT NULL DEFAULT 0,
              currency CHAR(3) NOT NULL DEFAULT 'USD', period_days INT NOT NULL DEFAULT 30,
              status ENUM('active','hidden') NOT NULL DEFAULT 'active', purchasable TINYINT(1) NOT NULL DEFAULT 1,
              device_limit INT NOT NULL DEFAULT 1, features TEXT NOT NULL, sort_order INT NOT NULL DEFAULT 0,
              updated_at DATETIME NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $ins = $pdo->prepare('INSERT IGNORE INTO plans (code, name, tagline, previous_price, current_price,
                currency, period_days, status, purchasable, device_limit, features, sort_order, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)');
            foreach (plan_seed_rows() as $p) {
                $ins->execute([$p['code'], $p['name'], $p['tagline'], $p['previous_price'], $p['current_price'],
                    $p['currency'], $p['period_days'], $p['status'], $p['purchasable'], $p['device_limit'],
                    $p['features'], $p['sort_order'], now()]);
            }
            $pdo->exec("CREATE TABLE IF NOT EXISTS coupons (
              id INT AUTO_INCREMENT PRIMARY KEY, code VARCHAR(40) NOT NULL UNIQUE, percent TINYINT NOT NULL,
              plans VARCHAR(64) NOT NULL DEFAULT 'pro,team', active TINYINT(1) NOT NULL DEFAULT 1,
              expires_at DATETIME NULL, max_uses INT NULL, max_uses_per_customer INT NULL,
              used_count INT NOT NULL DEFAULT 0, notes VARCHAR(500) NULL, created_by VARCHAR(64) NULL,
              created_at DATETIME NOT NULL, revoked_at DATETIME NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("CREATE TABLE IF NOT EXISTS coupon_redemptions (
              id INT AUTO_INCREMENT PRIMARY KEY, coupon_id INT NOT NULL, order_id INT NULL,
              email VARCHAR(190) NULL, created_at DATETIME NOT NULL,
              UNIQUE KEY uq_order (order_id), KEY idx_coupon_email (coupon_id, email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $pdo->exec("CREATE TABLE IF NOT EXISTS orders (
              id INT AUTO_INCREMENT PRIMARY KEY, ref VARCHAR(24) NOT NULL UNIQUE, access_token CHAR(32) NOT NULL,
              plan_code VARCHAR(16) NOT NULL, email VARCHAR(190) NOT NULL, customer_name VARCHAR(190) NULL,
              currency CHAR(3) NOT NULL DEFAULT 'USD', original_amount DECIMAL(10,2) NOT NULL,
              discount_amount DECIMAL(10,2) NOT NULL DEFAULT 0, final_amount DECIMAL(10,2) NOT NULL,
              coupon_id INT NULL, coupon_code VARCHAR(40) NULL, coupon_percent TINYINT NULL,
              period_days INT NOT NULL, device_limit INT NOT NULL, provider VARCHAR(24) NOT NULL,
              provider_order_id VARCHAR(190) NULL, status VARCHAR(32) NOT NULL DEFAULT 'pending',
              license_id INT NULL, payment_id INT NULL, failure_reason VARCHAR(255) NULL,
              created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, paid_at DATETIME NULL,
              KEY idx_status (status, created_at), KEY idx_provider_order (provider_order_id), KEY idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            foreach ([
                ['order_id', 'INT NULL'], ['plan_code', 'VARCHAR(16) NULL'],
                ['original_amount', 'DECIMAL(12,2) NULL'], ['discount_amount', 'DECIMAL(12,2) NULL'],
                ['coupon_code', 'VARCHAR(40) NULL'], ['customer_name', 'VARCHAR(190) NULL'],
                ['method', 'VARCHAR(32) NULL'], ['notes', 'TEXT NULL'], ['reviewed_by', 'VARCHAR(64) NULL'],
                ['reviewed_at', 'DATETIME NULL'], ['updated_at', 'DATETIME NULL'],
            ] as [$c, $d]) {
                mig_add_column($pdo, 'payments', $c, $d);
            }
            // every licence the old system issued from a payment was a Pro licence
            $pdo->exec("UPDATE payments SET plan_code = 'pro' WHERE plan_code IS NULL AND license_id IS NOT NULL");
        }],
        7 => ['contact channels, releases, script checksums, audit actor, one master switch', static function (PDO $pdo): void {
            $pdo->exec("CREATE TABLE IF NOT EXISTS channels (
              code VARCHAR(16) PRIMARY KEY, display_name VARCHAR(80) NOT NULL,
              url VARCHAR(500) NOT NULL DEFAULT '', handle VARCHAR(120) NOT NULL DEFAULT '',
              icon VARCHAR(16) NOT NULL DEFAULT '', instructions TEXT NULL,
              enabled TINYINT(1) NOT NULL DEFAULT 0, manual_payments TINYINT(1) NOT NULL DEFAULT 1,
              sort_order INT NOT NULL DEFAULT 0, updated_at DATETIME NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $ch = $pdo->prepare('INSERT IGNORE INTO channels (code, display_name, icon, instructions, enabled,
                                  manual_payments, sort_order, updated_at) VALUES (?,?,?,?,0,1,?,?)');
            $ch->execute(['whatsapp', 'WhatsApp', 'whatsapp',
                'Message us your order reference. We reply with payment details and confirm your licence once the payment is verified.', 1, now()]);
            $ch->execute(['telegram', 'Telegram', 'telegram',
                'Send your order reference to our Telegram account for payment details.', 2, now()]);
            $ch->execute(['facebook', 'Facebook Messenger', 'facebook',
                'Message our Facebook page with your order reference for help or payment details.', 3, now()]);

            $pdo->exec("CREATE TABLE IF NOT EXISTS app_releases (
              id INT AUTO_INCREMENT PRIMARY KEY, version VARCHAR(24) NOT NULL, min_version VARCHAR(24) NULL,
              update_type ENUM('optional','mandatory') NOT NULL DEFAULT 'optional', notes TEXT NULL,
              file_url VARCHAR(500) NULL, file_name VARCHAR(190) NULL, file_sha256 CHAR(64) NULL,
              file_size BIGINT NULL, is_current TINYINT(1) NOT NULL DEFAULT 0, published_by VARCHAR(64) NULL,
              published_at DATETIME NOT NULL, KEY idx_current (is_current)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
            $has = (int)$pdo->query('SELECT COUNT(*) FROM app_releases')->fetchColumn();
            $latest = (string)setting('latest_version', '');
            if ($has === 0 && $latest !== '') {
                $pdo->prepare("INSERT INTO app_releases (version, min_version, update_type, notes, file_url,
                    is_current, published_by, published_at) VALUES (?,?,?,?,?,1,'migration',?)")
                    ->execute([$latest, (string)setting('min_version', ''), 'optional',
                        'Imported from the previous dashboard settings.', (string)setting('download_url', ''), now()]);
            }
            mig_add_column($pdo, 'scripts', 'checksum', 'CHAR(64) NULL');
            mig_add_column($pdo, 'scripts', 'published_at', 'DATETIME NULL');
            mig_add_column($pdo, 'scripts', 'published_by', 'VARCHAR(64) NULL');
            $pdo->exec('UPDATE scripts SET checksum = SHA2(source, 256), published_at = updated_at WHERE checksum IS NULL');
            mig_add_column($pdo, 'audit_log', 'actor', 'VARCHAR(64) NULL');

            $pdo->exec("INSERT IGNORE INTO settings (k, v) VALUES
              ('checkin_seconds','180'), ('update_type','optional'), ('release_notes',''),
              ('download_sha256',''), ('download_size','0'), ('app_status_changed_at', UTC_TIMESTAMP()),
              ('app_status_changed_by','')");
            // the old default wording becomes the clearer one; a custom message is kept
            $pdo->exec("UPDATE settings SET v = 'The application is temporarily disabled by the administrator.'
                         WHERE k = 'blocked_message'
                           AND v = 'This application has been disabled by the administrator. Please contact support.'");
            // one master switch: if the old kill switch was on, the app is OFF everywhere
            if (setting('kill_switch') === '1') {
                set_setting('app_enabled', '0');
            }
            settings_cache(true);
        }],
        8 => ['widen orders.status for awaiting_verification', static function (PDO $pdo): void {
            // 'awaiting_verification' is 21 chars; the v6/v7 column was VARCHAR(20)
            // and truncated it, so a manual-payment claim failed. Widen it. Safe
            // and idempotent: MODIFY to the same width on a fresh v8 table is a no-op.
            if (column_exists('orders', 'status')) {
                $pdo->exec("ALTER TABLE orders MODIFY status VARCHAR(32) NOT NULL DEFAULT 'pending'");
            }
            if (column_exists('orders', 'failure_reason')) {
                $pdo->exec("ALTER TABLE orders MODIFY failure_reason VARCHAR(255) NULL");
            }
            settings_cache(true);
        }],
        9 => ['admin account management + signing keys in settings', static function (PDO $pdo): void {
            // v6.2.1. Purely additive: two new nullable/defaulted columns on
            // admins, and three settings rows. No column is dropped, renamed
            // or retyped, and no existing row is modified.
            //
            // session_epoch backs "sign my other browsers out" when the
            // password or username changes. Existing sessions carry epoch 0
            // and the column defaults to 0, so installing this version does
            // not sign anybody out.
            mig_add_column($pdo, 'admins', 'session_epoch', 'INT NOT NULL DEFAULT 0');
            mig_add_column($pdo, 'admins', 'password_changed_at', 'DATETIME NULL');

            // The licence signing keypair can now live here instead of in
            // includes/config.php. Empty values mean "not configured yet";
            // the resolver in license.php then falls back to the constants,
            // so an install that already pasted them keeps working untouched.
            $pdo->exec("INSERT IGNORE INTO settings (k, v) VALUES
              ('license_secret_key',''), ('license_public_key',''), ('license_key_created_at','')");
            settings_cache(true);
        }],
        10 => ['referral programme: customers, devices and referrals', static function (PDO $pdo): void {
            // v6.3. Purely additive: three NEW tables, two NEW nullable
            // columns on orders, and settings rows. No existing table is
            // dropped, renamed, retyped or emptied, and no existing row is
            // modified except orders rows that gain NULLs by default.
            //
            // customers is the durable buyer identity this project did not
            // have. It is keyed on the SAME normalised email that
            // licenses.email and orders.email already carry, so it lines up
            // with everything already stored instead of replacing it.
            $pdo->exec("CREATE TABLE IF NOT EXISTS customers (
              id INT AUTO_INCREMENT PRIMARY KEY,
              email VARCHAR(190) NOT NULL UNIQUE,
              referral_code VARCHAR(16) NOT NULL UNIQUE,
              referred_by VARCHAR(16) NULL,
              referred_by_customer_id INT NULL,
              referral_count_confirmed INT NOT NULL DEFAULT 0,
              reward_status ENUM('none','eligible','pro_granted','cash_paid') NOT NULL DEFAULT 'none',
              reward_granted_at DATETIME NULL,
              reward_license_id INT NULL,
              reward_popup_seen_at DATETIME NULL,
              last_referral_popup_seen_at DATETIME NULL,
              flagged TINYINT(1) NOT NULL DEFAULT 0,
              flag_reason VARCHAR(255) NULL,
              payout_note VARCHAR(255) NULL,
              source VARCHAR(32) NOT NULL DEFAULT 'site',
              created_at DATETIME NOT NULL,
              updated_at DATETIME NOT NULL,
              KEY idx_code (referral_code), KEY idx_referred_by (referred_by),
              KEY idx_reward (reward_status), KEY idx_flagged (flagged)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");

            // which installations belong to a customer, so a FREE user with
            // no licence and no serial can still be recognised, and so
            // self-referral can be spotted across two email addresses
            $pdo->exec("CREATE TABLE IF NOT EXISTS customer_devices (
              id INT AUTO_INCREMENT PRIMARY KEY,
              customer_id INT NOT NULL,
              device_hash VARCHAR(64) NOT NULL,
              first_seen DATETIME NOT NULL,
              last_seen DATETIME NOT NULL,
              last_ip VARCHAR(45) NULL,
              UNIQUE KEY uq_cust_device (customer_id, device_hash),
              KEY idx_device (device_hash)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");

            // one row per referral EVENT.
            // uq_referrer_buyer is what makes 'one buyer counts once, even
            // across repeat purchases' true in the database rather than only
            // in application code.
            $pdo->exec("CREATE TABLE IF NOT EXISTS referrals (
              id INT AUTO_INCREMENT PRIMARY KEY,
              referrer_customer_id INT NOT NULL,
              referred_customer_id INT NULL,
              referred_email VARCHAR(190) NOT NULL,
              referral_code VARCHAR(16) NOT NULL,
              order_id INT NULL,
              license_id INT NULL,
              license_serial VARCHAR(32) NULL,
              amount DECIMAL(10,2) NULL,
              currency CHAR(3) NULL,
              status ENUM('pending','confirmed','reverted','rejected') NOT NULL DEFAULT 'pending',
              flagged TINYINT(1) NOT NULL DEFAULT 0,
              flag_reason VARCHAR(255) NULL,
              notes VARCHAR(500) NULL,
              ip VARCHAR(45) NULL,
              seen_by_referrer TINYINT(1) NOT NULL DEFAULT 0,
              created_at DATETIME NOT NULL,
              confirmed_at DATETIME NULL,
              reverted_at DATETIME NULL,
              UNIQUE KEY uq_referrer_buyer (referrer_customer_id, referred_email),
              UNIQUE KEY uq_order (order_id),
              KEY idx_status (status, created_at),
              KEY idx_referrer (referrer_customer_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");

            // the attribution carried on the order itself
            mig_add_column($pdo, 'orders', 'referred_by', 'VARCHAR(16) NULL');
            mig_add_column($pdo, 'orders', 'referrer_customer_id', 'INT NULL');

            $pdo->exec("INSERT IGNORE INTO settings (k, v) VALUES
              ('referral_enabled','1'), ('referral_threshold','5'),
              ('referral_cookie_days','30'), ('referral_reward_plan','pro'),
              ('referral_cash_amount','15')");

            // ---- backfill -------------------------------------------------
            // Give every email this site already knows a customer row and a
            // code, so existing buyers can start inviting immediately instead
            // of waiting to be discovered. Codes are generated here rather
            // than by includes/referral.php on purpose: migrate.php must not
            // depend on a file that loads bootstrap.php, which would re-enter
            // the migrator.
            $alphabet = '23456789ABCDEFGHJKLMNPQRSTVWXYZ';
            $reserved = ['APP', 'WEB', 'REF', 'NONE', 'NULL', 'TEST', 'ADMIN', 'EMAIL', 'SITE'];
            $taken = [];
            foreach ($pdo->query('SELECT referral_code FROM customers') as $r) {
                $taken[$r['referral_code']] = true;
            }
            $newCode = static function () use ($alphabet, $reserved, &$taken): string {
                for ($i = 0; $i < 40; $i++) {
                    $c = '';
                    for ($j = 0; $j < 8; $j++) {
                        $c .= $alphabet[random_int(0, strlen($alphabet) - 1)];
                    }
                    if (!isset($taken[$c]) && !in_array($c, $reserved, true)) {
                        $taken[$c] = true;
                        return $c;
                    }
                }
                throw new RuntimeException('could not allocate a referral code');
            };
            $emails = $pdo->query("SELECT DISTINCT LOWER(TRIM(email)) AS email FROM licenses
                                    WHERE email IS NOT NULL AND TRIM(email) <> ''
                                   UNION
                                   SELECT DISTINCT LOWER(TRIM(email)) FROM orders
                                    WHERE email IS NOT NULL AND TRIM(email) <> ''")->fetchAll();
            $ins = $pdo->prepare("INSERT IGNORE INTO customers
                (email, referral_code, source, created_at, updated_at) VALUES (?,?,'backfill',?,?)");
            foreach ($emails as $row) {
                $email = (string)$row['email'];
                if ($email === '' || mb_strlen($email) > 190) {
                    continue;
                }
                $ins->execute([$email, $newCode(), now(), now()]);
            }
            settings_cache(true);
        }],
        11 => ['referral clicks, per-plan scripts, activation limits, channel placement',
               static function (PDO $pdo): void {
            // v6.3.1. Additive: one new table, new nullable columns on three
            // existing tables, and settings rows. Nothing is dropped, renamed
            // or retyped, and no existing row's meaning changes.

            // --- TASK 1: click log -------------------------------------
            // Clicks NEVER count toward the reward. This is for visibility
            // only, deduplicated per code+visitor so the page stays readable.
            $pdo->exec("CREATE TABLE IF NOT EXISTS referral_clicks (
              id INT AUTO_INCREMENT PRIMARY KEY,
              referral_code VARCHAR(16) NOT NULL,
              referrer_customer_id INT NULL,
              ip_hash VARCHAR(32) NOT NULL,
              user_agent VARCHAR(255) NULL,
              referer VARCHAR(255) NULL,
              created_at DATETIME NOT NULL,
              KEY idx_code_time (referral_code, created_at),
              KEY idx_dedupe (referral_code, ip_hash, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");

            // --- TASK 4: per-plan script entitlement --------------------
            // scripts.min_tier is a MINIMUM-TIER threshold: it can say
            // "everyone" or "paid only", and cannot say "Free only". It is
            // left in place untouched as the fallback for any row that has
            // no explicit list. NULL here means "use min_tier as before".
            mig_add_column($pdo, 'scripts', 'plans', "VARCHAR(40) NULL");
            // Script 1 -> Free only. Script 2 -> Pro and Team. Source code,
            // version, checksum and slug are not touched.
            $pdo->prepare("UPDATE scripts SET plans = 'free' WHERE slug = 'script1' AND plans IS NULL")
                ->execute();
            $pdo->prepare("UPDATE scripts SET plans = 'pro,team' WHERE slug = 'script2' AND plans IS NULL")
                ->execute();

            // --- TASK 2: activation attempt limit -----------------------
            // Keyed to the installation (device_hash), which activate.php
            // already receives. IP is recorded for the admin to look at, and
            // is deliberately NOT part of the key, so one office behind one
            // NAT cannot lock each other out.
            mig_add_column($pdo, 'installations', 'activation_fails', 'INT NOT NULL DEFAULT 0');
            mig_add_column($pdo, 'installations', 'activation_locked_until', 'DATETIME NULL');
            mig_add_column($pdo, 'installations', 'activation_last_fail_at', 'DATETIME NULL');
            mig_add_column($pdo, 'installations', 'activation_last_fail_ip', 'VARCHAR(45) NULL');

            // --- TASK 3: where a channel appears ------------------------
            // Defaults to 'none' on purpose: existing rows are manual PAYMENT
            // channels, and they must not silently become social buttons on
            // the website and in the tool. The admin opts each one in.
            mig_add_column($pdo, 'channels', 'show_on',
                "ENUM('none','website','tool','both') NOT NULL DEFAULT 'none'");
            mig_add_column($pdo, 'channels', 'tooltip', 'VARCHAR(160) NULL');
            // rows to fill in, disabled and hidden until the admin sets a URL
            $ch = $pdo->prepare("INSERT IGNORE INTO channels
                (code, display_name, url, handle, icon, instructions, enabled,
                 manual_payments, sort_order, show_on, updated_at)
                VALUES (?,?,'','',?,NULL,0,0,?,'none',?)");
            foreach ([['facebook', 'Facebook', 'facebook', 2],
                      ['telegram', 'Telegram', 'telegram', 3],
                      ['youtube',  'YouTube',  'youtube',  4]] as [$c, $n, $i, $o]) {
                $ch->execute([$c, $n, $i, $o, now()]);
            }

            $pdo->exec("INSERT IGNORE INTO settings (k, v) VALUES
              ('site_public_url',''),
              ('referral_click_dedupe_seconds','900'),
              ('activation_max_attempts','3'),
              ('activation_lockout_hours','24'),
              ('theme_default','system'),
              ('theme_toggle_visible','1'),
              ('activation_generic_errors','1'),
              ('silent_registration','1')");
            settings_cache(true);
        }],
        12 => ['server-controlled Python tabs for the desktop tool',
               static function (PDO $pdo): void {
            // v7.0.0. Additive: ONE new table and three settings rows.
            // Nothing existing is dropped, renamed, retyped or rewritten -
            // in particular the `scripts` table (the userscripts injected
            // into browser profiles) is a different thing entirely and is
            // not touched here.
            //
            // `sort_order` rather than `order`: ORDER is a reserved word in
            // MySQL, and sort_order is already the name this schema uses on
            // `plans` and `channels`.
            $pdo->exec("CREATE TABLE IF NOT EXISTS tool_tabs (
              id               INT AUTO_INCREMENT PRIMARY KEY,
              slug             VARCHAR(64)  NOT NULL UNIQUE,
              title            VARCHAR(80)  NOT NULL,
              sort_order       INT          NOT NULL DEFAULT 0,
              enabled          TINYINT(1)   NOT NULL DEFAULT 1,
              required_plan    ENUM('free','pro','team') NOT NULL DEFAULT 'free',
              script           MEDIUMTEXT   NOT NULL,
              checksum         CHAR(64)     NOT NULL DEFAULT '',
              version          INT          NOT NULL DEFAULT 1,
              min_tool_version VARCHAR(32)  NULL,
              ui_width         INT          NOT NULL DEFAULT 960,
              ui_height        INT          NOT NULL DEFAULT 340,
              notes            TEXT         NULL,
              published_by     VARCHAR(64)  NULL,
              published_at     DATETIME     NULL,
              created_at       DATETIME     NOT NULL,
              updated_at       DATETIME     NOT NULL,
              KEY idx_live (enabled, sort_order)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");

            // tool_tabs_enabled is the revocation lever includes/features.php
            // named as a prerequisite for ever shipping executable code:
            // set it to 0 and every installation stops loading remote tabs
            // at its next launch, with no release and no database edit.
            $pdo->exec("INSERT IGNORE INTO settings (k, v) VALUES
              ('tool_tabs_enabled','1'),
              ('tool_tabs_changed_at',''),
              ('tool_tabs_changed_by','')");
            settings_cache(true);
        }],
    ];
}
