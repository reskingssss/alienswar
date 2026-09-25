<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/license.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * User scripts: the ONE place scripts are managed. The desktop receives
 * whatever is published here and injects it; it cannot create or edit
 * scripts. Tier is fixed — Script 1 reaches Free, Pro and Team; Script 2
 * reaches only Pro and Team, and the server enforces that. Saving bumps
 * the version and records a SHA-256 so clients can tell a real change from
 * a redelivery and verify what they downloaded.
 */
const MANAGED_SLUGS = ['script1', 'script2'];

foreach (MANAGED_SLUGS as $i => $slug) {
    $st = db()->prepare('SELECT 1 FROM scripts WHERE slug = ?');
    $st->execute([$slug]);
    if (!$st->fetch()) {
        db()->prepare("INSERT INTO scripts (slug, name, min_tier, enabled, version, source, checksum, updated_at)
                       VALUES (?,?,?,1,1,'',?,?)")
            ->execute([$slug, 'Script ' . ($i + 1), $i === 0 ? 'free' : 'pro', hash('sha256', ''), now()]);
    }
}

if (admin_post()) {
    $slug = (string)($_POST['slug'] ?? '');
    if (!in_array($slug, MANAGED_SLUGS, true)) {
        back_to('scripts.php', 'Unknown script.', false);
    }
    $act = (string)($_POST['action'] ?? '');

    // v6.3.1 (TASK 4): entitlement is data-driven now. Saved on every
    // action so a plan change does not need a republish of the source.
    if (in_array($act, ['save', 'plans'], true)) {
        $picked = array_values(array_intersect(
            ['free', 'pro', 'team'],
            array_map('strval', (array)($_POST['plans'] ?? []))
        ));
        if (!$picked) {
            back_to('scripts.php#' . $slug,
                'Choose at least one plan, or use Disable to stop delivering this script.', false);
        }
        db()->prepare('UPDATE scripts SET plans = ?, updated_at = ? WHERE slug = ?')
            ->execute([implode(',', $picked), now(), $slug]);
        audit('script.plans', $slug . ' -> ' . implode(',', $picked));
        if ($act === 'plans') {
            back_to('scripts.php#' . $slug,
                'Entitlement saved. Installations pick it up at their next check-in.');
        }
    }

    if ($act === 'save') {
        $source = (string)($_POST['source'] ?? '');
        if (strlen($source) > 4000000) {
            back_to('scripts.php', 'That script is too large (over 4 MB).', false);
        }
        $enabled = isset($_POST['enabled']) ? 1 : 0;
        // tier is fixed per slug and never taken from the form, so a Free
        // client can never be granted Script 2 by mistake
        db()->prepare('UPDATE scripts SET source = ?, enabled = ?, version = version + 1, checksum = ?,
                       published_at = ?, published_by = ?, updated_at = ? WHERE slug = ?')
            ->execute([$source, $enabled, hash('sha256', $source), now(), admin_actor(), now(), $slug]);
        $v = (int)db()->query('SELECT version FROM scripts WHERE slug = ' . db()->quote($slug))->fetchColumn();
        audit('script.published', $slug . ' version ' . $v . ' ' . ($enabled ? 'enabled' : 'disabled')
            . ' ' . strlen($source) . ' bytes');
        back_to('scripts.php#' . $slug, ucfirst($slug) . ' published as version ' . $v
            . '. Installations receive it at their next check-in.');
    }
    if ($act === 'enable' || $act === 'disable') {
        $on = $act === 'enable' ? 1 : 0;
        db()->prepare('UPDATE scripts SET enabled = ?, updated_at = ? WHERE slug = ?')->execute([$on, now(), $slug]);
        audit('script.' . $act, $slug);
        back_to('scripts.php#' . $slug, ucfirst($slug) . ($on ? ' enabled.' : ' disabled.'));
    }
}

$scripts = [];
foreach (db()->query("SELECT * FROM scripts WHERE slug IN ('script1','script2')") as $row) {
    $scripts[$row['slug']] = $row;
}
$ordered = [];
foreach (MANAGED_SLUGS as $slug) {
    if (isset($scripts[$slug])) {
        $ordered[] = $scripts[$slug];
    }
}

layout_top('User scripts', 'The scripts injected into generated profiles. Managed here, delivered by check-in.');
?>
<section class="card">
  <p class="muted">Scripts live here, not inside the app. Each installation downloads the scripts it is
    entitled to and injects them into the profiles it generates; the sources are verified against a
    checksum on the way in. <b>Entitlement is set per script below</b> — tick the plans each script
    goes to, and the server enforces it, so an installation can never fetch a script its plan is not
    entitled to. Editing a script here changes it for everyone at their next check-in.</p>
</section>

<?php foreach ($ordered as $s):
    // v6.3.1: the badge and caption now READ the stored entitlement instead
    // of being hard-coded, so they can never drift from what is delivered.
    $planList = array_values(array_filter(array_map('trim',
        explode(',', (string)($s['plans'] ?? '')))));
    if (!$planList) {                       // no list: original min_tier meaning
        $planList = $s['min_tier'] === 'pro' ? ['pro', 'team'] : ['free', 'pro', 'team'];
    }
    $names = ['free' => 'Free', 'pro' => 'Pro', 'team' => 'Team'];
    $labels = array_map(fn($p) => $names[$p] ?? $p, $planList);
    $caption = count($labels) === 1 ? $labels[0]
        : implode(', ', array_slice($labels, 0, -1)) . ' and ' . end($labels);
    $isPaid = !in_array('free', $planList, true);
    $on = (int)$s['enabled'] === 1;
    $empty = trim((string)$s['source']) === ''; ?>
<section class="card" id="<?= e($s['slug']) ?>" aria-labelledby="h-<?= e($s['slug']) ?>">
  <div class="script-head">
    <h2 id="h-<?= e($s['slug']) ?>"><?= e($s['name']) ?></h2>
    <?= plan_badge($isPaid ? 'pro' : 'free') ?>
    <?= state_chip($on ? 'enabled' : 'disabled') ?>
    <span class="muted small">Available to <b><?= e($caption) ?></b></span>
  </div>
  <div class="status-grid" style="margin:10px 0">
    <div class="status-item"><span class="k">Version</span><b><?= (int)$s['version'] ?></b></div>
    <div class="status-item"><span class="k">Last published</span><?= when($s['published_at'] ?? $s['updated_at']) ?>
      <?= !empty($s['published_by']) ? '<span class="small muted">by ' . e($s['published_by']) . '</span>' : '' ?></div>
    <div class="status-item"><span class="k">Checksum</span><span class="mono small"><?= e(substr((string)($s['checksum'] ?: ''), 0, 16)) ?>…</span></div>
    <div class="status-item"><span class="k">Size</span><b><?= number_format(strlen((string)$s['source'])) ?> bytes</b></div>
  </div>
  <?php if ($empty): ?>
    <div class="alert alert-warn" role="status">This script is empty, so nothing is injected for it yet. Paste your
      <?= e($s['name']) ?> source below and publish.</div>
  <?php endif; ?>

  <form method="post" data-guard>
    <?= csrf_field() ?>
    <input type="hidden" name="slug" value="<?= e($s['slug']) ?>">
    <input type="hidden" name="action" value="save">
    <label class="field">Source
      <textarea class="code" name="source" spellcheck="false" placeholder="// Paste your <?= e($s['name']) ?> here (a Tampermonkey-style userscript)."><?= e($s['source']) ?></textarea></label>
    <label class="check"><input type="checkbox" name="enabled"<?= $on ? ' checked' : '' ?>> Enabled — deliver this script to entitled installations</label>
    <fieldset class="plan-picker" style="margin:10px 0;border:1px solid var(--line,#2a3550);border-radius:8px;padding:10px 12px">
      <legend class="muted small" style="padding:0 6px">Deliver to these plans</legend>
      <?php foreach (['free' => 'Free', 'pro' => 'Pro', 'team' => 'Unlimited for Team'] as $pk => $pl): ?>
        <label class="check" style="display:inline-block;margin-right:16px">
          <input type="checkbox" name="plans[]" value="<?= e($pk) ?>"
            <?= in_array($pk, $planList, true) ? ' checked' : '' ?>> <?= e($pl) ?>
        </label>
      <?php endforeach; ?>
      <button class="btn btn-sm btn-ghost" name="action" value="plans" style="margin-left:8px">Save entitlement only</button>
      <p class="muted small" style="margin:8px 0 0">
        The signed manifest lists only the scripts the requesting installation's plan is entitled to.
        Changing this here takes effect at the next check-in — the source code, version and checksum
        are not touched, and the app drops the cached copy of a script it is no longer entitled to.
      </p>
    </fieldset>
    <button class="btn btn-primary" name="action" value="save"<?= confirm_attr('Publish ' . $s['name'] . '? It reaches installations at their next check-in.') ?>>Save &amp; publish</button>
    <?php if ($on): ?>
      <button class="btn btn-danger" name="action" value="disable" formnovalidate<?= confirm_attr('Disable ' . $s['name'] . '? It stops being delivered.') ?>>Disable</button>
    <?php else: ?>
      <button class="btn btn-good" name="action" value="enable" formnovalidate>Enable</button>
    <?php endif; ?>
  </form>
</section>
<?php endforeach; ?>

<section class="card">
  <h2>How delivery works</h2>
  <p class="muted small">On each check-in the app receives a signed manifest of the scripts its plan is entitled to,
    listing each script's version and SHA-256. It downloads a script only when the version changed, verifies the
    bytes against the checksum, and holds the source in memory to inject into new profiles. If a download fails or a
    checksum does not match, the app keeps the previous good copy and records an error you can see under
    <a href="logs.php?tab=errors">Audit &amp; error logs</a>.</p>
</section>
<?php layout_bottom(); ?>
