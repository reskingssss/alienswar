<?php
/**
 * MavelyLink 6.3 - referral programme.
 *
 * ADDITIVE. Nothing in this file replaces existing behaviour. It adds three
 * tables (customers, customer_devices, referrals) and two nullable columns
 * on orders, and it hooks into the existing order lifecycle at exactly two
 * points, both guarded so a referral problem can never break a sale:
 *
 *   order paid     -> referral_on_order_paid()      (confirm + maybe reward)
 *   order refunded -> referral_on_order_refunded()  (revert + flag)
 *
 * IDENTITY. This codebase has no user accounts - includes/auth.php is
 * admin-only, and a buyer is just an email address on orders/licenses. The
 * `customers` table adds the missing durable identity WITHOUT touching any
 * existing table: it is keyed on the normalised email that licenses.email
 * and orders.email already use, so it lines up with everything that is
 * already there. Free users (who have no licence and no serial) are linked
 * through customer_devices using the same device_hash the check-in already
 * reports.
 *
 * REWARD. At the threshold the referrer is granted a Pro licence, server
 * side, through the EXISTING issue_license(). Exactly-once is inherited
 * from that function's UNIQUE KEY uq_external on licenses.external_id: the
 * reward is issued with external_id 'referral:<customer id>', so a repeat
 * call returns the licence that already exists instead of making another.
 */
declare(strict_types=1);
require_once __DIR__ . '/license.php';
// public_session_start() lives here. Loading it means the session half of
// the attribution (spec 2.3: "cookie + server-side session") always works,
// not only on pages that happened to load csrf.php already. It starts a
// session ONLY when a real code is seen, so an ordinary visitor still gets
// no session cookie.
require_once __DIR__ . '/csrf.php';

// Same alphabet the serials use: no I, O, U, 0 or 1, so a code cannot be
// misread over the phone or mistyped into somebody else's code.
const REFERRAL_ALPHABET   = '23456789ABCDEFGHJKLMNPQRSTVWXYZ';
const REFERRAL_CODE_LEN   = 8;

/**
 * Codes that must never be handed out, because the app already puts them
 * in ?ref= as plain provenance markers (pricing.php?ref=app) or because
 * they would read as something else in a URL.
 */
const REFERRAL_RESERVED = ['APP', 'WEB', 'REF', 'NONE', 'NULL', 'TEST', 'ADMIN', 'EMAIL', 'SITE'];

// ---------------------------------------------------------------------
// settings
// ---------------------------------------------------------------------
function referral_enabled(): bool
{
    return setting_bool('referral_enabled', true);
}

/** Confirmed referrals needed for the reward. Marketing copy says 5. */
function referral_threshold(): int
{
    return max(1, (int)setting('referral_threshold', '5'));
}

/** How long an attributed visit stays attached to the visitor. */
function referral_cookie_days(): int
{
    return max(1, min(365, (int)setting('referral_cookie_days', '30')));
}

/** The plan granted at the threshold. */
function referral_reward_plan(): string
{
    $p = (string)setting('referral_reward_plan', 'pro');
    return in_array($p, PAID_PLANS, true) ? $p : 'pro';
}

/** The cash alternative, requested manually from support (offer wording). */
function referral_cash_amount(): string
{
    return (string)setting('referral_cash_amount', '15');
}

function referral_terms_url(): string
{
    return site_url('referral-terms.php');
}

// ---------------------------------------------------------------------
// codes
// ---------------------------------------------------------------------
function referral_normalise_code($code): string
{
    $c = strtoupper(trim((string)$code));
    $c = preg_replace('/[^A-Z0-9]/', '', $c) ?? '';
    return substr($c, 0, 16);
}

/**
 * A fresh code. Random, so it is neither sequential nor derivable from the
 * customer id (spec section 4), and checked for uniqueness and against the
 * reserved list before it is returned.
 */
function referral_generate_code(): string
{
    $pdo = db();
    for ($attempt = 0; $attempt < 20; $attempt++) {
        $code = '';
        for ($i = 0; $i < REFERRAL_CODE_LEN; $i++) {
            $code .= REFERRAL_ALPHABET[random_int(0, strlen(REFERRAL_ALPHABET) - 1)];
        }
        if (in_array($code, REFERRAL_RESERVED, true)) {
            continue;
        }
        $st = $pdo->prepare('SELECT 1 FROM customers WHERE referral_code = ?');
        $st->execute([$code]);
        if (!$st->fetch()) {
            return $code;
        }
    }
    throw new RuntimeException('could not allocate a referral code');
}

