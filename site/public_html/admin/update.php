<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/license.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * Application updates. Publish a build: version, the minimum supported
 * version, the installer URL with its SHA-256, release notes, and whether
 * the update is optional or mandatory. The desktop verifies the download
 * against the SHA-256 before installing, so the file cannot be swapped.
 */
$clean_ver = static function (string $v): string {
    $v = preg_replace('/[^0-9.]/', '', trim($v)) ?? '';
    return mb_substr(trim($v, '.'), 0, 24);
};

if (admin_post()) {
    if (isset($_POST['publish'])) {
        $latest = $clean_ver((string)($_POST['latest_version'] ?? ''));
        $min    = $clean_ver((string)($_POST['min_version'] ?? ''));
        $url    = trim((string)($_POST['download_url'] ?? ''));
        $sha    = strtolower(preg_replace('/[^a-f0-9]/i', '', (string)($_POST['download_sha256'] ?? '')) ?? '');
        $sizeMb = trim((string)($_POST['download_mb'] ?? ''));
        $type   = ($_POST['update_type'] ?? 'optional') === 'mandatory' ? 'mandatory' : 'optional';
        $notes  = trim(str_replace("\r\n", "\n", (string)($_POST['release_notes'] ?? '')));
        $fname  = mb_substr(trim((string)($_POST['file_name'] ?? '')), 0, 190);

        $errors = [];
        if ($latest === '') {
            $errors[] = 'Enter the version you are publishing, for example 4.1.0.';
        }
        if ($min === '') {
            $min = $latest;
        }
        if ($latest !== '' && $min !== '' && version_cmp($min, $latest) > 0) {
            $errors[] = 'The minimum supported version cannot be newer than the version you are publishing.';
        }
        if ($url !== '' && !is_web_url($url, true)) {
            $errors[] = 'The installer URL must be a full https:// address (http is refused for downloads).';
        }
        if ($sha !== '' && strlen($sha) !== 64) {
            $errors[] = 'The SHA-256 checksum must be 64 hex characters. Leave it empty only if you cannot compute it.';
        }
        if ($type === 'mandatory' && $url === '') {
            $errors[] = 'A mandatory update needs an installer URL, or clients cannot update to continue.';
        }
        if ($sizeMb !== '' && !preg_match('/^\d{1,5}(\.\d{1,2})?$/', $sizeMb)) {
            $errors[] = 'File size must be a number of megabytes, for example 42.5.';
        }
        if ($errors) {
            back_to('update.php', implode(' ', $errors), false);
        }
        $sizeBytes = $sizeMb !== '' ? (int)round((float)$sizeMb * 1048576) : 0;

        set_setting('latest_version', $latest);
        set_setting('min_version', $min);
        set_setting('download_url', mb_substr($url, 0, 500));
        set_setting('download_sha256', $sha);
        set_setting('download_size', (string)$sizeBytes);
        set_setting('update_type', $type);
        set_setting('release_notes', mb_substr($notes, 0, 4000));
        set_setting('force_update', $type === 'mandatory' ? '1' : '0');

        db()->prepare("UPDATE app_releases SET is_current = 0 WHERE is_current = 1")->execute();
        db()->prepare("INSERT INTO app_releases (version, min_version, update_type, notes, file_url, file_name,
                       file_sha256, file_size, is_current, published_by, published_at)
                       VALUES (?,?,?,?,?,?,?,?,1,?,?)")
            ->execute([$latest, $min, $type, mb_substr($notes, 0, 4000) ?: null, $url ?: null, $fname ?: null,
                       $sha ?: null, $sizeBytes ?: null, admin_actor(), now()]);
        audit('app.update.published', 'version ' . $latest . ' min ' . $min . ' ' . $type
            . ($url !== '' ? ' url set' : ' no url') . ($sha !== '' ? ' sha set' : ' no sha'));
        back_to('update.php', 'Version ' . $latest . ' published. Installations apply the policy at their next check-in.');
    }
    if (isset($_POST['make_current'])) {
        $rid = (int)($_POST['release_id'] ?? 0);
        $st = db()->prepare('SELECT * FROM app_releases WHERE id = ?');
        $st->execute([$rid]);
        $rel = $st->fetch();
        if (!$rel) {
            back_to('update.php', 'That release no longer exists.', false);
        }
        db()->prepare('UPDATE app_releases SET is_current = 0 WHERE is_current = 1')->execute();
        db()->prepare('UPDATE app_releases SET is_current = 1 WHERE id = ?')->execute([$rid]);
        set_setting('latest_version', (string)$rel['version']);
        set_setting('min_version', (string)($rel['min_version'] ?: $rel['version']));
        set_setting('download_url', (string)($rel['file_url'] ?? ''));
        set_setting('download_sha256', strtolower((string)($rel['file_sha256'] ?? '')));
        set_setting('download_size', (string)((int)($rel['file_size'] ?? 0)));
        set_setting('update_type', (string)$rel['update_type']);
        set_setting('release_notes', (string)($rel['notes'] ?? ''));
        set_setting('force_update', $rel['update_type'] === 'mandatory' ? '1' : '0');
        audit('app.update.rollback', 'made version ' . $rel['version'] . ' current again');
        back_to('update.php', 'Version ' . $rel['version'] . ' is current again.');
    }
}

