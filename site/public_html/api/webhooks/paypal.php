<?php
/**
 * PayPal webhook. PayPal retries, so every handler is idempotent on the
 * event id. Nothing here trusts the request body until PayPal itself has
 * confirmed the signature.
 *
 * v7: events are matched to the checkout order (custom_id = order ref).
 * Only a COMPLETED capture whose amount covers the order total issues a
 * licence. "Order approved" is not "paid": it triggers a server capture.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/orders.php';

$raw   = file_get_contents('php://input') ?: '';
$event = json_decode($raw, true);
if (!is_array($event)) {
    json_out(['ok' => false], 400);
}

function paypal_base(): string
{
    $override = (string)cfg('PAYPAL_API_BASE_OVERRIDE', '');
    if ($override !== '') {
        return rtrim($override, '/');
    }
    return setting('paypal_live') === '1'
        ? 'https://api-m.paypal.com'
        : 'https://api-m.sandbox.paypal.com';
}

function paypal_token(): ?string
{
    $ch = curl_init(paypal_base() . '/v1/oauth2/token');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_USERPWD        => setting('paypal_client_id') . ':' . setting('paypal_secret'),
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => 'grant_type=client_credentials',
        CURLOPT_TIMEOUT        => 20,
    ]);
    $res = curl_exec($ch);
    curl_close($ch);
    $data = json_decode((string)$res, true);
    return $data['access_token'] ?? null;
}

/** Ask PayPal whether this really came from PayPal. */
function paypal_verify(array $event, string $raw): bool
{
    $token = paypal_token();
    if (!$token) {
        return false;
    }
    $body = [
        'auth_algo'         => $_SERVER['HTTP_PAYPAL_AUTH_ALGO'] ?? '',
        'cert_url'          => $_SERVER['HTTP_PAYPAL_CERT_URL'] ?? '',
        'transmission_id'   => $_SERVER['HTTP_PAYPAL_TRANSMISSION_ID'] ?? '',
        'transmission_sig'  => $_SERVER['HTTP_PAYPAL_TRANSMISSION_SIG'] ?? '',
        'transmission_time' => $_SERVER['HTTP_PAYPAL_TRANSMISSION_TIME'] ?? '',
        'webhook_id'        => setting('paypal_webhook_id', ''),
        'webhook_event'     => json_decode($raw, true),
    ];
    $ch = curl_init(paypal_base() . '/v1/notifications/verify-webhook-signature');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_HTTPHEADER     => ['Content-Type: application/json', 'Authorization: Bearer ' . $token],
        CURLOPT_POSTFIELDS     => json_encode($body),
        CURLOPT_TIMEOUT        => 20,
    ]);
    $res = curl_exec($ch);
    curl_close($ch);
    $out = json_decode((string)$res, true);
    return ($out['verification_status'] ?? '') === 'SUCCESS';
}

if (!paypal_verify($event, $raw)) {
    audit('paypal.webhook.bad_signature', (string)($event['id'] ?? ''));
    json_out(['ok' => false, 'error' => 'signature'], 400);
}

$eventId = (string)($event['id'] ?? '');
$type    = (string)($event['event_type'] ?? '');
$res     = $event['resource'] ?? [];
if ($eventId === '') {
    json_out(['ok' => false], 400);
}
$email = (string)($res['payer']['email_address']
      ?? $res['subscriber']['email_address']
      ?? ($res['custom_id'] ?? ''));
$amount = (float)($res['amount']['value'] ?? $res['billing_info']['last_payment']['amount']['value'] ?? 0);
$currency = (string)($res['amount']['currency_code'] ?? 'USD');

// idempotency: the unique key makes a replay a no-op. Events are kept in the
// payments table under provider "paypal_event" (hidden from the sales list).
try {
    db()->prepare(
        'INSERT INTO payments (provider, external_id, email, amount, currency, status, raw, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
    )->execute(['paypal_event', $eventId, valid_email($email) ? $email : null, $amount, $currency,
                $type, mb_substr($raw, 0, 60000), now()]);
} catch (PDOException $e) {
    json_out(['ok' => true, 'note' => 'already processed']);   // duplicate delivery
}

