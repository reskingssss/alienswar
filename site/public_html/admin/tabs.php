<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/tabs.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * ADD Tabs *Py in Your Tool  (v7.0.0)
 *
 * The one place remote tabs are managed. Each row here becomes a tab in
 * the desktop tool's tab bar, beside Profiles and Invite. The Python module
 * lives in this database and is delivered at runtime — it is not inside the
 * distributed build.
 *
 * Renaming a tab here renames it in the tool. The `slug` is the stable
 * internal key and is deliberately NOT recomputed from the title, so a
 * rename is a rename and not a new tab.
 */

// ---------------------------------------------------------------------
// POST actions
// ---------------------------------------------------------------------
if (admin_post()) {
    $act = (string)($_POST['action'] ?? '');
    $id  = (int)($_POST['id'] ?? 0);

    // ---- the master switch for the whole feature ----------------------
    if ($act === 'master') {
        $on = (string)($_POST['on'] ?? '0') === '1';
        tabs_set_enabled($on);
        audit('tab.master', $on ? 'on' : 'off');
        back_to('tabs.php', $on
            ? 'Remote tabs are ON. Installations load them at their next launch or Refresh.'
            : 'Remote tabs are OFF. Every installation stops loading them at its next launch.');
    }

    // ---- validate only: never writes ----------------------------------
    if ($act === 'validate') {
        $_SESSION['tab_validate'] = tabs_validate_script((string)($_POST['script'] ?? ''));
        $_SESSION['tab_draft'] = [
            'id' => $id,
            'title' => (string)($_POST['title'] ?? ''),
            'slug' => (string)($_POST['slug'] ?? ''),
            'order' => (string)($_POST['order'] ?? '0'),
            'enabled' => isset($_POST['enabled']),
            'required_plan' => (string)($_POST['required_plan'] ?? 'free'),
            'script' => (string)($_POST['script'] ?? ''),
            'min_tool_version' => (string)($_POST['min_tool_version'] ?? ''),
            'ui_width' => (string)($_POST['ui_width'] ?? (string)TAB_ADVISED_W),
            'ui_height' => (string)($_POST['ui_height'] ?? (string)TAB_ADVISED_H),
            'notes' => (string)($_POST['notes'] ?? ''),
        ];
        header('Location: tabs.php?edit=' . ($id > 0 ? $id : 'new') . '#editor');
        exit;
    }

    if ($act === 'save') {
        // A script that will not compile is never published: an installation
        // that downloaded it would show a broken tab and there would be no
        // way to tell from here that it had happened.
        $check = tabs_validate_script((string)($_POST['script'] ?? ''));
        $force = !empty($_POST['force']);
        if (!$check['ok'] && !$force) {
            $_SESSION['tab_validate'] = $check;
            $_SESSION['tab_draft'] = $_POST;
            back_to('tabs.php?edit=' . ($id > 0 ? $id : 'new') . '#editor',
                'Not saved: the script has ' . count($check['errors'])
                . ' problem(s). Fix them, or tick "save anyway".', false);
        }
        $res = tab_save([
            'id' => $id,
            'title' => (string)($_POST['title'] ?? ''),
            'slug' => (string)($_POST['slug'] ?? ''),
            'order' => (int)($_POST['order'] ?? 0),
            'enabled' => isset($_POST['enabled']),
            'required_plan' => (string)($_POST['required_plan'] ?? 'free'),
            'script' => (string)($_POST['script'] ?? ''),
            'min_tool_version' => (string)($_POST['min_tool_version'] ?? ''),
            'ui_width' => (int)($_POST['ui_width'] ?? TAB_ADVISED_W),
            'ui_height' => (int)($_POST['ui_height'] ?? TAB_ADVISED_H),
            'notes' => (string)($_POST['notes'] ?? ''),
        ]);
        if (!$res['ok']) {
            $_SESSION['tab_draft'] = $_POST;
            back_to('tabs.php?edit=' . ($id > 0 ? $id : 'new') . '#editor', $res['error'], false);
        }
        unset($_SESSION['tab_validate'], $_SESSION['tab_draft']);
        back_to('tabs.php?edit=' . $res['id'] . '#editor',
            'Saved as version ' . $res['version'] . '. Installations pick it up at their next launch '
            . 'or when the user presses Refresh tabs.');
    }

    if ($act === 'enable' || $act === 'disable') {
        if (!tab_set_enabled($id, $act === 'enable')) {
            back_to('tabs.php', 'That tab no longer exists.', false);
        }
        back_to('tabs.php', $act === 'enable'
            ? 'Tab enabled. It appears in the tool at the next launch or Refresh.'
            : 'Tab disabled. It disappears from the tool at the next launch or Refresh.');
    }

    if ($act === 'duplicate') {
        $new = tab_duplicate($id);
        if ($new === null) {
            back_to('tabs.php', 'That tab no longer exists.', false);
        }
        back_to('tabs.php?edit=' . $new . '#editor',
            'Duplicated. The copy is disabled until you enable it.');
    }

    if ($act === 'delete') {
        if (!tab_delete($id)) {
            back_to('tabs.php', 'That tab no longer exists.', false);
        }
        back_to('tabs.php', 'Tab deleted. Installations drop it at their next launch or Refresh.');
    }

    if ($act === 'reorder') {
        $ids = (string)($_POST['order_ids'] ?? '');
        $list = array_filter(array_map('intval', explode(',', $ids)));
        if (!$list) {
            back_to('tabs.php', 'Nothing to reorder.', false);
        }
        tabs_reorder($list);
        back_to('tabs.php', 'Order saved. The tool uses it at the next launch or Refresh.');
    }

    back_to('tabs.php', 'Unknown action.', false);
}

