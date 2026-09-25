<?php
declare(strict_types=1);
require_once __DIR__ . '/helpers.php';
require_once __DIR__ . '/ratelimit.php';

function session_start_hardened(): void
{
    if (session_status() === PHP_SESSION_ACTIVE) {
        return;
    }
    $https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
        || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
    session_set_cookie_params([
        'lifetime' => 0,
        'path'     => '/',
        'httponly' => true,      // JavaScript cannot read the session cookie
        'secure'   => $https,    // never sent over plain http
        'samesite' => 'Strict',  // blocks cross-site submission of the cookie
    ]);
    session_name('MVLADMIN');
    session_start();
}

function admin_login(string $username, string $password): bool
{
    // Two buckets slow a single attacker and a distributed one. Only FAILED
    // attempts are counted, so an administrator signing in from several
    // browsers is never locked out by their own successful logins.
    $userKey = strtolower($username);
    if (rate_count('login_ip', client_ip(), 900) >= 10
        || rate_count('login_user', $userKey, 900) >= 5) {
        audit('admin.login.ratelimited', $username);
        return false;
    }

    $st = db()->prepare('SELECT * FROM admins WHERE username = ?');
    $st->execute([$username]);
    $row = $st->fetch();

    // run a hash either way so a missing user and a wrong password take
    // the same time and cannot be told apart
    $hash = $row['password_hash'] ?? '$2y$12$invalidinvalidinvalidinvalidinvalidinvalidinvalidinvalidin';
    if (!password_verify($password, $hash) || !$row) {
        rate_hit('login_ip', client_ip(), 900);
        rate_hit('login_user', $userKey, 900);
        audit('admin.login.failed', $username);
        return false;
    }

    if (password_needs_rehash($hash, PASSWORD_DEFAULT)) {
        db()->prepare('UPDATE admins SET password_hash = ? WHERE id = ?')
            ->execute([password_hash($password, PASSWORD_DEFAULT), $row['id']]);
    }

    session_regenerate_id(true);           // stops session fixation
    $_SESSION['admin_id']   = (int)$row['id'];
    $_SESSION['admin_user'] = $row['username'];
    $_SESSION['admin_ua']   = hash('sha256', $_SERVER['HTTP_USER_AGENT'] ?? '');
    $_SESSION['last_seen']  = time();
    // v6.2.1: remember which "generation" of the account this session belongs
    // to. Changing the password or username bumps the stored counter, which
    // logs every OTHER browser out at its next request.
    $_SESSION['admin_epoch'] = admin_session_epoch((int)$row['id']);

    db()->prepare('UPDATE admins SET last_login = ? WHERE id = ?')->execute([now(), $row['id']]);
    audit('admin.login.ok', $username);
    return true;
}

function require_admin(): void
{
    session_start_hardened();

    $ok = !empty($_SESSION['admin_id'])
        && hash_equals($_SESSION['admin_ua'] ?? '', hash('sha256', $_SERVER['HTTP_USER_AGENT'] ?? ''));

    // 2 hours idle and the session is gone
    if ($ok && (time() - (int)($_SESSION['last_seen'] ?? 0)) > 7200) {
        $ok = false;
    }

    // v6.2.1: a password or username change elsewhere ends this session.
    // Sessions created before the upgrade have no stored epoch; they are
    // accepted while the account is still at epoch 0, so nobody is thrown
    // out merely by installing this version.
    if ($ok) {
        $current = admin_session_epoch((int)$_SESSION['admin_id']);
        if ($current !== (int)($_SESSION['admin_epoch'] ?? 0)) {
            $ok = false;
        }
    }
    if (!$ok) {
        session_unset();
        session_destroy();
        header('Location: login.php?expired=1');
        exit;
    }
    $_SESSION['last_seen'] = time();
}

function admin_logout(): void
{
    session_start_hardened();
    audit('admin.logout', $_SESSION['admin_user'] ?? '');
    session_unset();
    session_destroy();
}

/** v6.2: the signed-in admin's username, for audit entries and notes. */
function admin_actor(): string
{
    return (string)($_SESSION['admin_user'] ?? 'admin');
}

/** v6.2: CSRF + method guard shared by every admin POST handler. */
function admin_post(): bool
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
        return false;
    }
    require_once __DIR__ . '/csrf.php';
    csrf_check();
    return true;
}

// ---------------------------------------------------------------------
// v6.2.1: self-service admin account management (Settings -> Admin account)
//
// All additive. admin_login() and require_admin() keep their signatures and
// their original behaviour; they only gained the session-epoch check above.
// ---------------------------------------------------------------------

/**
 * The account's session generation. Bumped whenever the credentials change.
 * Returns 0 when the column does not exist yet (database not migrated), so
 * every existing session keeps working until the migration is applied.
 */
function admin_session_epoch(int $adminId): int
{
    static $cache = [];
    if (array_key_exists($adminId, $cache)) {
        return $cache[$adminId];
    }
    try {
        $st = db()->prepare('SELECT session_epoch FROM admins WHERE id = ?');
        $st->execute([$adminId]);
        $cache[$adminId] = (int)($st->fetchColumn() ?: 0);
    } catch (PDOException $e) {
        // column not added yet: behave exactly as the previous version did
        $cache[$adminId] = 0;
    }
    return $cache[$adminId];
}

