<?php
/**
 * POST /api/v1/referral/popup-seen.php  {device_hash, token?, reward?: bool}
 *
 * The tool calls this after the user dismisses a referral popup. Every
 * confirmed referral for this referrer is marked seen, so popup 1 does not
 * come back on the next launch (spec 2.5). Passing reward=true also stamps
 * popup 2 as shown (spec 2.6).
 *
 * Same authentication as me.php: an existing licence token, or the device
 * hash the check-in already reports.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../../includes/referral.php';
require_once __DIR__ . '/../../../includes/ratelimit.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$in = json_in();

$token = '';
$hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
if (preg_match('/^Bearer\s+(\S+)$/i', $hdr, $m)) {
    $token = $m[1];
} elseif (!empty($in['token']) && is_string($in['token'])) {
    $token = $in['token'];
}
$device = clean_hex($in['device_hash'] ?? '');

if ($token === '' && strlen($device) !== 64) {
    json_out(['ok' => false, 'error' => 'A licence token or a device id is required.'], 401);
}
if (!rate_ok('ref_seen_ip', client_ip(), 300, 600)) {
    json_out(['ok' => false, 'error' => 'Too many requests.'], 429);
}

$customer = referral_identify($token, $device);
if (!$customer) {
    // nothing to mark; still a success so the tool never shows an error for it
    json_out(['ok' => true, 'identified' => false]);
}

referral_mark_seen((int)$customer['id'], !empty($in['reward']));
$customer = customer_by_id((int)$customer['id']);

json_out(['identified' => true] + referral_state($customer));
