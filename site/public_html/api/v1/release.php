<?php
/** POST /api/v1/release  {serial, device_hash} - free this computer's slot on the licence. */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/license.php';
require_once __DIR__ . '/../../includes/ratelimit.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$in     = json_in();
$serial = normalise_serial((string)($in['serial'] ?? ''));
$device = clean_hex($in['device_hash'] ?? '');

if (!rate_ok('release', $serial, 5, 86400)) {
    json_out(['ok' => false, 'error' => 'Too many device changes today.'], 429);
}

$st = db()->prepare('SELECT * FROM licenses WHERE serial = ?');
$st->execute([$serial]);
$lic = $st->fetch();
$bound = $lic && ($device !== '') && (license_device_active((int)$lic['id'], $device)
    || hash_equals((string)$lic['device_hash'], $device));
if (!$bound) {
    json_out(['ok' => false, 'error' => 'Serial and device do not match.'], 403);
}
if ((int)$lic['device_resets'] >= DEVICE_RESET_MAX) {
    json_out(['ok' => false, 'error' => 'Device change limit reached. Contact support.'], 403);
}

license_release_device((int)$lic['id'], $device, 'released');
db()->prepare('UPDATE licenses SET device_resets = device_resets + 1, updated_at = ? WHERE id = ?')
    ->execute([now(), $lic['id']]);
audit('device.released', (string)($lic['device_label'] ?? ''), (int)$lic['id']);

json_out(['ok' => true, 'message' => 'This computer was released. You can now activate the licence on another computer.',
          'resets_left' => DEVICE_RESET_MAX - (int)$lic['device_resets'] - 1,
          'devices_used' => license_device_count((int)$lic['id']), 'max_devices' => (int)$lic['max_devices']]);
