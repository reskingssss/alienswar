<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/license.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/** Coupons: 10 %, 20 % or 35 % off, checked and applied only on the server. */
function coupon_form_values(array $in): array
{
    $plans = array_values(array_intersect(PAID_PLANS, (array)($in['plans'] ?? [])));
    $errors = [];
    if (!$plans) {
        $errors[] = 'Choose at least one plan the coupon applies to.';
    }
    $exp = trim((string)($in['expires_at'] ?? ''));
    $expires = null;
    if ($exp !== '') {
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $exp)) {
            $errors[] = 'Expiry must be a date.';
        } else {
            $expires = $exp . ' 23:59:59';
            if (strtotime($expires . ' UTC') <= time()) {
                $errors[] = 'The expiry date must be in the future.';
            }
        }
    }
    $num = static function (string $key) use ($in, &$errors): ?int {
        $v = trim((string)($in[$key] ?? ''));
        if ($v === '') {
            return null;
        }
        if (!ctype_digit($v) || (int)$v < 1 || (int)$v > 1000000) {
            $errors[] = ($key === 'max_uses' ? 'Maximum total uses' : 'Maximum uses per customer') . ' must be a whole number of 1 or more.';
            return null;
        }
        return (int)$v;
    };
    return [$errors, [
        'plans' => implode(',', $plans), 'expires_at' => $expires,
        'max_uses' => $num('max_uses'), 'max_uses_per_customer' => $num('max_uses_per_customer'),
        'notes' => mb_substr(trim((string)($in['notes'] ?? '')), 0, 500) ?: null,
    ]];
}

if (admin_post()) {
    $act = (string)($_POST['action'] ?? '');
    if ($act === 'create') {
        $percent = (int)($_POST['percent'] ?? 0);
        [$errors, $v] = coupon_form_values($_POST);
        if (!in_array($percent, COUPON_PERCENTS, true)) {
            $errors[] = 'Choose a 10 %, 20 % or 35 % discount.';
        }
        $code = coupon_normalise((string)($_POST['code'] ?? ''));
        if ($code === '' && !$errors) {
            $code = coupon_generate_code($percent);
        } elseif ($code !== '' && (strlen($code) < 4 || !preg_match('/^[A-Z0-9][A-Z0-9-]*$/', $code))) {
            $errors[] = 'A custom code needs at least 4 letters or digits (dashes allowed).';
        } elseif ($code !== '' && coupon_find($code)) {
            $errors[] = 'The code ' . $code . ' already exists.';
        }
        if ($errors) {
            back_to('coupons.php', implode(' ', $errors), false);
        }
        db()->prepare('INSERT INTO coupons (code, percent, plans, active, expires_at, max_uses, max_uses_per_customer,
                       used_count, notes, created_by, created_at) VALUES (?,?,?,?,?,?,?,0,?,?,?)')
            ->execute([$code, $percent, $v['plans'], isset($_POST['active']) ? 1 : 0, $v['expires_at'], $v['max_uses'],
                       $v['max_uses_per_customer'], $v['notes'], admin_actor(), now()]);
        audit('coupon.created', $code . ' ' . $percent . '% plans=' . $v['plans']
            . ' expires=' . ($v['expires_at'] ?? 'never') . ' max=' . ($v['max_uses'] ?? '∞'));
        back_to('coupons.php', 'Coupon ' . $code . ' created (' . $percent . ' % off).');
    }

    $c = coupon_find((string)($_POST['code'] ?? ''));
    if (!$c) {
        back_to('coupons.php', 'That coupon no longer exists.', false);
    }
    if ($act === 'activate' || $act === 'deactivate') {
        if ($c['revoked_at'] && $act === 'activate') {
            back_to('coupons.php', 'A revoked coupon cannot be activated again. Create a new one.', false);
        }
        db()->prepare('UPDATE coupons SET active = ? WHERE id = ?')->execute([$act === 'activate' ? 1 : 0, $c['id']]);
        audit('coupon.' . $act, $c['code']);
        back_to('coupons.php', 'Coupon ' . $c['code'] . ($act === 'activate' ? ' activated.' : ' deactivated.'));
    }
    if ($act === 'revoke') {
        db()->prepare('UPDATE coupons SET active = 0, revoked_at = ? WHERE id = ?')->execute([now(), $c['id']]);
        audit('coupon.revoked', $c['code']);
        back_to('coupons.php', 'Coupon ' . $c['code'] . ' revoked. It can no longer be used.');
    }
    if ($act === 'update') {
        [$errors, $v] = coupon_form_values($_POST);
        if ($errors) {
            back_to('coupons.php', implode(' ', $errors), false);
        }
        db()->prepare('UPDATE coupons SET plans = ?, expires_at = ?, max_uses = ?, max_uses_per_customer = ?, notes = ? WHERE id = ?')
            ->execute([$v['plans'], $v['expires_at'], $v['max_uses'], $v['max_uses_per_customer'], $v['notes'], $c['id']]);
        audit('coupon.updated', $c['code'] . ' plans=' . $v['plans'] . ' expires=' . ($v['expires_at'] ?? 'never')
            . ' max=' . ($v['max_uses'] ?? '∞') . ' per_customer=' . ($v['max_uses_per_customer'] ?? '∞'));
        back_to('coupons.php', 'Coupon ' . $c['code'] . ' updated.');
    }
    back_to('coupons.php', 'Choose an action.', false);
}