$u = update_info('0');
$releases = db()->query('SELECT * FROM app_releases ORDER BY id DESC LIMIT 40')->fetchAll();
$installs = db()->query("SELECT app_version, COUNT(*) c FROM installations
                         WHERE last_seen > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 30 DAY) AND app_version <> ''
                         GROUP BY app_version ORDER BY c DESC LIMIT 12")->fetchAll();

layout_top('Application updates', 'Publish a new build and choose whether updating is optional or required.');
?>
<section class="card" aria-labelledby="cur">
  <div class="card-head"><h2 id="cur">Current release</h2>
    <?= $u['type'] === 'mandatory' ? state_chip('mandatory', 'Mandatory') : state_chip('optional', 'Optional') ?></div>
  <div class="status-grid">
    <div class="status-item"><span class="k">Version published</span><b><?= e($u['latest_version'] ?: 'none yet') ?></b></div>
    <div class="status-item"><span class="k">Minimum supported</span><b><?= e($u['min_version'] ?: '—') ?></b></div>
    <div class="status-item"><span class="k">Installer</span>
      <?php if ($u['url']): ?><a href="<?= e($u['url']) ?>" target="_blank" rel="noopener">Download link</a>
        <?= $u['sha256'] ? state_chip('ok', 'Checksum set') : state_chip('warn', 'No checksum') ?>
      <?php else: ?><span class="muted">not set</span><?php endif; ?></div>
    <div class="status-item"><span class="k">Verified before install</span>
      <?= $u['sha256'] ? '<b>Yes — SHA-256</b>' : '<span class="muted">Only if a checksum is set</span>' ?></div>
  </div>
</section>

