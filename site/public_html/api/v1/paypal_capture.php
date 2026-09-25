<?php
/** POST /api/v1/paypal_capture.php {ref, t} - the buyer approved in PayPal; capture on the server. */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/orders.php';
require_once __DIR__ . '/../../includes/csrf.php';
require_once __DIR__ . '/../../includes/ratelimit.php';
public_session_start();

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$in = json_in();
if (!csrf_valid((string)($_SERVER['HTTP_X_CSRF_TOKEN'] ?? ($in['csrf'] ?? '')))) {
    json_out(['ok' => false, 'error' => 'Your session expired. Reload the page and try again.'], 419);
}
if (!rate_ok('capture_ip', client_ip(), 30, 3600)) {
    json_out(['ok' => false, 'error' => 'Too many attempts.'], 429);
}
$order = order_by_ref((string)($in['ref'] ?? ''));
if (!order_access_ok($order, (string)($in['t'] ?? ''))) {
    json_out(['ok' => false, 'error' => 'Order not found.'], 404);
}
$urls = order_urls($order);
if ($order['status'] === 'paid') {
    json_out(['ok' => true, 'status' => 'paid', 'redirect' => $urls['status']]);
}
$r = paypal_capture_and_fulfil($order);
json_out([
    'ok' => $r['ok'], 'status' => $r['status'], 'error' => $r['error'] ?? null,
    'redirect' => $r['status'] === 'failed' ? $urls['failed'] : ($r['status'] === 'retry' ? null : $urls['status']),
]);
