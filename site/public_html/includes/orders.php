<?php
/**
 * Orders and payments.
 *
 * A paid licence is created in exactly one place, order_fulfil(), and only
 * after the PAYMENT PROVIDER (server to server) or an ADMINISTRATOR has
 * confirmed the money. The amount confirmed must cover the order total the
 * server calculated. A browser "success" message never issues anything.
 */
declare(strict_types=1);
require_once __DIR__ . '/license.php';
// v6.3: the referral programme hooks into the order lifecycle below. It is
// loaded here so EVERY path that fulfils or refunds an order - webhooks,
// the PayPal capture, and the admin Payments page - gets the hooks without
// each of them having to remember. referral.php does not require this file
// back, so there is no load loop.
require_once __DIR__ . '/referral.php';

const ORDER_OPEN = ['pending', 'awaiting_verification', 'approved'];

function order_new_ref(): string
{
    for ($try = 0; $try < 20; $try++) {
        $s = 'ORD-';
        for ($i = 0; $i < 8; $i++) {
            $s .= SERIAL_ALPHABET[random_int(0, strlen(SERIAL_ALPHABET) - 1)];
        }
        if (!order_by_ref($s)) {
            return $s;
        }
    }
    throw new RuntimeException('could not allocate an order reference');
}

function order_by_id(int $id): ?array
{
    $st = db()->prepare('SELECT * FROM orders WHERE id = ?');
    $st->execute([$id]);
    return $st->fetch() ?: null;
}

function order_by_ref(string $ref): ?array
{
    $st = db()->prepare('SELECT * FROM orders WHERE ref = ?');
    $st->execute([strtoupper(trim($ref))]);
    return $st->fetch() ?: null;
}

function order_by_provider_id(string $providerOrderId): ?array
{
    if ($providerOrderId === '') {
        return null;
    }
    $st = db()->prepare('SELECT * FROM orders WHERE provider_order_id = ? ORDER BY id DESC LIMIT 1');
    $st->execute([$providerOrderId]);
    return $st->fetch() ?: null;
}

function order_access_ok(?array $order, string $token): bool
{
    return $order !== null && $token !== '' && hash_equals((string)$order['access_token'], $token);
}

function order_update(int $id, array $fields): void
{
    $allowed = ['status', 'provider', 'provider_order_id', 'failure_reason', 'license_id', 'payment_id', 'paid_at'];
    $sets = [];
    $args = [];
    foreach ($fields as $k => $v) {
        if (in_array($k, $allowed, true)) {
            $sets[] = "`$k` = ?";
            $args[] = $v;
        }
    }
    if (!$sets) {
        return;
    }
    $args[] = now();
    $args[] = $id;
    db()->prepare('UPDATE orders SET ' . implode(', ', $sets) . ', updated_at = ? WHERE id = ?')->execute($args);
}

function order_urls(array $o): array
{
    $q = 'ref=' . rawurlencode((string)$o['ref']) . '&t=' . rawurlencode((string)$o['access_token']);
    return [
        'status'  => site_url('thanks.php?' . $q),
        'receipt' => site_url('receipt.php?' . $q),
        'cancel'  => site_url('cancel.php?' . $q),
        'failed'  => site_url('payment-failed.php?' . $q),
    ];
}

