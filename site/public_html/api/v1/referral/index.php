<?php
/**
 * RESCUE ROUTE — v6.3.1
 *
 * Invite links built before the base_url() fix pointed here:
 *     https://mavlink.click/api/v1/referral/?ref=CODE
 *
 * That is a directory with no index file, and .htaccess sets
 * Options -Indexes, so the web server answered 403 Forbidden before PHP was
 * ever reached. Anyone who already copied or shared such a link has a dead
 * link in the wild.
 *
 * This file exists purely so those links keep working. It does not serve the
 * API and it never returns data: it forwards the visitor to the real public
 * landing page, carrying the code, and the normal attribution runs there.
 *
 * Do not delete it. Old links live in chat histories and bookmarks forever.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../../includes/referral.php';

$code = referral_normalise_code($_GET['ref'] ?? '');
$target = referral_public_base() . '/';
if ($code !== '') {
    $target .= '?ref=' . rawurlencode($code);
}
header('Location: ' . $target, true, 302);
header('Cache-Control: no-store');
echo '<!doctype html><meta charset="utf-8">'
   . '<meta http-equiv="refresh" content="0;url=' . htmlspecialchars($target, ENT_QUOTES) . '">'
   . '<title>Redirecting</title>';
exit;
