<?php
/**
 * Plans, entitlements, prices and coupons.
 *
 * Prices and discounts are ALWAYS computed here, on the server. Nothing a
 * browser or desktop client sends about a price, a discount, a plan name or
 * a device limit is ever trusted.
 */
declare(strict_types=1);
require_once __DIR__ . '/helpers.php';

const PLAN_CODES = ['free', 'pro', 'team'];
const PAID_PLANS = ['pro', 'team'];
const COUPON_PERCENTS = [10, 20, 35];
const ALL_LANGUAGES = ['en-US', 'en-GB', 'fr-FR', 'ar-SA'];
const ALL_RESOLUTIONS = ['1920x1080', '1366x768', '1536x864', '1440x900', '1280x720', '1600x900', '1280x1024'];
const FREE_LANGUAGES = ['en-US', 'fr-FR'];
const FREE_RESOLUTIONS = ['1920x1080'];
const FREE_MAX_PROFILES = 5;

function plan_seed_rows(): array
{
    $pro = number_format((float)setting('price_usd', '29.00'), 2, '.', '');
    return [
        'free' => ['code' => 'free', 'name' => 'Free', 'tagline' => 'Start right away on one computer. No sign-up.',
            'previous_price' => null, 'current_price' => '0.00', 'currency' => 'USD', 'period_days' => 0,
            'status' => 'active', 'purchasable' => 0, 'device_limit' => 1, 'sort_order' => 1,
            'features' => "Up to 5 browser profiles\nLanguages: en-US and fr-FR\nScreen size: 1920×1080\nScript 1 included\nOne computer\nNo email, card or licence key needed\n!Fingerprint engine (Pro)\n!Script 2 (Pro)"],
        'pro' => ['code' => 'pro', 'name' => 'Pro', 'tagline' => 'The complete tool on one computer.',
            'previous_price' => '49.00', 'current_price' => $pro, 'currency' => 'USD', 'period_days' => 30,
            'status' => 'active', 'purchasable' => 1, 'device_limit' => 1, 'sort_order' => 2,
            'features' => "Unlimited browser profiles\nFull fingerprint engine\nAll languages and screen sizes\nScript 1 and Script 2\nOne computer\nNo automatic renewal"],
        'team' => ['code' => 'team', 'name' => 'Unlimited for Team', 'tagline' => 'Everything in Pro, on up to three computers.',
            'previous_price' => '119.00', 'current_price' => '49.00', 'currency' => 'USD', 'period_days' => 30,
            'status' => 'active', 'purchasable' => 1, 'device_limit' => 3, 'sort_order' => 3,
            'features' => "Everything in Pro\nOne licence key for up to 3 computers\nUnlimited browser profiles\nScript 1 and Script 2\nNo automatic renewal"],
    ];
}

function plans_all(bool $publicOnly = false): array
{
    $rows = [];
    try {
        foreach (db()->query('SELECT * FROM plans ORDER BY sort_order, code') as $r) {
            $rows[$r['code']] = $r;
        }
    } catch (PDOException $e) {
        $rows = plan_seed_rows();   // before the upgrade has run
    }
    if ($publicOnly) {
        $rows = array_filter($rows, static fn($p) => $p['status'] === 'active');
    }
    return $rows;
}

function plan_get(string $code): ?array
{
    $all = plans_all();
    return $all[$code] ?? null;
}

function plan_name(string $code): string
{
    $p = plan_get($code);
    if ($p) {
        return (string)$p['name'];
    }
    return ['free' => 'Free', 'pro' => 'Pro', 'team' => 'Unlimited for Team'][$code] ?? ucfirst($code);
}

function plan_is_paid(string $code): bool
{
    return in_array($code, PAID_PLANS, true);
}

function plan_features(array $plan): array
{
    return array_values(array_filter(array_map('trim', preg_split('/\R/', (string)$plan['features']) ?: [])));
}

function plan_period_label(array $plan): string
{
    $d = (int)$plan['period_days'];
    if ($d <= 0) {
        return 'no time limit';
    }
    return $d . ' days of access';
}

/**
 * What a plan unlocks. Hard rules from the product brief; the desktop app
 * receives these inside an Ed25519-signed token so they cannot be edited.
 * 0 = unlimited. '*' = every supported value.
 */