// ---------------------------------------------------------------------
// state for the page
// ---------------------------------------------------------------------
$rows = tabs_all();
$editParam = (string)get_str('edit', 12);
$editing = null;
$isNew = ($editParam === 'new');
if ($editParam !== '' && !$isNew) {
    $editing = tab_by_id((int)$editParam);
    if (!$editing) {
        $editParam = '';
    }
}

// A draft survives a failed validate/save so long edits are never lost.
$draft = $_SESSION['tab_draft'] ?? null;
unset($_SESSION['tab_draft']);
$report = $_SESSION['tab_validate'] ?? null;
unset($_SESSION['tab_validate']);

/** Field value: the draft wins, then the stored row, then the default. */
$val = static function (string $key, $default = '') use ($draft, $editing) {
    if (is_array($draft) && array_key_exists($key, $draft)) {
        return $draft[$key];
    }
    if ($editing) {
        $map = ['order' => 'sort_order'];
        $col = $map[$key] ?? $key;
        if (array_key_exists($col, $editing)) {
            return $editing[$col];
        }
    }
    return $default;
};
$checked = static function (string $key, bool $default) use ($draft, $editing): bool {
    if (is_array($draft)) {
        return !empty($draft[$key]);
    }
    if ($editing) {
        return (int)($editing[$key] ?? 0) === 1;
    }
    return $default;
};

$masterOn = tabs_enabled();
$pyBin = tabs_python_binary();
$signingReady = license_signing_ready();
$planNames = ['free' => 'Free — every installation', 'pro' => 'Pro — Pro and Unlimited for Team',
              'team' => 'Unlimited for Team only'];

$sizeVerdict = tab_size_verdict((int)$val('ui_width', TAB_ADVISED_W), (int)$val('ui_height', TAB_ADVISED_H));

layout_top('ADD Tabs *Py in Your Tool',
    'Python tabs defined here appear inside the desktop tool. The code stays on this server.');
?>
<link rel="stylesheet" href="../assets/css/pytabs.css?v=700">

<?php if (!$signingReady): ?>
<div class="alert alert-bad" role="alert"><b>No licence signing key is configured.</b>
  Tab modules are delivered with an Ed25519 signature that the tool verifies before it runs anything,
  so with no key the server refuses to deliver them at all. Generate one under
  <a href="settings.php">Settings → Licence signing keys</a> first.</div>
<?php endif; ?>

<section class="card switch-card <?= $masterOn ? 'is-on' : 'is-off' ?>">
  <div class="switch-state">
    <h2>Remote tabs</h2>
    <p class="switch-now">Remote tabs are
      <?= state_chip($masterOn ? 'on' : 'off',
          $masterOn ? 'ON — installations load them' : 'OFF — no installation loads any tab') ?></p>
    <p class="muted small">
      <?= $masterOn
        ? 'This is the revocation lever. Turning it OFF stops every installation loading every remote tab at its next launch, with no release and no database edit. Use it if a module turns out to be wrong or if this dashboard is ever compromised.'
        : 'No installation is loading remote tabs. The tabs below keep their definitions; nothing is deleted.' ?>
    </p>
  </div>
  <form method="post">
    <?= csrf_field() ?><input type="hidden" name="action" value="master">
    <?php if ($masterOn): ?>
      <button class="btn btn-danger btn-lg" name="on" value="0"
        <?= confirm_attr('Turn remote tabs OFF? Every installation stops loading them at its next launch. Nothing is deleted.') ?>>Turn remote tabs OFF</button>
    <?php else: ?>
      <button class="btn btn-good btn-lg" name="on" value="1">Turn remote tabs ON</button>
    <?php endif; ?>
  </form>
