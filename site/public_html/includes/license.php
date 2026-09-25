<?php
declare(strict_types=1);
require_once __DIR__ . '/bootstrap.php';

/**
 * Serial format: MVL-XXXXX-XXXXX-XXXXX-XXXXX
 * Crockford-style alphabet with I, O, U and 0/1 removed so serials read
 * cleanly over the phone and cannot be mistyped into a different valid one.
 */
const SERIAL_ALPHABET = '23456789ABCDEFGHJKLMNPQRSTVWXYZ';

function generate_serial(): string
{
    $groups = [];
    for ($g = 0; $g < 4; $g++) {
        $s = '';
        for ($i = 0; $i < 5; $i++) {
            $s .= SERIAL_ALPHABET[random_int(0, strlen(SERIAL_ALPHABET) - 1)];
        }
        $groups[] = $s;
    }
    return 'MVL-' . implode('-', $groups);
}

function normalise_serial(string $serial): string
{
    $s = strtoupper(trim($serial));
    $s = preg_replace('/[^A-Z0-9-]/', '', $s) ?? '';
    return $s;
}

function unique_serial(): string
{
    $pdo = db();
    for ($attempt = 0; $attempt < 12; $attempt++) {
        $serial = generate_serial();
        $st = $pdo->prepare('SELECT 1 FROM licenses WHERE serial = ?');
        $st->execute([$serial]);
        if (!$st->fetch()) {
            return $serial;
        }
    }
    throw new RuntimeException('could not allocate a serial');
}

function license_by_id(int $id): ?array
{
    $st = db()->prepare('SELECT * FROM licenses WHERE id = ?');
    $st->execute([$id]);
    return $st->fetch() ?: null;
}

/**
 * Create or extend a paid licence. Idempotent on the order and on the
 * external payment id: a webhook retry never extends anything twice.
 *
 * v7: $plan picks the licence type ('pro' or 'team'). A Team licence is its
 * own licence type with its own device limit, never three Pro licences.
 * $opts: order_id, payment_id, coupon_code, customer_name, period_days, device_limit.
 */
function issue_license(string $email, string $source, ?string $externalId = null,
                       string $plan = 'pro', array $opts = []): array
{
    $pdo = db();
    $plan = in_array($plan, PAID_PLANS, true) ? $plan : 'pro';
    $planRow = plan_get($plan);
    $days = (int)($opts['period_days'] ?? ($planRow['period_days'] ?? SUBSCRIPTION_DAYS));
    if ($days < 1) {
        $days = SUBSCRIPTION_DAYS;
    }
    $devices = max(1, (int)($opts['device_limit'] ?? ($planRow['device_limit'] ?? ($plan === 'team' ? 3 : 1))));
    $orderId = isset($opts['order_id']) ? (int)$opts['order_id'] : null;
    $paymentId = isset($opts['payment_id']) ? (int)$opts['payment_id'] : null;
    $coupon = isset($opts['coupon_code']) && $opts['coupon_code'] !== '' ? (string)$opts['coupon_code'] : null;
    $customer = isset($opts['customer_name']) && $opts['customer_name'] !== '' ? (string)$opts['customer_name'] : null;

    if ($orderId) {
        $st = $pdo->prepare('SELECT l.* FROM orders o JOIN licenses l ON l.id = o.license_id WHERE o.id = ?');
        $st->execute([$orderId]);
        if ($row = $st->fetch()) {
            return $row;    // this order was already fulfilled
        }
    }
    if ($externalId !== null) {
        $st = $pdo->prepare('SELECT * FROM licenses WHERE external_id = ?');
        $st->execute([$externalId]);
        if ($existing = $st->fetch()) {
            return $existing;   // webhook retry, already handled
        }
    }

    // an ACTIVE licence of the same type for this email is extended rather than duplicated
    $st = $pdo->prepare("SELECT * FROM licenses WHERE email = ? AND tier = ? AND status = 'active'
                          ORDER BY id DESC LIMIT 1");
    $st->execute([$email, $plan]);
    $row = $st->fetch();

    if ($row) {
        $base = max(time(), strtotime($row['expires_at'] . ' UTC'));
        $newExpiry = gmdate('Y-m-d H:i:s', $base + $days * 86400);
        $pdo->prepare(
            "UPDATE licenses SET expires_at = ?, status = 'active', external_id = COALESCE(?, external_id),
                    updated_at = ?, renewed_at = ?, max_devices = GREATEST(max_devices, ?),
                    order_id = COALESCE(?, order_id), payment_id = COALESCE(?, payment_id),
                    coupon_code = COALESCE(?, coupon_code), customer_name = COALESCE(?, customer_name)
              WHERE id = ?"
        )->execute([$newExpiry, $externalId, now(), now(), $devices, $orderId, $paymentId, $coupon, $customer, $row['id']]);
        audit('license.renewed', $source . ' ' . $plan . ' -> ' . $newExpiry, (int)$row['id']);
        return license_by_id((int)$row['id']);
    }

    $serial = unique_serial();
    $pdo->prepare(
        "INSERT INTO licenses (serial, email, tier, status, expires_at, source, external_id, created_at, updated_at,
                               max_devices, order_id, payment_id, coupon_code, customer_name)
         VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )->execute([$serial, $email, $plan, days_from_now($days), $source, $externalId, now(), now(),
                $devices, $orderId, $paymentId, $coupon, $customer]);

    $id = (int)$pdo->lastInsertId();
    audit('license.issued', $source . ' ' . $plan . ' ' . $email, $id);
    return license_by_id($id);
}

