<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
session_start_hardened();

$error = '';
if (($_SERVER['REQUEST_METHOD'] ?? '') === 'POST') {
    csrf_check();
    $u = trim((string)($_POST['username'] ?? ''));
    $p = (string)($_POST['password'] ?? '');
    if (admin_login($u, $p)) {
        header('Location: index.php');
        exit;
    }
    // one message for every failure mode: no hints about which part was wrong
    $error = 'Login failed. Check your username and password and try again. '
           . 'After 5 failed attempts, sign-in pauses for 15 minutes.';
    sleep(1);
}
?><!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Admin sign in · <?= e(SITE_NAME) ?></title><meta name="color-scheme" content="light dark"><link rel="stylesheet" href="../assets/css/admin.css?v=8"><script src="../assets/js/theme.js?v=8"></script>
</head><body class="login-page">
<form method="post" class="card login" novalidate>
  <div class="side-brand login-brand"><span class="brand-mark" aria-hidden="true"></span><?= e(SITE_NAME) ?> <span>Admin</span></div>
  <h1>Sign in</h1>
  <?php if ($error): ?><div class="alert alert-bad" role="alert"><?= e($error) ?></div><?php endif; ?>
  <?php if (!empty($_GET['expired'])): ?><div class="alert alert-warn" role="status">Your session ended. Sign in again.</div><?php endif; ?>
  <?php if (!empty($_GET['out'])): ?><div class="alert alert-good" role="status">You are signed out.</div><?php endif; ?>
  <?= csrf_field() ?>
  <label class="field">Username<input name="username" autocomplete="username" required autofocus></label>
  <label class="field">Password<input type="password" name="password" autocomplete="current-password" required></label>
  <button class="btn btn-primary btn-block" type="submit">Sign in</button>
</form>
</body></html>