function order_create(string $planCode, string $email, string $name, string $couponCode, string $provider): array
{
    $email = strtolower(trim($email));
    $name = mb_substr(trim($name), 0, 190);
    if (!valid_email($email)) {
        return ['ok' => false, 'field' => 'email', 'error' => 'Enter a valid email address. Your licence key is sent there.'];
    }
    $q = price_quote($planCode, $couponCode, $email);
    if (!$q['ok']) {
        return $q;
    }
    if (cents($q['final']) <= 0) {
        return ['ok' => false, 'error' => 'This order total is zero. Contact support to activate it.'];
    }
    $ref = order_new_ref();
    db()->prepare('INSERT INTO orders (ref, access_token, plan_code, email, customer_name, currency,
                   original_amount, discount_amount, final_amount, coupon_id, coupon_code, coupon_percent,
                   period_days, device_limit, provider, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)')
        ->execute([$ref, random_token(16), $planCode, $email, $name !== '' ? $name : null, $q['currency'],
            $q['original'], $q['discount'], $q['final'], $q['coupon']['id'] ?? null,
            $q['coupon_code'] !== '' ? $q['coupon_code'] : null, $q['percent'] ?: null,
            $q['period_days'], $q['device_limit'], $provider, 'pending', now(), now()]);
    $order = order_by_id((int)db()->lastInsertId());
    audit('order.created', $ref . ' ' . $planCode . ' ' . $q['final'] . ' ' . $q['currency']
        . ($q['coupon_code'] ? ' coupon ' . $q['coupon_code'] : '') . ' via ' . $provider);
    return ['ok' => true, 'order' => $order, 'quote' => $q];
}

/** Insert or update a payment row keyed on (provider, external_id). Returns its id. */
function payment_upsert(array $p): int
{
    $pdo = db();
    $st = $pdo->prepare('SELECT id FROM payments WHERE provider = ? AND external_id = ?');
    $st->execute([$p['provider'], $p['external_id']]);
    $id = (int)($st->fetchColumn() ?: 0);
    $cols = ['email', 'amount', 'currency', 'status', 'license_id', 'raw', 'order_id', 'plan_code',
             'original_amount', 'discount_amount', 'coupon_code', 'customer_name', 'method', 'notes',
             'reviewed_by', 'reviewed_at'];
    $data = array_intersect_key($p, array_flip($cols));
    if ($id) {
        if ($data) {
            $sets = implode(', ', array_map(static fn($k) => "`$k` = ?", array_keys($data)));
            $pdo->prepare("UPDATE payments SET $sets, updated_at = ? WHERE id = ?")
                ->execute([...array_values($data), now(), $id]);
        }
        return $id;
    }
    $data += ['status' => 'pending', 'amount' => 0, 'currency' => 'USD'];
    $keys = array_keys($data);
    $pdo->prepare('INSERT INTO payments (provider, external_id, ' . implode(', ', array_map(static fn($k) => "`$k`", $keys))
        . ', created_at, updated_at) VALUES (?, ?' . str_repeat(', ?', count($keys)) . ', ?, ?)')
        ->execute([$p['provider'], $p['external_id'], ...array_values($data), now(), now()]);
    return (int)$pdo->lastInsertId();
}

/**
 * Turn a CONFIRMED payment into a licence. Safe to call many times for the
 * same order (webhook retries, capture + webhook racing): the order row is
 * locked and a fulfilled order is returned as-is.
 */
