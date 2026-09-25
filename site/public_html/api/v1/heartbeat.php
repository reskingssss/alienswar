<?php
/**
 * POST /api/v1/heartbeat  {token, device_hash, app_version, profile_count}
 * The licence check used by app builds before v7 (v7 uses checkin.php).
 * Same response shape as before, with the fixes applied:
 *  - a genuine token that expired recently can still be renewed
 *  - a computer removed from the licence is asked to re-activate
 *  - Team licences are reported as 'pro' to builds that only know free/pro
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/license.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}

$in     = json_in();
$claims = verify_token((string)($in['token'] ?? ''), (int)cfg('TOKEN_RENEW_GRACE_DAYS', 45) * 86400);
if (!$claims) {
    json_out(['ok' => false, 'state' => 'reauth', 'error' => 'Session expired, re-activate.'], 401);
}

$device = clean_hex($in['device_hash'] ?? '');
if (!hash_equals((string)$claims['device'], $device)) {
    json_out(['ok' => false, 'state' => 'reauth', 'error' => 'Device mismatch.'], 401);
}

$lic = license_by_id((int)$claims['sub']);
if (!$lic) {
    json_out(['ok' => false, 'state' => 'revoked', 'error' => 'Licence no longer exists.'], 403);
}
if (!license_device_active((int)$lic['id'], $device)) {
    json_out(['ok' => false, 'state' => 'reauth', 'error' => 'This computer is no longer registered to the licence.'], 401);
}

// operational telemetry only: version, count, last seen. Never what the
// user does inside their profiles.
$clientVersion = mb_substr((string)($in['app_version'] ?? ''), 0, 32);
$profiles = max(0, min(9999, (int)($in['profile_count'] ?? 0)));
db()->prepare('UPDATE licenses SET last_seen = ?, last_ip = ?, app_version = ?, profile_count = ?, last_validated_at = ? WHERE id = ?')
    ->execute([now(), client_ip(), $clientVersion, $profiles, now(), $lic['id']]);
db()->prepare('UPDATE license_devices SET last_seen = ?, last_ip = ?, app_version = ? WHERE license_id = ? AND device_hash = ?')
    ->execute([now(), client_ip(), $clientVersion, $lic['id'], $device]);

$control = update_block_fields($clientVersion);
$state = effective_state($lic);
installation_touch($device, $state['state'] === 'active' ? (string)$lic['tier'] : 'free', (int)$lic['id'],
    $clientVersion, $profiles, $control['application_enabled'] ? $state['state'] : 'disabled');

// master switch (one switch; both stored flags are kept in step)
if (!$control['application_enabled']) {
    json_out(array_merge($control, [
        'ok'      => true,
        'enabled' => false,
        'state'   => 'disabled',
        'message' => app_disabled_message(),
    ]));
}

if ($state['state'] !== 'active') {
    json_out(array_merge($control, [
        'ok'       => true,
        'enabled'  => false,
        'state'    => $state['state'],
        'message'  => $state['message'],
        'buy_url'  => site_url('pricing.php?ref=app'),
    ]));
}

$tier = (string)$lic['tier'];
$manifest = array_map(static fn($s) => ['slug' => $s['slug'], 'name' => $s['name'],
    'version' => $s['version'], 'min_tier' => $s['min_tier']], scripts_manifest($tier));

json_out(array_merge($control, [
    'ok'         => true,
    'enabled'    => true,
    'state'      => 'active',
    'tier'       => legacy_tier($tier),
    'plan'       => $tier,
    'expires_at' => $lic['expires_at'],
    'remaining'  => remaining($lic['expires_at']),
    'token'      => sign_token(license_claims($lic, $device)),
    'scripts'    => $manifest,
    'buy_url'    => site_url('pricing.php?ref=app'),
]));
