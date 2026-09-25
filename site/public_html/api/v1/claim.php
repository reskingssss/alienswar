<?php
declare(strict_types=1);
require_once __DIR__ . '/../../includes/orders.php';
require_once __DIR__ . '/../../includes/csrf.php';
require_once __DIR__ . '/../../includes/ratelimit.php';
public_session_start();

// A customer who paid through a manual channel (USDT, WhatsApp, etc.) submits
// their transaction reference here. It records a PENDING payment for the admin
// to verify - it NEVER issues a licence by itself.
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$in = json_in();
if (!csrf_valid((string)($_SERVER['HTTP_X_CSRF_TOKEN'] ?? ($in['csrf'] ?? '')))) {
    json_out(['ok' => false, 'error' => 'Your session expired. Reload the page and try again.'], 419);
}
if (!rate_ok('claim_ip', client_ip(), 20, 3600)) {
    json_out(['ok' => false, 'error' => 'Too many attempts. Try again later.'], 429);
}
$order = order_by_ref((string)($in['ref'] ?? ''));
if (!order_access_ok($order, (string)($in['t'] ?? ''))) {
    json_out(['ok' => false, 'error' => 'Order not found.'], 404);
}
$method = mb_substr(trim((string)($in['method'] ?? 'manual')), 0, 40) ?: 'manual';
$r = order_manual_claim($order, $method, (string)($in['reference'] ?? ''), (string)($in['note'] ?? ''));
json_out($r['ok'] ? ['ok' => true, 'message' => 'Thank you. We will verify your payment and email your licence key.'] : $r, $r['ok'] ? 200 : 422);
