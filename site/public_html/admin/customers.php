<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/orders.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * v6.3 - Customers & referrals (spec section 3, "Users view").
 *
 * A NEW page. Nothing on the existing dashboard is moved or restructured.
 * One row per customer, with their code, their full invite link, their
 * confirmed / pending / reverted counts, their reward state and who
 * referred them.
 */

const CUST_PER_PAGE = 40;

// ------------------------------------------------------------- actions
if (admin_post()) {
    $id = (int)($_POST['id'] ?? 0);
    $why = mb_substr(trim((string)($_POST['why'] ?? '')), 0, 240);
    $back = 'customers.php?' . http_build_query(array_filter([
        'q' => (string)($_POST['q'] ?? ''), 'f' => (string)($_POST['f'] ?? ''),
    ]));
    if ($id <= 0 || !customer_by_id($id)) {
        back_to($back, 'Unknown customer.', false);
    }
    if (isset($_POST['grant'])) {
        $r = referral_admin_grant_reward($id);
        back_to($back, $r['ok'] ? 'Pro licence granted: ' . $r['license']['serial'] : $r['error'], $r['ok']);
    }
    if (isset($_POST['revoke'])) {
        if ($why === '') {
            back_to($back, 'Give a reason before revoking a reward.', false);
        }
        $r = referral_admin_revoke_reward($id, $why);
        back_to($back, $r['ok'] ? 'Reward revoked.' : $r['error'], $r['ok']);
    }
    if (isset($_POST['paid'])) {
        referral_admin_mark_paid($id, $why !== '' ? $why : 'Cash payout marked paid.');
        back_to($back, 'Marked as paid.');
    }
    if (isset($_POST['unflag'])) {
        referral_admin_unflag($id);
        back_to($back, 'Flag cleared.');
    }
    if (isset($_POST['recount'])) {
        $n = referral_recount($id);
        referral_maybe_grant_reward($id);
        back_to($back, 'Recounted: ' . $n . ' confirmed referral(s).');
    }
    back_to($back, 'Nothing to do.', false);
}

// ------------------------------------------------------------- filters
$q = trim((string)($_GET['q'] ?? ''));
$f = (string)($_GET['f'] ?? '');
$where = [];
$args = [];
if ($q !== '') {
    $where[] = '(c.email LIKE ? OR c.referral_code = ? OR c.referred_by = ?)';
    $args[] = '%' . $q . '%';
    $args[] = referral_normalise_code($q);
    $args[] = referral_normalise_code($q);
}
if (in_array($f, ['none', 'eligible', 'pro_granted', 'cash_paid'], true)) {
    $where[] = 'c.reward_status = ?';
    $args[] = $f;
} elseif ($f === 'flagged') {
    $where[] = 'c.flagged = 1';
} elseif ($f === 'referrers') {
    $where[] = 'c.referral_count_confirmed > 0';
}
$sqlWhere = $where ? ' WHERE ' . implode(' AND ', $where) : '';

$select = "SELECT c.*,
  (SELECT COUNT(*) FROM referrals r WHERE r.referrer_customer_id = c.id AND r.status = 'confirmed') AS n_confirmed,
  (SELECT COUNT(*) FROM referrals r WHERE r.referrer_customer_id = c.id AND r.status = 'pending')   AS n_pending,
  (SELECT COUNT(*) FROM referrals r WHERE r.referrer_customer_id = c.id AND r.status = 'reverted')  AS n_reverted,
  (SELECT l.tier FROM licenses l WHERE l.email = c.email AND l.status = 'active'
      AND l.expires_at > UTC_TIMESTAMP()
    ORDER BY (l.tier = 'team') DESC, (l.tier = 'pro') DESC, l.expires_at DESC LIMIT 1) AS live_plan,
  (SELECT GROUP_CONCAT(l.serial ORDER BY l.id DESC SEPARATOR ' ')
     FROM licenses l WHERE l.email = c.email) AS serials
  FROM customers c" . $sqlWhere;

