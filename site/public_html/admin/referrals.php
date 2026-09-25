<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/orders.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * v6.3 - Referral events (spec section 3, "Referrals view").
 *
 * A NEW page. One row per referral event: referrer, referred buyer, order,
 * licence serial, amount, status and timestamps, with manual approve,
 * reject and reverse.
 */

const REF_PER_PAGE = 50;

// ------------------------------------------------------------- actions
if (admin_post()) {
    $id = (int)($_POST['id'] ?? 0);
    $why = mb_substr(trim((string)($_POST['why'] ?? '')), 0, 240);
    $back = 'referrals.php?' . http_build_query(array_filter([
        'q' => (string)($_POST['q'] ?? ''), 's' => (string)($_POST['s'] ?? ''),
    ]));
    $map = ['approve' => 'confirmed', 'reject' => 'rejected', 'reverse' => 'reverted'];
    foreach ($map as $button => $status) {
        if (isset($_POST[$button])) {
            if ($button !== 'approve' && $why === '') {
                back_to($back, 'Give a reason before you ' . $button . ' a referral.', false);
            }
            $r = referral_admin_set_status($id, $status, $why !== '' ? $why : 'approved by admin');
            back_to($back, $r['ok']
                ? 'Referral set to ' . $status . '. The referrer now has ' . $r['count'] . ' confirmed.'
                : $r['error'], $r['ok']);
        }
    }
    back_to($back, 'Nothing to do.', false);
}

// ------------------------------------------------------------- filters
$q = trim((string)($_GET['q'] ?? ''));
$s = (string)($_GET['s'] ?? '');
$where = [];
$args = [];
if ($q !== '') {
    $where[] = '(r.referred_email LIKE ? OR r.referral_code = ? OR rc.email LIKE ?
                 OR r.license_serial = ? OR o.ref = ?)';
    $args[] = '%' . $q . '%';
    $args[] = referral_normalise_code($q);
    $args[] = '%' . $q . '%';
    $args[] = normalise_serial($q);
    $args[] = strtoupper(trim($q));
}
if (in_array($s, ['pending', 'confirmed', 'reverted', 'rejected'], true)) {
    $where[] = 'r.status = ?';
    $args[] = $s;
} elseif ($s === 'flagged') {
    $where[] = 'r.flagged = 1';
}
$sqlFrom = ' FROM referrals r
             LEFT JOIN customers rc ON rc.id = r.referrer_customer_id
             LEFT JOIN orders o     ON o.id  = r.order_id'
         . ($where ? ' WHERE ' . implode(' AND ', $where) : '');