function order_fulfil(array $order, string $provider, string $externalId, float $amountPaid,
                      string $currency, string $raw = '', string $method = ''): array
{
    $pdo = db();
    $pdo->beginTransaction();
    try {
        $st = $pdo->prepare('SELECT * FROM orders WHERE id = ? FOR UPDATE');
        $st->execute([$order['id']]);
        $o = $st->fetch();
        if (!$o) {
            $pdo->rollBack();
            return ['ok' => false, 'error' => 'order not found'];
        }
        if ($o['license_id']) {
            $pdo->commit();
            return ['ok' => true, 'already' => true, 'order' => $o, 'license' => license_by_id((int)$o['license_id'])];
        }
        if ($o['status'] === 'refunded') {
            $pdo->commit();
            return ['ok' => false, 'error' => 'order was refunded'];
        }
        $due = cents($o['final_amount']);
        if (strtoupper($currency) !== strtoupper((string)$o['currency']) || cents($amountPaid) + 1 < $due) {
            payment_upsert(['provider' => $provider, 'external_id' => $externalId, 'email' => $o['email'],
                'amount' => $amountPaid, 'currency' => strtoupper($currency), 'status' => 'review',
                'order_id' => $o['id'], 'plan_code' => $o['plan_code'], 'method' => $method,
                'raw' => mb_substr($raw, 0, 60000),
                'notes' => 'Amount or currency does not match the order total '
                           . $o['final_amount'] . ' ' . $o['currency'] . '. No licence was issued.']);
            $pdo->prepare("UPDATE orders SET status = 'review', failure_reason = ?, updated_at = ? WHERE id = ?")
                ->execute(['Payment of ' . $amountPaid . ' ' . $currency . ' does not match the total.', now(), $o['id']]);
            $pdo->commit();
            audit('order.amount_mismatch', $o['ref'] . ' paid ' . $amountPaid . ' ' . $currency
                . ' due ' . $o['final_amount'] . ' ' . $o['currency']);
            return ['ok' => false, 'error' => 'amount mismatch'];
        }
        $paymentId = payment_upsert(['provider' => $provider, 'external_id' => $externalId,
            'email' => $o['email'], 'amount' => $amountPaid, 'currency' => strtoupper($currency),
            'status' => 'completed', 'order_id' => $o['id'], 'plan_code' => $o['plan_code'],
            'original_amount' => $o['original_amount'], 'discount_amount' => $o['discount_amount'],
            'coupon_code' => $o['coupon_code'], 'customer_name' => $o['customer_name'],
            'method' => $method !== '' ? $method : $provider, 'raw' => mb_substr($raw, 0, 60000)]);
        $lic = issue_license((string)$o['email'], $provider, $externalId, (string)$o['plan_code'], [
            'order_id' => (int)$o['id'], 'payment_id' => $paymentId, 'coupon_code' => (string)$o['coupon_code'],
            'customer_name' => (string)$o['customer_name'], 'period_days' => (int)$o['period_days'],
            'device_limit' => (int)$o['device_limit'],
        ]);
        $pdo->prepare('UPDATE payments SET license_id = ? WHERE id = ?')->execute([$lic['id'], $paymentId]);
        $pdo->prepare("UPDATE orders SET status = 'paid', paid_at = ?, license_id = ?, payment_id = ?,
                       failure_reason = NULL, updated_at = ? WHERE id = ?")
            ->execute([now(), $lic['id'], $paymentId, now(), $o['id']]);
        if ($o['coupon_id']) {
            $r = $pdo->prepare('INSERT IGNORE INTO coupon_redemptions (coupon_id, order_id, email, created_at)
                                VALUES (?,?,?,?)');
            $r->execute([$o['coupon_id'], $o['id'], $o['email'], now()]);
            if ($r->rowCount() > 0) {
                $pdo->prepare('UPDATE coupons SET used_count = used_count + 1 WHERE id = ?')->execute([$o['coupon_id']]);
            }
        }
        $pdo->commit();
    } catch (Throwable $e) {
        if ($pdo->inTransaction()) {
            $pdo->rollBack();
        }
        throw $e;
    }
    $o = order_by_id((int)$order['id']);
    audit('order.paid', $o['ref'] . ' ' . $o['final_amount'] . ' ' . $o['currency'] . ' via ' . $provider, (int)$lic['id']);
    // The licence is already committed above. Emailing is best-effort: a mail
    // problem (bad address, SMTP down) must never fail an approval or a capture,
    // so it is isolated here and only logged.
    try {
        order_email_license($o, $lic);
    } catch (Throwable $e) {
        error_log('order_email_license failed for ' . $o['ref'] . ': ' . $e->getMessage());
        audit('order.email_failed', $o['ref'] . ' ' . mb_substr($e->getMessage(), 0, 120), (int)$lic['id']);
    }
    // v6.3 REFERRAL: a confirmed payment is the ONLY thing that counts a
    // referral (spec 2.3). Isolated exactly like the email above: the sale
    // is already committed, and a referral problem must never undo it or
    // fail an approval. Also idempotent, so a webhook retry that lands here
    // again adds nothing.
    try {
        if (function_exists('referral_on_order_paid')) {
            referral_on_order_paid($o);
        }
    } catch (Throwable $e) {
        error_log('referral_on_order_paid failed for ' . $o['ref'] . ': ' . $e->getMessage());
        audit('referral.hook_failed', $o['ref'] . ' ' . mb_substr($e->getMessage(), 0, 120));
    }
    return ['ok' => true, 'order' => $o, 'license' => $lic];
}

function order_email_license(array $o, array $lic): void
{
    $urls = order_urls($o);
    $plan = plan_name((string)$o['plan_code']);
    $lines = [
        'Thank you for your purchase.',
        '',
        'Plan: ' . $plan . ' (' . (int)$o['period_days'] . ' days, up to ' . (int)$o['device_limit']
            . ' computer' . ((int)$o['device_limit'] === 1 ? '' : 's') . ')',
        'Licence key: ' . $lic['serial'],
        'Valid until: ' . substr((string)$lic['expires_at'], 0, 16) . ' UTC',
        'Order: ' . $o['ref'] . '   Paid: ' . money((float)$o['final_amount'], (string)$o['currency'])
            . ($o['coupon_code'] ? '   Coupon: ' . $o['coupon_code'] . ' (-' . (int)$o['coupon_percent'] . '%)' : ''),
        '',
        'To activate:',
        '1. Open ' . SITE_NAME . ' on your computer.',
        '2. Click "Register licence".',
        '3. Paste the key above and click Activate.',
        '',
        'Receipt: ' . $urls['receipt'],
        'Access does not renew automatically.',
        '',
        'Questions? Reply to this email or write to ' . SUPPORT_EMAIL . '.',
    ];
    send_mail((string)$o['email'], 'Your ' . SITE_NAME . ' ' . $plan . ' licence key', implode("\n", $lines));
}

/** A manual payment (USDT address, WhatsApp, Telegram, Facebook) waiting for review. */
function order_manual_claim(array $o, string $method, string $reference, string $note = ''): array
{
    $reference = mb_substr(trim($reference), 0, 150);
    if ($reference === '') {
        return ['ok' => false, 'error' => 'Enter the transaction reference so we can find your payment.'];
    }
    if (!in_array($o['status'], ORDER_OPEN, true)) {
        return ['ok' => false, 'error' => 'This order can no longer take a payment reference.'];
    }
    $ext = 'claim:' . $o['ref'];
    payment_upsert(['provider' => 'manual', 'external_id' => $ext, 'email' => $o['email'],
        'amount' => $o['final_amount'], 'currency' => $o['currency'], 'status' => 'pending',
        'order_id' => $o['id'], 'plan_code' => $o['plan_code'], 'original_amount' => $o['original_amount'],
        'discount_amount' => $o['discount_amount'], 'coupon_code' => $o['coupon_code'],
        'customer_name' => $o['customer_name'], 'method' => $method,
        'notes' => 'Customer reference: ' . $reference . ($note !== '' ? "\nNote: " . mb_substr($note, 0, 500) : '')]);
    order_update((int)$o['id'], ['status' => 'awaiting_verification', 'provider' => 'manual']);
    audit('order.manual_claim', $o['ref'] . ' ' . $method . ' ' . mb_substr($reference, 0, 40));
    return ['ok' => true];
}

// ---------------------------------------------------------------------
// PayPal (Orders v2). The amount always comes from the order row.
// ---------------------------------------------------------------------
if (!function_exists('paypal_base')) {
    function paypal_base(): string
    {
        $override = (string)cfg('PAYPAL_API_BASE_OVERRIDE', '');
        if ($override !== '') {
            return rtrim($override, '/');
        }
        return setting('paypal_live') === '1' ? 'https://api-m.paypal.com' : 'https://api-m.sandbox.paypal.com';
    }
}

if (!function_exists('paypal_token')) {
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
}

function paypal_request(string $method, string $path, ?array $body = null, array $headers = []): array
{
    $token = paypal_token();
    if (!$token) {
        return ['status' => 0, 'body' => [], 'error' => 'PayPal authentication failed. Check the client ID and secret.'];
    }
    $ch = curl_init(paypal_base() . $path);
    $h = array_merge(['Content-Type: application/json', 'Authorization: Bearer ' . $token], $headers);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CUSTOMREQUEST  => $method,
        CURLOPT_HTTPHEADER     => $h,
        CURLOPT_TIMEOUT        => 30,
    ]);
    if ($body !== null) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($body, JSON_UNESCAPED_SLASHES));
    }
    $res = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    $err = curl_error($ch);
    curl_close($ch);
    return ['status' => $status, 'body' => json_decode((string)$res, true) ?: [], 'error' => $err];
}

