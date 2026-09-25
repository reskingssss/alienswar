<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/license.php';
require_once __DIR__ . '/_layout.php';
require_once __DIR__ . '/../includes/activation_limit.php';
require_admin();

/**
 * Application Status: the ONE master switch. ON = installations may run.
 * OFF = every installation is disabled at its next check-in (Free and paid
 * alike). The state travels inside the Ed25519-signed check-in reply, so
 * it cannot be forged, and nothing about licences or profiles changes.
 */
if (admin_post()) {
    // v6.3.2 (TASK 1.5): unblock a genuine customer who burned their three
    // attempts. Additive - the master switch handling below is untouched.
    if (isset($_POST['reset_attempts'])) {
        $dev = clean_hex((string)($_POST['device_hash'] ?? ''));
        $ok = activation_admin_reset($dev, admin_actor());
        back_to('status.php#installs',
            $ok ? 'Attempts reset. That installation can register again immediately.'
                : 'Unknown installation.', $ok);
    }
    $allowed = [];
    foreach (admin_nav() as [, $items]) {
        foreach ($items as [$href]) {
            $allowed[] = $href;
        }
    }
    $return = in_array($_POST['return'] ?? '', $allowed, true) ? (string)$_POST['return'] : 'status.php';

    if (isset($_POST['set_enabled'])) {
        $on = $_POST['set_enabled'] === '1';
        set_application_enabled($on);
        back_to($return, $on
            ? 'Application turned ON. Installations resume at their next check-in.'
            : 'Application turned OFF. Installations stop at their next check-in.');
    }
    if (isset($_POST['save_message'])) {
        $msg = trim(mb_substr((string)($_POST['blocked_message'] ?? ''), 0, 500));
        if ($msg === '') {
            back_to('status.php', 'Enter the message people see while the application is OFF.', false);
        }
        set_setting('blocked_message', $msg);
        set_setting('kill_message', $msg);   // older app builds read this one
        audit('app.status.message', $msg);
        back_to('status.php', 'Message saved.');
    }
    if (isset($_POST['save_interval'])) {
        $sec = (int)($_POST['checkin_seconds'] ?? 0);
        if ($sec < 60 || $sec > 3600) {
            back_to('status.php', 'Choose a check-in interval between 60 and 3600 seconds.', false);
        }
        set_setting('checkin_seconds', (string)$sec);
        audit('app.checkin_interval', $sec . ' s');
        back_to('status.php', 'Check-in interval saved. Installations pick it up at their next check-in.');
    }
}

$enabled   = application_enabled();
$changedAt = setting('app_status_changed_at');
$interval  = max(60, (int)setting('checkin_seconds', (string)cfg('CHECKIN_SECONDS', 180)));
$pdo = db();
$active7 = (int)$pdo->query("SELECT COUNT(*) FROM installations WHERE last_seen > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 7 DAY)")->fetchColumn();
$seen = 0;
if ($changedAt) {
    $st = $pdo->prepare('SELECT COUNT(*) FROM installations WHERE last_seen >= ?');
    $st->execute([$changedAt]);
    $seen = (int)$st->fetchColumn();
}
$rows = $pdo->query("SELECT i.*, (SELECT d.device_label FROM license_devices d WHERE d.device_hash = i.device_hash
                                    ORDER BY d.id DESC LIMIT 1) AS label
                       FROM installations i ORDER BY i.last_seen DESC LIMIT 60")->fetchAll();