/** Invalidate every session for this admin except the one calling us. */
function admin_bump_session_epoch(int $adminId): int
{
    try {
        db()->prepare('UPDATE admins SET session_epoch = COALESCE(session_epoch, 0) + 1 WHERE id = ?')
            ->execute([$adminId]);
    } catch (PDOException $e) {
        error_log('[mavelylink] session_epoch not available: ' . $e->getMessage());
        return 0;
    }
    $st = db()->prepare('SELECT session_epoch FROM admins WHERE id = ?');
    $st->execute([$adminId]);
    $epoch = (int)($st->fetchColumn() ?: 0);
    // keep THIS browser signed in
    if (session_status() === PHP_SESSION_ACTIVE && (int)($_SESSION['admin_id'] ?? 0) === $adminId) {
        $_SESSION['admin_epoch'] = $epoch;
    }
    return $epoch;
}

/** Shared password policy. Returns '' when acceptable, else the reason. */
function admin_password_problem(string $password): string
{
    if (strlen($password) < 12) {
        return 'Use at least 12 characters.';
    }
    if (preg_match('/^\s|\s$/', $password)) {
        return 'Remove the leading or trailing space.';
    }
    if (strlen($password) > 200) {
        return 'That password is too long (200 characters maximum).';
    }
    return '';
}

/**
 * Change the signed-in administrator's password.
 * Requires the current password, hashes with PASSWORD_DEFAULT (bcrypt today,
 * whatever PHP considers best tomorrow), and signs other browsers out.
 */
function admin_change_password(int $adminId, string $current, string $new, string $confirm = ''): array
{
    $st = db()->prepare('SELECT * FROM admins WHERE id = ?');
    $st->execute([$adminId]);
    $row = $st->fetch();
    if (!$row) {
        return ['ok' => false, 'error' => 'That administrator account no longer exists.'];
    }
    if (!password_verify($current, (string)$row['password_hash'])) {
        audit('admin.password.failed', (string)$row['username']);
        return ['ok' => false, 'error' => 'The current password is not correct.'];
    }
    if ($confirm !== '' && $new !== $confirm) {
        return ['ok' => false, 'error' => 'The two new passwords do not match.'];
    }
    $problem = admin_password_problem($new);
    if ($problem !== '') {
        return ['ok' => false, 'error' => $problem];
    }
    if (password_verify($new, (string)$row['password_hash'])) {
        return ['ok' => false, 'error' => 'That is already your password. Choose a different one.'];
    }

    db()->prepare('UPDATE admins SET password_hash = ? WHERE id = ?')
        ->execute([password_hash($new, PASSWORD_DEFAULT), $adminId]);
    try {
        db()->prepare('UPDATE admins SET password_changed_at = ? WHERE id = ?')->execute([now(), $adminId]);
    } catch (PDOException $e) {
        // optional column; the change itself has already been stored
    }
    admin_bump_session_epoch($adminId);
    session_regenerate_id(true);
    audit('admin.password.changed', (string)$row['username']);
    return ['ok' => true, 'error' => ''];
}

/** Change the signed-in administrator's username. Requires the password. */
function admin_change_username(int $adminId, string $current, string $newUsername): array
{
    $newUsername = trim($newUsername);
    $st = db()->prepare('SELECT * FROM admins WHERE id = ?');
    $st->execute([$adminId]);
    $row = $st->fetch();
    if (!$row) {
        return ['ok' => false, 'error' => 'That administrator account no longer exists.'];
    }
    if (!password_verify($current, (string)$row['password_hash'])) {
        audit('admin.username.failed', (string)$row['username']);
        return ['ok' => false, 'error' => 'The current password is not correct.'];
    }
    if (!preg_match('/^[A-Za-z0-9._-]{3,64}$/', $newUsername)) {
        return ['ok' => false, 'error' => 'Use 3 to 64 characters: letters, digits, dot, dash or underscore.'];
    }
    if (strcasecmp($newUsername, (string)$row['username']) === 0) {
        return ['ok' => false, 'error' => 'That is already your username.'];
    }
    $taken = db()->prepare('SELECT 1 FROM admins WHERE username = ? AND id <> ?');
    $taken->execute([$newUsername, $adminId]);
    if ($taken->fetch()) {
        return ['ok' => false, 'error' => 'Another administrator already uses that username.'];
    }

    $was = (string)$row['username'];
    db()->prepare('UPDATE admins SET username = ? WHERE id = ?')->execute([$newUsername, $adminId]);
    admin_bump_session_epoch($adminId);
    if (session_status() === PHP_SESSION_ACTIVE && (int)($_SESSION['admin_id'] ?? 0) === $adminId) {
        $_SESSION['admin_user'] = $newUsername;
    }
    audit('admin.username.changed', $was . ' -> ' . $newUsername);
    return ['ok' => true, 'error' => ''];
}
