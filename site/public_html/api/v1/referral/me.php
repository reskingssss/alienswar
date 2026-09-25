<?php
/**
 * GET  /api/v1/referral/me.php      Authorization: Bearer <licence token>
 * POST /api/v1/referral/me.php      {device_hash, token?}
 *
 * Returns:
 *   {ok, identified, referral_code, referral_link, confirmed_count,
 *    threshold, remaining, new_unseen_count, reward_status,
 *    reward_popup_pending, cash_amount, terms_url}
 *
 * Authentication uses ONLY what already exists (spec section 5): the
 * Ed25519 licence token the tool already holds, or the device hash the
 * check-in already sends. No new auth system.
 *
 * A Free installation that has never given an email is not an error - it
 * comes back identified=false with register_url, which is what makes the
 * Invite tab show "enter your email" instead of a broken link (spec 2.2).
 */
declare(strict_types=1);
require_once __DIR__ . '/../../../includes/referral.php';
require_once __DIR__ . '/../../../includes/ratelimit.php';

$in = ($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST' ? json_in() : [];

$token = '';
$hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
if (preg_match('/^Bearer\s+(\S+)$/i', $hdr, $m)) {
    $token = $m[1];
} elseif (!empty($in['token']) && is_string($in['token'])) {
    $token = $in['token'];      // some hosts strip the Authorization header
}
$device = clean_hex($in['device_hash'] ?? ($_GET['device_hash'] ?? ''));

if ($token === '' && strlen($device) !== 64) {
    json_out(['ok' => false, 'error' => 'A licence token or a device id is required.'], 401);
}
if (!rate_ok('ref_me_ip', client_ip(), 600, 600)
    || ($device !== '' && !rate_ok('ref_me_dev', $device, 60, 600))) {
    json_out(['ok' => false, 'error' => 'Too many requests.', 'retry_after' => 300], 429);
}
if (!application_enabled()) {
    json_out(['ok' => false, 'state' => 'disabled', 'error' => app_disabled_message()], 503);
}
if (!referral_enabled()) {
    json_out(['ok' => true, 'identified' => false, 'enabled' => false,
              'message' => 'The referral programme is not running at the moment.']);
}

$customer = referral_identify($token, $device);
if (!$customer) {
    json_out([
        'ok'           => true,
        'identified'   => false,
        'enabled'      => true,
        'register_url' => site_url('api/v1/referral/register.php'),
        'signup_url'   => site_url('pricing.php'),
        'threshold'    => referral_threshold(),
        'cash_amount'  => referral_cash_amount(),
        'terms_url'    => referral_terms_url(),
        'message'      => 'Add your email address to get your personal invite link.',
    ]);
}

json_out(['identified' => true] + referral_state($customer));