/**
 * The public base URL invite links are built from. ONE source of truth
 * (spec 1.4): an admin can change it in Settings without a release, and the
 * desktop tool only ever displays what the server sends.
 *
 * Falls back to base_url(), which is now correct from any directory.
 * Anything that is not a plain https/http origin is ignored rather than
 * trusted, so a bad value cannot poison every invite link.
 */
function referral_public_base(): string
{
    $configured = trim((string)setting('site_public_url', ''));
    if ($configured !== ''
        && preg_match('~^https?://[A-Za-z0-9.\-]+(:\d+)?(/[A-Za-z0-9._\-/]*)?$~', $configured)) {
        return rtrim($configured, '/');
    }
    return rtrim(base_url(), '/');
}

function referral_link_for(string $code): string
{
    return referral_public_base() . '/?ref=' . rawurlencode($code);
}

/**
 * Record a click on an invite link. Clicks NEVER count toward the reward
 * (spec 1.5) - only a confirmed paid purchase does. This table exists so
 * the admin can see traffic, and it is deduplicated per code+visitor inside
 * a short window so one person refreshing does not flood the page.
 */
function referral_log_click(string $code, int $customerId): void
{
    try {
        $ipHash = substr(hash_hmac('sha256', client_ip(), APP_SECRET), 0, 32);
        $ua = mb_substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 255);
        $window = max(60, (int)setting('referral_click_dedupe_seconds', '900'));
        $st = db()->prepare('SELECT id FROM referral_clicks
                              WHERE referral_code = ? AND ip_hash = ?
                                AND created_at > DATE_SUB(UTC_TIMESTAMP(), INTERVAL ? SECOND)
                              LIMIT 1');
        $st->execute([$code, $ipHash, $window]);
        if ($st->fetch()) {
            return;     // same visitor, same code, moments ago
        }
        db()->prepare('INSERT INTO referral_clicks
            (referral_code, referrer_customer_id, ip_hash, user_agent, referer, created_at)
            VALUES (?,?,?,?,?,?)')
            ->execute([$code, $customerId, $ipHash, $ua,
                       mb_substr((string)($_SERVER['HTTP_REFERER'] ?? ''), 0, 255), now()]);
    } catch (Throwable $e) {
        error_log('[mavelylink] referral_log_click: ' . $e->getMessage());
    }
}

// ---------------------------------------------------------------------
// customers - the durable identity behind a referral code
// ---------------------------------------------------------------------
function customer_normalise_email($email): string
{
    return mb_substr(strtolower(trim((string)$email)), 0, 190);
}

function customer_by_id(?int $id): ?array
{
    if (!$id) {
        return null;
    }
    $st = db()->prepare('SELECT * FROM customers WHERE id = ?');
    $st->execute([$id]);
    return $st->fetch() ?: null;
}

function customer_by_email($email): ?array
{
    $email = customer_normalise_email($email);
    if ($email === '') {
        return null;
    }
    $st = db()->prepare('SELECT * FROM customers WHERE email = ?');
    $st->execute([$email]);
    return $st->fetch() ?: null;
}

function customer_by_code($code): ?array
{
    $code = referral_normalise_code($code);
    if ($code === '') {
        return null;
    }
    $st = db()->prepare('SELECT * FROM customers WHERE referral_code = ?');
    $st->execute([$code]);
    return $st->fetch() ?: null;
}

/** The customer that owns this installation, through its device hash. */
function customer_by_device(string $device): ?array
{
    $device = clean_hex($device);
    if (strlen($device) !== 64) {
        return null;
    }
    $st = db()->prepare('SELECT c.* FROM customer_devices d JOIN customers c ON c.id = d.customer_id
                          WHERE d.device_hash = ? ORDER BY d.last_seen DESC LIMIT 1');
    $st->execute([$device]);
    return $st->fetch() ?: null;
}

/**
 * Find or create the customer for an email. Safe to call repeatedly and
 * safe under a race: the UNIQUE KEY on customers.email means a losing
 * insert is simply re-read.
 */
function customer_get_or_create($email, string $source = 'site', string $device = ''): ?array
{
    $email = customer_normalise_email($email);
    if ($email === '' || !valid_email($email)) {
        return null;
    }
    $row = customer_by_email($email);
    if (!$row) {
        try {
            db()->prepare('INSERT INTO customers (email, referral_code, source, created_at, updated_at)
                           VALUES (?,?,?,?,?)')
                ->execute([$email, referral_generate_code(), mb_substr($source, 0, 32), now(), now()]);
            audit('referral.customer_created', $email . ' via ' . $source);
        } catch (PDOException $e) {
            // someone inserted the same email a moment ago - fall through
        }
        $row = customer_by_email($email);
    }
    if ($row && $device !== '') {
        customer_touch_device((int)$row['id'], $device);
        $row = customer_by_id((int)$row['id']);
    }
    return $row;
}

/** Record that this installation belongs to this customer. */
function customer_touch_device(int $customerId, string $device): void
{
    $device = clean_hex($device);
    if ($customerId <= 0 || strlen($device) !== 64) {
        return;
    }
    try {
        db()->prepare('INSERT INTO customer_devices (customer_id, device_hash, first_seen, last_seen, last_ip)
                       VALUES (?,?,?,?,?)
                       ON DUPLICATE KEY UPDATE last_seen = VALUES(last_seen), last_ip = VALUES(last_ip)')
            ->execute([$customerId, $device, now(), now(), client_ip()]);
    } catch (PDOException $e) {
        error_log('[mavelylink] customer_touch_device: ' . $e->getMessage());
    }
}

/** True when these two customers look like the same person. */
function customer_same_person(array $a, array $b): bool
{
    if ((int)$a['id'] === (int)$b['id']) {
        return true;
    }
    return customer_normalise_email($a['email']) === customer_normalise_email($b['email']);
}

/** True when the two customers have ever been seen on the same machine. */
function customer_shares_device(int $aId, int $bId): bool
{
    $st = db()->prepare('SELECT 1 FROM customer_devices x JOIN customer_devices y
                          ON x.device_hash = y.device_hash
                         WHERE x.customer_id = ? AND y.customer_id = ? LIMIT 1');
    $st->execute([$aId, $bId]);
    return (bool)$st->fetch();
}

function customer_flag(int $customerId, string $reason): void
{
    db()->prepare('UPDATE customers SET flagged = 1, flag_reason = ?, updated_at = ? WHERE id = ?')
        ->execute([mb_substr($reason, 0, 255), now(), $customerId]);
    audit('referral.flagged', '#' . $customerId . ': ' . $reason);
}

// ---------------------------------------------------------------------
// attribution: ?ref=CODE  ->  cookie + public session  ->  order
// ---------------------------------------------------------------------
const REFERRAL_COOKIE = 'mvl_ref';

/**
 * Called from every public page. Reads ?ref=CODE and remembers it for
 * referral_cookie_days(), in BOTH a cookie and the existing public
 * session (includes/csrf.php public_session_start, cookie MVLSHOP).
 *
 * A session is only started when there is actually something to store or
 * an existing shop session is already running, so an ordinary visitor who
 * never saw a referral link is not given a session cookie.
 */
function referral_capture_from_request(): void
{
    if (!referral_enabled()) {
        return;
    }
    $code = referral_normalise_code($_GET['ref'] ?? '');
    if ($code === '' || in_array($code, REFERRAL_RESERVED, true)) {
        return;     // no code, or one of the app's provenance markers
    }
    if (strlen($code) !== REFERRAL_CODE_LEN) {
        return;
    }
    try {
        $customer = customer_by_code($code);
        if (!$customer) {
            return;   // unknown or disabled code: store nothing, show nothing
        }
    } catch (Throwable $e) {
        return;       // table not migrated yet: stay silent
    }
    // spec 1.5: rate-limit the public route per IP. A blocked visitor still
    // gets the page - they simply do not get attribution or a click row.
    if (function_exists('rate_ok') && !rate_ok('ref_click', client_ip(), 120, 3600)) {
        return;
    }
    referral_log_click($code, (int)$customer['id']);
    $days = referral_cookie_days();
    $https = (!empty($_SERVER['HTTPS']) && strtolower((string)$_SERVER['HTTPS']) !== 'off')
        || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
    if (!headers_sent()) {
        setcookie(REFERRAL_COOKIE, $code, [
            'expires'  => time() + $days * 86400,
            'path'     => '/',
            'httponly' => true,
            'secure'   => $https,
            'samesite' => 'Lax',   // must survive arriving from another site
        ]);
    }
    $_COOKIE[REFERRAL_COOKIE] = $code;
    // The cookie above is the primary record. The session is the belt to its
    // braces, and is only started when a session can still legitimately be
    // started - if a page has already sent output, starting one would emit
    // warnings and achieve nothing. Attribution still works from the cookie.
    if (function_exists('public_session_start')
        && (!headers_sent() || session_status() === PHP_SESSION_ACTIVE)) {
        public_session_start();
        $_SESSION['mvl_ref'] = $code;
        $_SESSION['mvl_ref_at'] = time();
    }
}

/** The code attached to this visitor right now, or ''. Session wins. */
function referral_current_code(): string
{
    if (session_status() === PHP_SESSION_ACTIVE && !empty($_SESSION['mvl_ref'])) {
        $age = time() - (int)($_SESSION['mvl_ref_at'] ?? 0);
        if ($age <= referral_cookie_days() * 86400) {
            return referral_normalise_code($_SESSION['mvl_ref']);
        }
    }
    return referral_normalise_code($_COOKIE[REFERRAL_COOKIE] ?? '');
}

/**
 * Stamp a freshly created order with the referral it came from. Called
 * straight after order_create(); order_create() itself is NOT modified.
 *
 * Self-referral is rejected HERE, before anything is written, on account
 * id and on email. A shared IP only raises a flag for the admin, because
 * families, offices and mobile carriers legitimately share one.
 */
function referral_attach_to_order(int $orderId, string $code = ''): void
{
    if (!referral_enabled() || $orderId <= 0) {
        return;
    }
    try {
        $code = $code !== '' ? referral_normalise_code($code) : referral_current_code();
        if ($code === '') {
            return;
        }
        $referrer = customer_by_code($code);
        if (!$referrer) {
            return;
        }
        // orders.php loads this file, not the other way round, so guard the
        // one call that reaches back into it. The API endpoints load
        // referral.php on its own and never take this path.
        if (!function_exists('order_by_id')) {
            return;
        }
        $order = order_by_id($orderId);
        if (!$order) {
            return;
        }
        $buyerEmail = customer_normalise_email($order['email']);

        // --- self-referral: same email as the code's owner -------------
        if ($buyerEmail !== '' && $buyerEmail === customer_normalise_email($referrer['email'])) {
            audit('referral.self_rejected', $order['ref'] . ' code ' . $code);
            return;
        }
        db()->prepare('UPDATE orders SET referred_by = ?, referrer_customer_id = ?, updated_at = ?
                        WHERE id = ? AND referrer_customer_id IS NULL')
            ->execute([$code, (int)$referrer['id'], now(), $orderId]);
        audit('referral.order_attributed', $order['ref'] . ' -> ' . $code);
    } catch (Throwable $e) {
        error_log('[mavelylink] referral_attach_to_order: ' . $e->getMessage());
    }
}

// ---------------------------------------------------------------------
// confirming a referral - only ever on a CONFIRMED payment
// ---------------------------------------------------------------------
/**
 * Called from order_fulfil() after the licence has been committed, inside
 * its own try/catch there, so nothing here can fail a sale.
 *
 * "One buyer counts once" (your decision) is enforced by the UNIQUE KEY
 * uq_referrer_buyer (referrer_customer_id, referred_email) on referrals:
 * a second purchase by the same buyer is an INSERT IGNORE that changes
 * nothing.
 */
function referral_on_order_paid(array $order): void
{
    if (!referral_enabled()) {
        return;
    }
    $referrerId = (int)($order['referrer_customer_id'] ?? 0);
    if ($referrerId <= 0) {
        return;
    }
    $referrer = customer_by_id($referrerId);
    if (!$referrer) {
        return;
    }

    // the buyer becomes a customer too, so they get their own code and can
    // refer people in turn
    $buyer = customer_get_or_create((string)$order['email'], 'purchase');
    $buyerEmail = customer_normalise_email($order['email']);

    // --- anti-abuse, checked again at confirmation time ----------------
    if ($buyer && customer_same_person($referrer, $buyer)) {
        audit('referral.self_rejected_at_payment', (string)$order['ref']);
        return;
    }
    $flag = '';
    if ($buyer && customer_shares_device((int)$referrer['id'], (int)$buyer['id'])) {
        $flag = 'Referrer and buyer have used the same computer.';
    }

    $pdo = db();
    $st = $pdo->prepare('INSERT IGNORE INTO referrals
        (referrer_customer_id, referred_customer_id, referred_email, referral_code, order_id,
         license_id, license_serial, amount, currency, status, flagged, flag_reason,
         created_at, confirmed_at, ip)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
    $serial = null;
    if (!empty($order['license_id'])) {
        $lic = license_by_id((int)$order['license_id']);
        $serial = $lic['serial'] ?? null;
    }
    $st->execute([
        (int)$referrer['id'],
        $buyer ? (int)$buyer['id'] : null,
        $buyerEmail,
        (string)($order['referred_by'] ?? $referrer['referral_code']),
        (int)$order['id'],
        !empty($order['license_id']) ? (int)$order['license_id'] : null,
        $serial,
        $order['final_amount'] ?? null,
        $order['currency'] ?? 'USD',
        'confirmed',
        $flag !== '' ? 1 : 0,
        $flag !== '' ? $flag : null,
        now(), now(), client_ip(),
    ]);
    if ($st->rowCount() === 0) {
        // this buyer already counted for this referrer - nothing to do
        audit('referral.repeat_buyer_ignored', (string)$order['ref']);
        return;
    }
    if ($flag !== '') {
        customer_flag((int)$referrer['id'], $flag);
    }
    audit('referral.confirmed', $referrer['referral_code'] . ' +1 (' . $order['ref'] . ')');
    referral_recount((int)$referrer['id']);
    referral_maybe_grant_reward((int)$referrer['id']);
}

/**
 * A refund or chargeback takes the referral back. Called from
 * refund_order_license(), so every refund path is covered at once.
 */
function referral_on_order_refunded(?array $order, string $why = ''): void
{
    if (!referral_enabled() || !$order) {
        return;
    }
    try {
        $st = db()->prepare("SELECT * FROM referrals WHERE order_id = ? AND status = 'confirmed'");
        $st->execute([(int)$order['id']]);
        $ref = $st->fetch();
        if (!$ref) {
            return;
        }
        db()->prepare("UPDATE referrals SET status = 'reverted', reverted_at = ?,
                        notes = CONCAT(COALESCE(notes,''), ?) WHERE id = ?")
            ->execute([now(), 'Reverted: ' . mb_substr($why ?: 'refund', 0, 200) . '. ', (int)$ref['id']]);
        $left = referral_recount((int)$ref['referrer_customer_id']);
        audit('referral.reverted', 'order ' . $order['ref'] . ', referrer now ' . $left);

        // spec 2.4: a reward already granted is NEVER revoked silently.
        // It is flagged for a human instead.
        $c = customer_by_id((int)$ref['referrer_customer_id']);
        if ($c && $c['reward_status'] === 'pro_granted' && $left < referral_threshold()) {
            customer_flag((int)$c['id'],
                'Reward already granted but confirmed referrals dropped to ' . $left
                . ' of ' . referral_threshold() . ' after a refund. Review manually.');
        }
    } catch (Throwable $e) {
        error_log('[mavelylink] referral_on_order_refunded: ' . $e->getMessage());
    }
}

/** Recalculate the cached count from the referrals table. Returns it. */
function referral_recount(int $customerId): int
{
    $st = db()->prepare("SELECT COUNT(*) FROM referrals
                          WHERE referrer_customer_id = ? AND status = 'confirmed'");
    $st->execute([$customerId]);
    $n = (int)$st->fetchColumn();
    db()->prepare('UPDATE customers SET referral_count_confirmed = ?, updated_at = ? WHERE id = ?')
        ->execute([$n, now(), $customerId]);
    return $n;
}

// ---------------------------------------------------------------------
// the reward
// ---------------------------------------------------------------------
/**
 * Grant the Pro licence once the threshold is reached.
 *
 * Exactly-once comes from two independent places, so a double check-in, a
 * webhook retry and two purchases confirming in the same second all give
 * the same single licence:
 *
 *   1. a MySQL named lock around the whole grant (the pattern migrate.php
 *      already uses), and
 *   2. issue_license()'s UNIQUE KEY on licenses.external_id, which returns
 *      the existing licence rather than issuing a second one.
 *
 * Your decision: always a Pro licence, including when the referrer already
 * holds Pro or Unlimited. For an existing ACTIVE Pro licence the existing
 * issue_license() extends it by the plan's period instead of creating a
 * duplicate serial, which is the same value with none of the confusion.
 */
function referral_maybe_grant_reward(int $customerId): void
{
    $c = customer_by_id($customerId);
    if (!$c || !referral_enabled()) {
        return;
    }
    $threshold = referral_threshold();
    if ((int)$c['referral_count_confirmed'] < $threshold) {
        return;
    }
    if ($c['reward_status'] === 'pro_granted' || $c['reward_status'] === 'cash_paid') {
        return;     // already rewarded
    }

    $pdo = db();
    $lockName = 'mvl_referral_reward_' . $customerId;
    $st = $pdo->prepare('SELECT GET_LOCK(?, 10)');
    $st->execute([$lockName]);
    if ((int)$st->fetchColumn() !== 1) {
        return;     // another request is granting it right now
    }
    try {
        $c = customer_by_id($customerId);        // re-read under the lock
        if (!$c || $c['reward_status'] === 'pro_granted' || $c['reward_status'] === 'cash_paid') {
            return;
        }
        if ((int)$c['referral_count_confirmed'] < $threshold) {
            return;
        }
        if ((int)$c['flagged'] === 1) {
            $pdo->prepare("UPDATE customers SET reward_status = 'eligible', updated_at = ? WHERE id = ?")
                ->execute([now(), $customerId]);
            audit('referral.reward_held', 'customer #' . $customerId . ' is flagged; awaiting review');
            return;
        }
        if (!license_signing_ready()) {
            // no signing key: leave the customer eligible and try again later
            $pdo->prepare("UPDATE customers SET reward_status = 'eligible', updated_at = ? WHERE id = ?")
                ->execute([now(), $customerId]);
            audit('referral.reward_deferred', 'customer #' . $customerId . ': no signing key');
            return;
        }
        $plan = referral_reward_plan();
        $planRow = plan_get($plan);
        $lic = issue_license((string)$c['email'], 'referral', 'referral:' . $customerId, $plan, [
            'period_days'  => (int)($planRow['period_days'] ?? 30),
            'device_limit' => (int)($planRow['device_limit'] ?? 1),
        ]);
        $pdo->prepare("UPDATE customers SET reward_status = 'pro_granted', reward_granted_at = ?,
                        reward_license_id = ?, reward_popup_seen_at = NULL, updated_at = ?
                        WHERE id = ?")
            ->execute([now(), (int)$lic['id'], now(), $customerId]);
        audit('referral.reward_granted',
              $c['email'] . ' -> ' . $plan . ' ' . $lic['serial'], (int)$lic['id']);
        try {
            referral_email_reward($c, $lic);
        } catch (Throwable $e) {
            error_log('[mavelylink] referral reward email: ' . $e->getMessage());
        }
    } finally {
        $rel = $pdo->prepare('SELECT RELEASE_LOCK(?)');
        $rel->execute([$lockName]);
        $rel->fetchColumn();
    }
}

function referral_email_reward(array $customer, array $lic): void
{
    $plan = plan_name((string)$lic['tier']);
    $body = implode("\n", [
        'Congratulations!',
        '',
        'You invited ' . referral_threshold() . ' people who bought a licence, so your '
            . $plan . ' licence has been activated automatically.',
        '',
        'Licence key: ' . $lic['serial'],
        'Valid until: ' . substr((string)$lic['expires_at'], 0, 16) . ' UTC',
        '',
        'It is already attached to this email address - the desktop tool picks it up on its',
        'next check-in, so there is nothing to type in.',
        '',
        'Referral terms: ' . referral_terms_url(),
    ]);
    send_mail((string)$customer['email'], 'Your referral reward is active', $body);
}

// ---------------------------------------------------------------------
// what the desktop tool asks for
// ---------------------------------------------------------------------
/** Confirmed referrals this referrer has not been shown a popup for yet. */
function referral_unseen_count(int $customerId): int
{
    $st = db()->prepare("SELECT COUNT(*) FROM referrals
                          WHERE referrer_customer_id = ? AND status = 'confirmed'
                            AND seen_by_referrer = 0");
    $st->execute([$customerId]);
    return (int)$st->fetchColumn();
}

/** The exact payload of GET /api/v1/referral/me. */
function referral_state(array $c): array
{
    $threshold = referral_threshold();
    $count = (int)$c['referral_count_confirmed'];
    $unseen = referral_unseen_count((int)$c['id']);
    return [
        'ok'                   => true,
        'enabled'              => referral_enabled(),
        'email'                => (string)$c['email'],
        'referral_code'        => (string)$c['referral_code'],
        'referral_link'        => referral_link_for((string)$c['referral_code']),
        'confirmed_count'      => $count,
        'threshold'            => $threshold,
        'remaining'            => max(0, $threshold - $count),
        'new_unseen_count'     => $unseen,
        'reward_status'        => (string)$c['reward_status'],
        // popup 2 is pending until the tool says it has shown it
        'reward_popup_pending' => $c['reward_status'] === 'pro_granted'
                                  && empty($c['reward_popup_seen_at']),
        'cash_amount'          => referral_cash_amount(),
        'terms_url'            => referral_terms_url(),
    ];
}

/**
 * The tool has shown the popups. Marks every confirmed referral as seen so
 * popup 1 does not come back, and stamps popup 2 when asked.
 */
function referral_mark_seen(int $customerId, bool $reward = false): void
{
    db()->prepare("UPDATE referrals SET seen_by_referrer = 1
                    WHERE referrer_customer_id = ? AND status = 'confirmed'")
        ->execute([$customerId]);
    if ($reward) {
        db()->prepare('UPDATE customers SET last_referral_popup_seen_at = ?, reward_popup_seen_at = ?,
                        updated_at = ? WHERE id = ?')
            ->execute([now(), now(), now(), $customerId]);
    } else {
        db()->prepare('UPDATE customers SET last_referral_popup_seen_at = ?, updated_at = ? WHERE id = ?')
            ->execute([now(), now(), $customerId]);
    }
}

// ---------------------------------------------------------------------
// admin actions (spec section 3)
// ---------------------------------------------------------------------
/**
 * Grant the reward by hand, ignoring the threshold. Used by the dashboard
 * for goodwill cases and for a customer whose count was held back by a
 * flag. Still exactly-once: the same external_id as the automatic grant.
 */
function referral_admin_grant_reward(int $customerId): array
{
    $c = customer_by_id($customerId);
    if (!$c) {
        return ['ok' => false, 'error' => 'Unknown customer.'];
    }
    if (!license_signing_ready()) {
        return ['ok' => false, 'error' => 'No licence signing key is configured yet (Settings -> Licence signing keys).'];
    }
    $plan = referral_reward_plan();
    $planRow = plan_get($plan);
    $lic = issue_license((string)$c['email'], 'referral', 'referral:' . $customerId, $plan, [
        'period_days'  => (int)($planRow['period_days'] ?? 30),
        'device_limit' => (int)($planRow['device_limit'] ?? 1),
    ]);
    db()->prepare("UPDATE customers SET reward_status = 'pro_granted', reward_granted_at = ?,
                    reward_license_id = ?, reward_popup_seen_at = NULL, updated_at = ? WHERE id = ?")
        ->execute([now(), (int)$lic['id'], now(), $customerId]);
    audit('referral.reward_granted_manually', $c['email'] . ' -> ' . $lic['serial'], (int)$lic['id']);
    return ['ok' => true, 'license' => $lic];
}

/** Take a granted reward licence back. Never happens automatically. */
function referral_admin_revoke_reward(int $customerId, string $why): array
{
    $c = customer_by_id($customerId);
    if (!$c) {
        return ['ok' => false, 'error' => 'Unknown customer.'];
    }
    if (!empty($c['reward_license_id'])) {
        db()->prepare("UPDATE licenses SET status = 'revoked', revoked_at = ?, updated_at = ?
                        WHERE id = ? AND status <> 'revoked'")
            ->execute([now(), now(), (int)$c['reward_license_id']]);
    }
    db()->prepare("UPDATE customers SET reward_status = 'none', reward_granted_at = NULL,
                    reward_license_id = NULL, updated_at = ? WHERE id = ?")
        ->execute([now(), $customerId]);
    audit('referral.reward_revoked', $c['email'] . ': ' . mb_substr($why, 0, 200),
          !empty($c['reward_license_id']) ? (int)$c['reward_license_id'] : null);
    return ['ok' => true];
}

/** Mark the cash alternative as paid out. */
function referral_admin_mark_paid(int $customerId, string $note): void
{
    db()->prepare("UPDATE customers SET reward_status = 'cash_paid', reward_granted_at = COALESCE(reward_granted_at, ?),
                    payout_note = ?, updated_at = ? WHERE id = ?")
        ->execute([now(), mb_substr($note, 0, 255), now(), $customerId]);
    audit('referral.cash_paid', '#' . $customerId . ' ' . mb_substr($note, 0, 200));
}

function referral_admin_unflag(int $customerId): void
{
    db()->prepare('UPDATE customers SET flagged = 0, flag_reason = NULL, updated_at = ? WHERE id = ?')
        ->execute([now(), $customerId]);
    audit('referral.unflagged', '#' . $customerId);
}

/** Force one referral into a state, then re-derive the referrer's count. */
function referral_admin_set_status(int $referralId, string $status, string $why): array
{
    $allowed = ['pending', 'confirmed', 'reverted', 'rejected'];
    if (!in_array($status, $allowed, true)) {
        return ['ok' => false, 'error' => 'Unknown status.'];
    }
    $st = db()->prepare('SELECT * FROM referrals WHERE id = ?');
    $st->execute([$referralId]);
    $r = $st->fetch();
    if (!$r) {
        return ['ok' => false, 'error' => 'Unknown referral.'];
    }
    db()->prepare('UPDATE referrals SET status = ?,
                    confirmed_at = IF(? = \'confirmed\', COALESCE(confirmed_at, ?), confirmed_at),
                    reverted_at  = IF(? = \'reverted\',  COALESCE(reverted_at, ?),  reverted_at),
                    notes = CONCAT(COALESCE(notes,\'\'), ?) WHERE id = ?')
        ->execute([$status, $status, now(), $status, now(),
                   'Admin set ' . $status . ': ' . mb_substr($why, 0, 160) . '. ', $referralId]);
    $left = referral_recount((int)$r['referrer_customer_id']);
    audit('referral.admin_status', '#' . $referralId . ' -> ' . $status . ', referrer now ' . $left);
    if ($status === 'confirmed') {
        referral_maybe_grant_reward((int)$r['referrer_customer_id']);
    }
    return ['ok' => true, 'count' => $left];
}

/**
 * Resolve the caller of a referral API call, using ONLY the mechanisms
 * that already exist: the signed licence token, or the device hash the
 * check-in already reports. No new auth system.
 *
 * Returns the customer, or null when this installation is not identified
 * yet (a Free user who has not given an email).
 */
function referral_identify(string $token, string $device): ?array
{
    $device = clean_hex($device);

    // 1) a signed licence token: authoritative, gives us the licence email
    if ($token !== '') {
        $claims = verify_token($token, (int)cfg('TOKEN_RENEW_GRACE_DAYS', 45) * 86400);
        if ($claims) {
            $lic = license_by_id((int)($claims['sub'] ?? 0));
            if ($lic) {
                return customer_get_or_create((string)$lic['email'], 'license', $device);
            }
        }
    }
    // 2) a device this installation has already registered
    if (strlen($device) === 64) {
        $c = customer_by_device($device);
        if ($c) {
            customer_touch_device((int)$c['id'], $device);
            return customer_by_id((int)$c['id']);
        }
    }
    return null;
}