// ----------------------------------------------------------------- CSV
if (($_GET['export'] ?? '') === 'csv') {
    $st = db()->prepare($select . ' ORDER BY c.id DESC LIMIT 50000');
    $st->execute($args);
    audit('referral.customers_exported', 'q=' . $q . ' f=' . $f);
    header('Content-Type: text/csv; charset=utf-8');
    header('Content-Disposition: attachment; filename="customers-' . gmdate('Ymd-His') . '.csv"');
    $out = fopen('php://output', 'w');
    fwrite($out, "\xEF\xBB\xBF");
    $cols = ['id', 'email', 'created_at', 'live_plan', 'serials', 'referral_code', 'referral_link',
             'referred_by', 'n_confirmed', 'n_pending', 'n_reverted', 'reward_status',
             'reward_granted_at', 'flagged', 'flag_reason', 'payout_note'];
    fputcsv($out, $cols);
    while ($r = $st->fetch()) {
        $r['referral_link'] = referral_link_for((string)$r['referral_code']);
        $line = [];
        foreach ($cols as $c) {
            $v = (string)($r[$c] ?? '');
            $line[] = preg_match('/^[=+\-@\t\r]/', $v) ? "'" . $v : $v;   // formula-injection guard
        }
        fputcsv($out, $line);
    }
    fclose($out);
    exit;
}

$page = max(1, (int)($_GET['p'] ?? 1));
$cnt = db()->prepare('SELECT COUNT(*) FROM customers c' . $sqlWhere);
$cnt->execute($args);
$total = (int)$cnt->fetchColumn();
$st = db()->prepare($select . ' ORDER BY c.referral_count_confirmed DESC, c.id DESC LIMIT '
    . CUST_PER_PAGE . ' OFFSET ' . (($page - 1) * CUST_PER_PAGE));
$st->execute($args);
$rows = $st->fetchAll();

$threshold = referral_threshold();
$flagged = (int)db()->query('SELECT COUNT(*) FROM customers WHERE flagged = 1')->fetchColumn();