/** A 7-day trial, one per device and one per email. (Kept for older app builds.) */
function issue_trial(string $email, string $deviceHash): array
{
    $pdo = db();

    $st = $pdo->prepare('SELECT * FROM licenses WHERE email = ? OR device_hash = ? LIMIT 1');
    $st->execute([$email, $deviceHash]);
    if ($row = $st->fetch()) {
        return ['reused' => true, 'license' => $row];
    }

    $serial = unique_serial();
    $pdo->prepare(
        "INSERT INTO licenses (serial, email, tier, status, expires_at, device_hash, source, created_at, updated_at)
         VALUES (?, ?, 'free', 'active', ?, ?, 'trial', ?, ?)"
    )->execute([$serial, $email, days_from_now(TRIAL_DAYS), $deviceHash, now(), now()]);

    $id = (int)$pdo->lastInsertId();
    audit('license.trial', $email, $id);
    return ['reused' => false, 'license' => license_by_id($id)];
}

function license_expired(array $lic): bool
{
    return strtotime($lic['expires_at'] . ' UTC') <= time();
}

// ---------------------------------------------------------------------
// remote application control: update + master switch
// ---------------------------------------------------------------------

/** The published release the dashboard marked as current, or null. */
function current_release(): ?array
{
    try {
        $r = db()->query('SELECT * FROM app_releases WHERE is_current = 1 ORDER BY id DESC LIMIT 1')->fetch();
        return $r ?: null;
    } catch (PDOException $e) {
        return null;
    }
}

/**
 * True when a client on $clientVersion must update before it may run:
 *  - it is below the minimum supported version (enforced whenever the
 *    dashboard's "require minimum" flag, force_update, is on), or
 *  - the current release is mandatory and the client is older than it.
 */
function update_required(string $clientVersion): bool
{
    $clientVersion = trim($clientVersion);
    if ($clientVersion === '') {
        return false;
    }
    $min = (string)setting('min_version', '');
    if (setting_bool('force_update') && $min !== '' && version_cmp($clientVersion, $min) < 0) {
        return true;
    }
    $latest = (string)setting('latest_version', '');
    return setting('update_type', 'optional') === 'mandatory' && $latest !== ''
        && version_cmp($clientVersion, $latest) < 0;
}

function update_available(string $clientVersion): bool
{
    $latest = (string)setting('latest_version', '');
    return trim($clientVersion) !== '' && $latest !== '' && version_cmp($clientVersion, $latest) < 0;
}

/** True when the application is allowed to run at all (master switch). */
function application_enabled(): bool
{
    // Either stored flag can disable the app. The dashboard writes both
    // together (see set_application_enabled) so every screen agrees.
    if (setting_bool('kill_switch')) {
        return false;
    }
    return setting_bool('app_enabled', true);
}

