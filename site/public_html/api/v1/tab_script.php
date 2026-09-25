<?php
/**
 * POST /api/v1/tab_script.php   {device_hash, slug, app_version, token?, have_version?}
 *
 * Delivers ONE tab module, sealed, to an installation whose plan satisfies
 * the tab's required_plan.
 *
 * THIS IS THE ENFORCEMENT POINT. The plan is read from the database here;
 * nothing the client sends about its own plan is believed. An installation
 * that is not entitled receives HTTP 403 with a `locked` state and no
 * source, no length, no checksum and no hint of what the module does —
 * so the tool's locked state cannot be bypassed by editing the client,
 * because there is nothing cached locally to unlock.
 *
 * `have_version` lets a tool that already holds the current module skip the
 * download: the answer is then 200 with state "current" and no payload.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/tabs.php';
require_once __DIR__ . '/../../includes/ratelimit.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$in = json_in();
$device  = clean_hex($in['device_hash'] ?? '');
$slug    = strtolower(preg_replace('/[^a-z0-9_]/i', '', (string)($in['slug'] ?? '')) ?? '');
$version = mb_substr(trim((string)($in['app_version'] ?? '')), 0, 32);
$have    = max(0, (int)($in['have_version'] ?? 0));

$token = '';
$hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
if (preg_match('/^Bearer\s+(\S+)$/i', $hdr, $m)) {
    $token = $m[1];
} elseif (!empty($in['token']) && is_string($in['token'])) {
    $token = $in['token'];
}

if (strlen($device) !== 64 || $slug === '') {
    json_out(['ok' => false, 'error' => 'A valid device id and tab id are required.'], 400);
}
if (!rate_ok('tabsrc_ip', client_ip(), 2000, 3600) || !rate_ok('tabsrc_dev', $device, 600, 3600)) {
    json_out(['ok' => false, 'error' => 'Too many requests.'], 429);
}
if (!application_enabled()) {
    json_out(['ok' => false, 'state' => 'disabled', 'error' => app_disabled_message()], 503);
}
if (!tabs_enabled()) {
    // the revocation lever: every installation stops loading remote tabs
    json_out(['ok' => false, 'state' => 'off', 'error' => 'Remote tabs are switched off.'], 503);
}
if (!license_signing_ready()) {
    // Refuse rather than ship a module the tool cannot verify. An unsigned
    // payload would be worse than no payload.
    json_out(['ok' => false, 'state' => 'unsigned',
              'error' => 'This server has no licence signing key configured.'], 500);
}

// ---- plan, from the database ------------------------------------------
$plan = 'free';
$serial = '';
$licenseId = null;
if ($token !== '') {
    $claims = verify_token($token, (int)cfg('TOKEN_RENEW_GRACE_DAYS', 45) * 86400);
    if ($claims && hash_equals((string)($claims['device'] ?? ''), $device)) {
        $lic = license_by_id((int)($claims['sub'] ?? 0));
        if ($lic && license_device_active((int)$lic['id'], $device)) {
            $state = effective_state($lic);
            if ($state['state'] === 'active') {
                $plan = (string)$state['plan'];
                $serial = (string)$lic['serial'];
                $licenseId = (int)$lic['id'];
            }
        }
    }
}

$row = tab_by_slug($slug);
if (!$row || (int)$row['enabled'] !== 1) {
    json_out(['ok' => false, 'state' => 'gone', 'error' => 'That tab is not available.'], 404);
}

// ---- the gate ----------------------------------------------------------
if (!tab_plan_satisfies($plan, (string)$row['required_plan'])) {
    audit('tab.denied', $slug . ' plan=' . $plan . ' needs=' . $row['required_plan'], $licenseId);
    json_out([
        'ok'            => false,
        'state'         => 'locked',
        'slug'          => $slug,
        'title'         => (string)$row['title'],
        'required_plan' => (string)$row['required_plan'],
        'error'         => 'This tab needs a higher plan.',
    ], 403);
}

// ---- build gate: an old tool cannot host a newer contract --------------
$minVer = trim((string)($row['min_tool_version'] ?? ''));
if ($minVer !== '' && $version !== '' && version_cmp($version, $minVer) < 0) {
    json_out([
        'ok'    => false,
        'state' => 'update_required',
        'slug'  => $slug,
        'min_tool_version' => $minVer,
        'error' => 'This tab needs version ' . $minVer . ' of the tool or newer.',
    ], 426);
}

if ((string)$row['script'] === '') {
    json_out(['ok' => false, 'state' => 'empty', 'slug' => $slug,
              'error' => 'That tab has no script yet.'], 404);
}

// ---- nothing to send: the tool already holds this exact version --------
if ($have > 0 && $have === (int)$row['version']) {
    json_out(['ok' => true, 'state' => 'current', 'slug' => $slug,
              'version' => (int)$row['version'], 'plan' => $plan]);
}

$payload = tab_seal($row, $device, $serial, $plan);
$payload['ok'] = true;
$payload['state'] = 'ok';
$payload['plan'] = $plan;

audit('tab.delivered', $slug . ' v' . $row['version'] . ' -> ' . $plan, $licenseId);
json_out($payload);
