<?php
/**
 * One-time setup: creates the tables and the first admin account.
 *
 * As soon as this succeeds it writes install/installed.lock and refuses to
 * run again, so the installer cannot be replayed to reset your admin. You
 * should still DELETE the whole install folder afterwards.
 */
declare(strict_types=1);
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/helpers.php';

const INSTALL_LOCK = __DIR__ . '/installed.lock';

/**
 * Split a .sql file into individual statements WITHOUT breaking on a
 * semicolon that sits inside a quoted string or a comment. The previous
 * version split on every ';', which corrupted any seed row whose text
 * contained one (for example a script body with `console.log("x");`) and
 * made the whole install fail with a syntax error - the "Service
 * unavailable / cannot log in" symptom. This tokenises properly instead.
 */
function split_sql(string $sql): array
{
    $stmts = [];
    $buf = '';
    $len = strlen($sql);
    $inSingle = $inDouble = $inBacktick = false;
    $inLineComment = $inBlockComment = false;

    for ($i = 0; $i < $len; $i++) {
        $ch = $sql[$i];
        $next = $i + 1 < $len ? $sql[$i + 1] : '';

        // end of a line comment
        if ($inLineComment) {
            if ($ch === "\n") { $inLineComment = false; $buf .= $ch; }
            continue;
        }
        // end of a block comment
        if ($inBlockComment) {
            if ($ch === '*' && $next === '/') { $inBlockComment = false; $i++; }
            continue;
        }

        if (!$inSingle && !$inDouble && !$inBacktick) {
            // start of a comment (only outside strings)
            if ($ch === '-' && $next === '-') { $inLineComment = true; $i++; continue; }
            if ($ch === '#') { $inLineComment = true; continue; }
            if ($ch === '/' && $next === '*') { $inBlockComment = true; $i++; continue; }
        }

        // quote handling with backslash-escape awareness
        if ($ch === "'" && !$inDouble && !$inBacktick) {
            if ($inSingle) {
                $bs = 0; $j = $i - 1;
                while ($j >= 0 && $sql[$j] === '\\') { $bs++; $j--; }
                if ($bs % 2 === 0) { $inSingle = false; }
            } else {
                $inSingle = true;
            }
        } elseif ($ch === '"' && !$inSingle && !$inBacktick) {
            if ($inDouble) {
                $bs = 0; $j = $i - 1;
                while ($j >= 0 && $sql[$j] === '\\') { $bs++; $j--; }
                if ($bs % 2 === 0) { $inDouble = false; }
            } else {
                $inDouble = true;
            }
        } elseif ($ch === '`' && !$inSingle && !$inDouble) {
            $inBacktick = !$inBacktick;
        }

        // a real statement terminator only outside strings/comments
        if ($ch === ';' && !$inSingle && !$inDouble && !$inBacktick) {
            $s = trim($buf);
            if ($s !== '') { $stmts[] = $s; }
            $buf = '';
            continue;
        }

        $buf .= $ch;
    }

    $s = trim($buf);
    if ($s !== '') { $stmts[] = $s; }
    return $stmts;
}

$done  = [];
$error = '';

// already installed? do not let the form run a second time.
$alreadyInstalled = false;
if (is_file(INSTALL_LOCK)) {
    $alreadyInstalled = true;
} else {
    try {
        $n = (int)db()->query('SELECT COUNT(*) FROM admins')->fetchColumn();
        if ($n > 0) { $alreadyInstalled = true; }
    } catch (Throwable $e) {
        // admins table not created yet -> genuinely a fresh install
    }
}

if (($_SERVER['REQUEST_METHOD'] ?? '') === 'POST' && !$alreadyInstalled) {
    $user  = trim((string)($_POST['username'] ?? ''));
    $pass  = (string)($_POST['password'] ?? '');
    $pass2 = (string)($_POST['password2'] ?? '');

    if (strlen($user) < 3) {
        $error = 'Username must be at least 3 characters.';
    } elseif (strlen($pass) < 12) {
        $error = 'Use a password of at least 12 characters.';
    } elseif ($pass !== $pass2) {
        $error = 'The two passwords do not match.';
    } else {
        try {
            // v7: build the CURRENT schema directly through the migration
            // runner, so a fresh install lands on the latest version (plans,
            // coupons, orders, devices, releases, channels...) instead of only
            // the original tables. schema.sql is kept for reference. On an
            // empty database this creates everything; a backup step is skipped
            // because there is nothing yet to back up.
            require_once __DIR__ . '/../includes/migrate.php';
            $report = run_migrations(false, 'installer');
            $count = count($report['steps'] ?? []);
            $done[] = 'Database created at schema v' . SCHEMA_VERSION
                    . ' (' . $count . ' step' . ($count === 1 ? '' : 's') . ' applied).';

            $st = db()->prepare('SELECT COUNT(*) FROM admins');
            $st->execute();
            if ((int)$st->fetchColumn() > 0) {
                $error = 'An admin already exists. Delete the install folder.';
            } else {
                db()->prepare('INSERT INTO admins (username, password_hash, created_at) VALUES (?,?,?)')
                    ->execute([$user, password_hash($pass, PASSWORD_DEFAULT), now()]);
                $done[] = 'Admin "' . e($user) . '" created.';

                // lock the installer so it cannot be replayed
                @file_put_contents(INSTALL_LOCK, 'installed ' . now() . "\n");
                $done[] = 'Installer locked. NOW DELETE THE install FOLDER, then log in at '
                        . e(site_url('admin/login.php'));
                $alreadyInstalled = true;
            }
        } catch (Throwable $e) {
            $error = 'Setup failed: ' . (DEBUG ? $e->getMessage() : 'check your database settings in includes/config.php.');
        }
    }
}
?><!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Setup</title>
<link rel="stylesheet" href="../assets/css/admin.css"></head>
<body class="login-page"><form method="post" class="card login">
<h1>First-time setup</h1>
<?php if ($error): ?><div class="alert bad"><?= e($error) ?></div><?php endif; ?>
<?php foreach ($done as $d): ?><div class="alert good"><?= $d ?></div><?php endforeach; ?>
<?php if ($alreadyInstalled && !$done): ?>
  <div class="alert warn">This site is already installed. For safety the installer is
    locked. <b>Delete the whole <code>install</code> folder now.</b></div>
<?php elseif (!$done): ?>
<p class="muted">Edit <code>includes/config.php</code> with your database details first,
and run <code>keygen.php</code> to generate your signing keys.</p>
<label>Admin username<input name="username" required></label>
<label>Password (12+ characters)<input type="password" name="password" required></label>
<label>Repeat password<input type="password" name="password2" required></label>
<button class="btn primary">Create tables and admin</button>
<?php endif; ?>
</form></body></html>
