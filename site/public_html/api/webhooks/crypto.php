<?php
/**
 * USDT / crypto IPN.
 *
 * Supports NOWPayments- and Cryptomus-style callbacks: both sign the raw
 * body with a shared secret. The signature is checked before anything is
 * read out of the payload.
 *
 * v7: callbacks are matched to the checkout order (order_id = order ref),
 * repeated callbacks for one payment update its status instead of being
 * dropped, and the paid amount must cover the order total.
 */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/orders.php';

$raw    = file_get_contents('php://input') ?: '';
$secret = (string)setting('crypto_ipn_secret', '');

if ($secret === '') {
    audit('crypto.webhook.no_secret');
    json_out(['ok' => false, 'error' => 'not configured'], 503);
}

$sigHeader = $_SERVER['HTTP_X_NOWPAYMENTS_SIG']
          ?? $_SERVER['HTTP_SIGN']
          ?? $_SERVER['HTTP_X_SIGNATURE']
          ?? '';

$data = json_decode($raw, true);
if (!is_array($data)) {
    json_out(['ok' => false], 400);
}

/** NOWPayments: HMAC-SHA512 over the key-sorted JSON. */
function sig_nowpayments(array $data, string $secret): string
{
    ksort($data);
    return hash_hmac('sha512', json_encode($data, JSON_UNESCAPED_SLASHES), $secret);
}

/** Cryptomus: md5 of base64(body) + key, with the sign field removed. */
function sig_cryptomus(array $data, string $secret): string
{
    unset($data['sign']);
    return md5(base64_encode(json_encode($data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)) . $secret);
}

$provided = $sigHeader !== '' ? $sigHeader : (string)($data['sign'] ?? '');
$valid = $provided !== '' && (hash_equals(sig_nowpayments($data, $secret), $provided)
      || hash_equals(sig_cryptomus($data, $secret), $provided));

if (!$valid) {
    audit('crypto.webhook.bad_signature', mb_substr($raw, 0, 200));
    json_out(['ok' => false, 'error' => 'signature'], 400);
}

$externalId = (string)($data['payment_id'] ?? $data['uuid'] ?? $data['order_id'] ?? '');
$status     = strtolower((string)($data['payment_status'] ?? $data['status'] ?? ''));
$email      = strtolower(trim((string)($data['order_description'] ?? $data['additional_data'] ?? '')));
$amount     = (float)($data['actually_paid'] ?? $data['amount'] ?? 0);
$currency   = strtoupper((string)($data['pay_currency'] ?? $data['currency'] ?? 'USDT'));

if ($externalId === '') {
    json_out(['ok' => false, 'error' => 'no payment id'], 400);
}

$st = db()->prepare("SELECT status FROM payments WHERE provider = 'crypto' AND external_id = ?");
$st->execute([$externalId]);
if ($st->fetchColumn() === 'completed') {
    json_out(['ok' => true, 'note' => 'already processed']);
}

// only a fully settled payment creates a licence. "confirming" is not paid.
$paid = in_array($status, ['finished', 'confirmed', 'paid', 'paid_over'], true);
$dead = in_array($status, ['failed', 'expired', 'refunded', 'cancel', 'fail', 'system_fail'], true);

$order = order_by_ref((string)($data['order_id'] ?? ''));
if ($order) {
    // the invoice amount in the order's own currency, as the gateway reports it
    $fiat = isset($data['price_amount']) ? (float)$data['price_amount'] : (float)($data['amount'] ?? 0);
    $fiatCurrency = strtoupper((string)(isset($data['price_amount']) ? ($data['price_currency'] ?? 'USD')
                                                                     : ($data['currency'] ?? 'USD')));
    if ($paid) {
        order_fulfil($order, 'crypto', $externalId, $fiat, $fiatCurrency, $raw, 'crypto');
    } else {
        payment_upsert(['provider' => 'crypto', 'external_id' => $externalId, 'email' => $order['email'],
            'amount' => $fiat, 'currency' => $fiatCurrency, 'status' => $status ?: 'pending',
            'order_id' => $order['id'], 'plan_code' => $order['plan_code'], 'method' => 'crypto',
            'raw' => mb_substr($raw, 0, 60000)]);
        if ($dead && in_array($order['status'], ORDER_OPEN, true)) {
            order_update((int)$order['id'], ['status' => 'failed', 'failure_reason' => 'Crypto payment ' . $status]);
        }
    }
    json_out(['ok' => true]);
}

// callbacks without an order reference (invoices made by the previous version)
payment_upsert(['provider' => 'crypto', 'external_id' => $externalId, 'email' => valid_email($email) ? $email : null,
    'amount' => $amount, 'currency' => $currency, 'status' => $status ?: 'pending', 'raw' => mb_substr($raw, 0, 60000)]);
if ($paid && valid_email($email)) {
    legacy_paid_email_issue('crypto', $email, $externalId, $amount, $currency, $raw);
}

json_out(['ok' => true]);