function paypal_ready(): bool
{
    return setting_bool('paypal_enabled') && (string)setting('paypal_client_id', '') !== ''
        && (string)setting('paypal_secret', '') !== '';
}

function paypal_create_order(array $o): array
{
    $urls = order_urls($o);
    $r = paypal_request('POST', '/v2/checkout/orders', [
        'intent' => 'CAPTURE',
        'purchase_units' => [[
            'reference_id' => $o['ref'],
            'custom_id'    => $o['ref'],
            'invoice_id'   => $o['ref'],
            'description'  => mb_substr(SITE_NAME . ' ' . plan_name((string)$o['plan_code']) . ' - '
                               . (int)$o['period_days'] . ' days', 0, 127),
            'amount' => ['currency_code' => $o['currency'], 'value' => number_format((float)$o['final_amount'], 2, '.', '')],
        ]],
        'application_context' => [
            'brand_name' => SITE_NAME, 'shipping_preference' => 'NO_SHIPPING', 'user_action' => 'PAY_NOW',
            'return_url' => $urls['status'], 'cancel_url' => $urls['cancel'],
        ],
    ], ['PayPal-Request-Id: create-' . $o['ref']]);
    $id = (string)($r['body']['id'] ?? '');
    if ($r['status'] < 200 || $r['status'] >= 300 || $id === '') {
        audit('paypal.create_failed', $o['ref'] . ' HTTP ' . $r['status'] . ' ' . ($r['error'] ?: ''));
        return ['ok' => false, 'error' => 'PayPal is not available right now. Try again or choose another payment method.'];
    }
    order_update((int)$o['id'], ['provider' => 'paypal', 'provider_order_id' => $id]);
    return ['ok' => true, 'id' => $id];
}

