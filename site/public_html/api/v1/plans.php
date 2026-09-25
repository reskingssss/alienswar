<?php
/** GET /api/v1/plans.php - the public price list (the desktop Upgrade screen reads this). */
declare(strict_types=1);
require_once __DIR__ . '/../../includes/license.php';

$out = [];
foreach (plans_all(true) as $p) {
    $out[] = [
        'code' => $p['code'], 'name' => $p['name'], 'tagline' => (string)$p['tagline'],
        'previous_price' => $p['previous_price'], 'current_price' => $p['current_price'],
        'currency' => $p['currency'], 'period_days' => (int)$p['period_days'],
        'device_limit' => (int)$p['device_limit'], 'purchasable' => (bool)$p['purchasable'],
        'features' => plan_features($p),
        'entitlements' => plan_entitlements((string)$p['code'], (int)$p['device_limit']),
        'checkout_url' => plan_is_paid((string)$p['code']) ? site_url('buy.php?plan=' . $p['code'] . '&ref=app') : null,
    ];
}
header('Cache-Control: public, max-age=300');
json_out(['ok' => true, 'plans' => $out, 'pricing_url' => site_url('pricing.php')]);