// ----------------------------------------------------------------- CSV
if (($_GET['export'] ?? '') === 'csv') {
    $st = db()->prepare('SELECT r.*, rc.email AS referrer_email, rc.referral_code AS referrer_code,
                                o.ref AS order_ref' . $sqlFrom . ' ORDER BY r.id DESC LIMIT 50000');
    $st->execute($args);
    audit('referral.events_exported', 'q=' . $q . ' s=' . $s);
    header('Content-Type: text/csv; charset=utf-8');
    header('Content-Disposition: attachment; filename="referrals-' . gmdate('Ymd-His') . '.csv"');
    $out = fopen('php://output', 'w');
    fwrite($out, "\xEF\xBB\xBF");
    $cols = ['id', 'referrer_email', 'referrer_code', 'referred_email', 'referral_code', 'order_ref',
             'license_serial', 'amount', 'currency', 'status', 'flagged', 'flag_reason',
             'created_at', 'confirmed_at', 'reverted_at', 'ip', 'notes'];
    fputcsv($out, $cols);
    while ($r = $st->fetch()) {
        $line = [];
        foreach ($cols as $c) {
            $v = (string)($r[$c] ?? '');
            $line[] = preg_match('/^[=+\-@\t\r]/', $v) ? "'" . $v : $v;
        }
        fputcsv($out, $line);
    }
    fclose($out);
    exit;
}

$page = max(1, (int)($_GET['p'] ?? 1));
$cnt = db()->prepare('SELECT COUNT(*)' . $sqlFrom);
$cnt->execute($args);
$total = (int)$cnt->fetchColumn();

$st = db()->prepare('SELECT r.*, rc.email AS referrer_email, rc.referral_code AS referrer_code,
                            rc.referral_count_confirmed AS referrer_count, rc.reward_status,
                            o.ref AS order_ref, o.status AS order_status' . $sqlFrom
    . ' ORDER BY r.id DESC LIMIT ' . REF_PER_PAGE . ' OFFSET ' . (($page - 1) * REF_PER_PAGE));
$st->execute($args);
$rows = $st->fetchAll();

$tot = db()->query("SELECT
    SUM(status = 'confirmed') AS c, SUM(status = 'pending') AS p,
    SUM(status = 'reverted') AS v, SUM(status = 'rejected') AS j,
    SUM(flagged = 1) AS f FROM referrals")->fetch() ?: [];

layout_top('Referral events', 'Every referral, where it came from and what it is worth.');
?>
<section class="card">
  <div class="card-head">
    <h2>Referrals</h2>
    <a class="btn btn-ghost" href="customers.php">Customers &amp; codes</a>
  </div>
  <div class="stats">
    <div class="stat"><span class="n"><?= (int)($tot['c'] ?? 0) ?></span><span class="l">Confirmed</span></div>
    <div class="stat"><span class="n"><?= (int)($tot['p'] ?? 0) ?></span><span class="l">Pending</span></div>
    <div class="stat"><span class="n"><?= (int)($tot['v'] ?? 0) ?></span><span class="l">Reverted</span></div>
    <div class="stat"><span class="n"><?= (int)($tot['j'] ?? 0) ?></span><span class="l">Rejected</span></div>
    <div class="stat<?= (int)($tot['f'] ?? 0) ? ' warn' : '' ?>"><span class="n"><?= (int)($tot['f'] ?? 0) ?></span><span class="l">Flagged</span></div>
  </div>
  <p class="muted small">
    A referral is only counted when the invited person&rsquo;s payment is confirmed &mdash; a click, a
    download or a Free install never counts. A refund sets it back to <i>reverted</i> automatically.
    The same buyer counts once for the same referrer, however many licences they buy.
  </p>

  <form method="get" class="toolbar" role="search">
    <label>Search <input type="search" name="q" value="<?= e($q) ?>" placeholder="email, code, serial or order"></label>
    <label>Status
      <select name="s">
        <option value="">All</option>
        <option value="confirmed"<?= $s === 'confirmed' ? ' selected' : '' ?>>Confirmed</option>
        <option value="pending"<?= $s === 'pending' ? ' selected' : '' ?>>Pending</option>
        <option value="reverted"<?= $s === 'reverted' ? ' selected' : '' ?>>Reverted</option>
        <option value="rejected"<?= $s === 'rejected' ? ' selected' : '' ?>>Rejected</option>
        <option value="flagged"<?= $s === 'flagged' ? ' selected' : '' ?>>Flagged / suspected abuse</option>
      </select>
    </label>
    <button class="btn btn-primary">Filter</button>
    <a class="btn btn-ghost" href="?<?= e(http_build_query(array_filter(['q' => $q, 's' => $s]))) ?>&export=csv">Export CSV</a>
  </form>

  <div class="table-wrap">
  <table class="grid">
    <thead><tr>
      <th scope="col">Referrer</th><th scope="col">Invited buyer</th><th scope="col">Order</th>
      <th scope="col">Licence</th><th scope="col" class="num">Amount</th>
      <th scope="col">Status</th><th scope="col">When</th><th scope="col">Actions</th>
    </tr></thead>
    <tbody>
    <?php if (!$rows): ?>
      <tr><td colspan="8" class="muted">No referrals yet.</td></tr>
    <?php endif; ?>
    <?php foreach ($rows as $r): ?>
      <tr<?= (int)$r['flagged'] ? ' class="warn"' : '' ?>>
        <td>
          <b><?= e((string)($r['referrer_email'] ?? '—')) ?></b><br>
          <span class="mono muted small"><?= e((string)$r['referral_code']) ?></span>
          <span class="muted small">&middot; <?= (int)($r['referrer_count'] ?? 0) ?> confirmed</span>
          <?php if (($r['reward_status'] ?? '') === 'pro_granted'): ?>
            <br><?= state_chip('active', 'Reward granted') ?>
          <?php endif; ?>
        </td>
        <td><?= e((string)$r['referred_email']) ?>
          <?php if ((int)$r['flagged']): ?>
            <br><?= state_chip('review', 'Flagged') ?>
            <span class="muted small"><?= e((string)$r['flag_reason']) ?></span>
          <?php endif; ?>
        </td>
        <td>
          <?php if ($r['order_ref']): ?>
            <a href="payments.php?q=<?= rawurlencode((string)$r['order_ref']) ?>"><?= e((string)$r['order_ref']) ?></a>
            <br><span class="muted small"><?= e((string)($r['order_status'] ?? '')) ?></span>
          <?php else: ?><span class="muted">&mdash;</span><?php endif; ?>
        </td>
        <td class="mono small"><?= $r['license_serial'] ? e((string)$r['license_serial']) : '<span class="muted">&mdash;</span>' ?></td>
        <td class="num"><?= $r['amount'] !== null ? e(money((float)$r['amount'], (string)($r['currency'] ?: 'USD'))) : '&mdash;' ?></td>
        <td><?= state_chip((string)$r['status']) ?></td>
        <td><?= when((string)($r['confirmed_at'] ?: $r['created_at'])) ?></td>
        <td>
          <form method="post" class="row-actions">
            <?= csrf_field() ?>
            <input type="hidden" name="id" value="<?= (int)$r['id'] ?>">
            <input type="hidden" name="q" value="<?= e($q) ?>">
            <input type="hidden" name="s" value="<?= e($s) ?>">
            <input type="text" name="why" placeholder="reason" maxlength="240" size="12">
            <?php if ($r['status'] !== 'confirmed'): ?>
              <button class="btn btn-sm btn-good" name="approve" value="1"
                <?= confirm_attr('Count this referral for ' . ($r['referrer_email'] ?? 'the referrer') . '? It may trigger the reward.') ?>>Approve</button>
            <?php else: ?>
              <button class="btn btn-sm btn-danger" name="reverse" value="1"
                <?= confirm_attr('Reverse this referral? The referrer loses one confirmed referral. A reward already granted is NOT revoked here.') ?>>Reverse</button>
            <?php endif; ?>
            <?php if ($r['status'] !== 'rejected'): ?>
              <button class="btn btn-sm btn-ghost" name="reject" value="1"
                <?= confirm_attr('Reject this referral as abuse?') ?>>Reject</button>
            <?php endif; ?>
          </form>
          <?php if ($r['notes']): ?><span class="muted small"><?= e(mb_substr((string)$r['notes'], 0, 120)) ?></span><?php endif; ?>
        </td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table>
  </div>
  <?= pager($total, REF_PER_PAGE, $page, array_filter(['q' => $q, 's' => $s])) ?>
</section>
<?php layout_bottom();
