<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/tool_control.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * Tool options by plan (v8).
 *
 * Every option of AutoPoster Pro - both methods - with three switches:
 * Free / Pro / Unlimited for team. The page is laid out like the tool, card
 * for card, so an option is found where it lives in the tool.
 *
 * A switched-off tier sees the option locked in the tool (controls disabled,
 * "🔒 PRO" on its title, the setting held off, the action refused) at the
 * installation's next check-in. The matrix travels inside the Ed25519-signed
 * check-in control block, so it cannot be forged or edited on the client.
 */
if (admin_post()) {
    $act = (string)($_POST['action'] ?? '');
    if ($act === 'save') {
        $gate = $_POST['gate'] ?? [];
        $n = tool_gates_save(is_array($gate) ? $gate : []);
        back_to('features.php', $n === 0
            ? 'Saved. Nothing changed.'
            : 'Saved: ' . $n . ' switch' . ($n === 1 ? '' : 'es') . ' changed. Installations apply it at their next check-in.');
    }
    if ($act === 'reset') {
        $all = [];
        foreach (tool_option_ids() as $id) {
            $all[$id] = ['free' => '1', 'pro' => '1', 'team' => '1'];
        }
        tool_gates_save($all);
        back_to('features.php', 'Every option is allowed on every plan again.');
    }
}

$matrix = tool_gates_matrix();
$catalog = tool_option_catalog();
$locked = ['free' => 0, 'pro' => 0, 'team' => 0];
foreach ($matrix as $row) {
    foreach (TOOL_TIERS as $t) {
        if (!$row[$t]) {
            $locked[$t]++;
        }
    }
}
$tierNames = ['free' => 'Free', 'pro' => 'Pro', 'team' => 'Unlimited for team'];
$tierShort = ['free' => 'Free', 'pro' => 'Pro', 'team' => 'Unlimited'];   // the switch labels; full name in the tooltip
$updated = setting('tool_control_updated_at');

layout_top('Tool options by plan', 'Allow or block every option of the tool for Free, Pro and Unlimited for team.');
?>
<section class="card tm-intro" aria-labelledby="how">
  <div class="card-head">
    <h2 id="how">How it works</h2>
    <?php if ($updated): ?><span class="muted small">Last change <?= when($updated) ?></span><?php endif; ?>
  </div>
  <p class="muted">Each option has three switches. <b>On</b> = the plan may use it. <b>Off</b> = installations on that plan see it
    locked (🔒) with an Upgrade button, and the tool refuses to run it. Changes reach every installation at its next
    check-in (a few minutes) through the signed check-in, so they cannot be bypassed by editing the tool.</p>
  <div class="tm-counts">
    <?php foreach (TOOL_TIERS as $t): ?>
      <div class="tm-count tm-<?= $t ?>"><span class="n"><?= (int)$locked[$t] ?></span>
        <span class="l">option<?= $locked[$t] === 1 ? '' : 's' ?> locked on <?= e($tierNames[$t]) ?></span></div>
    <?php endforeach; ?>
  </div>
</section>

<form method="post" id="gates-form" class="tm-form" data-guard>
  <?= csrf_field() ?>
  <input type="hidden" name="action" value="save">

  <?php foreach ([1 => 'Method 1 · Posting', 2 => 'Method 2 · Profiles'] as $method => $mtitle): ?>
  <h2 class="tm-method"><span class="tm-mnum"><?= $method ?></span><?= e($mtitle) ?></h2>
  <div class="tm-grid">
    <?php foreach ($catalog as [$key, $title, $icon, $m, $items]): if ($m !== $method) { continue; } ?>
    <section class="tm-card" aria-labelledby="c-<?= e($key) ?>">
      <header class="tm-card-head">
        <h3 id="c-<?= e($key) ?>"><span class="tm-ico" aria-hidden="true"><?= e($icon) ?></span><?= e($title) ?></h3>
        <div class="tm-bulk" role="group" aria-label="Quick settings for <?= e($title) ?>">
          <button type="button" class="tm-chip" data-bulk="all">All plans</button>
          <button type="button" class="tm-chip" data-bulk="paid">Pro &amp; Team</button>
          <button type="button" class="tm-chip" data-bulk="team">Team only</button>
        </div>
      </header>
      <?php foreach ($items as [$id, $label, $hint]): $row = $matrix[$id]; ?>
      <div class="tm-row" data-option="<?= e($id) ?>">
        <div class="tm-label">
          <span class="tm-name"><?= e($label) ?></span>
          <span class="tm-hint"><?= e($hint) ?></span>
        </div>
        <div class="tm-switches">
          <?php foreach (TOOL_TIERS as $t): $fid = 'g-' . preg_replace('/[^a-z0-9]/', '-', $id) . '-' . $t; ?>
          <label class="tm-switch tm-<?= $t ?>" for="<?= e($fid) ?>" title="<?= e($label . ' · ' . $tierNames[$t]) ?>">
            <input type="checkbox" id="<?= e($fid) ?>" name="gate[<?= e($id) ?>][<?= $t ?>]" value="1"<?= $row[$t] ? ' checked' : '' ?>
                   aria-label="<?= e($label . ' — ' . $tierNames[$t]) ?>">
            <span class="tm-track" aria-hidden="true"><span class="tm-knob"></span></span>
            <span class="tm-tier" aria-hidden="true"><?= e($tierShort[$t]) ?></span>
          </label>
          <?php endforeach; ?>
        </div>
      </div>
      <?php endforeach; ?>
    </section>
    <?php endforeach; ?>
  </div>
  <?php endforeach; ?>

  <div class="tm-savebar" role="region" aria-label="Save">
    <span class="muted small" id="tm-dirty" hidden>Unsaved changes</span>
    <button type="submit" class="btn btn-primary btn-lg">Save changes</button>
  </div>
</form>

<form method="post" class="tm-reset">
  <?= csrf_field() ?>
  <input type="hidden" name="action" value="reset">
  <button type="submit" class="btn btn-ghost"<?= confirm_attr('Allow every option on every plan again?') ?>>Allow everything on every plan</button>
  <span class="muted small">The ZIP link rules have their own page: <a href="ziplinks.php">Control ZIP Links</a>.</span>
</form>

<?php layout_bottom();
