<?php
/**
 * POST /api/v1/tabs.php   {device_hash, app_version, token?}
 *
 * The tab bar the desktop tool should draw. Metadata only — title, order,
 * required plan and a `locked` flag. The Python module itself is NEVER in
 * this answer, not even for an entitled installation; that needs a second
 * call to tab_script.php.
 *
 * EVERY enabled tab is listed for EVERY plan, Free included. The brief is
 * explicit that the tab is always visible and that gating changes the
 * CONTENT, not the presence, so a Free user can see that a Pro feature
 * exists and what it is called.
 *
 * Authentication reuses exactly what the rest of the API already uses: the
 * signed licence token when there is one, and the device hash the check-in
 * already sends when there is not. No second auth system.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/tabs.php';
require_once __DIR__ . '/../../includes/ratelimit.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$in = json_in();
$device  = clean_hex($in['device_hash'] ?? '');
$version = mb_substr(trim((string)($in['app_version'] ?? '')), 0, 32);

$token = '';
$hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
if (preg_match('/^Bearer\s+(\S+)$/i', $hdr, $m)) {
    $token = $m[1];
} elseif (!empty($in['token']) && is_string($in['token'])) {
    $token = $in['token'];   // some hosts strip the Authorization header
}

if (strlen($device) !== 64) {
    json_out(['ok' => false, 'error' => 'A valid device id is required.'], 400);
}
if (!rate_ok('tabs_ip', client_ip(), 600, 3600) || !rate_ok('tabs_dev', $device, 120, 3600)) {
    json_out(['ok' => false, 'error' => 'Too many requests.'], 429);
}
if (!application_enabled()) {
    json_out(['ok' => false, 'state' => 'disabled', 'error' => app_disabled_message()], 503);
}

// ---- resolve the plan from the database, never from the client --------
// No token, a token that will not verify, a licence that is not active, or
// a device that is not bound to it: all mean Free. A tab is never unlocked
// by accident.
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

$tabs = tabs_manifest($plan, $version);

// A signed manifest, so a fake server cannot invent tabs, rename the real
// ones, or flip a `locked` flag on the way to the tool.
$compact = array_map(
    static fn($t) => [$t['slug'], $t['version'], $t['locked'] ? 1 : 0, $t['order']],
    $tabs
);

json_out([
    'ok'       => true,
    'plan'     => $plan,
    'enabled'  => tabs_enabled(),
    'tabs'     => $tabs,
    'canvas'   => [
        'width'      => TAB_CANVAS_W,
        'height'     => TAB_CANVAS_H,
        'min_width'  => TAB_CANVAS_MIN_W,
        'min_height' => TAB_CANVAS_MIN_H,
    ],
    'manifest_token' => sign_control([
        'typ'  => 'tabs',
        'sub'  => $device,
        'plan' => $plan,
        'tabs' => $compact,
    ], (int)GRACE_DAYS * 86400),
]);
