<?php
/** POST /api/v1/activate  {serial, device_hash, device_label, app_version, legacy_device_hash?, protocol?} */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/license.php';
require_once __DIR__ . '/../../includes/ratelimit.php';
// v6.3.1 (TASK 2): three rejected keys, then a lockout. Loaded here so the
// rule is enforced server-side, not merely shown in the UI.
require_once __DIR__ . '/../../includes/activation_limit.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}

$in      = json_in();
$serial  = normalise_serial((string)($in['serial'] ?? ''));
$device  = clean_hex($in['device_hash'] ?? '');
$legacy  = clean_hex($in['legacy_device_hash'] ?? '');
$label   = mb_substr(trim((string)($in['device_label'] ?? '')), 0, 120);
$version = mb_substr(trim((string)($in['app_version'] ?? '')), 0, 32);
$modern  = (int)($in['protocol'] ?? 1) >= 2;

if ($serial === '' || strlen($device) !== 64) {
    json_out(['ok' => false, 'error' => 'Serial and device id are required.'], 400);
}
if (!rate_ok('act_ip', client_ip(), 20, 3600) || !rate_ok('act_serial', $serial, 10, 3600)) {
    json_out(['ok' => false, 'error' => 'Too many attempts. Try again later.'], 429);
}
// v6.3.1 (TASK 2): refuse a submission during the lockout window, even a
// hand-crafted one. Checked BEFORE the serial is looked at, so a locked
// installation cannot use this endpoint to probe for valid serials either.
$actLock = activation_state($device);
if ($actLock['locked']) {
    // v6.3.2 (TASK 1.4): identical answer to every other rejection, so a
    // lockout cannot be told apart from a wrong key.
    if (activation_generic_errors()) {
        audit('activate.blocked_by_lockout', 'device ' . substr($device, 0, 12));
        json_out(activation_reject($actLock, 'locked'), 403);
    }
    json_out([
        'ok' => false, 'state' => 'locked',
        'error' => 'Too many failed attempts. You can try again later.',
        'activation' => $actLock,
        'retry_after' => $actLock['retry_after_seconds'],
    ], 429);
}
if (!application_enabled()) {
    json_out(['ok' => false, 'state' => 'disabled', 'error' => app_disabled_message()], 503);
}

/**
 * v6.2.1: fail BEFORE touching any state.
 *
 * Signing happens at the very end of this script, inside the json_out()
 * argument list. Without this guard a server with no keypair still ran
 * license_bind_device() and the UPDATE below, so a failed activation
 * consumed a device seat and stamped activated_at / last_validated_at on a
 * licence the user was told had NOT been activated. Checking first makes
 * the failure clean and repeatable.
 */
if (!license_signing_ready()) {
    audit('activate.no_signing_key', $serial);
    json_out(['ok' => false, 'state' => 'server_misconfigured',
              'error' => 'server signing key not configured'], 500);
}

$st = db()->prepare('SELECT * FROM licenses WHERE serial = ?');
$st->execute([$serial]);
$lic = $st->fetch();

// identical response for unknown and malformed so serials cannot be probed
if (!$lic) {
    audit('activate.unknown', $serial);
    // a rejected key: this one counts (spec 2.2)
    $after = activation_record_failure($device, $serial, 'unknown serial');
    if (activation_generic_errors()) {
        json_out(activation_reject($after, 'unknown'), 403);
    }
    json_out(['ok' => false, 'state' => 'unknown', 'activation' => $after,
              'error' => 'That serial was not recognised. Check it for typos (it looks like MVL-XXXXX-XXXXX-XXXXX-XXXXX).'], 404);
}

$state = effective_state($lic);
if ($state['state'] !== 'active') {
    // also a rejected key from the user's point of view: it counts
    $after = activation_record_failure($device, $serial, 'licence ' . $state['state']);
    if (activation_generic_errors()) {
        json_out(activation_reject($after, $state['state']), 403);
    }
    json_out(['ok' => false, 'state' => $state['state'], 'error' => $state['message'],
              'activation' => $after,
              'fallback_plan' => 'free', 'expires_at' => $lic['expires_at']], 403);
}

// ---- device binding: Pro = 1 computer, Team = up to 3 -----------------
// v6.2.1: binding + stamping + signing are now one atomic unit. If signing
// fails, ed25519_sign_compact() exits and the open transaction is rolled
// back by PDO at shutdown, so the licence is left exactly as it was.
$pdo = db();
$ownTransaction = !$pdo->inTransaction();
if ($ownTransaction) {
    $pdo->beginTransaction();
}

$bind = license_bind_device($lic, $device, $label, $version, strlen($legacy) === 64 ? $legacy : '');
if (!$bind['ok']) {
    if ($ownTransaction && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    audit('activate.device_limit', $label, (int)$lic['id']);
    if (activation_generic_errors()) {
        // deliberately NOT counted as an attempt: this is a valid key that
        // hit a seat limit, not a rejected key (spec 1.3)
        json_out(activation_reject(activation_state($device), 'device_limit'), 403);
    }
    json_out([
        'ok' => false, 'state' => $bind['state'], 'error' => $bind['error'],
        'devices_used' => $bind['used'] ?? null, 'max_devices' => $bind['max'] ?? null,
        'resets_left' => max(0, DEVICE_RESET_MAX - (int)$lic['device_resets']),
    ], 409);
}

$pdo->prepare('UPDATE licenses SET app_version = ?, last_seen = ?, last_ip = ?, last_validated_at = ?, updated_at = ? WHERE id = ?')
    ->execute([$version, now(), client_ip(), now(), now(), $lic['id']]);
$lic = license_by_id((int)$lic['id']);

// signed first, committed second: nothing is persisted unless the client
// will actually receive a token it can verify
$token = sign_token(license_claims($lic, $device));

if ($ownTransaction && $pdo->inTransaction()) {
    $pdo->commit();
}

installation_touch($device, (string)$lic['tier'], (int)$lic['id'], $version, 0, 'active');
// v6.3.1 (TASK 2): a successful registration resets the counter immediately.
// Note the device-limit rejection above deliberately does NOT count: that is
// a VALID key that hit a seat limit, not a rejected key (spec 2.2).
activation_clear($device);

json_out([
    'ok'           => true,
    'token'        => $token,
    // older builds only understand free/pro; Team includes every Pro feature
    'tier'         => $modern ? $lic['tier'] : legacy_tier((string)$lic['tier']),
    'plan'         => $lic['tier'],
    'plan_name'    => plan_name((string)$lic['tier']),
    'expires_at'   => $lic['expires_at'],
    'remaining'    => remaining($lic['expires_at']),
    'license'      => license_public($lic),
    'entitlements' => plan_entitlements((string)$lic['tier'], (int)$lic['max_devices']),
]);
