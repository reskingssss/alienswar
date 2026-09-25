<?php
/**
 * Script delivery.
 *  GET  + Authorization: Bearer <token>   (builds before v7, unchanged contract)
 *  POST {device_hash, token?, protocol: 2} (v7: works without a licence too)
 *
 * Script 1 goes to every plan. Script 2 goes only to an active Pro or Team
 * licence on a registered computer - decided here from the database, never
 * from anything the client says. Every answer carries a signed manifest
 * (slug, version, SHA-256) so the app can verify what it downloaded.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/license.php';
require_once __DIR__ . '/../../includes/ratelimit.php';

$isPost = ($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST';
$in = $isPost ? json_in() : [];
$token = '';
$hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
if (preg_match('/^Bearer\s+(\S+)$/i', $hdr, $m)) {
    $token = $m[1];
} elseif (!empty($in['token']) && is_string($in['token'])) {
    $token = $in['token'];   // some hosts strip the Authorization header
}
$device = clean_hex($in['device_hash'] ?? '');
$legacyCall = !$isPost;

if ($token === '' && ($legacyCall || strlen($device) !== 64)) {
    json_out(['ok' => false, 'error' => 'Missing token'], 401);
}
if (!rate_ok('scripts_ip', client_ip(), 300, 600)) {
    json_out(['ok' => false, 'error' => 'Too many requests.'], 429);
}
if (!application_enabled()) {
    json_out(['ok' => false, 'state' => 'disabled', 'error' => app_disabled_message()], 503);
}

$plan = 'free';
if ($token !== '') {
    $claims = verify_token($token, $legacyCall ? 0 : (int)cfg('TOKEN_RENEW_GRACE_DAYS', 45) * 86400);
    $lic = $claims ? license_by_id((int)$claims['sub']) : null;
    $state = $lic ? effective_state($lic) : ['state' => 'revoked', 'message' => 'Unknown licence'];
    if ($legacyCall) {
        if (!$claims) {
            json_out(['ok' => false, 'state' => 'reauth', 'error' => 'Session expired'], 401);
        }
        if (!$lic) {
            json_out(['ok' => false, 'state' => 'revoked', 'error' => 'Unknown licence'], 403);
        }
        if ($state['state'] !== 'active') {
            json_out(['ok' => false, 'state' => $state['state'], 'error' => $state['message']], 403);
        }
        $device = (string)$claims['device'];
        $plan = (string)$lic['tier'];
    } elseif ($claims && $lic && $state['state'] === 'active'
              && hash_equals((string)$claims['device'], $device)
              && license_device_active((int)$lic['id'], $device)) {
        $plan = (string)$lic['tier'];
    }
}

// tier is read from the database, never from the token, so a downgrade
// takes effect immediately rather than when the token expires
$scripts = scripts_manifest($plan, true);
$manifest = array_map(static fn($s) => [$s['slug'], $s['version'], $s['sha256']], $scripts);

json_out([
    'ok'      => true,
    'tier'    => legacy_tier(plan_is_paid($plan) ? $plan : 'free'),
    'plan'    => $plan,
    'scripts' => $scripts,
    'manifest_token' => sign_control(['typ' => 'scripts', 'sub' => $device, 'plan' => $plan,
                                      'scripts' => $manifest], (int)GRACE_DAYS * 86400),
]);
