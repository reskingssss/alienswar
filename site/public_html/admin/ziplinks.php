<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/tool_control.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * Control ZIP Links (v8).
 *
 * The ZIP posting feature reads post folders: comment.txt (the link),
 * description.txt and image.png. Before a post is published the tool checks
 * the link's domain against the list allowed for the installation's plan:
 *   supported      -> posted normally
 *   not supported  -> NOT posted; the user sees the message below, the
 *                     supported domains and a button to get supported links.
 * A plan whose switch is OFF has no check at all: every link is supported.
 * The feature switch removes the check for everybody.
 */
$testResult = null;
$errors = [];
if (admin_post()) {
    $act = (string)($_POST['action'] ?? '');
    if ($act === 'save') {
        $errors = ziplinks_save($_POST);
        if (!$errors) {
            back_to('ziplinks.php', 'Saved. Installations apply the new rules at their next check-in.');
        }
    }
    if ($act === 'test') {
        $link = mb_substr(trim((string)($_POST['link'] ?? '')), 0, 500);
        $plan = in_array($_POST['plan'] ?? '', TOOL_TIERS, true) ? (string)$_POST['plan'] : 'free';
        $testResult = ['link' => $link, 'plan' => $plan, 'ok' => ziplinks_link_allowed($link, $plan)];
    }
}

$cfg = ziplinks_config();
if ($errors) {                     // show what was typed, not what is stored
    $cfg['enabled'] = !empty($_POST['enabled']);
    $cfg['message'] = (string)($_POST['message'] ?? $cfg['message']);
    $cfg['redirect_url'] = (string)($_POST['redirect_url'] ?? $cfg['redirect_url']);
}
$tierNames = ['free' => 'Free', 'pro' => 'Pro', 'team' => 'Unlimited for team'];
$lists = array_map(static fn($t) => implode("\n", $cfg['tiers'][$t]['domains']), array_combine(TOOL_TIERS, TOOL_TIERS));
$same = count(array_unique($lists)) === 1;

