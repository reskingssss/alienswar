<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/license.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * Database: shows the schema version and lets an admin run a pending upgrade
 * by hand (it also runs automatically on the first request after new files
 * are uploaded). Every upgrade copies all tables to bak_<timestamp>_* first.
 */
$report = null;
if (admin_post() && isset($_POST['run'])) {
    try {
        $report = run_migrations(true, 'admin');
        audit('schema.manual_upgrade', 'to v' . ($report['to'] ?? '?'));
    } catch (Throwable $e) {
        back_to('upgrade.php', 'Upgrade failed: ' . $e->getMessage(), false);
    }
}

$backups = backup_table_list();
$applied = [];
try {
    $applied = db()->query('SELECT * FROM schema_migrations ORDER BY version DESC')->fetchAll();
} catch (Throwable $e) {
}
$lastBackup = setting('schema_last_backup', '');

layout_top('Database', 'Schema version, upgrades and the automatic backups they take.');
?>
<?php if ($report): ?>
  <div class="alert alert-good" role="status"><b>Upgrade complete.</b>
    <?php if (!empty($report['steps'])): ?>Applied: <?= e(implode('; ', $report['steps'])) ?>.<?php else: ?>Nothing to do — already up to date.<?php endif; ?>
    <?php if (!empty($report['backups'])): ?><br>Backup copies made: <?= count($report['backups']) ?> table(s).<?php endif; ?>
  </div>
<?php endif; ?>

<section class="card" aria-labelledby="ver">
  <div class="card-head"><h2 id="ver">Schema version</h2>
    <?= schema_pending() ? state_chip('pending', 'Upgrade pending') : state_chip('ok', 'Up to date') ?></div>
  <dl class="kv">
    <dt>Installed version</dt><dd><b>v<?= (int)schema_version() ?></b></dd>
    <dt>Code expects</dt><dd><b>v<?= (int)SCHEMA_VERSION ?></b></dd>
    <dt>Automatic upgrade</dt><dd><?= cfg('AUTO_MIGRATE', true) ? 'On — runs on the next request after an upload' : 'Off — run it here' ?></dd>
  </dl>
  <?php if (schema_pending()): ?>
    <div class="alert alert-warn" role="status">An upgrade is available. It only adds tables and columns, and it copies
      every existing table to a timestamped backup first. Existing licences, payments, settings and scripts are kept.</div>
    <form method="post">
      <?= csrf_field() ?>
      <button class="btn btn-primary" name="run" value="1"<?= confirm_attr('Run the database upgrade now? A backup of every table is taken first.') ?>>Back up and upgrade now</button>
    </form>
  <?php else: ?>
    <p class="muted">The database is at the version this code expects. There is nothing to upgrade.</p>
  <?php endif; ?>
</section>

<div class="grid grid-2">
  <section class="card" aria-labelledby="hist">
    <h2 id="hist">Upgrades applied</h2>
    <?php if (!$applied): ?><p class="empty">No upgrade history yet.</p><?php else: ?>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Version</th><th>What it added</th><th>When</th><th>By</th></tr></thead>
      <tbody>
      <?php foreach ($applied as $a): ?>
        <tr><td><b>v<?= (int)$a['version'] ?></b></td><td class="small"><?= e($a['label']) ?></td>
            <td><?= when($a['applied_at']) ?></td><td><?= e($a['trigger_src']) ?></td></tr>
      <?php endforeach; ?>
      </tbody></table></div>
    <?php endif; ?>
  </section>

  <section class="card" aria-labelledby="bk">
    <h2 id="bk">Backup copies</h2>
    <p class="muted small">Each upgrade copies your tables to <code>bak_&lt;date&gt;_&lt;table&gt;</code>. They are kept in the
      database so you can restore from phpMyAdmin if needed. Delete old ones there once you are sure the upgrade went well.</p>
    <?php if ($lastBackup): ?><p class="small">Most recent backup set: <span class="muted"><?= e(substr((string)$lastBackup, 0, 120)) ?><?= strlen((string)$lastBackup) > 120 ? '…' : '' ?></span></p><?php endif; ?>
    <?php if (!$backups): ?><p class="empty">No backup tables yet. They appear after the first upgrade.</p><?php else: ?>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Backup table</th><th class="num">Approx rows</th><th>Created</th></tr></thead>
      <tbody>
      <?php foreach (array_slice($backups, 0, 60) as $b): ?>
        <tr><td class="mono small"><?= e($b['name']) ?></td><td class="num"><?= (int)$b['approx_rows'] ?></td><td><?= when($b['created']) ?></td></tr>
      <?php endforeach; ?>
      </tbody></table></div>
    <?php endif; ?>
  </section>
</div>
<?php layout_bottom(); ?>
