<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/license.php';
require_once __DIR__ . '/_layout.php';
require_admin();

if (admin_post()) {
    // the original dashboard form posted toggle_kill; it now flips the one
    // master switch through the same function as Application status
    if (isset($_POST['toggle_kill'])) {
        set_application_enabled(!application_enabled());
        back_to('index.php', application_enabled()
            ? 'Application turned ON. Installations resume at their next check-in.'
            : 'Application turned OFF. Installations stop at their next check-in.');
    }
}

$pdo = db();
$n = static function (string $sql, array $a = []) use ($pdo): int {
    $s = $pdo->prepare($sql);
    $s->execute($a);
    return (int)$s->fetchColumn();
};
$interval = max(60, (int)setting('checkin_seconds', (string)cfg('CHECKIN_SECONDS', 180)));
$window = max(600, $interval * 3);

$installs  = $n('SELECT COUNT(*) FROM installations');
$online    = $n('SELECT COUNT(*) FROM installations WHERE last_seen > DATE_SUB(UTC_TIMESTAMP(), INTERVAL ? SECOND)', [$window]);
$freeWeek  = $n("SELECT COUNT(*) FROM installations WHERE plan = 'free' AND last_seen > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 7 DAY)");
$pro       = $n("SELECT COUNT(*) FROM licenses WHERE tier = 'pro' AND status = 'active' AND expires_at > UTC_TIMESTAMP()");
$team      = $n("SELECT COUNT(*) FROM licenses WHERE tier = 'team' AND status = 'active' AND expires_at > UTC_TIMESTAMP()");
$trials    = $n("SELECT COUNT(*) FROM licenses WHERE source = 'trial' AND expires_at > UTC_TIMESTAMP()");
$devices   = $n("SELECT COUNT(*) FROM license_devices WHERE status = 'active'");
$expSoon   = $n("SELECT COUNT(*) FROM licenses WHERE tier IN ('pro','team') AND status = 'active'
                 AND expires_at BETWEEN UTC_TIMESTAMP() AND DATE_ADD(UTC_TIMESTAMP(), INTERVAL 5 DAY)");
$toReview  = $n("SELECT COUNT(*) FROM payments WHERE status IN ('pending','review')");
$errors24  = $n('SELECT COUNT(*) FROM client_errors WHERE created_at > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 DAY)');
$rev30 = (float)$pdo->query("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status = 'completed'
                             AND created_at > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 30 DAY)")->fetchColumn();
$revAll = (float)$pdo->query("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status = 'completed'")->fetchColumn();

$scripts = [];
foreach ($pdo->query("SELECT slug, name, enabled, version, min_tier FROM scripts WHERE slug IN ('script1','script2')") as $r) {
    $scripts[$r['slug']] = $r;
}
$u = update_info('0');
$recent = $pdo->query('SELECT id, serial, email, customer_name, tier, status, expires_at, source, max_devices,
                              last_validated_at, last_seen
                         FROM licenses ORDER BY id DESC LIMIT 8')->fetchAll();
$review = $pdo->query("SELECT id, email, amount, currency, plan_code, method, provider, created_at FROM payments
                        WHERE status IN ('pending','review') ORDER BY id DESC LIMIT 5")->fetchAll();
$log = $pdo->query('SELECT action, detail, actor, created_at FROM audit_log ORDER BY id DESC LIMIT 12')->fetchAll();

layout_top('Overview', 'What is happening across the website and every installation.');
?>
<div class="stats">
  <div class="stat accent"><span class="n"><?= $online ?></span><span class="l">Installations online now</span></div>
  <div class="stat"><span class="n"><?= $installs ?></span><span class="l">Installations known</span></div>
  <div class="stat"><span class="n"><?= $freeWeek ?></span><span class="l">Free installs active this week</span></div>
  <div class="stat"><span class="n"><?= $pro ?></span><span class="l">Active Pro licences</span></div>
  <div class="stat"><span class="n"><?= $team ?></span><span class="l">Active Team licences</span></div>
  <div class="stat"><span class="n"><?= $devices ?></span><span class="l">Activated computers</span></div>
  <div class="stat<?= $expSoon ? ' warn' : '' ?>"><span class="n"><?= $expSoon ?></span><span class="l">Paid licences ending in 5 days</span></div>
  <div class="stat<?= $toReview ? ' warn' : '' ?>"><span class="n"><?= $toReview ?></span><span class="l"><a href="payments.php?status=open">Payments to review</a></span></div>
  <div class="stat"><span class="n"><?= e(money($rev30)) ?></span><span class="l">Revenue, last 30 days</span></div>
  <div class="stat"><span class="n"><?= e(money($revAll)) ?></span><span class="l">Revenue, all time</span></div>
  <?php if ($trials): ?><div class="stat"><span class="n"><?= $trials ?></span><span class="l">Legacy trials still running</span></div><?php endif; ?>
  <div class="stat<?= $errors24 ? ' warn' : '' ?>"><span class="n"><?= $errors24 ?></span><span class="l"><a href="logs.php?tab=errors">App errors, last 24 h</a></span></div>
</div>

<?php master_switch_card(false); ?>

<section class="card" aria-labelledby="sys">
  <div class="card-head"><h2 id="sys">System status</h2></div>
  <div class="status-grid">
    <div class="status-item"><span class="k">Application</span>
      <?= state_chip(application_enabled() ? 'on' : 'off', application_enabled() ? 'Enabled' : 'Disabled') ?>
      <a class="small" href="status.php">Manage</a></div>
    <?php foreach (['script1' => 'Free, Pro and Team', 'script2' => 'Pro and Team only'] as $slug => $who):
        $s = $scripts[$slug] ?? null; ?>
    <div class="status-item"><span class="k"><?= e($s['name'] ?? ucfirst($slug)) ?> · <?= e($who) ?></span>
      <?= $s ? state_chip((int)$s['enabled'] ? 'enabled' : 'disabled') . ' <span class="small muted">version ' . (int)$s['version'] . '</span>' : state_chip('error', 'Missing') ?>
      <a class="small" href="scripts.php#<?= e($slug) ?>">Edit</a></div>
    <?php endforeach; ?>
    <div class="status-item"><span class="k">Current app version</span>
      <b><?= e($u['latest_version'] ?: 'not published') ?></b>
      <span class="small muted">minimum <?= e($u['min_version'] ?: '—') ?> · <?= e($u['type']) ?> update</span>
      <a class="small" href="update.php">Manage</a></div>
    <div class="status-item"><span class="k">Check-in interval</span>
      <b><?= (int)round($interval / 60) ?> min</b><a class="small" href="status.php#interval">Change</a></div>
    <div class="status-item"><span class="k">Database</span>
      <?= schema_pending() ? state_chip('pending', 'Upgrade pending') : state_chip('ok', 'Schema v' . schema_version()) ?>
      <a class="small" href="upgrade.php">Details</a></div>
  </div>
</section>

<div class="grid grid-2">
  <section class="card" aria-labelledby="newlic">
    <div class="card-head"><h2 id="newlic">Newest licences</h2><a href="licenses.php">All licences</a></div>
    <?php if (!$recent): ?><p class="empty">No licences yet. Paid orders create them automatically.</p><?php else: ?>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Customer</th><th>Plan</th><th>State</th><th>Ends</th></tr></thead>
      <tbody>
      <?php foreach ($recent as $r): $st = effective_state($r); ?>
        <tr>
          <td><a href="licenses.php?id=<?= (int)$r['id'] ?>"><?= e($r['customer_name'] ?: $r['email']) ?></a>
            <div class="small muted mono"><?= e(mask_serial((string)$r['serial'])) ?></div></td>
          <td><?= plan_badge((string)$r['tier']) ?></td>
          <td><?= state_chip($st['state']) ?></td>
          <td><?= e(remaining($r['expires_at'])) ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody></table></div>
    <?php endif; ?>
  </section>

  <section class="card" aria-labelledby="rev">
    <div class="card-head"><h2 id="rev">Payments waiting for review</h2><a href="payments.php?status=open">Review</a></div>
    <?php if (!$review): ?><p class="empty">Nothing to review.</p><?php else: ?>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Customer</th><th>Plan</th><th class="num">Amount</th><th>Received</th></tr></thead>
      <tbody>
      <?php foreach ($review as $p): ?>
        <tr><td><?= e($p['email'] ?? '—') ?><div class="small muted"><?= e($p['method'] ?: $p['provider']) ?></div></td>
            <td><?= $p['plan_code'] ? plan_badge((string)$p['plan_code']) : '—' ?></td>
            <td class="num"><?= e(number_format((float)$p['amount'], 2)) ?> <?= e($p['currency']) ?></td>
            <td><?= when($p['created_at']) ?></td></tr>
      <?php endforeach; ?>
      </tbody></table></div>
    <?php endif; ?>
  </section>
</div>

<section class="card" aria-labelledby="act">
  <div class="card-head"><h2 id="act">Recent activity</h2><a href="logs.php">Full audit log</a></div>
  <?php if (!$log): ?><p class="empty">No activity recorded yet.</p><?php else: ?>
  <ul class="log">
    <?php foreach ($log as $l): ?>
      <li><span class="muted small"><?= when($l['created_at']) ?></span>
          <span class="what"><b><?= e($l['action']) ?></b> <?= e($l['detail'] ?? '') ?>
          <?php if (!empty($l['actor'])): ?><span class="muted small">· <?= e($l['actor']) ?></span><?php endif; ?></span></li>
    <?php endforeach; ?>
  </ul>
  <?php endif; ?>
</section>
<?php layout_bottom(); ?>
