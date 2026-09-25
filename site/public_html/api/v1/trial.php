<?php
/** POST /api/v1/trial  {email, device_hash, app_version} -> 7-day free licence */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/license.php';
require_once __DIR__ . '/../../includes/ratelimit.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
if (!setting_bool('trial_enabled', true)) {
    json_out(['ok' => false, 'error' => 'Free trials are not available right now.'], 403);
}

$in     = json_in();
$email  = strtolower(trim((string)($in['email'] ?? '')));
$device = preg_replace('/[^a-f0-9]/i', '', (string)($in['device_hash'] ?? '')) ?? '';

// v6.0: the 7-day trial requires NO email. The device id alone identifies the
// trial (one per machine). If a client still sends an email we keep it for
// support; otherwise we derive a stable per-device address so the NOT NULL
// email column and the one-trial-per-device rule both still hold.
if (strlen($device) !== 64) {
    json_out(['ok' => false, 'error' => 'A valid device id is required.'], 400);
}
if ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
    $email = '';   // ignore a malformed email rather than blocking the trial
}
if ($email === '') {
    $email = 'device-' . substr($device, 0, 16) . '@trial.local';
}
if (!rate_ok('trial_ip', client_ip(), 5, 3600) || !rate_ok('trial_dev', $device, 3, 86400)) {
    json_out(['ok' => false, 'error' => 'Too many attempts. Try again later.'], 429);
}

$result = issue_trial($email, $device);
$lic    = $result['license'];

if ($result['reused']) {
    $state = effective_state($lic);
    json_out([
        'ok'      => false,
        'error'   => $state['state'] === 'active'
            ? 'A licence already exists for this device or email. Use Register serial instead.'
            : 'Your free trial was already used on this device. Buy the Pro version to continue.',
        'serial'  => $lic['serial'],
        'state'   => $state['state'],
    ], 409);
}

json_out([
    'ok'         => true,
    'serial'     => $lic['serial'],
    'tier'       => 'free',
    'expires_at' => $lic['expires_at'],
    'days'       => TRIAL_DAYS,
    'message'    => 'Your ' . TRIAL_DAYS . '-day free trial is active.',
]);
