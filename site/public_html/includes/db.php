<?php
declare(strict_types=1);
require_once __DIR__ . '/config.php';

/**
 * v6.2.1: optional connection overrides written by the dashboard
 * (Settings -> Database connection), so the database can be re-pointed from
 * a browser with no file editing.
 *
 * includes/config.php is deliberately NOT modified by any of this: it stays
 * exactly as the site owner left it and remains the fallback for every
 * value. That also means an upgrade can never clobber working credentials.
 * The file returns a plain array and lives behind includes/.htaccess
 * ("Require all denied"), so it is not reachable over the web.
 */
function mvl_local_config(bool $reload = false): array
{
    static $cache = null;
    if ($cache !== null && !$reload) {
        return $cache;
    }
    $cache = [];
    $path = __DIR__ . '/config.local.php';
    if (is_file($path)) {
        try {
            $loaded = require $path;
            if (is_array($loaded)) {
                $cache = $loaded;
            }
        } catch (Throwable $e) {
            error_log('[mavelylink] config.local.php could not be read: ' . $e->getMessage());
        }
    }
    return $cache;
}

/** One connection value: dashboard override first, then config.php, then a default. */
function db_conf(string $key, string $default = ''): string
{
    $local = mvl_local_config();
    if (isset($local[$key]) && $local[$key] !== '') {
        return (string)$local[$key];
    }
    return defined($key) ? (string)constant($key) : $default;
}

/** Build the DSN from whichever source supplied the values. */
function db_dsn(?array $creds = null): string
{
    $host    = $creds['DB_HOST']    ?? db_conf('DB_HOST', 'localhost');
    $name    = $creds['DB_NAME']    ?? db_conf('DB_NAME', '');
    $port    = (int)($creds['DB_PORT'] ?? db_conf('DB_PORT', '3306'));
    $charset = $creds['DB_CHARSET'] ?? db_conf('DB_CHARSET', 'utf8mb4');
    $dsn = sprintf('mysql:host=%s;dbname=%s;charset=%s', $host, $name, $charset);
    if ($port > 0 && $port !== 3306) {
        $dsn = sprintf('mysql:host=%s;port=%d;dbname=%s;charset=%s', $host, $port, $name, $charset);
    }
    return $dsn;
}

/**
 * Try a set of credentials WITHOUT disturbing the live connection.
 * Used by the "Test connection" button, and again on save so bad details
 * can never be written to disk. Returns ['ok' => bool, 'error' => string].
 */
function db_test_connection(array $creds): array
{
    try {
        $probe = new PDO(db_dsn($creds), (string)($creds['DB_USER'] ?? ''), (string)($creds['DB_PASS'] ?? ''), [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_TIMEOUT => 5,
        ]);
        $probe->query('SELECT 1');
        $probe = null;
        return ['ok' => true, 'error' => ''];
    } catch (PDOException $e) {
        // the driver message names the host and user but never the password
        return ['ok' => false, 'error' => $e->getMessage()];
    }
}

function db(): PDO
{
    static $pdo = null;
    if ($pdo instanceof PDO) {
        return $pdo;
    }
    $dsn = db_dsn();
    try {
        $pdo = new PDO($dsn, db_conf('DB_USER'), db_conf('DB_PASS'), [
            // prepared statements are real, not emulated, so parameters can
            // never be interpolated into the SQL text
            PDO::ATTR_EMULATE_PREPARES   => false,
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
        // every DATETIME in this schema is UTC
        $pdo->exec("SET time_zone = '+00:00'");
    } catch (PDOException $e) {
        // A connection failure on a fresh upload almost always means the
        // database details in includes/config.php have not been filled in,
        // or the database/user has not been created yet. Say so, instead of
        // a bare "Service unavailable" that gives no clue what to fix.
        http_response_code(503);
        header('Retry-After: 120');
        if (DEBUG) {
            exit('DB connection failed: ' . $e->getMessage());
        }
        exit('Service temporarily unavailable: the database could not be '
           . 'reached. If you are the site owner, open includes/config.php '
           . 'and enter your MySQL database name, user and password, then '
           . 'run the installer in the /install/ folder. Delete /install '
           . 'once setup is finished.');
    }

    // v7: bring the schema up to date the first time a connection is made,
    // so EVERY entry point (public pages, admin, API, webhooks) upgrades an
    // older database before it reads it - not only files that include
    // bootstrap.php. The connection is stored above first, so the queries
    // migrate_if_needed() runs re-enter db() without recursing, and the work
    // is skipped on an empty database (the installer builds that from zero).
    static $autoMigrated = false;
    if (!$autoMigrated && !defined('MVL_NO_AUTO_MIGRATE') && cfg('AUTO_MIGRATE', true)) {
        $autoMigrated = true;
        require_once __DIR__ . '/migrate.php';
        if (table_exists('licenses', true)) {
            migrate_if_needed();
        }
    }

    return $pdo;
}