<section class="card" aria-labelledby="pub">
  <h2 id="pub">Publish a build</h2>
  <form method="post" data-guard>
    <?= csrf_field() ?>
    <div class="form-grid">
      <label class="field">Version you are publishing<input name="latest_version" value="<?= e($u['latest_version']) ?>" placeholder="4.1.0" required></label>
      <label class="field">Minimum supported version <?= tip('Installations older than this must update. Leave empty to match the version you are publishing.') ?>
        <input name="min_version" value="<?= e($u['min_version']) ?>" placeholder="4.0.0"></label>
    </div>
    <label class="field">Installer URL <span class="hint">https only; where the app downloads the update from</span>
      <input name="download_url" value="<?= e($u['url']) ?>" placeholder="https://your-domain.com/download/ChromeProfileGenerator-Setup.exe"></label>
    <div class="form-grid">
      <label class="field">Installer SHA-256 <?= tip('The app checks the downloaded file against this before installing, so a swapped file is rejected. On Windows: Get-FileHash installer.exe') ?>
        <input name="download_sha256" value="<?= e($u['sha256']) ?>" placeholder="64 hex characters" maxlength="64" spellcheck="false"></label>
      <label class="field">File name <span class="hint">optional</span><input name="file_name" placeholder="ChromeProfileGenerator-Setup.exe" maxlength="190"></label>
      <label class="field">File size, MB <span class="hint">optional</span><input name="download_mb" value="<?= $u['size'] ? e((string)round($u['size'] / 1048576, 2)) : '' ?>" inputmode="decimal" placeholder="42.5"></label>
    </div>
    <fieldset class="field" style="border:0;padding:0;margin:0 0 12px">
      <legend style="margin-bottom:5px">Update type</legend>
      <div class="seg" role="radiogroup">
        <label><input type="radio" name="update_type" value="optional"<?= $u['type'] !== 'mandatory' ? ' checked' : '' ?>><span>Optional — the app offers it</span></label>
        <label><input type="radio" name="update_type" value="mandatory"<?= $u['type'] === 'mandatory' ? ' checked' : '' ?>><span>Mandatory — older versions must update</span></label>
      </div>
    </fieldset>
    <label class="field">Release notes <span class="hint">shown to users; one point per line</span>
      <textarea name="release_notes" rows="5"><?= e($u['notes']) ?></textarea></label>
    <button class="btn btn-primary" name="publish" value="1"<?= confirm_attr('Publish this build? Installations apply the new policy at their next check-in.') ?>>Publish build</button>
  </form>
</section>

<div class="grid grid-2">
  <section class="card" aria-labelledby="hist">
    <h2 id="hist">Version history</h2>
    <?php if (!$releases): ?><p class="empty">No builds published yet.</p><?php else: ?>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Version</th><th>Type</th><th>Installer</th><th>Published</th><th></th></tr></thead>
      <tbody>
      <?php foreach ($releases as $r): ?>
        <tr>
          <td><b><?= e($r['version']) ?></b><?= (int)$r['is_current'] ? ' ' . state_chip('current', 'Current') : '' ?>
            <div class="small muted">min <?= e($r['min_version'] ?: $r['version']) ?></div></td>
          <td><?= state_chip($r['update_type']) ?></td>
          <td><?= $r['file_url'] ? '<a href="' . e($r['file_url']) . '" target="_blank" rel="noopener">link</a>'
              . ($r['file_sha256'] ? ' ✓' : '') : '<span class="muted">—</span>' ?></td>
          <td><?= when($r['published_at']) ?><?= $r['published_by'] ? '<div class="small muted">' . e($r['published_by']) . '</div>' : '' ?></td>
          <td class="actions"><?php if (!(int)$r['is_current']): ?>
            <form method="post"><?= csrf_field() ?><input type="hidden" name="release_id" value="<?= (int)$r['id'] ?>">
              <button class="btn btn-sm" name="make_current" value="1"<?= confirm_attr('Make version ' . $r['version'] . ' the current release again?') ?>>Make current</button></form>
          <?php endif; ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody></table></div>
    <?php endif; ?>
  </section>

  <section class="card" aria-labelledby="ver">
    <h2 id="ver">Versions in the field <span class="muted small">(last 30 days)</span></h2>
    <?php if (!$installs): ?><p class="empty">No installations have reported a version yet.</p><?php else: ?>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Version</th><th class="num">Installations</th><th>Update status</th></tr></thead>
      <tbody>
      <?php foreach ($installs as $i):
          $old = $u['min_version'] !== '' && version_cmp((string)$i['app_version'], $u['min_version']) < 0;
          $behind = $u['latest_version'] !== '' && version_cmp((string)$i['app_version'], $u['latest_version']) < 0; ?>
        <tr><td><?= e($i['app_version']) ?></td><td class="num"><?= (int)$i['c'] ?></td>
          <td><?= $old ? state_chip('update_required', 'Below minimum') : ($behind ? state_chip('optional', 'Update available') : state_chip('ok', 'Up to date')) ?></td></tr>
      <?php endforeach; ?>
      </tbody></table></div>
    <?php endif; ?>
  </section>
</div>
<?php layout_bottom(); ?>
