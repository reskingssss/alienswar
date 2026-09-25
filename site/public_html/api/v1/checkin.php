<?php
/**
 * POST /api/v1/checkin.php
 * {device_hash, legacy_device_hash?, app_version, profile_count, token?, errors?}
 *
 * Works WITHOUT a licence, so Free installations also receive the master
 * switch, updates and Script 1. See includes/checkin.php.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/checkin.php';
require_once __DIR__ . '/../../includes/ratelimit.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$in = json_in();
$device = clean_hex($in['device_hash'] ?? '');
$legacy = clean_hex($in['legacy_device_hash'] ?? '');
if (strlen($device) !== 64) {
    json_out(['ok' => false, 'error' => 'A valid device id is required.'], 400);
}
if (!rate_ok('checkin_dev', $device, 40, 600) || !rate_ok('checkin_ip', client_ip(), 1500, 600)) {
    json_out(['ok' => false, 'error' => 'Too many check-ins. Try again in a few minutes.', 'retry_after' => 300], 429);
}
json_out(checkin_evaluate(
    $device,
    strlen($legacy) === 64 ? $legacy : '',
    mb_substr(trim((string)($in['app_version'] ?? '')), 0, 32),
    max(0, min(99999, (int)($in['profile_count'] ?? 0))),
    (string)($in['token'] ?? ''),
    $in
));