function coupon_state(array $c): array
{
    if ($c['revoked_at']) {
        return ['revoked', 'Revoked'];
    }
    if (!(int)$c['active']) {
        return ['inactive', 'Inactive'];
    }
    if ($c['expires_at'] && strtotime($c['expires_at'] . ' UTC') <= time()) {
        return ['expired', 'Expired'];
    }
    if ($c['max_uses'] !== null && (int)$c['used_count'] >= (int)$c['max_uses']) {
        return ['used_up', 'Used up'];
    }
    return ['active', 'Active'];
}

$rows = db()->query('SELECT * FROM coupons ORDER BY id DESC LIMIT 500')->fetchAll();
layout_top('Coupons', 'Discount codes customers enter at checkout.');
?>
<section class="card" aria-labelledby="newc">
  <h2 id="newc">Create a coupon</h2>
  <form method="post" class="form-grid" style="margin-top:12px">
    <?= csrf_field() ?><input type="hidden" name="action" value="create">
    <fieldset class="field" style="border:0;padding:0;margin:0 0 12px">
      <legend style="margin-bottom:5px">Discount</legend>
      <div class="seg" role="radiogroup">
        <?php foreach (COUPON_PERCENTS as $i => $pc): ?>
          <label><input type="radio" name="percent" value="<?= $pc ?>"<?= $i === 0 ? ' checked' : '' ?>><span><?= $pc ?> %</span></label>
        <?php endforeach; ?>
      </div>
    </fieldset>
    <label class="field">Code <span class="hint">leave empty to generate one</span>
      <input name="code" maxlength="40" data-suggest placeholder="Leave empty for SAVE10-XXXXXX" style="text-transform:uppercase"></label>
    <fieldset class="field" style="border:0;padding:0;margin:0 0 12px">
      <legend style="margin-bottom:5px">Applies to</legend>
      <?php foreach (PAID_PLANS as $pc): ?>
        <label class="check" style="margin:2px 0"><input type="checkbox" name="plans[]" value="<?= $pc ?>" checked> <?= e(plan_name($pc)) ?></label>
      <?php endforeach; ?>
    </fieldset>
    <label class="field">Expires <span class="hint">end of that day, UTC; empty = never</span><input type="date" name="expires_at"></label>
    <label class="field">Maximum total uses <span class="hint">empty = unlimited</span><input type="number" name="max_uses" min="1"></label>
    <label class="field">Maximum uses per customer <span class="hint">by email</span><input type="number" name="max_uses_per_customer" min="1" value="1"></label>
    <label class="field">Internal notes<input name="notes" maxlength="500" placeholder="Where this coupon was shared"></label>
    <label class="check"><input type="checkbox" name="active" value="1" checked> Active now</label>
    <div><button class="btn btn-primary">Create coupon</button></div>
  </form>