function plan_entitlements(string $tier, ?int $deviceLimit = null): array
{
    if (plan_is_paid($tier)) {
        $plan = plan_get($tier);
        return [
            'plan' => $tier,
            'max_profiles' => 0,
            'fingerprint' => true,
            'languages' => ['*'],
            'resolutions' => ['*'],
            'scripts' => ['free', 'pro'],
            'max_devices' => $deviceLimit ?? (int)($plan['device_limit'] ?? ($tier === 'team' ? 3 : 1)),
        ];
    }
    return [
        'plan' => 'free',
        'max_profiles' => FREE_MAX_PROFILES,
        'fingerprint' => false,
        'languages' => FREE_LANGUAGES,
        'resolutions' => FREE_RESOLUTIONS,
        'scripts' => ['free'],
        'max_devices' => 1,
    ];
}

/** Validate and store one plan from the dashboard. Returns a list of errors. */
function plan_save(string $code, array $in): array
{
    $errors = [];
    if (!in_array($code, PLAN_CODES, true)) {
        return ['Unknown plan.'];
    }
    $name = trim((string)($in['name'] ?? ''));
    $prev = trim((string)($in['previous_price'] ?? ''));
    $curr = trim((string)($in['current_price'] ?? ''));
    $currency = strtoupper(trim((string)($in['currency'] ?? 'USD')));
    $days = trim((string)($in['period_days'] ?? '0'));
    $devices = trim((string)($in['device_limit'] ?? '1'));
    $order = trim((string)($in['sort_order'] ?? '0'));
    $features = trim(str_replace("\r\n", "\n", (string)($in['features'] ?? '')));
    $status = ($in['status'] ?? 'active') === 'hidden' ? 'hidden' : 'active';
    $buyable = !empty($in['purchasable']) ? 1 : 0;

    if ($name === '' || mb_strlen($name) > 80) {
        $errors[] = 'Plan name is required (80 characters at most).';
    }
    $num = '/^\d{1,7}(\.\d{1,2})?$/';
    if ($curr === '' || !preg_match($num, $curr)) {
        $errors[] = 'Current price must be a number of 0 or more with up to two decimals.';
    }
    if ($prev !== '' && !preg_match($num, $prev)) {
        $errors[] = 'Previous price must be empty or a number of 0 or more.';
    }
    if ($prev !== '' && $curr !== '' && !$errors && (float)$prev <= (float)$curr) {
        $errors[] = 'Previous price must be higher than the current price (leave it empty to hide it).';
    }
    if (!preg_match('/^[A-Z]{3}$/', $currency)) {
        $errors[] = 'Currency must be a three-letter code such as USD.';
    }
    if (!ctype_digit($days) || (int)$days > 3650) {
        $errors[] = 'Access period must be a whole number of days between 0 and 3650.';
    }
    if (!ctype_digit($devices) || (int)$devices < 1 || (int)$devices > 100) {
        $errors[] = 'Device limit must be between 1 and 100.';
    }
    if (!preg_match('/^-?\d{1,4}$/', $order)) {
        $errors[] = 'Display order must be a whole number.';
    }
    if ($features === '') {
        $errors[] = 'List at least one feature for the pricing page.';
    }
    if (plan_is_paid($code)) {
        if ($buyable && (float)$curr <= 0) {
            $errors[] = 'A plan that can be purchased needs a price above 0.';
        }
        if ((int)$days < 1) {
            $errors[] = 'Paid plans need an access period of at least 1 day.';
        }
    } else {
        $buyable = 0;    // Free is never sold
        if ((float)$curr != 0.0) {
            $errors[] = 'The Free plan price must stay at 0.';
        }
        if ((int)$devices !== 1) {
            $errors[] = 'The Free plan is limited to one computer.';
        }
    }
    if ($errors) {
        return $errors;
    }
    db()->prepare('UPDATE plans SET name=?, tagline=?, previous_price=?, current_price=?, currency=?,
                   period_days=?, status=?, purchasable=?, device_limit=?, features=?, sort_order=?, updated_at=?
                   WHERE code=?')
        ->execute([$name, mb_substr(trim((string)($in['tagline'] ?? '')), 0, 160), $prev === '' ? null : $prev,
            $curr, $currency, (int)$days, $status, $buyable, (int)$devices, mb_substr($features, 0, 2000),
            (int)$order, now(), $code]);
    if ($code === 'pro') {
        set_setting('price_usd', number_format((float)$curr, 2, '.', ''));   // legacy readers
    }
    audit('plan.saved', $code . ' price=' . $curr . ' prev=' . ($prev ?: '-') . ' devices=' . $devices
        . ' status=' . $status . ' buyable=' . $buyable);
    return [];
}

// ---------------------------------------------------------------------
// coupons
// ---------------------------------------------------------------------
function coupon_normalise(string $code): string
{
    return substr(preg_replace('/[^A-Z0-9-]/', '', strtoupper(trim($code))) ?? '', 0, 40);
}

function coupon_generate_code(int $percent): string
{
    $alpha = '23456789ABCDEFGHJKLMNPQRSTVWXYZ';
    for ($try = 0; $try < 20; $try++) {
        $s = 'SAVE' . $percent . '-';
        for ($i = 0; $i < 6; $i++) {
            $s .= $alpha[random_int(0, strlen($alpha) - 1)];
        }
        if (!coupon_find($s)) {
            return $s;
        }
    }
    throw new RuntimeException('could not allocate a coupon code');
}

function coupon_find(string $code): ?array
{
    $code = coupon_normalise($code);
    if ($code === '') {
        return null;
    }
    $st = db()->prepare('SELECT * FROM coupons WHERE code = ?');
    $st->execute([$code]);
    return $st->fetch() ?: null;
}

function coupon_plans(array $coupon): array
{
    return array_values(array_intersect(PAID_PLANS, array_map('trim', explode(',', (string)$coupon['plans']))));
}

/** Why this coupon cannot be used, or null when it can. */
function coupon_problem(array $c, string $plan, string $email = ''): ?string
{
    if (!(int)$c['active'] || $c['revoked_at']) {
        return 'This coupon is no longer active.';
    }
    if ($c['expires_at'] && strtotime($c['expires_at'] . ' UTC') <= time()) {
        return 'This coupon has expired.';
    }
    if (!in_array((int)$c['percent'], COUPON_PERCENTS, true)) {
        return 'This coupon is not valid.';
    }
    if ($c['max_uses'] !== null && (int)$c['used_count'] >= (int)$c['max_uses']) {
        return 'This coupon has reached its usage limit.';
    }
    if (!in_array($plan, coupon_plans($c), true)) {
        return 'This coupon does not apply to the ' . plan_name($plan) . ' plan.';
    }
    if ($email !== '' && $c['max_uses_per_customer'] !== null) {
        $st = db()->prepare('SELECT COUNT(*) FROM coupon_redemptions WHERE coupon_id = ? AND email = ?');
        $st->execute([$c['id'], strtolower($email)]);
        if ((int)$st->fetchColumn() >= (int)$c['max_uses_per_customer']) {
            return 'You have already used this coupon the maximum number of times.';
        }
    }
    return null;
}

/**
 * The one place a price is calculated.
 * Returns ok=false with a message when the plan or the coupon is not usable.
 */
function price_quote(string $planCode, string $couponCode = '', string $email = ''): array
{
    $plan = plan_get($planCode);
    if (!$plan || !plan_is_paid($planCode) || $plan['status'] !== 'active' || !(int)$plan['purchasable']) {
        return ['ok' => false, 'field' => 'plan', 'error' => 'That plan is not available for purchase right now.'];
    }
    $originalC = cents($plan['current_price']);
    $quote = [
        'ok' => true, 'plan' => $planCode, 'plan_name' => $plan['name'], 'currency' => $plan['currency'],
        'original' => from_cents($originalC), 'discount' => '0.00', 'final' => from_cents($originalC),
        'percent' => 0, 'coupon' => null, 'coupon_code' => '',
        'period_days' => (int)$plan['period_days'], 'device_limit' => (int)$plan['device_limit'],
        'previous_price' => $plan['previous_price'],
    ];
    $couponCode = coupon_normalise($couponCode);
    if ($couponCode === '') {
        return $quote;
    }
    $c = coupon_find($couponCode);
    if (!$c) {
        return ['ok' => false, 'field' => 'coupon', 'error' => 'That coupon code was not recognised.'] + $quote;
    }
    $problem = coupon_problem($c, $planCode, strtolower($email));
    if ($problem !== null) {
        return ['ok' => false, 'field' => 'coupon', 'error' => $problem] + $quote;
    }
    $discountC = intdiv($originalC * (int)$c['percent'] + 50, 100);   // round half up
    $quote['discount'] = from_cents($discountC);
    $quote['final'] = from_cents($originalC - $discountC);
    $quote['percent'] = (int)$c['percent'];
    $quote['coupon'] = $c;
    $quote['coupon_code'] = $c['code'];
    return $quote;
}
