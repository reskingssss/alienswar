<?php
/**
 * Short invite route — v6.3.1
 *
 *     https://mavlink.click/r/CODE      (via the .htaccess rewrite)
 *     https://mavlink.click/r.php?ref=CODE
 *
 * An alias, not the canonical link. The canonical one the server hands the
 * desktop tool is https://host/?ref=CODE, because index.php certainly exists
 * and therefore cannot 403. This route is for pasting into a message, where
 * the short form reads better.
 *
 * Anonymous, GET, no API key, no session. An unknown or disabled code is NOT
 * an error page (spec 1.3): the visitor is sent silently to the homepage with
 * nothing attributed.
 */
declare(strict_types=1);
require_once __DIR__ . '/includes/referral.php';

$code = referral_normalise_code($_GET['ref'] ?? ($_GET['c'] ?? ''));
$base = referral_public_base();
$target = $base . '/';

if ($code !== '' && !in_array($code, REFERRAL_RESERVED, true)) {
    try {
        if (referral_enabled() && customer_by_code($code)) {
            $target = $base . '/?ref=' . rawurlencode($code);
        }
    } catch (Throwable $e) {
        // database unavailable: fall through to the plain homepage
    }
}

header('Location: ' . $target, true, 302);
header('Cache-Control: no-store');
header('Referrer-Policy: no-referrer');
exit;