function app_disabled_message(): string
{
    $m = trim((string)setting('blocked_message', ''));
    return $m !== '' ? $m : 'The application is temporarily disabled by the administrator.';
}

/** The ONE way to flip the master switch. Saved immediately and logged. */
function set_application_enabled(bool $on): void
{
    set_setting('app_enabled', $on ? '1' : '0');
    set_setting('kill_switch', $on ? '0' : '1');
    set_setting('app_status_changed_at', now());
    set_setting('app_status_changed_by', (string)($_SESSION['admin_user'] ?? 'system'));
    audit('app.master_switch', $on ? 'ON (application enabled)' : 'OFF (application disabled)');
}

/** Update details for one client version. */
function update_info(string $clientVersion): array
{
    $rel = current_release();
    return [
        'available'     => update_available($clientVersion),
        'mandatory'     => update_required($clientVersion),
        'type'          => (string)setting('update_type', 'optional'),
        'latest_version'=> (string)setting('latest_version', ''),
        'min_version'   => (string)setting('min_version', ''),
        'url'           => (string)setting('download_url', ''),
        'sha256'        => strtolower((string)setting('download_sha256', '')),
        'size'          => (int)setting('download_size', '0'),
        'notes'         => (string)($rel['notes'] ?? setting('release_notes', '')),
        'published_at'  => (string)($rel['published_at'] ?? ''),
    ];
}

/**
 * The update + block block attached to every heartbeat response, so the
 * desktop learns the current update policy and block state on each check-in.
 */
function update_block_fields(string $clientVersion): array
{
    $u = update_info($clientVersion);
    return [
        'application_enabled' => application_enabled(),
        'latest_version'      => $u['latest_version'],
        'min_version'         => $u['min_version'],
        'download_url'        => $u['url'],
        'update_required'     => $u['mandatory'],
        'update_available'    => $u['available'],
        'update_type'         => $u['type'],
        'download_sha256'     => $u['sha256'],
        'release_notes'       => $u['notes'],
        'blocked_message'     => app_disabled_message(),
    ];
}

/**
 * Effective state right now. An expired paid licence is not "pro"; v7
 * clients then fall back to the Free plan without losing anything.
 */
function effective_state(array $lic): array
{
    if ($lic['status'] === 'blocked') {
        return ['state' => 'blocked', 'tier' => 'none', 'plan' => 'free',
                'message' => 'This licence has been deactivated. The app continues on the Free plan. Contact support for help.'];
    }
    if ($lic['status'] === 'revoked') {
        return ['state' => 'revoked', 'tier' => 'none', 'plan' => 'free',
                'message' => 'This licence was revoked. The app continues on the Free plan.'];
    }
    if (license_expired($lic)) {
        return ['state' => 'expired', 'tier' => 'none', 'plan' => 'free',
                'message' => $lic['source'] === 'trial'
                    ? 'Your 7-day trial has ended. You are on the Free plan now; upgrade any time for Pro features.'
                    : 'Your ' . plan_name((string)$lic['tier']) . ' access ended on '
                      . substr((string)$lic['expires_at'], 0, 10)
                      . '. The app continues on the Free plan. Renew to unlock paid features again.'];
    }
    return ['state' => 'active', 'tier' => $lic['tier'], 'plan' => $lic['tier'], 'message' => ''];
}

/** Older app builds only know 'free' and 'pro'; Team includes every Pro feature. */
function legacy_tier(string $tier): string
{
    return $tier === 'team' ? 'pro' : $tier;
}

// ---------------------------------------------------------------------
// devices: Pro = 1, Team = 3 (per licence, from max_devices)
// ---------------------------------------------------------------------
function license_device_row(int $licenseId, string $device): ?array
{
    $st = db()->prepare('SELECT * FROM license_devices WHERE license_id = ? AND device_hash = ?');
    $st->execute([$licenseId, $device]);
    return $st->fetch() ?: null;
}