</section>

<section class="card">
  <div class="card-head">
    <h2>Tabs</h2>
    <a class="btn btn-primary" href="tabs.php?edit=new#editor">New tab</a>
  </div>
  <?php if (!$rows): ?>
    <p class="muted">No tabs yet. <a href="tabs.php?edit=new#editor">Create the first one</a> — it appears in the
      tool's tab bar beside <b>Profiles</b> and <b>Invite</b> at the next launch.</p>
  <?php else: ?>
  <form method="post" id="reorder-form">
    <?= csrf_field() ?><input type="hidden" name="action" value="reorder">
    <input type="hidden" name="order_ids" id="order-ids" value="<?= e(implode(',', array_column($rows, 'id'))) ?>">
    <div class="table-wrap">
      <table class="data" id="tab-table">
        <thead><tr>
          <th style="width:2.5rem"><span class="muted small">Drag</span></th>
          <th>Title</th><th>Key</th><th>Plan</th><th>State</th>
          <th>Version</th><th>Size</th><th>Updated</th><th></th>
        </tr></thead>
        <tbody>
        <?php foreach ($rows as $r):
            $locked = $r['required_plan'] !== 'free';
            $empty = trim((string)$r['script']) === ''; ?>
          <tr draggable="true" data-id="<?= (int)$r['id'] ?>">
            <td class="drag-cell" aria-hidden="true">⠿</td>
            <td><a href="tabs.php?edit=<?= (int)$r['id'] ?>#editor"><b><?= e($r['title']) ?></b></a>
              <?php if ($empty): ?><br><span class="chip chip-warn"><span aria-hidden="true">▲</span> No script</span><?php endif; ?></td>
            <td class="mono small"><?= e($r['slug']) ?></td>
            <td><?= plan_badge($locked ? (string)$r['required_plan'] : 'free') ?></td>
            <td><?= (int)$r['enabled'] === 1 ? state_chip('enabled') : state_chip('disabled') ?></td>
            <td><?= (int)$r['version'] ?></td>
            <td class="mono small"><?= (int)$r['ui_width'] ?>×<?= (int)$r['ui_height'] ?></td>
            <td><?= when($r['updated_at']) ?></td>
            <td class="row-actions">
              <a class="btn btn-sm" href="tabs.php?edit=<?= (int)$r['id'] ?>#editor">Edit</a>
            </td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>
    <p class="muted small" style="margin-top:8px">Drag a row to reorder, then save. Without JavaScript, set the
      <b>Order</b> field in each tab's editor instead — both write the same column.</p>
    <button class="btn btn-primary btn-sm">Save order</button>
  </form>
  <?php endif; ?>
</section>