layout_top('Customers & referrals', 'Everyone with an invite code, what they have earned, and who sent them.');
?>
<section class="card">
  <div class="card-head">
    <h2>Customers</h2>
    <a class="btn btn-ghost" href="referrals.php">Referral events</a>
  </div>
  <p class="muted small">
    A customer is one email address. It is created the first time somebody buys, activates a licence,
    or asks for an invite link in the desktop tool &mdash; this site has no separate sign-up.
    The reward at <b><?= $threshold ?></b> confirmed referrals is a <?= e(plan_name(referral_reward_plan())) ?> licence,
    issued automatically. <?= $flagged ? '<b>' . $flagged . ' flagged for review.</b>' : '' ?>
  </p>
  <form method="get" class="toolbar" role="search">
    <label>Search <input type="search" name="q" value="<?= e($q) ?>" placeholder="email or code"></label>
    <label>Show
      <select name="f">
        <option value="">Everyone</option>
        <option value="referrers"<?= $f === 'referrers' ? ' selected' : '' ?>>Has referrals</option>
        <option value="eligible"<?= $f === 'eligible' ? ' selected' : '' ?>>Eligible, not yet rewarded</option>
        <option value="pro_granted"<?= $f === 'pro_granted' ? ' selected' : '' ?>>Reward granted</option>
        <option value="cash_paid"<?= $f === 'cash_paid' ? ' selected' : '' ?>>Cash paid</option>
        <option value="flagged"<?= $f === 'flagged' ? ' selected' : '' ?>>Flagged / suspected abuse</option>
        <option value="none"<?= $f === 'none' ? ' selected' : '' ?>>No reward</option>
      </select>
    </label>
    <button class="btn btn-primary">Filter</button>
    <a class="btn btn-ghost" href="?<?= e(http_build_query(array_filter(['q' => $q, 'f' => $f]))) ?>&export=csv">Export CSV</a>
  </form>

  <div class="table-wrap">
  <table class="grid">
    
    <thead><tr>
      <th scope="col">Customer</th><th scope="col">Plan</th><th scope="col">Invite code</th>
      <th scope="col" class="num">Confirmed</th><th scope="col" class="num">Pending</th>
      <th scope="col" class="num">Reverted</th><th scope="col">Reward</th>
      <th scope="col">Referred by</th><th scope="col">Actions</th>
    </tr></thead>
    <tbody>
    <?php if (!$rows): ?>
      <tr><td colspan="9" class="muted">No customers match that.</td></tr>
    <?php endif; ?>
    <?php foreach ($rows as $r): $link = referral_link_for((string)$r['referral_code']); ?>
      <tr<?= (int)$r['flagged'] ? ' class="warn"' : '' ?>>
        <td>
          <b><?= e((string)$r['email']) ?></b><br>
          <span class="muted small">#<?= (int)$r['id'] ?> &middot; joined <?= when((string)$r['created_at']) ?></span>
          <?php if ((int)$r['flagged']): ?>
            <br><?= state_chip('review', 'Flagged') ?>
            <span class="muted small"><?= e((string)$r['flag_reason']) ?></span>
          <?php endif; ?>
        </td>
        <td><?= plan_badge((string)($r['live_plan'] ?: 'free')) ?>
          <?php if ($r['serials']): ?>
            <br><span class="muted small mono"><?= e(mb_substr((string)$r['serials'], 0, 60)) ?></span>
          <?php endif; ?>
        </td>
        <td><span class="mono"><?= e((string)$r['referral_code']) ?></span><br>
          <span class="muted small"><?= e($link) ?></span></td>
        <td class="num"><b><?= (int)$r['n_confirmed'] ?></b> / <?= $threshold ?></td>
        <td class="num"><?= (int)$r['n_pending'] ?></td>
        <td class="num"><?= (int)$r['n_reverted'] ?></td>
        <td>
          <?php
          $rw = (string)$r['reward_status'];
          echo state_chip(
              ['none' => 'inactive', 'eligible' => 'pending', 'pro_granted' => 'active', 'cash_paid' => 'paid'][$rw] ?? 'muted',
              ['none' => 'None', 'eligible' => 'Eligible', 'pro_granted' => 'Pro granted', 'cash_paid' => 'Cash paid'][$rw] ?? $rw
          );
          ?>
          <?php if ($r['reward_granted_at']): ?><br><span class="muted small"><?= when((string)$r['reward_granted_at']) ?></span><?php endif; ?>
        </td>
        <td><?= $r['referred_by'] ? '<span class="mono">' . e((string)$r['referred_by']) . '</span>' : '<span class="muted">&mdash;</span>' ?></td>
        <td>
          <form method="post" class="row-actions">
            <?= csrf_field() ?>
            <input type="hidden" name="id" value="<?= (int)$r['id'] ?>">
            <input type="hidden" name="q" value="<?= e($q) ?>">
            <input type="hidden" name="f" value="<?= e($f) ?>">
            <input type="text" name="why" placeholder="reason / note" maxlength="240" size="14">
            <?php if ($r['reward_status'] !== 'pro_granted'): ?>
              <button class="btn btn-sm btn-good" name="grant" value="1"
                <?= confirm_attr('Grant a ' . plan_name(referral_reward_plan()) . ' licence to ' . $r['email'] . ' now?') ?>>Grant Pro</button>
            <?php else: ?>
              <button class="btn btn-sm btn-danger" name="revoke" value="1"
                <?= confirm_attr('Revoke the reward licence for ' . $r['email'] . '? Give a reason first.') ?>>Revoke</button>
            <?php endif; ?>
            <button class="btn btn-sm btn-ghost" name="paid" value="1"
              <?= confirm_attr('Mark the $' . referral_cash_amount() . ' payout to ' . $r['email'] . ' as paid?') ?>>Mark $<?= e(referral_cash_amount()) ?> paid</button>
            <button class="btn btn-sm btn-ghost" name="recount" value="1">Recount</button>
            <?php if ((int)$r['flagged']): ?>
              <button class="btn btn-sm btn-ghost" name="unflag" value="1">Clear flag</button>
            <?php endif; ?>
          </form>
        </td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table>
  </div>
  <?= pager($total, CUST_PER_PAGE, $page, array_filter(['q' => $q, 'f' => $f])) ?>
</section>
<?php layout_bottom();
