<?php
/**
 * The check-in every desktop client makes at start-up and every few
 * minutes, with or without a licence. One answer carries: the master
 * switch, the update policy, the licence state (with a renewed signed
 * token), the plan's entitlements and the script manifest.
 */
declare(strict_types=1);
// v6.3.1: activation limits (TASK 2) and channels/theme (TASK 3) ride the
// existing check-in response below.
require_once __DIR__ . '/activation_limit.php';
require_once __DIR__ . '/channels.php';
require_once __DIR__ . '/license.php';

function checkin_evaluate(string $device, string $legacy, string $version, int $profiles,
                          string $token, array $in): array
{
    $appOn = application_enabled();
    $licState = 'none';
    $licMessage = '';
    $lic = null;
    $newToken = '';

    if ($token !== '') {
        $claims = verify_token($token, (int)cfg('TOKEN_RENEW_GRACE_DAYS', 45) * 86400);
        if (!$claims) {
            $licState = 'reauth';
            $licMessage = 'The saved licence session could not be verified.';
        } elseif (!hash_equals((string)($claims['device'] ?? ''), $device)) {
            $licState = 'reauth';
            $licMessage = 'The saved licence belongs to a different computer.';
        } else {
            $lic = license_by_id((int)$claims['sub']);
            if (!$lic) {
                $licState = 'revoked';
                $licMessage = 'This licence no longer exists. The app continues on the Free plan.';
            } else {
                $state = effective_state($lic);
                if ($state['state'] !== 'active') {
                    $licState = $state['state'];
                    $licMessage = $state['message'];
                } elseif (!license_device_active((int)$lic['id'], $device)) {
                    $licState = 'device_removed';
                    $licMessage = 'This computer is no longer registered to the licence. Register it again, or contact support.';
                } else {
                    $licState = 'active';
                    $newToken = sign_token(license_claims($lic, $device));
                    db()->prepare('UPDATE licenses SET last_seen = ?, last_ip = ?, app_version = ?,
                                   profile_count = ?, last_validated_at = ? WHERE id = ?')
                        ->execute([now(), client_ip(), $version, $profiles, now(), $lic['id']]);
                    db()->prepare('UPDATE license_devices SET last_seen = ?, last_ip = ?, app_version = ?
                                   WHERE license_id = ? AND device_hash = ?')
                        ->execute([now(), client_ip(), $version, $lic['id'], $device]);
                }
            }
        }
    }

    $plan = ($licState === 'active' && plan_is_paid((string)$lic['tier'])) ? (string)$lic['tier'] : 'free';
    $ent = plan_entitlements($plan, $lic ? (int)$lic['max_devices'] : null);
    $update = update_info($version);
    $state = !$appOn ? 'disabled' : ($update['mandatory'] ? 'update_required' : 'active');

    installation_touch($device, $plan, $lic ? (int)$lic['id'] : null, $version, $profiles, $state);
    if (!empty($in['errors']) && is_array($in['errors'])) {
        client_errors_store($in['errors'], $device, $lic ? (int)$lic['id'] : null, $version);
    }

    $scripts = $appOn ? scripts_manifest($plan) : [];
    $interval = max(60, min(3600, (int)setting('checkin_seconds', (string)cfg('CHECKIN_SECONDS', 180))));
    $control = sign_control([
        'typ' => 'control',
        'sub' => $device,
        'app_enabled' => $appOn,
        'message' => $appOn ? '' : app_disabled_message(),
        'plan' => $plan,
        'license_state' => $licState,
        'update' => $update,
        'scripts' => array_map(static fn($s) => [$s['slug'], $s['version'], $s['sha256']], $scripts),
        'next' => $interval,
    ], max(3600, (int)GRACE_DAYS * 86400));

    return array_merge(update_block_fields($version), [
        'ok' => true,
        'protocol' => 2,
        'server_time' => time(),
        'next_checkin_seconds' => $interval,
        'enabled' => $appOn,
        'state' => $state,
        'message' => $appOn ? '' : app_disabled_message(),
        'plan' => $plan,
        'plan_name' => plan_name($plan),
        'entitlements' => $ent,
        'license_state' => $licState,
        'license_message' => $licMessage,
        'license' => $lic ? license_public($lic) : null,
        'token' => $newToken,
        'update' => $update,
        'scripts' => $scripts,
        'control' => $control,
        // v6.3.1 (TASK 2): the attempt/lockout state, so the tool's UI is
        // correct after a restart and the SERVER value always wins.
        'activation' => function_exists('activation_state')
            ? activation_state($device) : null,
        // v6.3.1 (TASK 3): social channels and theme defaults ride the
        // EXISTING check-in - no new polling mechanism. Both are inside the
        // signed payload, so they cannot be tampered with in transit.
        'channels' => function_exists('channels_for_client') ? channels_for_client('tool') : [],
        'theme' => function_exists('theme_defaults') ? theme_defaults() : null,
        'pricing_url' => site_url('pricing.php?ref=app'),
        'buy_url' => site_url('buy.php?plan=pro&ref=app'),
        'team_url' => site_url('buy.php?plan=team&ref=app'),
    ]);
}