<!-- ================= editor ================= -->
<?php if ($editing || $isNew): ?>
<section class="card" id="editor">
  <div class="card-head">
    <h2><?= $isNew ? 'New tab' : 'Edit “' . e((string)$editing['title']) . '”' ?></h2>
    <?php if ($editing): ?>
      <div class="head-actions">
        <form method="post" style="display:inline">
          <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$editing['id'] ?>">
          <button class="btn btn-sm" name="action" value="duplicate">Duplicate</button>
        </form>
        <form method="post" style="display:inline">
          <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$editing['id'] ?>">
          <?php if ((int)$editing['enabled'] === 1): ?>
            <button class="btn btn-sm btn-danger" name="action" value="disable"
              <?= confirm_attr('Disable “' . $editing['title'] . '”? It disappears from the tool at the next launch.') ?>>Disable</button>
          <?php else: ?>
            <button class="btn btn-sm btn-good" name="action" value="enable">Enable</button>
          <?php endif; ?>
        </form>
        <form method="post" style="display:inline">
          <?= csrf_field() ?><input type="hidden" name="id" value="<?= (int)$editing['id'] ?>">
          <button class="btn btn-sm btn-danger" name="action" value="delete"
            <?= confirm_attr('Delete “' . $editing['title'] . '” for good? The Python module is deleted with it and cannot be recovered.') ?>>Delete</button>
        </form>
      </div>
    <?php endif; ?>
  </div>

  <?php if ($report): ?>
    <div class="alert alert-<?= $report['ok'] ? 'good' : 'bad' ?>" role="status">
      <b><?= $report['ok'] ? 'Script looks valid.' : 'Script has problems.' ?></b>
      <span class="muted small">Checked with <?= e($report['engine']) ?>.</span>
      <?php if ($report['errors']): ?>
        <ul><?php foreach ($report['errors'] as $er): ?><li><?= e((string)$er) ?></li><?php endforeach; ?></ul>
      <?php endif; ?>
    </div>
    <?php if ($report['warnings']): ?>
      <div class="alert alert-warn" role="status"><b>Worth a look.</b>
        <ul><?php foreach ($report['warnings'] as $w): ?><li><?= e((string)$w) ?></li><?php endforeach; ?></ul></div>
    <?php endif; ?>
  <?php endif; ?>

  <form method="post" data-guard id="tab-form">
    <?= csrf_field() ?>
    <input type="hidden" name="id" value="<?= $editing ? (int)$editing['id'] : 0 ?>">

    <div class="form-grid">
      <label class="field">Title <?= tip('The label shown on the tab in the desktop tool. Changing it renames the tab; the internal key below does not change.') ?>
        <input name="title" maxlength="80" required value="<?= e((string)$val('title', '')) ?>"
               placeholder="My Tool"></label>
      <label class="field">Internal key (slug) <?= tip('The stable identifier. Leave it alone once installations have the tab: changing it looks like a brand-new tab and the old one disappears.') ?>
        <input name="slug" maxlength="64" class="mono" value="<?= e((string)$val('slug', '')) ?>"
               placeholder="leave empty to generate from the title"
               <?= $editing ? '' : '' ?>>
        <span class="hint">Letters, digits and underscores. Generated from the title when empty.</span></label>
    </div>

    <div class="form-grid">
      <label class="field">Order <?= tip('Lower numbers sit further left in the tab bar. The drag-and-drop list above writes the same value.') ?>
        <input name="order" type="number" min="0" max="9999" value="<?= (int)$val('order', 0) ?>"></label>
      <label class="field">Required plan
        <select name="required_plan">
          <?php $cur = (string)$val('required_plan', 'free');
          foreach ($planNames as $code => $label): ?>
            <option value="<?= e($code) ?>"<?= $cur === $code ? ' selected' : '' ?>><?= e($label) ?></option>
          <?php endforeach; ?>
        </select>
        <span class="hint">The tab is always visible on every plan. This decides who gets the code.</span></label>
      <label class="field">Minimum tool version <?= tip('Optional. An older build is told to update instead of being handed a module whose contract it does not implement.') ?>
        <input name="min_tool_version" maxlength="32" class="mono" placeholder="e.g. 6.2.0"
               value="<?= e((string)$val('min_tool_version', '')) ?>"></label>
    </div>

    <label class="check"><input type="checkbox" name="enabled"<?= $checked('enabled', true) ? ' checked' : '' ?>>
      Enabled — show this tab in the tool</label>

    <h3>Script <span class="muted small">Python 3.7.7 · Tkinter · standard library only</span></h3>
    <div class="code-wrap" data-pytabs-editor>
      <pre class="code-underlay" aria-hidden="true"></pre>
      <textarea class="code" name="script" id="tab-script" spellcheck="false" wrap="off"
        placeholder="# See “Convert my script with AI” below for the full contract."><?= e((string)$val('script', '')) ?></textarea>
    </div>
    <p class="muted small">Must define <code>TAB_META</code> and <code>def build(parent, ctx):</code>.
      Never <code>Tk()</code>, <code>mainloop()</code> or <code>sys.exit()</code>.
      <?php if ($pyBin === ''): ?>
        <br><b>Note:</b> no Python interpreter was found on this host, so <b>Validate</b> runs the structural
        check only. It catches the contract, 3.8+ syntax and the forbidden calls, but it cannot catch every
        syntax error the way a real <code>compile()</code> would.
      <?php endif; ?></p>

    <h3>Size</h3>
    <div class="form-grid">
      <label class="field">ui_width
        <input name="ui_width" type="number" min="320" max="4096" id="ui-w"
               value="<?= (int)$val('ui_width', TAB_ADVISED_W) ?>"></label>
      <label class="field">ui_height
        <input name="ui_height" type="number" min="200" max="4096" id="ui-h"
               value="<?= (int)$val('ui_height', TAB_ADVISED_H) ?>"></label>
    </div>

    <div class="fitter" id="fitter"
         data-canvas-w="<?= TAB_CANVAS_W ?>" data-canvas-h="<?= TAB_CANVAS_H ?>"
         data-min-w="<?= TAB_CANVAS_MIN_W ?>" data-min-h="<?= TAB_CANVAS_MIN_H ?>"
         data-advised-w="<?= TAB_ADVISED_W ?>" data-advised-h="<?= TAB_ADVISED_H ?>">
      <div class="fitter-stage" aria-hidden="true">
        <div class="fitter-canvas"><span class="fitter-tag">tab canvas <?= TAB_CANVAS_W ?>×<?= TAB_CANVAS_H ?></span>
          <div class="fitter-min"><span class="fitter-tag">smallest window <?= TAB_CANVAS_MIN_W ?>×<?= TAB_CANVAS_MIN_H ?></span></div>
          <div class="fitter-script"><span class="fitter-tag">your script</span></div>
        </div>
      </div>
      <div class="fitter-note" id="fitter-note">
        <?php if ($sizeVerdict['ok']): ?>
          <p class="chip chip-good"><span aria-hidden="true">●</span> Fits the tab canvas at every supported window size.</p>
        <?php else: ?>
          <?php foreach ($sizeVerdict['problems'] as $p): ?>
            <p class="chip chip-warn"><span aria-hidden="true">▲</span> <?= e($p) ?></p>
          <?php endforeach; ?>
          <p class="muted small">Recommended: <b><?= TAB_ADVISED_W ?> × <?= TAB_ADVISED_H ?></b>.
            Larger still works — the container scrolls — but the user has to scroll to reach it.</p>
        <?php endif; ?>
      </div>
    </div>
    <p class="muted small">The tool's tab canvas is <b><?= TAB_CANVAS_W ?> × <?= TAB_CANVAS_H ?> px</b> at the default
      window and never smaller than <b><?= TAB_CANVAS_MIN_W ?> × <?= TAB_CANVAS_MIN_H ?> px</b>. The container is
      DPI-aware and scrollable, so a taller script still works; these numbers say when the user will have to scroll.</p>

    <label class="field">Internal notes <span class="hint">Never sent to any installation.</span>
      <textarea name="notes" rows="3" maxlength="2000"><?= e((string)$val('notes', '')) ?></textarea></label>

    <div class="editor-actions">
      <button class="btn btn-primary" name="action" value="save">Save &amp; publish</button>
      <button class="btn" name="action" value="validate" formnovalidate>Validate script</button>
      <label class="check" style="margin-left:10px"><input type="checkbox" name="force"> Save anyway if validation fails</label>
      <a class="btn btn-ghost" href="tabs.php">Close</a>
    </div>
  </form>