/** Pull the capture facts out of an order / capture response. */
function paypal_capture_facts(array $body): array
{
    $unit = $body['purchase_units'][0] ?? [];
    $cap = $unit['payments']['captures'][0] ?? [];
    return [
        'order_status' => (string)($body['status'] ?? ''),
        'status'       => (string)($cap['status'] ?? ''),
        'capture_id'   => (string)($cap['id'] ?? ''),
        'amount'       => (float)($cap['amount']['value'] ?? 0),
        'currency'     => (string)($cap['amount']['currency_code'] ?? ''),
        'custom_id'    => (string)($cap['custom_id'] ?? ($unit['custom_id'] ?? ($unit['reference_id'] ?? ''))),
        'payer_email'  => (string)($body['payer']['email_address'] ?? ''),
        'reason'       => (string)($cap['status_details']['reason'] ?? ''),
    ];
}

/** Capture on the server, then fulfil. Used by the checkout and by the webhook. */
function paypal_capture_and_fulfil(array $o): array
{
    $pp = (string)$o['provider_order_id'];
    if ($pp === '') {
        return ['ok' => false, 'status' => 'failed', 'error' => 'No PayPal order is attached to this order.'];
    }
    $r = paypal_request('POST', '/v2/checkout/orders/' . rawurlencode($pp) . '/capture', null,
        ['PayPal-Request-Id: capture-' . $o['ref']]);
    $issue = (string)($r['body']['details'][0]['issue'] ?? '');
    if ($r['status'] === 422 && $issue === 'ORDER_ALREADY_CAPTURED') {
        $r = paypal_request('GET', '/v2/checkout/orders/' . rawurlencode($pp));
    }
    if ($r['status'] < 200 || $r['status'] >= 300) {
        $declined = in_array($issue, ['INSTRUMENT_DECLINED', 'PAYER_ACTION_REQUIRED'], true);
        if (!$declined) {
            order_update((int)$o['id'], ['status' => 'failed', 'failure_reason' => 'PayPal capture failed: ' . ($issue ?: 'HTTP ' . $r['status'])]);
        }
        audit('paypal.capture_failed', $o['ref'] . ' ' . ($issue ?: 'HTTP ' . $r['status']));
        return ['ok' => false, 'status' => $declined ? 'retry' : 'failed',
                'error' => $declined ? 'PayPal declined this payment method. Please try another card or account.'
                                     : 'PayPal could not complete the payment.'];
    }
    $f = paypal_capture_facts($r['body']);
    if ($f['custom_id'] !== '' && $f['custom_id'] !== $o['ref']) {
        audit('paypal.mismatch', $o['ref'] . ' custom_id ' . $f['custom_id']);
        return ['ok' => false, 'status' => 'failed', 'error' => 'Payment reference mismatch.'];
    }
    if ($f['status'] === 'COMPLETED') {
        $res = order_fulfil($o, 'paypal', $f['capture_id'], $f['amount'], $f['currency'],
            json_encode($r['body']) ?: '', 'paypal');
        return $res['ok'] ? ['ok' => true, 'status' => 'paid'] + $res
                          : ['ok' => false, 'status' => 'review', 'error' => 'We received a payment that needs a manual check. Support will contact you.'];
    }
    if ($f['status'] === 'PENDING') {
        order_update((int)$o['id'], ['status' => 'approved', 'failure_reason' => 'PayPal is holding the payment: ' . $f['reason']]);
        return ['ok' => true, 'status' => 'pending'];
    }
    order_update((int)$o['id'], ['status' => 'failed', 'failure_reason' => 'PayPal status ' . ($f['status'] ?: $f['order_status'])]);
    return ['ok' => false, 'status' => 'failed', 'error' => 'The payment was not completed.'];
}

