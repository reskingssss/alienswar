<?php
/** POST /api/v1/coupon.php {code, plan, email?} - check a coupon and quote the total. */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/license.php';
require_once __DIR__ . '/../../includes/ratelimit.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
if (!rate_ok('coupon_ip', client_ip(), 30, 600)) {
    json_out(['ok' => false, 'error' => 'Too many attempts. Wait a few minutes and try again.'], 429);
}
$in = json_in();
$q = price_quote((string)($in['plan'] ?? ''), (string)($in['code'] ?? ''), strtolower(trim((string)($in['email'] ?? ''))));
unset($q['coupon']);
json_out($q + ['valid' => $q['ok'] && $q['percent'] > 0]);
