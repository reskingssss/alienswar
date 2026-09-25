<?php
/**
 * POST /api/v1/checkout.php {plan, email, name, coupon, method}
 * Header: X-CSRF-Token (from the checkout page session)
 * Creates the order with a server-calculated total. For PayPal it also
 * creates the PayPal order and returns its id to the PayPal buttons.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/orders.php';
require_once __DIR__ . '/../../includes/ratelimit.php';
require_once __DIR__ . '/../../includes/csrf.php';
public_session_start();

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$in = json_in();
if (!csrf_valid((string)($_SERVER['HTTP_X_CSRF_TOKEN'] ?? ($in['csrf'] ?? '')))) {
    json_out(['ok' => false, 'error' => 'Your session expired. Reload the page and try again.'], 419);
}
if (!rate_ok('checkout_ip', client_ip(), 20, 3600)) {
    json_out(['ok' => false, 'error' => 'Too many checkout attempts. Try again later.'], 429);
}
$method = (string)($in['method'] ?? '');
$methods = checkout_methods();
if (!isset($methods[$method])) {
    json_out(['ok' => false, 'error' => 'That payment method is not available.'], 400);
}
$made = order_create((string)($in['plan'] ?? ''), (string)($in['email'] ?? ''), (string)($in['name'] ?? ''),
    (string)($in['coupon'] ?? ''), $method === 'paypal' ? 'paypal' : ($method === 'crypto' ? 'crypto' : 'manual'));
if (!$made['ok']) {
    json_out(['ok' => false, 'field' => $made['field'] ?? null, 'error' => $made['error']], 422);
}
$order = $made['order'];
// v6.3 REFERRAL: stamp the order with the code this visitor arrived on.
// order_create() above is untouched; this is a separate, additive step, and
// a failure here must not stop a sale. Self-referral is rejected inside.
try {
    referral_attach_to_order((int)$order['id'], (string)($in['ref'] ?? ''));
    $order = order_by_id((int)$order['id']) ?: $order;
} catch (Throwable $e) {
    error_log('[mavelylink] referral_attach_to_order: ' . $e->getMessage());
}
$_SESSION['orders'][$order['ref']] = $order['access_token'];
$urls = order_urls($order);

if ($method === 'paypal') {
    $pp = paypal_create_order($order);
    if (!$pp['ok']) {
        order_update((int)$order['id'], ['status' => 'failed', 'failure_reason' => 'PayPal order could not be created']);
        json_out(['ok' => false, 'error' => $pp['error'], 'redirect' => $urls['failed']], 502);
    }
    json_out(['ok' => true, 'ref' => $order['ref'], 't' => $order['access_token'], 'paypal_order_id' => $pp['id']]);
}
if ($method === 'crypto') {
    $inv = crypto_create_invoice($order);
    if (!$inv['ok']) {
        order_update((int)$order['id'], ['status' => 'failed', 'failure_reason' => 'Crypto invoice could not be created']);
        json_out(['ok' => false, 'error' => $inv['error'], 'redirect' => $urls['failed']], 502);
    }
    json_out(['ok' => true, 'ref' => $order['ref'], 'redirect' => $inv['url']]);
}
// manual methods: show the instructions and the reference form
json_out(['ok' => true, 'ref' => $order['ref'], 'redirect' => $urls['status'] . '&m=' . rawurlencode($method)]);