function license_devices(int $licenseId, bool $activeOnly = true): array
{
    $sql = 'SELECT * FROM license_devices WHERE license_id = ?' . ($activeOnly ? " AND status = 'active'" : '')
         . ' ORDER BY activated_at';
    $st = db()->prepare($sql);
    $st->execute([$licenseId]);
    return $st->fetchAll();
}

function license_device_count(int $licenseId): int
{
    $st = db()->prepare("SELECT COUNT(*) FROM license_devices WHERE license_id = ? AND status = 'active'");
    $st->execute([$licenseId]);
    return (int)$st->fetchColumn();
}

function license_device_active(int $licenseId, string $device): bool
{
    $row = license_device_row($licenseId, $device);
    return $row !== null && $row['status'] === 'active';
}

/** Keep licenses.device_hash (read by older screens) pointing at an active device. */
function license_sync_legacy_device(int $licenseId): void
{
    $st = db()->prepare("SELECT device_hash, device_label FROM license_devices
                          WHERE license_id = ? AND status = 'active' ORDER BY activated_at LIMIT 1");
    $st->execute([$licenseId]);
    $d = $st->fetch();
    db()->prepare('UPDATE licenses SET device_hash = ?, device_label = ?, updated_at = ? WHERE id = ?')
        ->execute([$d['device_hash'] ?? null, $d['device_label'] ?? null, now(), $licenseId]);
}

/**
 * Bind $device to the licence, enforcing max_devices on the server.
 * $legacy is the identity an older build of the app used on the same
 * computer; a binding under that identity is moved over instead of using
 * a second slot.
 */
function license_bind_device(array $lic, string $device, string $label, string $version, string $legacy = ''): array
{
    $pdo = db();
    $id = (int)$lic['id'];
    $max = max(1, (int)($lic['max_devices'] ?? 1));

    if (!empty($lic['device_hash']) && !license_device_row($id, (string)$lic['device_hash'])) {
        $pdo->prepare("INSERT IGNORE INTO license_devices (license_id, device_hash, device_label, app_version,
                       status, activated_at, last_seen) VALUES (?,?,?,?, 'active', ?, ?)")
            ->execute([$id, $lic['device_hash'], $lic['device_label'], $lic['app_version'],
                       $lic['activated_at'] ?? $lic['updated_at'], $lic['last_seen']]);
    }

    $row = license_device_row($id, $device);
    if ($row && $row['status'] === 'active') {
        $pdo->prepare('UPDATE license_devices SET device_label = ?, app_version = ?, last_seen = ?, last_ip = ? WHERE id = ?')
            ->execute([$label, $version, now(), client_ip(), $row['id']]);
        return ['ok' => true, 'new' => false];
    }

    if ($legacy !== '' && $legacy !== $device) {
        $old = license_device_row($id, $legacy);
        if ($old && $old['status'] === 'active') {
            if ($row) {
                $pdo->prepare('DELETE FROM license_devices WHERE id = ?')->execute([$row['id']]);
            }
            $pdo->prepare('UPDATE license_devices SET device_hash = ?, device_label = ?, app_version = ?,
                           last_seen = ?, last_ip = ? WHERE id = ?')
                ->execute([$device, $label, $version, now(), client_ip(), $old['id']]);
            license_sync_legacy_device($id);
            audit('device.identity_upgraded', $label, $id);
            return ['ok' => true, 'new' => false];
        }
    }

    $used = license_device_count($id);
    if ($used >= $max) {
        return [
            'ok' => false, 'state' => 'device_limit', 'used' => $used, 'max' => $max,
            'error' => $max === 1
                ? 'This serial is already active on another computer. Use "Release this computer" on the other machine, or contact support.'
                : 'This licence is already active on ' . $used . ' of ' . $max . ' computers. Release one of them first (Plan & licence > Release this computer), or contact support.',
        ];
    }

    if ($row) {
        $pdo->prepare("UPDATE license_devices SET status = 'active', device_label = ?, app_version = ?,
                       activated_at = ?, last_seen = ?, last_ip = ?, released_at = NULL WHERE id = ?")
            ->execute([$label, $version, now(), now(), client_ip(), $row['id']]);
    } else {
        $pdo->prepare("INSERT INTO license_devices (license_id, device_hash, device_label, app_version, status,
                       activated_at, last_seen, last_ip) VALUES (?,?,?,?, 'active', ?, ?, ?)")
            ->execute([$id, $device, $label, $version, now(), now(), client_ip()]);
    }
    if (empty($lic['activated_at'])) {
        $pdo->prepare('UPDATE licenses SET activated_at = ? WHERE id = ?')->execute([now(), $id]);
    }
    license_sync_legacy_device($id);
    audit('activate.bound', $label . ' (' . ($used + 1) . '/' . $max . ')', $id);
    return ['ok' => true, 'new' => true];
}

function license_release_device(int $licenseId, string $device, string $status = 'released'): bool
{
    $status = $status === 'removed' ? 'removed' : 'released';
    $st = db()->prepare("UPDATE license_devices SET status = ?, released_at = ?
                          WHERE license_id = ? AND device_hash = ? AND status = 'active'");
    $st->execute([$status, now(), $licenseId, $device]);
    $changed = $st->rowCount() > 0;
    license_sync_legacy_device($licenseId);
    return $changed;
}

/** What a customer or the desktop may see about a licence. */
function license_public(array $lic): array
{
    $state = effective_state($lic);
    return [
        'serial_masked'  => mask_serial((string)$lic['serial']),
        'plan'           => $lic['tier'],
        'plan_name'      => plan_name((string)$lic['tier']),
        'status'         => $lic['status'],
        'state'          => $state['state'],
        'message'        => $state['message'],
        'created_at'     => $lic['created_at'],
        'activated_at'   => $lic['activated_at'] ?? null,
        'expires_at'     => $lic['expires_at'],
        'remaining'      => remaining($lic['expires_at']),
        'max_devices'    => (int)($lic['max_devices'] ?? 1),
        'devices_used'   => license_device_count((int)$lic['id']),
    ];
}

/** Claims for the signed session token the desktop keeps. */
function license_claims(array $lic, string $device): array
{
    $tier = (string)$lic['tier'];
    return [
        'sub'      => (int)$lic['id'],
        'serial'   => $lic['serial'],
        'device'   => $device,
        'tier'     => $tier,
        'plan'     => $tier,
        'features' => plan_is_paid($tier) ? ['scripts.free', 'scripts.pro'] : ['scripts.free'],
        'ent'      => plan_entitlements($tier, (int)($lic['max_devices'] ?? 1)),
        'lexp'     => strtotime($lic['expires_at'] . ' UTC'),
        'maxd'     => (int)($lic['max_devices'] ?? 1),
    ];
}

// ---------------------------------------------------------------------
// signed session token
// ---------------------------------------------------------------------

/** Base64url without padding, as used by JWT. */
function b64u(string $bin): string
{
    return rtrim(strtr(base64_encode($bin), '+/', '-_'), '=');
}

function b64u_decode(string $txt): string
{
    return base64_decode(strtr($txt, '-_', '+/')) ?: '';
}

// ---------------------------------------------------------------------
// v6.2.1: where the signing keypair comes from.
//
// ROOT CAUSE OF THE ACTIVATION BUG: the keypair used to live ONLY in two
// constants in includes/config.php, filled in by hand after running
// install/keygen.php in a browser. When that manual step is skipped the
// constants stay empty, ed25519_sign_compact() refuses to issue an
// unsigned token, and EVERY signing endpoint returns HTTP 500
// "server signing key not configured" - activation, check-in and the
// script manifest alike.
//
// The keypair can now ALSO live in the settings table, where the dashboard
// generates it with one button (Settings -> Licence signing keys). The
// resolution order is:
//
//   1) the settings table  (written by the dashboard)
//   2) the config.php constants  (existing installs keep working, unchanged)
//
// Nothing is removed. An install that already has LICENSE_SECRET_KEY and
// LICENSE_PUBLIC_KEY filled in behaves exactly as it did before.
// ---------------------------------------------------------------------

const LICENSE_KEY_SETTING_SECRET  = 'license_secret_key';
const LICENSE_KEY_SETTING_PUBLIC  = 'license_public_key';
const LICENSE_KEY_SETTING_CREATED = 'license_key_created_at';

/**
 * The raw (binary) Ed25519 secret key, or '' when none is configured.
 * Never returned to a browser, never logged, never sent to a client.
 */
function license_signing_secret(): string
{
    static $cached = null;
    static $generation = -1;
    $now = (int)($GLOBALS['__mvl_key_generation'] ?? 0);
    if ($cached !== null && $generation === $now) {
        return $cached;
    }
    $generation = $now;
    $cached = '';
    // 1) dashboard-generated key
    $stored = (string)setting(LICENSE_KEY_SETTING_SECRET, '');
    if ($stored !== '') {
        $raw = base64_decode($stored, true);
        if ($raw !== false && strlen($raw) === SODIUM_CRYPTO_SIGN_SECRETKEYBYTES) {
            $cached = $raw;
            return $cached;
        }
    }
    // 2) the original config.php constant
    $raw = base64_decode((string)cfg('LICENSE_SECRET_KEY', ''), true);
    if ($raw !== false && strlen($raw) === SODIUM_CRYPTO_SIGN_SECRETKEYBYTES) {
        $cached = $raw;
    }
    return $cached;
}

/** The raw (binary) Ed25519 public key, or '' when none is configured. */
function license_signing_public(): string
{
    static $cached = null;
    static $generation = -1;
    $now = (int)($GLOBALS['__mvl_key_generation'] ?? 0);
    if ($cached !== null && $generation === $now) {
        return $cached;
    }
    $generation = $now;
    $cached = '';
    $stored = (string)setting(LICENSE_KEY_SETTING_PUBLIC, '');
    if ($stored !== '') {
        $raw = base64_decode($stored, true);
        if ($raw !== false && strlen($raw) === SODIUM_CRYPTO_SIGN_PUBLICKEYBYTES) {
            $cached = $raw;
            return $cached;
        }
    }
    $raw = base64_decode((string)cfg('LICENSE_PUBLIC_KEY', ''), true);
    if ($raw !== false && strlen($raw) === SODIUM_CRYPTO_SIGN_PUBLICKEYBYTES) {
        $cached = $raw;
    }
    return $cached;
}

/** True when this server can actually sign. Check BEFORE writing any state. */
function license_signing_ready(): bool
{
    return license_signing_secret() !== '' && license_signing_public() !== '';
}

/**
 * Short, safe identifier for a public key, so the dashboard can show WHICH
 * key is installed without showing the key itself. Derived from the public
 * half only - it never reveals anything secret.
 */
function license_key_fingerprint(string $publicRaw = ''): string
{
    if ($publicRaw === '') {
        $publicRaw = license_signing_public();
    }
    if ($publicRaw === '') {
        return '';
    }
    return strtoupper(implode(' ', str_split(substr(hash('sha256', $publicRaw), 0, 16), 4)));
}

/**
 * Everything the Settings page needs to describe the current keypair.
 * The secret key is NEVER part of this array.
 */
function license_key_status(): array
{
    $public = license_signing_public();
    $fromDb = (string)setting(LICENSE_KEY_SETTING_PUBLIC, '') !== '';
    return [
        'configured'  => license_signing_ready(),
        'source'      => $public === '' ? 'none' : ($fromDb ? 'dashboard' : 'config.php'),
        'public_b64'  => $public === '' ? '' : base64_encode($public),
        'fingerprint' => license_key_fingerprint($public),
        'created_at'  => (string)setting(LICENSE_KEY_SETTING_CREATED, ''),
    ];
}

/**
 * Create a fresh Ed25519 keypair and store it in the settings table.
 * Returns ['ok' => bool, 'error' => string, 'public_b64' => string, ...].
 *
 * Regenerating invalidates every token signed by the previous key, so every
 * installed copy of the desktop tool must be rebuilt with the new public
 * key. The dashboard warns about this before calling us.
 */
function license_keypair_generate(): array
{
    if (!function_exists('sodium_crypto_sign_keypair')) {
        return ['ok' => false, 'error' => 'This PHP build has no sodium extension, so keys cannot be generated. Ask your host to enable it.'];
    }
    try {
        $pair   = sodium_crypto_sign_keypair();
        $secret = sodium_crypto_sign_secretkey($pair);
        $public = sodium_crypto_sign_publickey($pair);
    } catch (Throwable $e) {
        error_log('[mavelylink] keypair generation failed: ' . $e->getMessage());
        return ['ok' => false, 'error' => 'The keypair could not be generated.'];
    }

    $previous = license_key_fingerprint();
    set_setting(LICENSE_KEY_SETTING_SECRET, base64_encode($secret));
    set_setting(LICENSE_KEY_SETTING_PUBLIC, base64_encode($public));
    set_setting(LICENSE_KEY_SETTING_CREATED, now());

    // drop the per-request caches so the new key is live immediately, in
    // this same request - otherwise the page would still report the old one
    license_signing_reset_cache();

    audit('settings.signing_key.generated',
          ($previous === '' ? 'first keypair' : 'replaced ' . $previous)
          . ' -> ' . license_key_fingerprint($public));

    return [
        'ok'          => true,
        'error'       => '',
        'public_b64'  => base64_encode($public),
        'fingerprint' => license_key_fingerprint($public),
        'replaced'    => $previous,
    ];
}

/**
 * Forget the cached keys. Called after the dashboard writes a new pair so
 * the rest of the request sees it without a reload.
 */
function license_signing_reset_cache(): void
{
    // Both resolvers cache in a function static AND compare a generation
    // counter held here. Bumping it makes them re-read the settings table on
    // their next call, so a key generated earlier in this request is live
    // straight away.
    $GLOBALS['__mvl_key_generation'] = (int)($GLOBALS['__mvl_key_generation'] ?? 0) + 1;
}

function ed25519_sign_compact(array $claims): string
{
    $header  = b64u(json_encode(['alg' => 'EdDSA', 'typ' => 'JWT']));
    $payload = b64u(json_encode($claims, JSON_UNESCAPED_SLASHES));
    $signing = $header . '.' . $payload;
    // v6.2.1: resolved from the settings table first, then the config.php
    // constant. The original constant path is preserved inside the resolver.
    $secret = license_signing_secret();
    if ($secret === '' || strlen($secret) !== SODIUM_CRYPTO_SIGN_SECRETKEYBYTES) {
        // Refuse to hand out an unsigned token; that would be worse than failing.
        json_out(['ok' => false, 'error' => 'server signing key not configured'], 500);
    }
    return $signing . '.' . b64u(sodium_crypto_sign_detached($signing, $secret));
}

/**
 * Ed25519-signed token. The desktop client embeds only the public key, so
 * a fake server (hosts file, DNS) cannot mint a token the client accepts.
 */
function sign_token(array $claims): string
{
    $claims['iat'] = time();
    $claims['exp'] = time() + LICENSE_TTL_HOURS * 3600;
    $claims['grace_until'] = time() + (LICENSE_TTL_HOURS * 3600) + GRACE_DAYS * 86400;
    return ed25519_sign_compact($claims);
}

/** Signed control message (master switch, update policy, script manifest). */
function sign_control(array $claims, int $ttlSeconds = 604800): string
{
    $claims['iat'] = time();
    $claims['exp'] = time() + $ttlSeconds;
    return ed25519_sign_compact($claims);
}

/**
 * $allowExpiredFor lets a genuine token that expired recently be renewed:
 * the database, not the token, decides whether the licence is still good.
 */
function verify_token(string $token, int $allowExpiredFor = 0): ?array
{
    $parts = explode('.', $token);
    if (count($parts) !== 3) {
        return null;
    }
    [$h, $p, $s] = $parts;
    // v6.2.1: same resolution order as the signer, so a dashboard-generated
    // key verifies the tokens it signed. The config.php constant is still
    // honoured, inside the resolver.
    $public = license_signing_public();
    if ($public === '' || strlen($public) !== SODIUM_CRYPTO_SIGN_PUBLICKEYBYTES) {
        return null;
    }
    $sig = b64u_decode($s);
    if (strlen($sig) !== SODIUM_CRYPTO_SIGN_BYTES
        || !sodium_crypto_sign_verify_detached($sig, $h . '.' . $p, $public)) {
        return null;
    }
    $claims = json_decode(b64u_decode($p), true);
    if (!is_array($claims) || ((int)($claims['exp'] ?? 0) + max(0, $allowExpiredFor)) < time()) {
        return null;
    }
    return $claims;
}

/** Scripts this plan is entitled to (metadata only). */
function scripts_manifest(string $plan, bool $withSource = false): array
{
    $cols = 'slug, name, version, min_tier, plans, COALESCE(checksum, SHA2(source, 256)) AS sha256'
          . ($withSource ? ', source' : '');
    // v6.3.1 (TASK 4). min_tier is a MINIMUM-TIER threshold: it can express
    // "everyone" and "paid only", but it cannot express "Free only", which is
    // now required for Script 1. So an explicit per-plan allow-list was added.
    //
    // Both paths are kept. A row with a `plans` list is matched against the
    // requesting installation's exact plan; a row that has none behaves
    // EXACTLY as it always did, through min_tier. Nothing was removed.
    //
    // FIND_IN_SET matches a whole comma-separated element, so 'pro' does not
    // match inside 'free' and there is no prefix ambiguity.
    $st = db()->prepare("SELECT $cols FROM scripts
                          WHERE enabled = 1 AND source IS NOT NULL AND source <> ''
                            AND (
                                  (plans IS NOT NULL AND plans <> '' AND FIND_IN_SET(?, plans))
                               OR ((plans IS NULL OR plans = '') AND (min_tier = 'free' OR ? = 1))
                                )
                          ORDER BY id");
    // An unknown or unverifiable plan falls back to Free entitlement here,
    // which is what spec 4.4 requires: never hand Script 2 to an
    // installation whose licence could not be verified.
    $resolved = in_array($plan, ['free', 'pro', 'team'], true) ? $plan : 'free';
    $st->execute([$resolved, plan_is_paid($resolved) ? 1 : 0]);
    $rows = $st->fetchAll();
    foreach ($rows as &$r) {
        $r['version'] = (int)$r['version'];
        if ($withSource) {
            $r['sha256'] = hash('sha256', (string)$r['source']);
        }
    }
    return $rows;
}

/** Record where an installation is and what it runs (all plans, free included). */
function installation_touch(string $device, string $plan, ?int $licenseId, string $version,
                            int $profiles, string $state): void
{
    try {
        db()->prepare('INSERT INTO installations (device_hash, plan, license_id, app_version, profile_count,
                        first_seen, last_seen, last_ip, last_state, checkins)
                       VALUES (?,?,?,?,?,?,?,?,?,1)
                       ON DUPLICATE KEY UPDATE plan = VALUES(plan), license_id = VALUES(license_id),
                         app_version = VALUES(app_version), profile_count = VALUES(profile_count),
                         last_seen = VALUES(last_seen), last_ip = VALUES(last_ip),
                         last_state = VALUES(last_state), checkins = checkins + 1')
            ->execute([$device, $plan, $licenseId, $version, $profiles, now(), now(), client_ip(), $state]);
    } catch (PDOException $e) {
        error_log('[mavelylink] installation_touch: ' . $e->getMessage());
    }
}

function client_errors_store(array $errors, string $device, ?int $licenseId, string $version): void
{
    $ins = db()->prepare('INSERT INTO client_errors (device_hash, license_id, app_version, kind, message, created_at)
                          VALUES (?,?,?,?,?,?)');
    foreach (array_slice($errors, 0, 10) as $err) {
        if (!is_array($err)) {
            continue;
        }
        $kind = preg_replace('/[^a-z0-9_.-]/', '', strtolower((string)($err['kind'] ?? 'error'))) ?: 'error';
        $msg = trim((string)($err['message'] ?? ''));
        if ($msg !== '') {
            $ins->execute([$device, $licenseId, $version, substr($kind, 0, 48), mb_substr($msg, 0, 500), now()]);
        }
    }
}
