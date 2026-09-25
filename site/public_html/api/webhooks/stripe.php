<?php
/**
 * Stripe webhook (v8): VISA / Mastercard payments.
 *
 * The Stripe-Signature header (HMAC-SHA256 over "timestamp.body" with the
 * endpoint's signing secret, 5-minute tolerance) is checked before anything
 * in the payload is read. Even then the payload is not trusted for money:
 * the Checkout Session is fetched back from Stripe with the secret key and
 * only that answer can issue a licence (stripe_sync_order).
 *
 * Events to enable in the Stripe dashboard:
 *   checkout.session.completed, checkout.session.async_payment_succeeded,
 *   checkout.session.async_payment_failed, checkout.session.expired,
 *   charge.refunded, charge.dispute.created
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/orders.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    json_out(['ok' => false, 'error' => 'POST only'], 405);
}
$raw = (string)file_get_contents('php://input', false, null, 0, 512 * 1024);
$secret = (string)setting('stripe_webhook_secret', '');
if ($secret === '') {
    audit('stripe.webhook.no_secret');
    json_out(['ok' => false, 'error' => 'not configured'], 503);
}
if (!stripe_signature_ok($raw, (string)($_SERVER['HTTP_STRIPE_SIGNATURE'] ?? ''), $secret)) {
    audit('stripe.webhook.bad_signature', mb_substr((string)($_SERVER['HTTP_STRIPE_SIGNATURE'] ?? ''), 0, 120));
    json_out(['ok' => false, 'error' => 'signature'], 400);
}
$event = json_decode($raw, true);
if (!is_array($event) || !isset($event['type'], $event['data']['object'])) {
    json_out(['ok' => false], 400);
}
$type = (string)$event['type'];
$obj = (array)$event['data']['object'];

/** The order a Stripe object belongs to (session id first, then our reference). */
function stripe_event_order(array $obj): ?array
{
    $sid = (string)($obj['id'] ?? '');
    if (strncmp($sid, 'cs_', 3) === 0 && ($o = order_by_provider_id($sid))) {
        return $o;
    }
    $ref = (string)($obj['client_reference_id'] ?? ($obj['metadata']['order_ref'] ?? ''));
    return $ref !== '' ? order_by_ref($ref) : null;
}

switch ($type) {
    case 'checkout.session.completed':
    case 'checkout.session.async_payment_succeeded':
    case 'checkout.session.expired':
        $order = stripe_event_order($obj);
        if (!$order) {
            audit('stripe.webhook.unknown_order', $type . ' ' . mb_substr((string)($obj['id'] ?? ''), 0, 80));
            break;
        }
        if ((string)$order['provider'] !== 'stripe') {
            break;
        }
        stripe_sync_order($order);      // reads the session back from Stripe
        break;

    case 'checkout.session.async_payment_failed':
        $order = stripe_event_order($obj);
        if ($order && !$order['license_id'] && in_array($order['status'], ORDER_OPEN, true)) {
            order_update((int)$order['id'], ['status' => 'failed', 'failure_reason' => 'The card payment failed.']);
        }
        break;

    case 'charge.refunded':
    case 'charge.dispute.created':
        // a refund or a chargeback: stop what that payment bought
        $pi = (string)($obj['payment_intent'] ?? '');
        if ($type === 'charge.refunded' && empty($obj['refunded'])) {
            break;                      // partial refund: left to the administrator
        }
        if ($pi === '') {
            break;
        }
        $st = db()->prepare("SELECT license_id, order_id FROM payments WHERE provider = 'stripe' AND external_id = ?");
        $st->execute([$pi]);
        $p = $st->fetch() ?: [];
        $licId = (int)($p['license_id'] ?? 0);
        $order = !empty($p['order_id']) ? order_by_id((int)$p['order_id']) : null;
        if ($licId) {
            refund_order_license($order, $licId, $type === 'charge.refunded' ? 'Card refund' : 'Card chargeback');
            if ($order) {
                order_update((int)$order['id'], ['status' => 'refunded']);
                db()->prepare("UPDATE payments SET status = 'refunded', updated_at = ? WHERE order_id = ? AND status = 'completed'")
                    ->execute([now(), $order['id']]);
            }
        }
        break;
}

json_out(['ok' => true]);