</section>

<section class="card">
  <div class="card-head"><h2>All coupons</h2><span class="muted"><?= count($rows) ?> coupon<?= count($rows) === 1 ? '' : 's' ?></span></div>
  <?php if (!$rows): ?><p class="empty">No coupons yet. Create one above and share its code.</p><?php else: ?>
  <div class="table-wrap"><table class="data">
    <thead><tr><th>Code</th><th class="num">Off</th><th>Plans</th><th>State</th><th class="num">Used</th>
      <th>Expires</th><th>Created</th><th>Actions</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $c): [$state, $label] = coupon_state($c); ?>
      <tr>
        <td><code><?= e($c['code']) ?></code> <button class="copy" data-copy="<?= e($c['code']) ?>" aria-label="Copy code" title="Copy"><?= icon('copy') ?></button>
          <?php if ($c['notes']): ?><div class="small muted"><?= e($c['notes']) ?></div><?php endif; ?></td>
        <td class="num"><b><?= (int)$c['percent'] ?> %</b></td>
        <td><?php foreach (coupon_plans($c) as $pc) { echo plan_badge($pc) . ' '; } ?></td>
        <td><?= state_chip($state, $label) ?></td>
        <td class="num"><a href="payments.php?q=<?= rawurlencode((string)$c['code']) ?>"><?= (int)$c['used_count'] ?></a>
          / <?= $c['max_uses'] === null ? '∞' : (int)$c['max_uses'] ?>
          <div class="small muted"><?= $c['max_uses_per_customer'] === null ? 'no per-customer limit' : (int)$c['max_uses_per_customer'] . ' per customer' ?></div></td>
        <td><?= $c['expires_at'] ? e(substr((string)$c['expires_at'], 0, 10)) : '<span class="muted">never</span>' ?></td>
        <td><?= when($c['created_at']) ?><?= $c['created_by'] ? '<div class="small muted">by ' . e($c['created_by']) . '</div>' : '' ?></td>
        <td class="actions">
          <form method="post" class="row-actions">
            <?= csrf_field() ?><input type="hidden" name="code" value="<?= e($c['code']) ?>">
            <?php if (!$c['revoked_at']): ?>
              <?php if ((int)$c['active']): ?><button class="btn btn-sm" name="action" value="deactivate">Deactivate</button>
              <?php else: ?><button class="btn btn-sm btn-good" name="action" value="activate">Activate</button><?php endif; ?>
              <button class="btn btn-sm btn-danger" name="action" value="revoke"<?= confirm_attr('Revoke coupon ' . $c['code'] . ' permanently?') ?>>Revoke</button>
            <?php endif; ?>
          </form>
          <?php if (!$c['revoked_at']): ?>
          <details class="more small"><summary>Edit limits</summary>
            <form method="post">
              <?= csrf_field() ?><input type="hidden" name="code" value="<?= e($c['code']) ?>"><input type="hidden" name="action" value="update">
              <?php foreach (PAID_PLANS as $pc): ?>
                <label class="check"><input type="checkbox" name="plans[]" value="<?= $pc ?>"<?= in_array($pc, coupon_plans($c), true) ? ' checked' : '' ?>> <?= e(plan_name($pc)) ?></label>
              <?php endforeach; ?>
              <label class="field">Expires<input type="date" name="expires_at" value="<?= e(substr((string)$c['expires_at'], 0, 10)) ?>"></label>
              <label class="field">Maximum total uses<input type="number" name="max_uses" min="1" value="<?= e((string)$c['max_uses']) ?>"></label>
              <label class="field">Per customer<input type="number" name="max_uses_per_customer" min="1" value="<?= e((string)$c['max_uses_per_customer']) ?>"></label>
              <label class="field">Notes<input name="notes" maxlength="500" value="<?= e($c['notes'] ?? '') ?>"></label>
              <button class="btn btn-sm btn-primary">Save</button>
            </form>
          </details>
          <?php endif; ?>
        </td>
      </tr>
    <?php endforeach; ?>
    </tbody></table></div>
  <?php endif; ?>
</section>
<?php layout_bottom(); ?>
