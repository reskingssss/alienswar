<?php
/**
 * POST /api/v1/feature.php   {id, device_hash, token?}
 *
 * The server half of a split feature. Returns the rules the tool needs to
 * render it. Authenticated with the mechanisms that already exist - the
 * signed licence token, or the device hash the check-in already sends.
 *
 * An installation that is not entitled gets nothing: no partial data, no
 * hint about what it is missing.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/features.php';
require_once __DIR__ . '/../../includes/ratelimit.php';

$in = ($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST' ? json_in() : $_GET;

$id = preg_replace('/[^a-z0-9_]/', '', strtolower((string)($in['id'] ?? '')));
$device = clean_hex($in['device_hash'] ?? '');

$token = '';
$hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
if (preg_match('/^Bearer\s+(\S+)$/i', $hdr, $m)) {
    $token = $m[1];
} elseif (!empty($in['token']) && is_string($in['token'])) {
    $token = $in['token'];
}

if ($id === '' || strlen($device) !== 64) {
    json_out(['ok' => false, 'error' => 'A feature id and a device id are required.'], 400);
}
if (!rate_ok('feature_ip', client_ip(), 300, 3600)
    || !rate_ok('feature_dev', $device, 120, 3600)) {
    json_out(['ok' => false, 'error' => 'Too many requests.'], 429);
}
if (!application_enabled()) {
    json_out(['ok' => false, 'state' => 'disabled', 'error' => app_disabled_message()], 503);
}

// ---- resolve the plan from the signed licence token -------------------
// No token, or one that will not verify, means Free. Features are never
// unlocked by accident.
$plan = 'free';
if ($token !== '') {
    $claims = verify_token($token, (int)cfg('TOKEN_RENEW_GRACE_DAYS', 45) * 86400);
    if ($claims) {
        $lic = license_by_id((int)($claims['sub'] ?? 0));
        if ($lic) {
            $state = effective_state($lic);
            if ($state['state'] === 'active') {
                $plan = (string)$state['plan'];
            }
        }
    }
}

$feature = feature_for_plan($id, $plan);
if (!$feature) {
    // identical answer whether the feature does not exist or the plan is
    // not entitled to it, so this cannot be used to enumerate features
    json_out(['ok' => false, 'error' => 'Not available for this installation.'], 403);
}

json_out([
    'ok'       => true,
    'id'       => $feature['id'],
    'version'  => $feature['version'],
    'plan'     => $plan,
    'data'     => $feature['data'],
    'manifest' => feature_manifest($plan),
]);