// ---------------------------------------------------------------------
// crypto gateways: hosted invoice pages
// ---------------------------------------------------------------------
function crypto_gateway(): string
{
    $p = (string)setting('crypto_provider', 'manual');
    return in_array($p, ['nowpayments', 'cryptomus'], true) ? $p : 'manual';
}

function crypto_http(string $url, array $body, array $headers): array
{
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true, CURLOPT_POST => true, CURLOPT_TIMEOUT => 30,
        CURLOPT_HTTPHEADER => array_merge(['Content-Type: application/json'], $headers),
        CURLOPT_POSTFIELDS => json_encode($body, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE),
    ]);
    $res = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    curl_close($ch);
    return ['status' => $status, 'body' => json_decode((string)$res, true) ?: []];
}

function crypto_create_invoice(array $o): array
{
    $urls = order_urls($o);
    $key = (string)setting('crypto_api_key', '');
    $amount = number_format((float)$o['final_amount'], 2, '.', '');
    $override = rtrim((string)cfg('CRYPTO_API_BASE_OVERRIDE', ''), '/');
    if ($key === '') {
        return ['ok' => false, 'error' => 'Crypto checkout is not configured.'];
    }
    if (crypto_gateway() === 'nowpayments') {
        $body = [
            'price_amount' => (float)$amount, 'price_currency' => strtolower((string)$o['currency']),
            'order_id' => $o['ref'], 'order_description' => $o['ref'],
            'ipn_callback_url' => site_url('api/webhooks/crypto.php'),
            'success_url' => $urls['status'], 'cancel_url' => $urls['cancel'],
        ];
        $r = crypto_http(($override ?: 'https://api.nowpayments.io') . '/v1/invoice', $body, ['x-api-key: ' . $key]);
        $url = (string)($r['body']['invoice_url'] ?? '');
        $id = (string)($r['body']['id'] ?? '');
    } elseif (crypto_gateway() === 'cryptomus') {
        $merchant = (string)setting('crypto_merchant_id', '');
        $body = [
            'amount' => $amount, 'currency' => $o['currency'], 'order_id' => $o['ref'],
            'url_callback' => site_url('api/webhooks/crypto.php'),
            'url_return' => $urls['cancel'], 'url_success' => $urls['status'],
        ];
        $sign = md5(base64_encode(json_encode($body, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)) . $key);
        $r = crypto_http(($override ?: 'https://api.cryptomus.com') . '/v1/payment', $body,
            ['merchant: ' . $merchant, 'sign: ' . $sign]);
        $url = (string)($r['body']['result']['url'] ?? '');
        $id = (string)($r['body']['result']['uuid'] ?? '');
    } else {
        return ['ok' => false, 'error' => 'Crypto checkout is not configured.'];
    }
    if ($url === '' || !is_web_url($url)) {
        audit('crypto.invoice_failed', $o['ref'] . ' HTTP ' . $r['status']);
        return ['ok' => false, 'error' => 'The crypto payment page could not be created. Try again or choose another method.'];
    }
    order_update((int)$o['id'], ['provider' => 'crypto', 'provider_order_id' => $id !== '' ? $id : null]);
    return ['ok' => true, 'url' => $url];
}

