<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/** Audit log and desktop error log, with search and CSV export. */
$tab = ($_GET['tab'] ?? 'audit') === 'errors' ? 'errors' : 'audit';
$q = trim((string)($_GET['q'] ?? ''));
$page = max(1, (int)($_GET['p'] ?? 1));
$per = 60;

if ($tab === 'audit') {
    $where = [];
    $args = [];
    if ($q !== '') {
        $where[] = '(action LIKE ? OR detail LIKE ? OR actor LIKE ?)';
        array_push($args, '%' . $q . '%', '%' . $q . '%', '%' . $q . '%');
    }
    $sql = 'FROM audit_log' . ($where ? ' WHERE ' . implode(' AND ', $where) : '');
} else {
    $where = [];
    $args = [];
    if ($q !== '') {
        $where[] = '(kind LIKE ? OR message LIKE ? OR app_version LIKE ?)';
        array_push($args, '%' . $q . '%', '%' . $q . '%', '%' . $q . '%');
    }
    $sql = 'FROM client_errors' . ($where ? ' WHERE ' . implode(' AND ', $where) : '');
}

if (($_GET['export'] ?? '') === 'csv') {
    $st = db()->prepare('SELECT * ' . $sql . ' ORDER BY id DESC LIMIT 50000');
    $st->execute($args);
    header('Content-Type: text/csv; charset=utf-8');
    header('Content-Disposition: attachment; filename="' . $tab . '-log-' . gmdate('Ymd-His') . '.csv"');
    $out = fopen('php://output', 'w');
    fwrite($out, "\xEF\xBB\xBF");
    $first = true;
    while ($r = $st->fetch()) {
        if ($first) {
            fputcsv($out, array_keys($r));
            $first = false;
        }
        fputcsv($out, array_map(static fn($v) => preg_match('/^[=+\-@\t\r]/', (string)$v) ? "'" . $v : (string)$v, $r));
    }
    fclose($out);
    exit;
}

$cnt = db()->prepare('SELECT COUNT(*) ' . $sql);
$cnt->execute($args);
$total = (int)$cnt->fetchColumn();
$st = db()->prepare('SELECT * ' . $sql . ' ORDER BY id DESC LIMIT ' . $per . ' OFFSET ' . (($page - 1) * $per));
$st->execute($args);
$rows = $st->fetchAll();

layout_top('Audit & error logs', 'Every change made here, and problems reported by installations.');
?>
<nav class="tabs" aria-label="Log type">
  <a href="?tab=audit"<?= $tab === 'audit' ? ' class="here" aria-current="page"' : '' ?>>Audit log</a>
  <a href="?tab=errors"<?= $tab === 'errors' ? ' class="here" aria-current="page"' : '' ?>>Desktop errors</a>
</nav>

<section class="card">
  <form method="get" class="toolbar" role="search">
    <input type="hidden" name="tab" value="<?= e($tab) ?>">
    <label class="field">Search<input name="q" value="<?= e($q) ?>" placeholder="<?= $tab === 'audit' ? 'Action, detail or admin' : 'Kind, message or version' ?>"></label>
    <button class="btn">Search</button>
    <a class="btn btn-ghost" href="?tab=<?= e($tab) ?>&q=<?= rawurlencode($q) ?>&export=csv">Export CSV</a>
    <span class="muted"><?= $total ?> entr<?= $total === 1 ? 'y' : 'ies' ?></span>
  </form>

  <?php if (!$rows): ?>
    <p class="empty"><?= $tab === 'audit' ? 'No audit entries match.' : 'No desktop errors reported. That is good.' ?></p>
  <?php elseif ($tab === 'audit'): ?>
  <div class="table-wrap"><table class="data">
    <thead><tr><th>When</th><th>Action</th><th>Detail</th><th>Admin</th><th>Licence</th><th>IP</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r): ?>
      <tr>
        <td><?= when($r['created_at']) ?></td>
        <td><b><?= e($r['action']) ?></b></td>
        <td class="small"><?= e($r['detail'] ?? '') ?></td>
        <td><?= e($r['actor'] ?? '—') ?></td>
        <td><?= $r['license_id'] ? '<a href="licenses.php?id=' . (int)$r['license_id'] . '">#' . (int)$r['license_id'] . '</a>' : '—' ?></td>
        <td class="mono small"><?= e($r['ip'] ?? '') ?></td>
      </tr>
    <?php endforeach; ?>
    </tbody></table></div>
  <?php else: ?>
  <div class="table-wrap"><table class="data">
    <thead><tr><th>When</th><th>Kind</th><th>Message</th><th>Version</th><th>Computer</th><th>Licence</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r): ?>
      <tr>
        <td><?= when($r['created_at']) ?></td>
        <td><?= state_chip('error', (string)$r['kind']) ?></td>
        <td class="small"><?= e($r['message']) ?></td>
        <td><?= e($r['app_version'] ?? '—') ?></td>
        <td class="mono small"><?= $r['device_hash'] ? e(substr((string)$r['device_hash'], 0, 12)) . '…' : '—' ?></td>
        <td><?= $r['license_id'] ? '<a href="licenses.php?id=' . (int)$r['license_id'] . '">#' . (int)$r['license_id'] . '</a>' : '—' ?></td>
      </tr>
    <?php endforeach; ?>
    </tbody></table></div>
  <?php endif; ?>
  <?= pager($total, $per, $page, ['tab' => $tab, 'q' => $q]) ?>
</section>
<?php layout_bottom(); ?>
