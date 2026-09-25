<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/license.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * Licences: Pro and Unlimited for Team are separate licence types. Each
 * licence carries its own device limit; activated computers are listed per
 * licence and can be removed one by one.
 */
if (admin_post()) {
    $id  = (int)($_POST['id'] ?? 0);
    $act = (string)($_POST['action'] ?? '');
    $to  = $id > 0 && ($_POST['from'] ?? '') === 'detail' ? 'licenses.php?id=' . $id : 'licenses.php';
    $pdo = db();

    if ($act === 'create') {
        $email = strtolower(trim((string)($_POST['email'] ?? '')));
        $name  = mb_substr(trim((string)($_POST['customer_name'] ?? '')), 0, 190);
        $plan  = (string)($_POST['tier'] ?? 'pro');
        if (!plan_is_paid($plan)) {
            $plan = 'pro';   // the original form also offered 'free'; Free needs no licence now
        }
        $p = plan_get($plan);
        $days = max(1, min(3650, (int)($_POST['days'] ?? ($p['period_days'] ?? SUBSCRIPTION_DAYS))));
        $maxIn = trim((string)($_POST['max_devices'] ?? ''));
        $maxd = $maxIn === '' ? (int)($p['device_limit'] ?? ($plan === 'team' ? 3 : 1)) : max(1, min(100, (int)$maxIn));
        if (!valid_email($email)) {
            back_to('licenses.php', 'Enter a valid customer email.', false);
        }
        $serial = unique_serial();
        $pdo->prepare("INSERT INTO licenses (serial, email, customer_name, tier, status, expires_at, max_devices,
                       source, notes, created_at, updated_at) VALUES (?,?,?,?,'active',?,?,'manual',?,?,?)")
            ->execute([$serial, $email, $name !== '' ? $name : null, $plan, days_from_now($days), $maxd,
                       mb_substr(trim((string)($_POST['notes'] ?? '')), 0, 2000) ?: null, now(), now()]);
        $newId = (int)$pdo->lastInsertId();
        audit('license.manual', $email . ' ' . $plan . ' ' . $days . 'd devices=' . $maxd, $newId);
        back_to('licenses.php?id=' . $newId, 'Created ' . plan_name($plan) . ' licence ' . $serial . '.');
    }

    $lic = $id > 0 ? license_by_id($id) : null;
    if (!$lic) {
        back_to('licenses.php', 'That licence no longer exists.', false);
    }
    $msg = '';
    switch ($act) {
        case 'extend':
        case 'renew':
            $d = $act === 'renew'
                ? max(1, (int)(plan_get((string)$lic['tier'])['period_days'] ?? SUBSCRIPTION_DAYS))
                : max(1, min(3650, (int)($_POST['days'] ?? 30)));
            $pdo->prepare("UPDATE licenses SET expires_at = DATE_ADD(GREATEST(expires_at, UTC_TIMESTAMP()), INTERVAL ? DAY),
                           status = 'active', revoked_at = NULL, renewed_at = ?, updated_at = ? WHERE id = ?")
                ->execute([$d, now(), now(), $id]);
            audit($act === 'renew' ? 'license.renewed' : 'license.extended', $d . 'd', $id);
            $msg = ($act === 'renew' ? 'Renewed' : 'Extended') . ' by ' . $d . ' days.';
            break;
        case 'block':
            $pdo->prepare("UPDATE licenses SET status = 'blocked', updated_at = ? WHERE id = ?")->execute([now(), $id]);
            audit('license.blocked', 'deactivated by admin', $id);
            $msg = 'Licence deactivated. Its computers switch to the Free plan at their next check-in.';
            break;
        case 'unblock':
            $pdo->prepare("UPDATE licenses SET status = 'active', revoked_at = NULL, updated_at = ? WHERE id = ?")->execute([now(), $id]);
            audit('license.unblocked', 'activated by admin', $id);
            $msg = 'Licence activated again.';
            break;
        case 'revoke':
            $pdo->prepare("UPDATE licenses SET status = 'revoked', revoked_at = ?, updated_at = ? WHERE id = ?")
                ->execute([now(), now(), $id]);
            audit('license.revoked', 'by admin', $id);
            $msg = 'Licence revoked. Its computers switch to the Free plan at their next check-in.';
            break;
        case 'reset_device':
            foreach (license_devices($id) as $dev) {
                license_release_device($id, (string)$dev['device_hash'], 'removed');
            }
            $pdo->prepare('UPDATE licenses SET device_hash = NULL, device_label = NULL, updated_at = ? WHERE id = ?')
                ->execute([now(), $id]);
            audit('license.device_reset', 'all computers removed', $id);
            $msg = 'All computers removed from this licence.';
            break;
        case 'remove_device':
            $devHash = clean_hex($_POST['device'] ?? '');
            if (strlen($devHash) === 64 && license_release_device($id, $devHash, 'removed')) {
                audit('license.device_removed', substr($devHash, 0, 12), $id);
                $msg = 'Computer removed. It can be registered again if a seat is free.';
            } else {
                back_to($to, 'That computer is not active on this licence.', false);
            }
            break;
        case 'set_devices':
            $maxd = (int)($_POST['max_devices'] ?? 0);
            if ($maxd < 1 || $maxd > 100) {
                back_to($to, 'Device limit must be between 1 and 100.', false);
            }
            $pdo->prepare('UPDATE licenses SET max_devices = ?, updated_at = ? WHERE id = ?')->execute([$maxd, now(), $id]);
            audit('license.max_devices', (string)$maxd, $id);
            $msg = 'Device limit set to ' . $maxd . '.';
            break;
        case 'set_plan':
            $plan = (string)($_POST['tier'] ?? '');
            if (!plan_is_paid($plan)) {
                back_to($to, 'Choose Pro or Unlimited for Team.', false);
            }
            $maxd = (int)(plan_get($plan)['device_limit'] ?? ($plan === 'team' ? 3 : 1));
            $pdo->prepare('UPDATE licenses SET tier = ?, max_devices = ?, updated_at = ? WHERE id = ?')
                ->execute([$plan, $maxd, now(), $id]);
            audit('license.plan_changed', $lic['tier'] . ' -> ' . $plan, $id);
            $msg = 'Licence type changed to ' . plan_name($plan) . ' (' . $maxd . ' computer' . ($maxd === 1 ? '' : 's') . ').';
            break;
        case 'save_notes':
            $pdo->prepare('UPDATE licenses SET notes = ?, customer_name = ?, updated_at = ? WHERE id = ?')
                ->execute([mb_substr(trim((string)($_POST['notes'] ?? '')), 0, 4000) ?: null,
                           mb_substr(trim((string)($_POST['customer_name'] ?? '')), 0, 190) ?: null, now(), $id]);
            audit('license.notes', '', $id);
            $msg = 'Customer details saved.';
            break;
        case 'delete':
            $pdo->prepare('DELETE FROM license_devices WHERE license_id = ?')->execute([$id]);
            $pdo->prepare('DELETE FROM licenses WHERE id = ?')->execute([$id]);
            audit('license.deleted', (string)$lic['serial'], $id);
            back_to('licenses.php', 'Licence deleted.');
        default:
            back_to($to, 'Choose an action.', false);
    }
    back_to($to, $msg);
}

$plans = plans_all();

// ------------------------------------------------------------ detail view
if (!empty($_GET['id'])) {
    $lic = license_by_id((int)$_GET['id']);
    if (!$lic) {
        back_to('licenses.php', 'That licence no longer exists.', false);
    }
    $state = effective_state($lic);
    $devs = db()->prepare('SELECT * FROM license_devices WHERE license_id = ? ORDER BY status = \'active\' DESC, id');
    $devs->execute([$lic['id']]);
    $devs = $devs->fetchAll();
    $used = license_device_count((int)$lic['id']);
    $pay = null;
    if (!empty($lic['payment_id'])) {
        $s = db()->prepare('SELECT * FROM payments WHERE id = ?');
        $s->execute([$lic['payment_id']]);
        $pay = $s->fetch() ?: null;
    }
    $ord = null;
    if (!empty($lic['order_id'])) {
        $s = db()->prepare('SELECT ref FROM orders WHERE id = ?');
        $s->execute([$lic['order_id']]);
        $ord = $s->fetchColumn() ?: null;
    }
    layout_top('Licence ' . mask_serial((string)$lic['serial']), plan_name((string)$lic['tier']) . ' · ' . $lic['email']);
    ?>
    <p><a href="licenses.php">← All licences</a></p>
    <div class="grid grid-2">
      <section class="card" aria-labelledby="ld">
        <div class="card-head"><h2 id="ld">Licence</h2><?= plan_badge((string)$lic['tier']) ?> <?= state_chip($state['state']) ?></div>
        <dl class="kv">
          <dt>Licence key</dt><dd><code><?= e($lic['serial']) ?></code>
            <button class="copy" data-copy="<?= e($lic['serial']) ?>" aria-label="Copy licence key" title="Copy"><?= icon('copy') ?></button></dd>
          <dt>Type</dt><dd><?= e(plan_name((string)$lic['tier'])) ?> <span class="muted small">(source: <?= e($lic['source']) ?>)</span></dd>
          <dt>Status</dt><dd><?= e($state['message'] ?: 'Active') ?></dd>
          <dt>Created</dt><dd><?= e($lic['created_at']) ?> UTC</dd>
          <dt>First activated</dt><dd><?= $lic['activated_at'] ? e($lic['activated_at']) . ' UTC' : '<span class="muted">not yet</span>' ?></dd>
          <dt>Expires</dt><dd><?= e($lic['expires_at']) ?> UTC · <?= e(remaining($lic['expires_at'])) ?></dd>
          <?php if (!empty($lic['renewed_at'])): ?><dt>Last renewed</dt><dd><?= e($lic['renewed_at']) ?> UTC</dd><?php endif; ?>
          <?php if (!empty($lic['revoked_at'])): ?><dt>Revoked</dt><dd><?= e($lic['revoked_at']) ?> UTC</dd><?php endif; ?>
          <dt>Computers</dt><dd><?= $used ?> of <?= (int)$lic['max_devices'] ?> in use</dd>
          <dt>Last validation</dt><dd><?= when($lic['last_validated_at'] ?? null) ?></dd>
          <dt>App version</dt><dd><?= e($lic['app_version'] ?: '—') ?></dd>
          <dt>Payment</dt><dd><?= $pay ? '<a href="payments.php?q=' . rawurlencode((string)$pay['external_id']) . '">#' . (int)$pay['id'] . '</a> '
              . e(number_format((float)$pay['amount'], 2) . ' ' . $pay['currency']) : '<span class="muted">none linked</span>' ?>
              <?= $ord ? ' · order <code>' . e($ord) . '</code>' : '' ?></dd>
          <dt>Coupon</dt><dd><?= !empty($lic['coupon_code']) ? '<code>' . e($lic['coupon_code']) . '</code>' : '<span class="muted">none</span>' ?></dd>
        </dl>
      </section>

      <section class="card" aria-labelledby="la">
        <h2 id="la">Actions</h2>
        <form method="post" class="toolbar">
          <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$lic['id'] ?>"><input type="hidden" name="from" value="detail">
          <button class="btn btn-primary" name="action" value="renew"<?= confirm_attr('Renew this licence by one ' . plan_name((string)$lic['tier']) . ' period?') ?>>Renew one period</button>
          <?php if ($lic['status'] === 'active'): ?>
            <button class="btn btn-danger" name="action" value="block"<?= confirm_attr('Deactivate this licence? Its computers fall back to the Free plan.') ?>>Deactivate</button>
          <?php else: ?>
            <button class="btn btn-good" name="action" value="unblock"<?= confirm_attr('Activate this licence again?') ?>>Activate</button>
          <?php endif; ?>
          <?php if ($lic['status'] !== 'revoked'): ?>
            <button class="btn btn-danger" name="action" value="revoke"<?= confirm_attr('Revoke this licence? This is meant for refunds and abuse.') ?>>Revoke</button>
          <?php endif; ?>
        </form>
        <form method="post" class="toolbar">
          <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$lic['id'] ?>"><input type="hidden" name="from" value="detail">
          <label class="field">Extend by days<input type="number" name="days" min="1" max="3650" value="30"></label>
          <button class="btn" name="action" value="extend">Extend</button>
        </form>
        <form method="post" class="toolbar">
          <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$lic['id'] ?>"><input type="hidden" name="from" value="detail">
          <label class="field">Licence type
            <select name="tier"><?php foreach (PAID_PLANS as $c): ?><option value="<?= $c ?>"<?= $lic['tier'] === $c ? ' selected' : '' ?>><?= e(plan_name($c)) ?></option><?php endforeach; ?></select></label>
          <button class="btn" name="action" value="set_plan"<?= confirm_attr('Change the licence type? The device limit is reset to that plan\'s limit.') ?>>Change type</button>
        </form>
        <form method="post" class="toolbar">
          <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$lic['id'] ?>"><input type="hidden" name="from" value="detail">
          <label class="field">Computer limit<input type="number" name="max_devices" min="1" max="100" value="<?= (int)$lic['max_devices'] ?>"></label>
          <button class="btn" name="action" value="set_devices">Save limit</button>
        </form>
        <form method="post">
          <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$lic['id'] ?>"><input type="hidden" name="from" value="detail">
          <label class="field">Customer name<input name="customer_name" value="<?= e($lic['customer_name'] ?? '') ?>" maxlength="190"></label>
          <label class="field">Internal notes<textarea name="notes" maxlength="4000"><?= e($lic['notes'] ?? '') ?></textarea></label>
          <button class="btn" name="action" value="save_notes">Save details</button>
        </form>
      </section>
    </div>

    <section class="card" aria-labelledby="dv">
      <div class="card-head"><h2 id="dv">Computers</h2>
        <?php if ($used): ?>
        <form method="post"><?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$lic['id'] ?>"><input type="hidden" name="from" value="detail">
          <button class="btn btn-danger btn-sm" name="action" value="reset_device"<?= confirm_attr('Remove every computer from this licence?') ?>>Remove all</button></form>
        <?php endif; ?>
      </div>
      <?php if (!$devs): ?><p class="empty">No computer has been registered with this key yet.</p><?php else: ?>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Computer</th><th>State</th><th>Registered</th><th>Last check-in</th><th>Version</th><th></th></tr></thead>
        <tbody>
        <?php foreach ($devs as $d): ?>
          <tr>
            <td><?= e($d['device_label'] ?: 'Unnamed computer') ?><div class="small muted mono"><?= e(substr((string)$d['device_hash'], 0, 16)) ?>…</div></td>
            <td><?= state_chip((string)$d['status']) ?></td>
            <td><?= when($d['activated_at']) ?></td>
            <td><?= when($d['last_seen']) ?></td>
            <td><?= e($d['app_version'] ?: '—') ?></td>
            <td class="actions"><?php if ($d['status'] === 'active'): ?>
              <form method="post"><?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$lic['id'] ?>">
                <input type="hidden" name="from" value="detail"><input type="hidden" name="device" value="<?= e($d['device_hash']) ?>">
                <button class="btn btn-sm btn-danger" name="action" value="remove_device"<?= confirm_attr('Remove this computer from the licence?') ?>>Remove</button></form>
            <?php endif; ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody></table></div>
      <?php endif; ?>
    </section>

    <section class="card"><h2>Danger zone</h2>
      <p class="muted small">Deleting removes the licence record permanently. Prefer Revoke, which keeps the history.</p>
      <form method="post"><?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$lic['id'] ?>">
        <button class="btn btn-danger" name="action" value="delete"<?= confirm_attr('Delete this licence permanently? This cannot be undone.') ?>>Delete licence</button></form>
    </section>
    <?php
    layout_bottom();
    exit;
}

// -------------------------------------------------------------- list view
$q      = trim((string)($_GET['q'] ?? ''));
$plan   = (string)($_GET['plan'] ?? 'all');
$filter = (string)($_GET['f'] ?? 'all');
$page   = max(1, (int)($_GET['p'] ?? 1));
$per    = 25;

$where = [];
$args = [];
if ($q !== '') {
    $where[] = '(serial LIKE ? OR email LIKE ? OR customer_name LIKE ?)';
    array_push($args, '%' . $q . '%', '%' . $q . '%', '%' . $q . '%');
}
if (in_array($plan, PLAN_CODES, true)) {
    $where[] = 'tier = ?';
    $args[] = $plan;
}
$filters = ['all' => 'Any state', 'active' => 'Active', 'pro' => 'Active paid', 'expiring' => 'Ending in 5 days',
            'expired' => 'Expired', 'blocked' => 'Deactivated or revoked', 'trial' => 'Legacy trials', 'online' => 'Seen in 10 min'];
switch ($filter) {
    case 'active':   $where[] = "status = 'active' AND expires_at > UTC_TIMESTAMP()"; break;
    case 'pro':      $where[] = "tier IN ('pro','team') AND status = 'active' AND expires_at > UTC_TIMESTAMP()"; break;
    case 'expiring': $where[] = "status = 'active' AND expires_at BETWEEN UTC_TIMESTAMP() AND DATE_ADD(UTC_TIMESTAMP(), INTERVAL 5 DAY)"; break;
    case 'expired':  $where[] = 'expires_at <= UTC_TIMESTAMP()'; break;
    case 'blocked':  $where[] = "status <> 'active'"; break;
    case 'trial':    $where[] = "source = 'trial'"; break;
    case 'online':   $where[] = 'last_seen > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 10 MINUTE)'; break;
}
$sql = 'FROM licenses' . ($where ? ' WHERE ' . implode(' AND ', $where) : '');
$cnt = db()->prepare('SELECT COUNT(*) ' . $sql);
$cnt->execute($args);
$total = (int)$cnt->fetchColumn();
$st = db()->prepare('SELECT *, (SELECT COUNT(*) FROM license_devices d WHERE d.license_id = licenses.id AND d.status = \'active\') AS used '
    . $sql . ' ORDER BY id DESC LIMIT ' . $per . ' OFFSET ' . (($page - 1) * $per));
$st->execute($args);
$rows = $st->fetchAll();

layout_top('Licences', 'Pro and Unlimited for Team keys, their computers and their state.');
?>
<section class="card" aria-labelledby="mk">
  <details class="more"<?= $total === 0 ? ' open' : '' ?>><summary id="mk">Create a licence by hand</summary>
  <form method="post" class="form-grid" style="margin-top:12px">
    <?= csrf_field() ?><input type="hidden" name="action" value="create">
    <label class="field">Customer email<input name="email" type="email" required placeholder="customer@email.com"></label>
    <label class="field">Customer name <span class="hint">optional</span><input name="customer_name" maxlength="190"></label>
    <label class="field">Licence type
      <select name="tier"><?php foreach (PAID_PLANS as $c): $pp = plan_get($c); ?>
        <option value="<?= $c ?>"><?= e(plan_name($c)) ?> — <?= (int)($pp['device_limit'] ?? 1) ?> computer<?= (int)($pp['device_limit'] ?? 1) === 1 ? '' : 's' ?></option><?php endforeach; ?></select></label>
    <label class="field">Days of access<input name="days" type="number" value="<?= (int)(plan_get('pro')['period_days'] ?? SUBSCRIPTION_DAYS) ?>" min="1" max="3650"></label>
    <label class="field">Computer limit <span class="hint">blank = plan default</span><input name="max_devices" type="number" min="1" max="100" placeholder="plan default"></label>
    <label class="field">Notes <span class="hint">internal</span><input name="notes" maxlength="2000"></label>
    <div><button class="btn btn-primary">Create licence key</button></div>
  </form>
  </details>
</section>

<section class="card">
  <form method="get" class="toolbar" role="search">
    <label class="field">Search<input name="q" value="<?= e($q) ?>" placeholder="Key, email or name"></label>
    <label class="field">Plan<select name="plan">
      <option value="all">Any plan</option>
      <?php foreach (PLAN_CODES as $c): ?><option value="<?= $c ?>"<?= $plan === $c ? ' selected' : '' ?>><?= e(plan_name($c)) ?></option><?php endforeach; ?>
    </select></label>
    <label class="field">State<select name="f">
      <?php foreach ($filters as $k => $v): ?><option value="<?= $k ?>"<?= $filter === $k ? ' selected' : '' ?>><?= e($v) ?></option><?php endforeach; ?>
    </select></label>
    <button class="btn">Filter</button>
    <span class="muted"><?= $total ?> licence<?= $total === 1 ? '' : 's' ?></span>
  </form>

  <?php if (!$rows): ?>
    <p class="empty">No licences match. Clear the filters, or create one above.</p>
  <?php else: ?>
  <div class="table-wrap"><table class="data">
    <thead><tr><th>Licence key</th><th>Customer</th><th>Plan</th><th>State</th><th>Ends</th>
      <th>Computers</th><th>Last validation</th><th>Actions</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r): $state = effective_state($r); ?>
      <tr>
        <td><a class="mono" href="?id=<?= (int)$r['id'] ?>"><?= e($r['serial']) ?></a>
          <button class="copy" data-copy="<?= e($r['serial']) ?>" aria-label="Copy licence key" title="Copy"><?= icon('copy') ?></button></td>
        <td><?= e($r['email']) ?><?php if (!empty($r['customer_name'])): ?><div class="small muted"><?= e($r['customer_name']) ?></div><?php endif; ?></td>
        <td><?= plan_badge((string)$r['tier']) ?></td>
        <td><?= state_chip($state['state']) ?></td>
        <td><?= e(remaining($r['expires_at'])) ?><div class="small muted"><?= e(substr((string)$r['expires_at'], 0, 10)) ?></div></td>
        <td><?= (int)$r['used'] ?> / <?= (int)$r['max_devices'] ?></td>
        <td><?= when($r['last_validated_at'] ?? null) ?></td>
        <td class="actions">
          <form method="post" class="row-actions">
            <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$r['id'] ?>">
            <label class="skip" for="act<?= (int)$r['id'] ?>">Action</label>
            <select name="action" id="act<?= (int)$r['id'] ?>" data-confirm-options>
              <option value="renew" data-confirm="Renew this licence by one plan period?">Renew one period</option>
              <option value="extend">Extend 30 days</option>
              <?php if ($r['status'] === 'active'): ?>
                <option value="block" data-confirm="Deactivate this licence? Its computers fall back to the Free plan.">Deactivate</option>
              <?php else: ?>
                <option value="unblock" data-confirm="Activate this licence again?">Activate</option>
              <?php endif; ?>
              <option value="reset_device" data-confirm="Remove every computer from this licence?">Remove all computers</option>
              <option value="revoke" data-confirm="Revoke this licence?">Revoke</option>
              <option value="delete" data-confirm="Delete this licence permanently? This cannot be undone.">Delete</option>
            </select>
            <input type="hidden" name="days" value="30">
            <button class="btn btn-sm">Apply</button>
            <a class="btn btn-sm btn-ghost" href="?id=<?= (int)$r['id'] ?>">Details</a>
          </form>
        </td>
      </tr>
    <?php endforeach; ?>
    </tbody></table></div>
  <?php endif; ?>
  <?= pager($total, $per, $page, ['q' => $q, 'plan' => $plan, 'f' => $filter]) ?>
</section>
<?php layout_bottom(); ?>