$ref = (string)($res['custom_id'] ?? $res['invoice_id'] ?? ($res['purchase_units'][0]['custom_id'] ?? ''));
$order = $ref !== '' ? order_by_ref($ref) : null;
if (!$order) {
    $ppOrder = (string)($res['supplementary_data']['related_ids']['order_id']
        ?? ($type === 'CHECKOUT.ORDER.APPROVED' ? ($res['id'] ?? '') : ''));
    $order = order_by_provider_id($ppOrder);
}

switch ($type) {
    case 'PAYMENT.CAPTURE.COMPLETED':
        if ($order) {
            order_fulfil($order, 'paypal', (string)($res['id'] ?? $eventId), $amount, $currency, $raw, 'paypal');
        } elseif (valid_email($email)) {
            legacy_paid_email_issue('paypal', $email, $eventId, $amount, $currency, $raw);
        }
        break;

    case 'CHECKOUT.ORDER.APPROVED':
        // approved is not paid: capture on the server, the capture decides
        if ($order && in_array($order['status'], ORDER_OPEN, true)) {
            paypal_capture_and_fulfil($order);
        }
        break;

    case 'BILLING.SUBSCRIPTION.ACTIVATED':
        // subscription buttons from the previous version only
        if (valid_email($email)) {
            legacy_paid_email_issue('paypal', $email, $eventId, $amount, $currency, $raw);
        }
        break;

    case 'PAYMENT.CAPTURE.PENDING':
        if ($order && $order['status'] !== 'paid') {
            order_update((int)$order['id'], ['status' => 'approved', 'failure_reason' => 'PayPal is holding the payment for review.']);
        }
        break;

    case 'PAYMENT.CAPTURE.DENIED':
    case 'PAYMENT.CAPTURE.DECLINED':
        if ($order && $order['status'] !== 'paid') {
            order_update((int)$order['id'], ['status' => 'failed', 'failure_reason' => 'PayPal denied the payment.']);
        }
        break;

    case 'PAYMENT.CAPTURE.REVERSED':
    case 'PAYMENT.CAPTURE.REFUNDED':
        // chargeback or refund: stop the licence this payment bought
        $captureId = $type === 'PAYMENT.CAPTURE.REVERSED' ? (string)($res['id'] ?? '') : '';
        foreach (($res['links'] ?? []) as $l) {
            if (($l['rel'] ?? '') === 'up' && preg_match('#/captures/([^/?]+)#', (string)($l['href'] ?? ''), $mm)) {
                $captureId = $mm[1];
            }
        }
        $licId = (int)($order['license_id'] ?? 0);
        if (!$licId && $captureId !== '') {
            $st = db()->prepare("SELECT license_id, order_id FROM payments WHERE provider = 'paypal' AND external_id = ?");
            $st->execute([$captureId]);
            $p = $st->fetch() ?: [];
            $licId = (int)($p['license_id'] ?? 0);
            $order = $order ?: (!empty($p['order_id']) ? order_by_id((int)$p['order_id']) : null);
        }
        if ($licId) {
            refund_order_license($order, $licId, 'PayPal ' . strtolower(substr($type, 16)));
            if ($order) {
                order_update((int)$order['id'], ['status' => 'refunded']);
                db()->prepare("UPDATE payments SET status = 'refunded', updated_at = ? WHERE order_id = ? AND status = 'completed'")
                    ->execute([now(), $order['id']]);
            }
        } elseif (valid_email($email)) {
            // previous-version payments carry no order: limit to PayPal-bought licences
            db()->prepare("UPDATE licenses SET status = 'revoked', revoked_at = ?, updated_at = ?
                            WHERE email = ? AND source = 'paypal'")->execute([now(), now(), $email]);
            audit('paypal.reversed', $email);
        }
        break;
}

json_out(['ok' => true]);
