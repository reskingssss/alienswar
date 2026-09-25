<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/license.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/** Pricing plans: what the pricing page and checkout show and charge. */
$errors = [];
$posted = [];
if (admin_post()) {
    $code = (string)($_POST['code'] ?? '');
    $errors = plan_save($code, $_POST);
    if (!$errors) {
        back_to('plans.php#plan-' . $code, plan_name($code) . ' saved. The pricing page and checkout use it immediately.');
    }
    $posted[$code] = $_POST;
}
$plans = plans_all();
layout_top('Pricing plans', 'Names, prices, access periods and the features listed on the pricing page.');
?>
<?php if ($errors): ?>
  <div class="alert alert-bad" role="alert"><b>The plan was not saved.</b><ul><?php foreach ($errors as $er): ?><li><?= e($er) ?></li><?php endforeach; ?></ul></div>
<?php endif; ?>
<p class="muted">Changes appear on the public <a href="../pricing.php" target="_blank" rel="noopener">pricing page</a>
  and checkout straight away. Orders already placed keep the price they were created with.</p>
<div class="grid grid-3">
<?php foreach ($plans as $p):
    $code = (string)$p['code'];
    $v = $posted[$code] ?? $p;
    $features = isset($posted[$code]) ? (string)$v['features'] : implode("\n", plan_features($p));
    $paid = plan_is_paid($code); ?>
  <section class="card" id="plan-<?= e($code) ?>" aria-labelledby="h-<?= e($code) ?>">
    <div class="card-head"><h2 id="h-<?= e($code) ?>"><?= e($p['name']) ?></h2><?= plan_badge($code) ?></div>
    <form method="post" data-price-form data-guard>
      <?= csrf_field() ?><input type="hidden" name="code" value="<?= e($code) ?>">
      <div class="price-preview" data-price-preview aria-live="polite">
        <span class="was strike"></span><span class="now"></span><span class="per muted small"></span>
      </div>
      <label class="field">Plan name<input name="name" value="<?= e((string)$v['name']) ?>" maxlength="80" required></label>
      <label class="field">Short description<input name="tagline" value="<?= e((string)($v['tagline'] ?? '')) ?>" maxlength="160"></label>
      <div class="form-grid">
        <label class="field">Previous price <?= tip('Shown crossed out next to the current price. Leave empty to show no previous price.') ?>
          <input name="previous_price" inputmode="decimal" value="<?= e((string)($v['previous_price'] ?? '')) ?>" <?= $paid ? '' : 'readonly' ?>></label>
        <label class="field">Current price<input name="current_price" inputmode="decimal" value="<?= e((string)$v['current_price']) ?>" required <?= $paid ? '' : 'readonly' ?>></label>
        <label class="field">Currency<input name="currency" value="<?= e((string)$v['currency']) ?>" maxlength="3" required></label>
        <label class="field">Access period, days <?= tip('How long a purchase unlocks the plan. 0 means no expiry (Free).') ?>
          <input type="number" name="period_days" min="0" max="3650" value="<?= (int)$v['period_days'] ?>" <?= $paid ? 'min="1"' : '' ?>></label>
        <label class="field">Computers per licence<input type="number" name="device_limit" min="1" max="100" value="<?= (int)$v['device_limit'] ?>" <?= $paid ? '' : 'readonly' ?>></label>
        <label class="field">Display order<input type="number" name="sort_order" value="<?= (int)$v['sort_order'] ?>"></label>
      </div>
      <label class="field">Status<select name="status">
        <option value="active"<?= ($v['status'] ?? 'active') === 'active' ? ' selected' : '' ?>>Shown on the pricing page</option>
        <option value="hidden"<?= ($v['status'] ?? '') === 'hidden' ? ' selected' : '' ?>>Hidden</option></select></label>
      <?php if ($paid): ?>
        <label class="check"><input type="checkbox" name="purchasable" value="1"<?= !empty($v['purchasable']) ? ' checked' : '' ?>> Can be bought at checkout</label>
      <?php endif; ?>
      <label class="field">Features on the pricing page <span class="hint">one per line</span>
        <textarea name="features" rows="7" required><?= e($features) ?></textarea></label>
      <button class="btn btn-primary">Save <?= e($p['name']) ?></button>
      <p class="small muted">Last saved <?= when($p['updated_at'] ?? null) ?></p>
    </form>
  </section>
<?php endforeach; ?>
</div>

<section class="card" aria-labelledby="ent">
  <h2 id="ent">What each plan unlocks in the app</h2>
  <p class="muted small">These limits are enforced by the server and inside the signed licence the app receives,
    so they cannot be changed by editing files on a computer. The computer limit comes from the plan above.</p>
  <div class="table-wrap"><table class="data">
    <thead><tr><th>Feature</th><?php foreach (PLAN_CODES as $c): ?><th><?= plan_badge($c) ?></th><?php endforeach; ?></tr></thead>
    <tbody>
    <?php $ents = []; foreach (PLAN_CODES as $c) { $ents[$c] = plan_entitlements($c, (int)(plan_get($c)['device_limit'] ?? 1)); }
    $rowsE = [
        'Browser profiles' => static fn($e) => (int)$e['max_profiles'] === 0 ? 'Unlimited' : 'Up to ' . (int)$e['max_profiles'],
        'Fingerprint engine' => static fn($e) => $e['fingerprint'] ? 'Full' : 'Off',
        'Languages' => static fn($e) => in_array('*', $e['languages'], true) ? 'All (' . count(ALL_LANGUAGES) . ')' : implode(', ', $e['languages']),
        'Screen sizes' => static fn($e) => in_array('*', $e['resolutions'], true) ? 'All (' . count(ALL_RESOLUTIONS) . ')' : implode(', ', $e['resolutions']),
        'Script 1' => static fn($e) => 'Yes',
        'Script 2' => static fn($e) => in_array('pro', $e['scripts'], true) ? 'Yes' : 'No',
        'Computers' => static fn($e) => (string)(int)$e['max_devices'],
    ];
    foreach ($rowsE as $label => $fn): ?>
      <tr><td><?= e($label) ?></td><?php foreach (PLAN_CODES as $c): ?><td><?= e($fn($ents[$c])) ?></td><?php endforeach; ?></tr>
    <?php endforeach; ?>
    </tbody></table></div>
</section>
<?php layout_bottom(); ?>