/** Payment methods the checkout may offer right now. */
function checkout_methods(): array
{
    $m = [];
    if (paypal_ready()) {
        $m['paypal'] = ['label' => 'PayPal or card', 'kind' => 'paypal',
                        'hint' => 'Pay securely with PayPal. Cards are handled by PayPal; we never see card details.'];
    }
    if (setting_bool('crypto_enabled')) {
        if (crypto_gateway() !== 'manual' && (string)setting('crypto_api_key', '') !== '') {
            $m['crypto'] = ['label' => 'Crypto (USDT and more)', 'kind' => 'redirect',
                            'hint' => 'You are sent to our crypto payment partner. Your key is issued once the network confirms the payment.'];
        } elseif ((string)setting('usdt_address', '') !== '') {
            $m['usdt'] = ['label' => 'USDT transfer (' . setting('usdt_network', 'TRC20') . ')', 'kind' => 'manual',
                          'hint' => 'Send the exact amount to our wallet, then submit the transaction hash. We verify it by hand.'];
        }
    }
    try {
        foreach (db()->query('SELECT * FROM channels WHERE enabled = 1 AND manual_payments = 1 ORDER BY sort_order') as $c) {
            $m['manual:' . $c['code']] = ['label' => 'Arrange payment on ' . $c['display_name'], 'kind' => 'manual',
                'hint' => (string)$c['instructions'], 'channel' => $c];
        }
    } catch (PDOException $e) {
    }
    return $m;
}

function channels_enabled(): array
{
    try {
        return db()->query('SELECT * FROM channels WHERE enabled = 1 ORDER BY sort_order')->fetchAll();
    } catch (PDOException $e) {
        return [];
    }
}

/** The link a customer opens for a contact channel. */
function channel_link(array $c, string $orderRef = ''): string
{
    $url = trim((string)$c['url']);
    $text = $orderRef !== '' ? 'Hello, I would like to pay for order ' . $orderRef . '.' : '';
    if ($c['code'] === 'whatsapp') {
        $digits = preg_replace('/\D/', '', (string)$c['handle']) ?? '';
        if ($url === '' && $digits !== '') {
            $url = 'https://wa.me/' . $digits;
        }
        if ($url !== '' && $text !== '' && str_starts_with($url, 'https://wa.me/')) {
            $url .= (str_contains($url, '?') ? '&' : '?') . 'text=' . rawurlencode($text);
        }
    } elseif ($c['code'] === 'telegram' && $url === '') {
        $h = ltrim((string)$c['handle'], '@');
        if ($h !== '') {
            $url = 'https://t.me/' . rawurlencode($h);
        }
    } elseif ($c['code'] === 'facebook' && $url === '') {
        // a page name or Messenger username becomes an m.me link
        $h = trim((string)$c['handle'], "@/ \t");
        if ($h !== '' && preg_match('/^[A-Za-z0-9.\-]+$/', $h)) {
            $url = 'https://m.me/' . $h;
        }
    }
    return is_web_url($url, true) ? $url : '';
}

