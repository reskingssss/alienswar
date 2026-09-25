<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/orders.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * Payments. A paid licence is only ever issued after the payment is
 * confirmed: by the provider (PayPal capture / webhook, crypto IPN) or by
 * an admin approving a manual payment here.
 */
const PAYMENT_METHODS = ['usdt' => 'USDT transfer', 'whatsapp' => 'WhatsApp', 'telegram' => 'Telegram',
                         'facebook' => 'Facebook', 'bank' => 'Bank transfer', 'cash' => 'Cash', 'other' => 'Other'];

function payment_row(int $id): ?array
{
    $st = db()->prepare('SELECT * FROM payments WHERE id = ?');
    $st->execute([$id]);
    return $st->fetch() ?: null;
}

function payment_note(int $id, string $text): void
{
    $line = '[' . now() . ' UTC · ' . admin_actor() . '] ' . $text;
    db()->prepare("UPDATE payments SET notes = CONCAT(COALESCE(notes, ''), IF(notes IS NULL OR notes = '', '', '\n'), ?),
                   updated_at = ? WHERE id = ?")->execute([mb_substr($line, 0, 1000), now(), $id]);
}

function payment_filters(): array
{
    $f = [
        'q'      => trim((string)($_GET['q'] ?? '')),
        'status' => (string)($_GET['status'] ?? 'all'),
        'plan'   => (string)($_GET['plan'] ?? 'all'),
        'from'   => (string)($_GET['from'] ?? ''),
        'to'     => (string)($_GET['to'] ?? ''),
    ];
    $where = [];
    $args = [];
    if ($f['q'] !== '') {
        $where[] = '(p.email LIKE ? OR p.external_id LIKE ? OR p.customer_name LIKE ? OR o.ref LIKE ? OR l.serial LIKE ? OR p.coupon_code LIKE ?)';
        for ($i = 0; $i < 6; $i++) {
            $args[] = '%' . $f['q'] . '%';
        }
    }
    $statusMap = ['open' => ['pending', 'review'], 'completed' => ['completed'], 'pending' => ['pending'],
                  'review' => ['review'], 'rejected' => ['rejected'], 'failed' => ['failed'], 'refunded' => ['refunded']];
    if (isset($statusMap[$f['status']])) {
        $where[] = 'p.status IN (' . implode(',', array_fill(0, count($statusMap[$f['status']]), '?')) . ')';
        array_push($args, ...$statusMap[$f['status']]);
    }
    if (in_array($f['plan'], PAID_PLANS, true)) {
        $where[] = 'p.plan_code = ?';
        $args[] = $f['plan'];
    }
    if (preg_match('/^\d{4}-\d{2}-\d{2}$/', $f['from'])) {
        $where[] = 'p.created_at >= ?';
        $args[] = $f['from'] . ' 00:00:00';
    }
    if (preg_match('/^\d{4}-\d{2}-\d{2}$/', $f['to'])) {
        $where[] = 'p.created_at <= ?';
        $args[] = $f['to'] . ' 23:59:59';
    }
    $sql = 'FROM payments p LEFT JOIN orders o ON o.id = p.order_id LEFT JOIN licenses l ON l.id = p.license_id'
         . ($where ? ' WHERE ' . implode(' AND ', $where) : '');
    return [$f, $sql, $args];
}

// ------------------------------------------------------------------ CSV
if (($_GET['export'] ?? '') === 'csv') {
    [$f, $sql, $args] = payment_filters();
    $st = db()->prepare('SELECT p.*, o.ref AS order_ref, l.serial ' . $sql . ' ORDER BY p.id DESC LIMIT 50000');
    $st->execute($args);
    audit('payments.exported', 'filters ' . json_encode($f));
    header('Content-Type: text/csv; charset=utf-8');
    header('Content-Disposition: attachment; filename="payments-' . gmdate('Ymd-His') . '.csv"');
    $out = fopen('php://output', 'w');
    fwrite($out, "\xEF\xBB\xBF");
    $cols = ['id', 'created_at', 'email', 'customer_name', 'plan_code', 'provider', 'method', 'external_id', 'order_ref',
             'original_amount', 'discount_amount', 'amount', 'currency', 'coupon_code', 'status', 'serial',
             'reviewed_by', 'reviewed_at', 'notes'];
    fputcsv($out, $cols);
    while ($r = $st->fetch()) {
        $line = [];
        foreach ($cols as $c) {
            $v = (string)($r[$c] ?? '');
            // spreadsheet formula injection guard
            $line[] = preg_match('/^[=+\-@\t\r]/', $v) ? "'" . $v : $v;
        }
        fputcsv($out, $line);
    }
    fclose($out);
    exit;
}

// ---------------------------------------------------------------- actions
if (admin_post()) {
    $act = (string)($_POST['action'] ?? '');
    $id = (int)($_POST['id'] ?? 0);
    $back = 'payments.php' . (!empty($_POST['qs']) ? '?' . preg_replace('/[^\w=&%.\-+@]/', '', (string)$_POST['qs']) : '');

    if ($act === 'add_manual') {
        $email = strtolower(trim((string)($_POST['email'] ?? '')));
        $plan = (string)($_POST['plan'] ?? 'pro');
        $method = array_key_exists($_POST['method'] ?? '', PAYMENT_METHODS) ? (string)$_POST['method'] : 'other';
        $ref = mb_substr(trim((string)($_POST['reference'] ?? '')), 0, 120);
        $amount = trim((string)($_POST['amount'] ?? ''));
        if (!plan_is_paid($plan)) {
            back_to('payments.php', 'Choose Pro or Unlimited for Team.', false);
        }
        if ($ref === '') {
            back_to('payments.php', 'Enter the payment reference (transaction id, message id or receipt number).', false);
        }
        if (!preg_match('/^\d{1,7}(\.\d{1,2})?$/', $amount)) {
            back_to('payments.php', 'Enter the amount received, for example 29.00.', false);
        }
        $made = order_create($plan, $email, (string)($_POST['customer_name'] ?? ''), (string)($_POST['coupon'] ?? ''), 'manual');
        if (!$made['ok']) {
            back_to('payments.php', $made['error'], false);
        }
        $o = $made['order'];
        $ext = 'admin:' . $o['ref'] . ':' . $ref;
        $pid = payment_upsert(['provider' => 'manual', 'external_id' => $ext, 'email' => $o['email'],
            'amount' => $amount, 'currency' => $o['currency'], 'status' => 'pending', 'order_id' => $o['id'],
            'plan_code' => $plan, 'original_amount' => $o['original_amount'], 'discount_amount' => $o['discount_amount'],
            'coupon_code' => $o['coupon_code'], 'customer_name' => $o['customer_name'], 'method' => $method,
            'notes' => 'Added by ' . admin_actor() . '. Reference: ' . $ref
                . (trim((string)($_POST['notes'] ?? '')) !== '' ? "\n" . mb_substr(trim((string)$_POST['notes']), 0, 500) : '')]);
        order_update((int)$o['id'], ['status' => 'awaiting_verification']);
        audit('payment.manual_added', $o['ref'] . ' ' . $amount . ' ' . $o['currency'] . ' ' . $method);
        if (($_POST['approve_now'] ?? '') === '1') {
            $r = order_fulfil(order_by_id((int)$o['id']), 'manual', $ext, (float)$amount, (string)$o['currency'], '', $method);
            if (!$r['ok']) {
                back_to('payments.php?status=open', 'Payment saved, but the amount does not cover the order total of '
                    . $o['final_amount'] . ' ' . $o['currency'] . '. It is waiting for review.', false);
            }
            db()->prepare('UPDATE payments SET reviewed_by = ?, reviewed_at = ? WHERE id = ?')->execute([admin_actor(), now(), $pid]);
            back_to('payments.php', 'Payment approved. Licence ' . $r['license']['serial'] . ' was issued to ' . $o['email'] . '.');
        }
        back_to('payments.php?status=open', 'Manual payment saved as pending. Approve it once you have verified it.');
    }

    $p = $id > 0 ? payment_row($id) : null;
    if (!$p) {
        back_to($back, 'That payment no longer exists.', false);
    }
    if ($act === 'approve') {
        if ($p['status'] === 'completed') {
            back_to($back, 'This payment was already approved.', false);
        }
        if ($p['order_id'] && ($o = order_by_id((int)$p['order_id']))) {
            $amount = (float)$p['amount'];
            if ($p['status'] === 'review') {
                // an admin accepting a short or different payment on purpose
                payment_note($id, 'Approved despite amount/currency mismatch (received ' . $p['amount'] . ' ' . $p['currency'] . ').');
                $amount = (float)$o['final_amount'];
                db()->prepare('UPDATE payments SET currency = ? WHERE id = ?')->execute([$o['currency'], $id]);
                $p['currency'] = $o['currency'];
            }
            $r = order_fulfil($o, (string)$p['provider'], (string)$p['external_id'], $amount, (string)$p['currency'],
                '', (string)($p['method'] ?? ''));
            if (!$r['ok']) {
                back_to($back, 'Could not approve: ' . $r['error'] . '.', false);
            }
            $lic = $r['license'];
        } else {
            // payments recorded by the previous version have no order: original behaviour
            if (!valid_email($p['email'])) {
                back_to($back, 'This payment has no valid customer email, so no licence can be issued.', false);
            }
            $lic = issue_license((string)$p['email'], (string)$p['provider'], 'manual-' . $p['id'],
                plan_is_paid((string)$p['plan_code']) ? (string)$p['plan_code'] : 'pro', ['payment_id' => $id]);
            db()->prepare("UPDATE payments SET status = 'completed', license_id = ?, updated_at = ? WHERE id = ?")
                ->execute([$lic['id'], now(), $id]);
        }
        db()->prepare('UPDATE payments SET reviewed_by = ?, reviewed_at = ? WHERE id = ?')->execute([admin_actor(), now(), $id]);
        audit('payment.approved', '#' . $id . ' ' . $p['email'], (int)$lic['id']);
        back_to($back, 'Approved. Licence ' . $lic['serial'] . ' (' . plan_name((string)$lic['tier']) . ') is active.');
    }
    if ($act === 'reject' || $act === 'pending') {
        if ($p['status'] === 'completed') {
            back_to($back, 'An approved payment cannot be changed here. Revoke the licence instead if it was refunded.', false);
        }
        $new = $act === 'reject' ? 'rejected' : 'pending';
        db()->prepare('UPDATE payments SET status = ?, reviewed_by = ?, reviewed_at = ?, updated_at = ? WHERE id = ?')
            ->execute([$new, admin_actor(), now(), now(), $id]);
        if ($p['order_id']) {
            order_update((int)$p['order_id'], $new === 'rejected'
                ? ['status' => 'failed', 'failure_reason' => 'The payment could not be verified.']
                : ['status' => 'awaiting_verification', 'failure_reason' => null]);
        }
        payment_note($id, $new === 'rejected' ? 'Marked rejected.' : 'Marked pending.');
        audit('payment.' . $new, '#' . $id);
        back_to($back, $new === 'rejected' ? 'Payment rejected. No licence was issued.' : 'Payment marked as pending.');
    }
    if ($act === 'note') {
        $text = trim((string)($_POST['note'] ?? ''));
        if ($text === '') {
            back_to($back, 'Write a note first.', false);
        }
        payment_note($id, $text);
        audit('payment.note', '#' . $id);
        back_to($back, 'Note added.');
    }
    back_to($back, 'Choose an action.', false);
}

// ------------------------------------------------------------------ list
[$f, $sql, $args] = payment_filters();
$page = max(1, (int)($_GET['p'] ?? 1));
$per = 30;
$cnt = db()->prepare('SELECT COUNT(*) ' . $sql);
$cnt->execute($args);
$total = (int)$cnt->fetchColumn();
$st = db()->prepare('SELECT p.*, o.ref AS order_ref, o.final_amount AS order_total, l.serial, l.tier AS lic_tier '
    . $sql . ' ORDER BY p.id DESC LIMIT ' . $per . ' OFFSET ' . (($page - 1) * $per));
$st->execute($args);
$rows = $st->fetchAll();
$qs = http_build_query(array_filter($f, static fn($v) => $v !== '' && $v !== 'all'));
$statusLabels = ['completed' => 'Approved', 'pending' => 'Pending', 'review' => 'Needs review', 'rejected' => 'Rejected',
                 'failed' => 'Failed', 'refunded' => 'Refunded'];

layout_top('Payments', 'Every payment, what it bought, and whether a licence was issued.');
?>
<section class="card" aria-labelledby="addp">
  <details class="more"><summary id="addp">Record a manual payment</summary>
    <p class="muted small">For payments arranged on WhatsApp, Telegram, Facebook or by transfer. The total is
      calculated from the plan and coupon; a licence is only issued when the payment is approved.</p>
    <form method="post" class="form-grid">
      <?= csrf_field() ?><input type="hidden" name="action" value="add_manual">
      <label class="field">Customer email<input type="email" name="email" required></label>
      <label class="field">Customer name <span class="hint">optional</span><input name="customer_name" maxlength="190"></label>
      <label class="field">Plan<select name="plan"><?php foreach (PAID_PLANS as $c): $pp = plan_get($c); ?>
        <option value="<?= $c ?>"><?= e(plan_name($c)) ?> — <?= e(money((float)($pp['current_price'] ?? 0), (string)($pp['currency'] ?? 'USD'))) ?></option><?php endforeach; ?></select></label>
      <label class="field">Coupon <span class="hint">optional</span><input name="coupon" maxlength="40"></label>
      <label class="field">Amount received<input name="amount" inputmode="decimal" required placeholder="29.00"></label>
      <label class="field">Method<select name="method"><?php foreach (PAYMENT_METHODS as $k => $v): ?><option value="<?= $k ?>"><?= e($v) ?></option><?php endforeach; ?></select></label>
      <label class="field">Reference<input name="reference" required maxlength="120" placeholder="Transaction id or message id"></label>
      <label class="field">Notes <span class="hint">internal</span><input name="notes" maxlength="500"></label>
      <label class="check"><input type="checkbox" name="approve_now" value="1"> I have verified it — approve and issue the licence now</label>
      <div><button class="btn btn-primary">Save payment</button></div>
    </form>
  </details>
</section>

<section class="card">
  <form method="get" class="toolbar" role="search">
    <label class="field">Search<input name="q" value="<?= e($f['q']) ?>" placeholder="Email, reference, order, key, coupon"></label>
    <label class="field">Status<select name="status">
      <?php foreach (['all' => 'Any status', 'open' => 'Needs action', 'completed' => 'Approved', 'pending' => 'Pending',
                      'review' => 'Needs review', 'rejected' => 'Rejected', 'failed' => 'Failed', 'refunded' => 'Refunded'] as $k => $v): ?>
        <option value="<?= $k ?>"<?= $f['status'] === $k ? ' selected' : '' ?>><?= e($v) ?></option><?php endforeach; ?></select></label>
    <label class="field">Plan<select name="plan"><option value="all">Any plan</option>
      <?php foreach (PAID_PLANS as $c): ?><option value="<?= $c ?>"<?= $f['plan'] === $c ? ' selected' : '' ?>><?= e(plan_name($c)) ?></option><?php endforeach; ?></select></label>
    <label class="field">From<input type="date" name="from" value="<?= e($f['from']) ?>"></label>
    <label class="field">To<input type="date" name="to" value="<?= e($f['to']) ?>"></label>
    <button class="btn">Filter</button>
    <a class="btn btn-ghost" href="?<?= e($qs . ($qs ? '&' : '') . 'export=csv') ?>">Export CSV</a>
    <span class="muted"><?= $total ?> payment<?= $total === 1 ? '' : 's' ?></span>
  </form>

  <?php if (!$rows): ?>
    <p class="empty">No payments match these filters.</p>
  <?php else: ?>
  <div class="table-wrap"><table class="data">
    <thead><tr><th>Received</th><th>Customer</th><th>Plan</th><th>Method &amp; reference</th>
      <th class="num">Price</th><th class="num">Discount</th><th class="num">Paid</th><th>Status</th><th>Licence</th><th>Actions</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r):
        $open = in_array($r['status'], ['pending', 'review'], true) || !in_array($r['status'], ['completed', 'rejected', 'failed', 'refunded'], true); ?>
      <tr>
        <td><?= when($r['created_at']) ?><div class="small muted">#<?= (int)$r['id'] ?></div></td>
        <td><?= e($r['email'] ?? '—') ?><?php if (!empty($r['customer_name'])): ?><div class="small muted"><?= e($r['customer_name']) ?></div><?php endif; ?></td>
        <td><?= $r['plan_code'] ? plan_badge((string)$r['plan_code']) : '<span class="muted">—</span>' ?></td>
        <td><?= e($r['method'] ?: $r['provider']) ?>
          <div class="small muted mono" title="<?= e($r['external_id']) ?>"><?= e(mb_substr((string)$r['external_id'], 0, 30)) ?></div>
          <?php if ($r['order_ref']): ?><div class="small">Order <code><?= e($r['order_ref']) ?></code></div><?php endif; ?></td>
        <td class="num"><?= $r['original_amount'] !== null ? e(number_format((float)$r['original_amount'], 2)) : '—' ?></td>
        <td class="num"><?= (float)$r['discount_amount'] > 0 ? '−' . e(number_format((float)$r['discount_amount'], 2))
            . ($r['coupon_code'] ? '<div class="small muted"><code>' . e($r['coupon_code']) . '</code></div>' : '') : '—' ?></td>
        <td class="num"><b><?= e(number_format((float)$r['amount'], 2)) ?></b> <?= e($r['currency']) ?>
          <?php if ($r['order_total'] !== null && cents($r['order_total']) !== cents($r['amount'])): ?>
            <div class="small" style="color:var(--bad)">order total <?= e($r['order_total']) ?></div><?php endif; ?></td>
        <td><?= state_chip(in_array($r['status'], ['completed', 'pending', 'review', 'rejected', 'failed', 'refunded'], true) ? (string)$r['status'] : 'unknown',
              $statusLabels[$r['status']] ?? (string)$r['status']) ?>
          <?php if ($r['reviewed_by']): ?><div class="small muted">by <?= e($r['reviewed_by']) ?></div><?php endif; ?></td>
        <td><?= $r['serial'] ? '<a class="mono small" href="licenses.php?id=' . (int)$r['license_id'] . '">' . e(mask_serial((string)$r['serial'])) . '</a>' : '<span class="muted">none</span>' ?></td>
        <td class="actions">
          <form method="post" class="row-actions">
            <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$r['id'] ?>"><input type="hidden" name="qs" value="<?= e($qs) ?>">
            <?php if ($open): ?>
              <button class="btn btn-sm btn-good" name="action" value="approve"<?= confirm_attr('Approve this payment and issue the licence? Verify the money has arrived first.') ?>>Approve</button>
              <button class="btn btn-sm btn-danger" name="action" value="reject"<?= confirm_attr('Reject this payment? No licence will be issued.') ?>>Reject</button>
            <?php endif; ?>
            <?php if (in_array($r['status'], ['rejected', 'failed'], true)): ?>
              <button class="btn btn-sm" name="action" value="pending">Mark pending</button>
            <?php endif; ?>
          </form>
          <details class="more small"><summary>Notes</summary>
            <?php if (!empty($r['notes'])): ?><pre class="small" style="white-space:pre-wrap;max-width:320px"><?= e($r['notes']) ?></pre><?php endif; ?>
            <form method="post">
              <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$r['id'] ?>"><input type="hidden" name="qs" value="<?= e($qs) ?>">
              <label class="field">Add a note<input name="note" maxlength="500"></label>
              <button class="btn btn-sm" name="action" value="note">Add note</button>
            </form>
          </details>
        </td>
      </tr>
    <?php endforeach; ?>
    </tbody></table></div>
  <?php endif; ?>
  <?= pager($total, $per, $page, array_filter($f, static fn($v) => $v !== '' && $v !== 'all')) ?>
</section>
<?php layout_bottom(); ?>
