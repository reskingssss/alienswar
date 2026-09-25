<?php
/**
 * POST /api/v1/referral/register.php  {email, device_hash, token?}
 *
 * The one new thing a FREE user has to do: give an email address once, so
 * the referral programme has something durable to hang a code on and
 * somewhere to send the reward licence. This project has no user accounts
 * (includes/auth.php is admin-only), so the email IS the identity - the
 * same one licenses.email and orders.email already use.
 *
 * Nothing here grants anything. It only creates or finds the customer row
 * and ties this installation to it.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../../includes/referral.php';
require_once __DIR__ . '/../../../includes/ratelimit.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$in = json_in();
$email  = customer_normalise_email($in['email'] ?? '');
$device = clean_hex($in['device_hash'] ?? '');

$token = '';
$hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
if (preg_match('/^Bearer\s+(\S+)$/i', $hdr, $m)) {
    $token = $m[1];
} elseif (!empty($in['token']) && is_string($in['token'])) {
    $token = $in['token'];
}

if (!valid_email($email)) {
    json_out(['ok' => false, 'field' => 'email',
              'error' => 'Enter a valid email address. Your invite link and any reward go there.'], 422);
}
if (strlen($device) !== 64) {
    json_out(['ok' => false, 'error' => 'A valid device id is required.'], 400);
}
// deliberately tight: this is the one endpoint that creates rows from
// unauthenticated input
if (!rate_ok('ref_reg_ip', client_ip(), 10, 3600) || !rate_ok('ref_reg_dev', $device, 5, 3600)) {
    json_out(['ok' => false, 'error' => 'Too many attempts. Try again later.'], 429);
}
if (!application_enabled()) {
    json_out(['ok' => false, 'state' => 'disabled', 'error' => app_disabled_message()], 503);
}
if (!referral_enabled()) {
    json_out(['ok' => false, 'error' => 'The referral programme is not running at the moment.'], 503);
}

// A licensed caller may only register the email its licence already uses,
// so a token cannot be used to attach someone else's address.
if ($token !== '') {
    $claims = verify_token($token, (int)cfg('TOKEN_RENEW_GRACE_DAYS', 45) * 86400);
    if ($claims) {
        $lic = license_by_id((int)($claims['sub'] ?? 0));
        if ($lic && customer_normalise_email($lic['email']) !== $email) {
            $email = customer_normalise_email($lic['email']);
        }
    }
}

$customer = customer_get_or_create($email, 'app', $device);
if (!$customer) {
    json_out(['ok' => false, 'error' => 'That email address could not be registered.'], 422);
}
audit('referral.registered', $email . ' from device ' . substr($device, 0, 12));

json_out(['identified' => true] + referral_state($customer));