layout_top('Control ZIP Links', 'Which links the ZIP posting feature may publish, per plan.');
foreach ($errors as $err) {
    echo '<div class="alert alert-bad" role="alert">' . e($err) . '</div>';
}
?>
<form method="post" class="zl-form" data-guard>
  <?= csrf_field() ?>
  <input type="hidden" name="action" value="save">

  <section class="card switch-card <?= $cfg['enabled'] ? 'is-on' : 'is-off' ?>" aria-labelledby="zl-master">
    <div class="switch-state">
      <h2 id="zl-master">Control ZIP Links</h2>
      <p class="muted small">When the feature is OFF it is removed completely: every link in every ZIP post is published,
        on every plan, exactly as before.</p>
    </div>
    <label class="tm-switch tm-big" for="zl-enabled">
      <input type="checkbox" id="zl-enabled" name="enabled" value="1"<?= $cfg['enabled'] ? ' checked' : '' ?>>
      <span class="tm-track" aria-hidden="true"><span class="tm-knob"></span></span>
      <span class="tm-tier">Feature enabled</span>
    </label>
  </section>

  <div id="zl-body">
  <section class="card" aria-labelledby="zl-tiers">
    <div class="card-head"><h2 id="zl-tiers">Which plans are checked</h2></div>
    <p class="muted small">Switch <b>on</b>: only supported links are posted on that plan. Switch <b>off</b>: every link is
      supported on that plan (“If the link is not supported → post normally”).</p>
    <div class="zl-tierrow">
      <?php foreach (TOOL_TIERS as $t): ?>
      <label class="tm-switch tm-<?= $t ?>" for="zl-e-<?= $t ?>">
        <input type="checkbox" id="zl-e-<?= $t ?>" name="enforce[<?= $t ?>]" value="1"<?= $cfg['tiers'][$t]['enforce'] ? ' checked' : '' ?>>
        <span class="tm-track" aria-hidden="true"><span class="tm-knob"></span></span>
        <span class="tm-tier"><?= e($tierNames[$t]) ?></span>
      </label>
      <?php endforeach; ?>
    </div>
  </section>

  <section class="card" aria-labelledby="zl-domains">
    <div class="card-head">
      <h2 id="zl-domains">Supported links</h2>
      <label class="check"><input type="checkbox" id="zl-same" name="same_for_all" value="1"<?= $same ? ' checked' : '' ?>> Same list for every plan</label>
    </div>
    <p class="muted small">One domain per line (<code>usathedeals.shop</code>). A domain also covers its sub-domains
      (<code>www.</code>, <code>go.</code> …). Paste full links if you like — only the domain is kept.</p>
    <div data-zl-all>
      <label class="field"><span>Domains for every plan</span>
        <textarea name="domains_all" rows="7" spellcheck="false" class="mono"><?= e($lists['free']) ?></textarea></label>
    </div>
    <div class="grid grid-3" data-zl-per>
      <?php foreach (TOOL_TIERS as $t): ?>
      <label class="field"><span><?= e($tierNames[$t]) ?></span>
        <textarea name="domains[<?= $t ?>]" rows="7" spellcheck="false" class="mono"><?= e($lists[$t]) ?></textarea></label>
      <?php endforeach; ?>
    </div>
  </section>

  <section class="card" aria-labelledby="zl-msg">
    <div class="card-head"><h2 id="zl-msg">What the user sees</h2></div>
    <div class="form-grid">
      <label class="field"><span>Message <span class="hint">{plan} becomes Free / Pro / Unlimited for Team</span></span>
        <input type="text" name="message" maxlength="300" required value="<?= e($cfg['message']) ?>"></label>
      <label class="field"><span>“Get supported links” address</span>
        <input type="url" name="redirect_url" maxlength="500" required value="<?= e($cfg['redirect_url']) ?>"></label>
      <label class="field"><span>Button text</span>
        <input type="text" name="redirect_label" maxlength="60" value="<?= e($cfg['redirect_label']) ?>"></label>
    </div>
    <label class="check"><input type="checkbox" name="check_description" value="1"<?= $cfg['check_description'] ? ' checked' : '' ?>>
      Also check links written in description.txt</label>
    <label class="check"><input type="checkbox" name="apply_to_csv" value="1"<?= $cfg['apply_to_csv'] ? ' checked' : '' ?>>
      Also apply to CSV / XLSX posts</label>

    <div class="zl-preview" aria-label="Preview of the message in the tool">
      <div class="zl-pv-title">⛔ Link not supported</div>
      <div class="zl-pv-msg"><?= e(str_replace('{plan}', 'Free', $cfg['message'])) ?></div>
      <div class="zl-pv-sub">Supported links:</div>
      <div class="zl-pv-list"><?php foreach (array_slice($cfg['tiers']['free']['domains'], 0, 6) as $d): ?><span>https://<?= e($d) ?></span><?php endforeach; ?></div>
      <div class="zl-pv-btns"><span class="zl-pv-ghost">Close</span><span class="zl-pv-accent">↗ <?= e($cfg['redirect_label']) ?></span></div>
    </div>
  </section>
  </div>

  <div class="tm-savebar"><button type="submit" class="btn btn-primary btn-lg">Save</button></div>
</form>

<section class="card" aria-labelledby="zl-test">
  <div class="card-head"><h2 id="zl-test">Test a link</h2><span class="muted small">Uses the saved rules — nothing is changed.</span></div>
  <form method="post" class="toolbar">
    <?= csrf_field() ?>
    <input type="hidden" name="action" value="test">
    <label class="field" style="flex:1;min-width:260px"><span>Link from comment.txt</span>
      <input type="text" name="link" maxlength="500" placeholder="https://usathedeals.shop/1j5ke9" value="<?= e($testResult['link'] ?? '') ?>"></label>
    <label class="field"><span>Plan</span>
      <select name="plan"><?php foreach ($tierNames as $k => $v): ?><option value="<?= $k ?>"<?= ($testResult['plan'] ?? '') === $k ? ' selected' : '' ?>><?= e($v) ?></option><?php endforeach; ?></select></label>
    <button class="btn">Test</button>
  </form>
  <?php if ($testResult !== null): ?>
    <p><?= $testResult['ok'] ? state_chip('ok', 'Supported — the post is published') : state_chip('blocked', 'Not supported — the post is skipped') ?></p>
  <?php endif; ?>
</section>
<?php layout_bottom();
