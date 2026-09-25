<?php
declare(strict_types=1);
require_once __DIR__ . '/db.php';

function e(?string $s): string
{
    return htmlspecialchars((string)$s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

/**
 * The site's own base URL, e.g. "https://your-domain.com" (no trailing slash).
 *
 * DOMAIN INDEPENDENCE: if SITE_URL is set in config it wins, so a deployment
 * can pin one canonical address. Otherwise the address is derived from the
 * incoming request, so the same source code works on any domain with no edit.
 */
function base_url(): string
{
    static $cached = null;
    if ($cached !== null) {
        return $cached;
    }
    $configured = defined('SITE_URL') ? trim((string)SITE_URL) : '';
    if ($configured !== '') {
        return $cached = rtrim($configured, '/');
    }
    $https = (!empty($_SERVER['HTTPS']) && strtolower((string)$_SERVER['HTTPS']) !== 'off')
        || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https')
        || (($_SERVER['SERVER_PORT'] ?? '') === '443');
    $scheme = $https ? 'https' : 'http';

    $host = (string)($_SERVER['HTTP_X_FORWARDED_HOST']
        ?? $_SERVER['HTTP_HOST']
        ?? $_SERVER['SERVER_NAME']
        ?? 'localhost');
    $host = trim(explode(',', $host)[0]);
    if (!preg_match('/^[A-Za-z0-9.\-]+(:\d+)?$/', $host)) {
        $host = 'localhost';
    }

    $script = str_replace('\\', '/', (string)($_SERVER['SCRIPT_NAME'] ?? ''));
    $dir = rtrim(str_replace('\\', '/', dirname($script)), '/');
    // v6.3.1: '/api/v1/referral' must come BEFORE '/api/v1', because the loop
    // stops at the first match and the longer path is the more specific one.
    // Without it a script in that directory resolved the site root to
    // https://host/api/v1/referral, which is what produced the broken invite
    // link (and then a 403, because that directory has no index file and
    // .htaccess sets Options -Indexes).
    foreach (['/admin', '/api/webhooks', '/api/v1/referral', '/api/v1', '/api', '/install'] as $sub) {
        if (substr($dir, -strlen($sub)) === $sub) {
            $dir = substr($dir, 0, -strlen($sub));
            break;
        }
    }
    $base = ($dir === '/' || $dir === '.') ? '' : $dir;
    return $cached = $scheme . '://' . $host . $base;
}

function json_out(array $data, int $code = 200): never
{
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('X-Content-Type-Options: nosniff');
    header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

function json_in(): array
{
    static $parsed = null;
    if ($parsed !== null) {
        return $parsed;
    }
    $raw = file_get_contents('php://input') ?: '';
    if (strlen($raw) > 65536) {
        json_out(['ok' => false, 'error' => 'payload too large'], 413);
    }
    $data = json_decode($raw, true);
    return $parsed = (is_array($data) ? $data : []);
}

function client_ip(): string
{
    // Only trust the proxy header when the request really came through one.
    $ip = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
    return filter_var($ip, FILTER_VALIDATE_IP) ? $ip : '0.0.0.0';
}

/** Absolute URL for a path within the site (leading slash optional). */
function site_url(string $path = ''): string
{
    if ($path === '') {
        return base_url();
    }
    return base_url() . '/' . ltrim($path, '/');
}

/** Numeric-aware dotted version compare: -1, 0 or 1 (4.10 > 4.2, 4.1 == 4.1.0). */
function version_cmp(string $a, string $b): int
{
    $pa = preg_split('/[.\-+]/', trim($a)) ?: [];
    $pb = preg_split('/[.\-+]/', trim($b)) ?: [];
    $n  = max(count($pa), count($pb));
    for ($i = 0; $i < $n; $i++) {
        $x = (int)($pa[$i] ?? 0);
        $y = (int)($pb[$i] ?? 0);
        if ($x !== $y) {
            return $x < $y ? -1 : 1;
        }
    }
    return 0;
}

/** Constant-time comparison wrapper. */
function same(string $a, string $b): bool
{
    return hash_equals($a, $b);
}

function now(): string
{
    return gmdate('Y-m-d H:i:s');
}

function days_from_now(int $days): string
{
    return gmdate('Y-m-d H:i:s', time() + $days * 86400);
}

/** Human "3 days left" / "expired". */
function remaining(?string $expiresAt): string
{
    if (!$expiresAt) {
        return 'no expiry';
    }
    $left = strtotime($expiresAt . ' UTC') - time();
    if ($left <= 0) {
        return 'expired';
    }
    $d = (int)floor($left / 86400);
    return $d >= 1 ? $d . ' day' . ($d === 1 ? '' : 's') . ' left' : 'under a day';
}

// ---------------------------------------------------------------------
// settings: a tiny key/value store the dashboard writes to
// ---------------------------------------------------------------------
/** Shared in-request cache, so set_setting() is visible to later reads. */
function &settings_cache(bool $reload = false): array
{
    static $cache = null;
    if ($cache === null || $reload) {
        $cache = [];
        try {
            foreach (db()->query('SELECT k, v FROM settings') as $row) {
                $cache[$row['k']] = $row['v'];
            }
        } catch (PDOException $e) {
            // settings table not created yet (fresh database): empty cache
        }
    }
    return $cache;
}

function setting(string $key, ?string $default = null): ?string
{
    $cache = &settings_cache();
    return $cache[$key] ?? $default;
}

function setting_bool(string $key, bool $default = false): bool
{
    $v = setting($key);
    return $v === null ? $default : ($v === '1');
}

function set_setting(string $key, string $value): void
{
    $st = db()->prepare(
        'INSERT INTO settings (k, v) VALUES (?, ?) ON DUPLICATE KEY UPDATE v = VALUES(v)'
    );
    $st->execute([$key, $value]);
    // keep this request's view consistent with what was just written
    $cache = &settings_cache();
    $cache[$key] = $value;
}

/** Read an optional config.php constant, with a default for older config files. */
function cfg(string $name, $default)
{
    return defined($name) ? constant($name) : $default;
}

// ---------------------------------------------------------------------
// audit log: every state change the dashboard or an API makes
// ---------------------------------------------------------------------
function audit(string $action, string $detail = '', ?int $licenseId = null): void
{
    $actor = null;
    if (session_status() === PHP_SESSION_ACTIVE && !empty($_SESSION['admin_user'])) {
        $actor = (string)$_SESSION['admin_user'];
    } elseif (PHP_SAPI === 'cli') {
        $actor = 'cli';
    }
    try {
        $st = db()->prepare(
            'INSERT INTO audit_log (action, detail, license_id, ip, created_at, actor)
             VALUES (?, ?, ?, ?, ?, ?)'
        );
        $st->execute([$action, mb_substr($detail, 0, 500), $licenseId, client_ip(), now(), $actor]);
    } catch (PDOException $e) {
        // database not upgraded yet (no actor column): use the original insert
        $st = db()->prepare(
            'INSERT INTO audit_log (action, detail, license_id, ip, created_at)
             VALUES (?, ?, ?, ?, ?)'
        );
        $st->execute([$action, mb_substr($detail, 0, 500), $licenseId, client_ip(), now()]);
    }
}

// ---------------------------------------------------------------------
// v6.2 small shared helpers
// ---------------------------------------------------------------------
function money(float|int|string $amount, string $currency = 'USD'): string
{
    $amount = (float)$amount;   // DECIMAL columns arrive as strings from PDO
    $symbols = ['USD' => '$', 'EUR' => "\u{20AC}", 'GBP' => "\u{00A3}"];
    $sym = $symbols[strtoupper($currency)] ?? '';
    $num = number_format($amount, 2);
    return $sym !== '' ? $sym . $num : $num . ' ' . strtoupper($currency);
}

/** "MVL-ABCDE-.....-.....-WXYZ1" style partial serial for logs and screens. */
function mask_serial(string $serial): string
{
    if (strlen($serial) < 12) {
        return $serial;
    }
    return substr($serial, 0, 10) . str_repeat('*', 5) . '-*****-' . substr($serial, -5);
}

function clean_device_hash($value): string
{
    $v = strtolower(preg_replace('/[^a-f0-9]/i', '', (string)$value) ?? '');
    return strlen($v) === 64 ? $v : '';
}

function is_post(): bool
{
    return ($_SERVER['REQUEST_METHOD'] ?? '') === 'POST';
}

/** Redirect with a one-line success (ok) or error (err) notice. */
function back_to(string $url, string $message, bool $ok = true): never
{
    $sep = strpos($url, '?') === false ? '?' : '&';
    header('Location: ' . $url . $sep . ($ok ? 'ok=' : 'err=') . rawurlencode($message));
    exit;
}

function random_token(int $bytes = 16): string
{
    return bin2hex(random_bytes($bytes));
}

function dt_or_null(?string $value): ?string
{
    $value = trim((string)$value);
    if ($value === '') {
        return null;
    }
    $ts = strtotime($value . (preg_match('/[zZ]|[+-]\d\d:?\d\d$/', $value) ? '' : ' UTC'));
    return $ts ? gmdate('Y-m-d H:i:s', $ts) : null;
}

/** Hex characters only, lower-case (device ids, hashes). */
function clean_hex($value, int $max = 128): string
{
    $v = strtolower(preg_replace('/[^a-f0-9]/i', '', (string)$value) ?? '');
    return substr($v, 0, $max);
}

/** A trimmed, length-capped string from the query string. */
function get_str(string $key, int $max = 200): string
{
    $v = $_GET[$key] ?? '';
    return is_string($v) ? mb_substr(trim($v), 0, $max) : '';
}

function valid_email($email): bool
{
    return is_string($email) && strlen($email) <= 190
        && filter_var($email, FILTER_VALIDATE_EMAIL) !== false;
}

/** Money as integer cents, so totals never suffer float rounding. */
function cents($amount): int
{
    if (is_int($amount)) {
        return $amount * 100;
    }
    $s = trim((string)$amount);
    if ($s === '' || !is_numeric($s)) {
        return 0;
    }
    return (int)round(((float)$s) * 100);
}

function from_cents(int $cents): string
{
    $neg = $cents < 0;
    $cents = abs($cents);
    return ($neg ? '-' : '') . intdiv($cents, 100) . '.' . str_pad((string)($cents % 100), 2, '0', STR_PAD_LEFT);
}

/** Does a table exist in the current database? $fresh skips the cache. */
function table_exists(string $table, bool $fresh = false): bool
{
    static $cache = [];
    if (!$fresh && array_key_exists($table, $cache)) {
        return $cache[$table];
    }
    try {
        $st = db()->prepare('SELECT COUNT(*) FROM information_schema.TABLES
                              WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?');
        $st->execute([$table]);
        $cache[$table] = (int)$st->fetchColumn() > 0;
    } catch (Throwable $e) {
        $cache[$table] = false;
    }
    return $cache[$table];
}

function column_exists(string $table, string $column): bool
{
    $st = db()->prepare('SELECT COUNT(*) FROM information_schema.COLUMNS
                          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?');
    $st->execute([$table, $column]);
    return (int)$st->fetchColumn() > 0;
}

/**
 * http(s) URL check. $httpsOnly additionally refuses plain http, which the
 * desktop updater requires for anything it downloads.
 */
function is_web_url(string $url, bool $httpsOnly = false): bool
{
    if ($url === '' || strlen($url) > 500 || filter_var($url, FILTER_VALIDATE_URL) === false) {
        return false;
    }
    $scheme = strtolower((string)parse_url($url, PHP_URL_SCHEME));
    return $httpsOnly ? $scheme === 'https' : in_array($scheme, ['http', 'https'], true);
}

/**
 * Plain-text mail through PHP mail() (works on Hostinger once the domain has
 * a mailbox). Failures are logged, never shown to customers.
 */
function send_mail(string $to, string $subject, string $body): bool
{
    if (!valid_email($to) || substr($to, -6) === '.local') {
        return false;
    }
    $from = trim((string)cfg('MAIL_FROM', ''));
    if ($from === '') {
        $from = SITE_NAME . ' <' . SUPPORT_EMAIL . '>';
    }
    $headers = [
        'From: ' . str_replace(["\r", "\n"], '', $from),
        'Reply-To: ' . SUPPORT_EMAIL,
        'MIME-Version: 1.0',
        'Content-Type: text/plain; charset=UTF-8',
        'Content-Transfer-Encoding: 8bit',
        'X-Mailer: ' . SITE_NAME,
    ];
    $subject = '=?UTF-8?B?' . base64_encode(str_replace(["\r", "\n"], ' ', $subject)) . '?=';
    $ok = false;
    try {
        $ok = function_exists('mail') && @mail($to, $subject, $body, implode("\r\n", $headers));
    } catch (Throwable $e) {
        $ok = false;
    }
    try {
        audit($ok ? 'mail.sent' : 'mail.failed', $to . ' | ' . mb_substr($subject, 0, 120));
    } catch (Throwable $e) {
    }
    return $ok;
}