/**
 * Callbacks that carry no order reference (buttons and invoices created by
 * the previous version). Still Pro-only as before, but the amount must now
 * cover the current Pro price, otherwise the payment waits for review.
 */
function legacy_paid_email_issue(string $provider, string $email, string $externalId,
                                 float $amount, string $currency, string $raw): ?array
{
    $pro = plan_get('pro');
    $price = cents($pro['current_price'] ?? setting('price_usd', '29.00'));
    $usdLike = (bool)preg_match('/^(USD|USDT|USDC)/', strtoupper($currency));
    $enough = $usdLike && cents($amount) * 100 >= $price * 99;   // 1% network/fee tolerance
    if (!$enough) {
        payment_upsert(['provider' => $provider, 'external_id' => $externalId, 'email' => $email,
            'amount' => $amount, 'currency' => strtoupper($currency), 'status' => 'review', 'plan_code' => 'pro',
            'raw' => mb_substr($raw, 0, 60000),
            'notes' => 'Paid amount does not cover the Pro price. Check it and approve by hand.']);
        audit($provider . '.amount_review', $email . ' ' . $amount . ' ' . $currency);
        return null;
    }
    $lic = issue_license($email, $provider, $externalId, 'pro');
    payment_upsert(['provider' => $provider, 'external_id' => $externalId, 'email' => $email,
        'amount' => $amount, 'currency' => strtoupper($currency), 'status' => 'completed',
        'license_id' => $lic['id'], 'plan_code' => 'pro', 'raw' => mb_substr($raw, 0, 60000)]);
    audit($provider . '.paid', $email . ' ' . $amount . $currency, (int)$lic['id']);
    return $lic;
}

/**
 * Undo what ONE order bought, and nothing else.
 *
 * A renewal extends the buyer's existing key, so one licence can be funded by
 * several paid orders. Refunding one of them takes back only the days that
 * order added; a licence bought by this order alone is revoked. Other licences
 * the customer owns are never touched. Returns 'shortened' or 'revoked'.
 */
function refund_order_license(?array $order, int $licenseId, string $why): string
{
    // v6.3 REFERRAL: a refunded or charged-back order takes its referral
    // back (spec 2.4). Done first so it happens whether the licence below
    // ends up shortened or revoked, and isolated so it can never stop a
    // refund being processed. A reward already granted is flagged for
    // review inside, never revoked silently.
    try {
        if (function_exists('referral_on_order_refunded')) {
            referral_on_order_refunded($order, $why);
        }
    } catch (Throwable $e) {
        error_log('referral_on_order_refunded failed: ' . $e->getMessage());
    }
    $days = $order ? max(0, (int)$order['period_days']) : 0;
    $others = 0;
    if ($order) {
        $st = db()->prepare("SELECT COUNT(*) FROM orders WHERE license_id = ? AND status = 'paid' AND id <> ?");
        $st->execute([$licenseId, (int)$order['id']]);
        $others = (int)$st->fetchColumn();
    }
    if ($others > 0 && $days > 0) {
        db()->prepare('UPDATE licenses SET expires_at = GREATEST(UTC_TIMESTAMP(), DATE_SUB(expires_at, INTERVAL ? DAY)),
                       updated_at = ? WHERE id = ?')->execute([$days, now(), $licenseId]);
        audit('license.refund_shortened', $why . ': -' . $days . ' days (order ' . $order['ref'] . ')', $licenseId);
        return 'shortened';
    }
    revoke_license_for_refund($licenseId, $why);
    return 'revoked';
}

function revoke_license_for_refund(int $licenseId, string $why): void
{
    db()->prepare("UPDATE licenses SET status = 'revoked', revoked_at = ?, updated_at = ? WHERE id = ?")
        ->execute([now(), now(), $licenseId]);
    audit('license.revoked', $why, $licenseId);
}