layout_top('Application status', 'Turn every installation on or off, and see who has received the change.');
master_switch_card(true);
?>
<section class="card" aria-labelledby="reach">
  <div class="card-head"><h2 id="reach">Has the change reached installations?</h2></div>
  <?php if (!$changedAt): ?>
    <p class="muted">The switch has not been changed since this dashboard started recording it.</p>
  <?php else: ?>
    <p><b><?= $seen ?></b> of <b><?= $active7 ?></b> installations active this week have checked in since the last change
      (<?= when($changedAt) ?>). The rest receive it at their next check-in, normally within
      <?= (int)ceil($interval / 60) ?> minutes, or as soon as they are next opened.</p>
  <?php endif; ?>
  <?php if (!$rows): ?>
    <p class="empty">No installation has checked in yet. Installations appear here after they start.</p>
  <?php else: ?>
  <div class="table-wrap"><table class="data">
    <thead><tr><th>Computer</th><th>Plan</th><th>Version</th><th class="num">Profiles</th>
      <th>Last check-in</th><th>State it received</th><th>Current switch state</th><th>Licence attempts</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r):
        $got = $changedAt && $r['last_seen'] >= $changedAt; ?>
      <tr>
        <td><?= e($r['label'] ?: 'Unnamed computer') ?><div class="small muted mono"><?= e(substr((string)$r['device_hash'], 0, 12)) ?>…</div></td>
        <td><?= plan_badge((string)$r['plan']) ?></td>
        <td><?= e($r['app_version'] ?: '—') ?></td>
        <td class="num"><?= (int)$r['profile_count'] ?></td>
        <td><?= when($r['last_seen']) ?></td>
        <td><?= state_chip((string)($r['last_state'] ?: 'unknown'), ['active' => 'Enabled', 'disabled' => 'Disabled',
              'update_required' => 'Update required'][(string)$r['last_state']] ?? 'Unknown') ?></td>
        <td><?= !$changedAt ? '—' : ($got ? state_chip('ok', 'Received') : state_chip('pending', 'Not yet')) ?></td>
        <?php $act = activation_state((string)$r['device_hash']); ?>
        <td>
          <?php if ($act['locked']): ?>
            <?= state_chip('review', 'Locked') ?>
            <div class="small muted">until <?= e(gmdate('j M H:i', strtotime((string)$act['locked_until']))) ?> UTC</div>
          <?php elseif ((int)$act['fails'] > 0): ?>
            <span class="small"><?= (int)$act['fails'] ?> of <?= (int)$act['max'] ?> failed</span>
          <?php else: ?>
            <span class="muted small">&mdash;</span>
          <?php endif; ?>
          <?php if ($act['locked'] || (int)$act['fails'] > 0): ?>
            <form method="post" class="row-actions" style="margin-top:4px">
              <?= csrf_field() ?>
              <input type="hidden" name="device_hash" value="<?= e((string)$r['device_hash']) ?>">
              <button class="btn btn-sm btn-ghost" name="reset_attempts" value="1"
                <?= confirm_attr('Reset licence attempts for this installation and unlock it now?') ?>>Reset / unlock</button>
            </form>
          <?php endif; ?>
        </td>
      </tr>
    <?php endforeach; ?>
    </tbody></table></div>
  <?php endif; ?>
</section>

<div class="grid grid-2">
  <section class="card" aria-labelledby="msg">
    <h2 id="msg">Message while OFF</h2>
    <p class="muted small">Shown inside the application while the switch is OFF.</p>
    <form method="post">
      <?= csrf_field() ?>
      <label class="field">Message
        <input name="blocked_message" value="<?= e(app_disabled_message()) ?>" maxlength="500" required></label>
      <button class="btn btn-primary" name="save_message" value="1">Save message</button>
    </form>
  </section>
  <section class="card" id="interval" aria-labelledby="int">
    <h2 id="int">Check-in interval <?= tip('How often each installation asks the server for the switch state, updates, scripts and its licence. Shorter reacts faster; longer puts less load on the server.') ?></h2>
    <p class="muted small">Every installation also checks in when it starts.</p>
    <form method="post">
      <?= csrf_field() ?>
      <label class="field">Seconds between check-ins (60–3600)
        <input type="number" name="checkin_seconds" min="60" max="3600" step="30" value="<?= $interval ?>" required></label>
      <button class="btn btn-primary" name="save_interval" value="1">Save interval</button>
    </form>
  </section>
</div>
<?php layout_bottom(); ?>
