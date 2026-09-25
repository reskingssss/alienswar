<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
// v7: logging out is a POST with a CSRF token, so another site cannot sign
// an admin out. A plain GET (old bookmark) still works but asks first.
session_start_hardened();
if (($_SERVER['REQUEST_METHOD'] ?? '') === 'POST') {
    csrf_check();
    admin_logout();
    header('Location: login.php?out=1');
    exit;
}
?><!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Log out</title><link rel="stylesheet" href="../assets/css/admin.css?v=7"></head>
<body class="login-page"><form method="post" class="card login">
<h1>Log out?</h1><?= csrf_field() ?>
<button class="btn btn-primary" type="submit">Log out</button>
<a class="btn btn-ghost" href="index.php">Stay signed in</a>
</form></body></html>
