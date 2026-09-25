<?php
/** GET /api/v1/order.php?ref=...&t=... - order status for the waiting page. */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/orders.php';
require_once __DIR__ . '/../../includes/ratelimit.php';

if (!rate_ok('order_ip', client_ip(), 240, 600)) {
    json_out(['ok' => false, 'error' => 'Too many requests.'], 429);
}
$order = order_by_ref(get_str('ref', 24));
if (!order_access_ok($order, get_str('t', 64))) {
    json_out(['ok' => false, 'error' => 'Order not found.'], 404);
}
$lic = $order['license_id'] ? license_by_id((int)$order['license_id']) : null;
json_out([
    'ok' => true, 'ref' => $order['ref'], 'status' => $order['status'],
    'plan' => $order['plan_code'], 'total' => $order['final_amount'], 'currency' => $order['currency'],
    'license_key' => ($order['status'] === 'paid' && $lic) ? $lic['serial'] : null,
    'expires_at' => $lic['expires_at'] ?? null,
]);