</section>
<?php endif; ?>

<!-- ================= AI converter prompt ================= -->
<section class="card" id="ai-prompt">
  <div class="card-head">
    <h2>Convert my script with AI</h2>
    <button class="btn btn-primary btn-sm" type="button" data-copy-target="#ai-prompt-text">Copy prompt</button>
  </div>
  <p class="muted">Paste this prompt into any AI assistant, then paste your existing Python script where it says so.
    What comes back already conforms to the tab-module contract and can go straight into the <b>Script</b> field above.
    The prompt is generated from the same constants the tool enforces, so it cannot drift from the real contract.</p>
  <pre class="prompt-box" id="ai-prompt-text"><?= e(tabs_ai_prompt()) ?></pre>
</section>

<section class="card">
  <h2>How delivery works</h2>
  <p class="muted small">At launch the tool asks <code>/api/v1/tabs.php</code> for the tab bar and receives titles,
    order and a <b>locked</b> flag — never code. For each tab it is entitled to, it then calls
    <code>/api/v1/tab_script.php</code>, which checks the plan <b>against this database</b> and, only then, returns
    the module sealed and signed. The tool verifies the Ed25519 signature against the public key built into it,
    checks the SHA-256, and executes the module from memory — it is never written to disk.</p>
  <p class="muted small">An installation whose plan does not satisfy <b>Required plan</b> receives HTTP 403 and no
    source at all. That is why the locked state cannot be bypassed by editing the client: there is nothing cached
    locally to unlock. The small popup in the tool is a courtesy, not the lock.</p>
  <p class="muted small"><b>Worth knowing:</b> every module you save here runs on every entitled customer's machine.
    The Ed25519 signature means a stolen copy of this database is not enough to push code to them — an attacker would
    also need the signing key, which is not in this table. It does <em>not</em> protect against someone who gets into
    this dashboard. Keep the admin password long and unique, and use the master switch above if anything looks wrong.</p>
</section>

<script src="../assets/js/pytabs.js?v=700"></script>
<?php layout_bottom(); ?>
