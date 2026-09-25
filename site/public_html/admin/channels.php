<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/orders.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * Facebook, WhatsApp and Telegram as contact / manual-payment channels.
 * They are not payment processors here: a customer opens a link to reach
 * you, and any payment stays pending until you approve it in Payments.
 */
const CHANNEL_DEFS = [
    'whatsapp' => ['WhatsApp', 'whatsapp', 'Number or wa.me link'],
    'telegram' => ['Telegram', 'telegram', 'Username, bot or channel'],
    'facebook' => ['Facebook Messenger', 'facebook', 'Page or m.me link'],
];

foreach (CHANNEL_DEFS as $code => [$name, $icon]) {
    $st = db()->prepare('SELECT 1 FROM channels WHERE code = ?');
    $st->execute([$code]);
    if (!$st->fetch()) {
        db()->prepare('INSERT INTO channels (code, display_name, icon, enabled, manual_payments, sort_order, updated_at)
                       VALUES (?,?,?,0,1,?,?)')->execute([$code, $name, $icon, array_search($code, array_keys(CHANNEL_DEFS), true), now()]);
    }
}

if (admin_post()) {
    $code = (string)($_POST['code'] ?? '');
    if (!isset(CHANNEL_DEFS[$code])) {
        back_to('channels.php', 'Unknown channel.', false);
    }
    $name = mb_substr(trim((string)($_POST['display_name'] ?? '')), 0, 80);
    $url = trim((string)($_POST['url'] ?? ''));
    $handle = mb_substr(trim((string)($_POST['handle'] ?? '')), 0, 120);
    $instructions = mb_substr(trim(str_replace("\r\n", "\n", (string)($_POST['instructions'] ?? ''))), 0, 1000);
    $enabled = isset($_POST['enabled']) ? 1 : 0;
    $manual = isset($_POST['manual_payments']) ? 1 : 0;

    if ($name === '') {
        $name = CHANNEL_DEFS[$code][0];
    }
    if ($url !== '' && !is_web_url($url)) {
        back_to('channels.php', 'The link must be a full http(s):// URL, or leave it empty and use the number/username field.', false);
    }
    if ($enabled && $url === '' && $handle === '') {
        back_to('channels.php', 'Add a link or a number/username before enabling ' . $name . '.', false);
    }
    db()->prepare('UPDATE channels SET display_name = ?, url = ?, handle = ?, instructions = ?, enabled = ?,
                   manual_payments = ?, updated_at = ? WHERE code = ?')
        ->execute([$name, $url, $handle, $instructions ?: null, $enabled, $manual, now(), $code]);
    audit('channel.saved', $code . ($enabled ? ' enabled' : ' disabled') . ($manual ? ' manual-pay' : ''));
    back_to('channels.php#' . $code, $name . ' saved.');
}

$rows = [];
foreach (db()->query('SELECT * FROM channels ORDER BY sort_order') as $r) {
    $rows[$r['code']] = $r;
}
layout_top('Contact channels', 'Facebook, WhatsApp and Telegram for support and manual payments.');
?>
<section class="card">
  <p class="muted">These appear on the website and checkout so customers can reach you or arrange a manual payment.
    They are not automatic payment processors: when a customer opens one of these links, any payment they make
    stays <b>pending</b> until you verify it and approve it in <a href="payments.php?status=open">Payments</a>.
    A licence is never issued just because a link was opened.</p>
</section>

<?php foreach (CHANNEL_DEFS as $code => [$name, $icon, $handleLabel]): $c = $rows[$code]; ?>
<section class="card" id="<?= e($code) ?>" aria-labelledby="h-<?= e($code) ?>">
  <div class="card-head"><h2 id="h-<?= e($code) ?>"><?= e($name) ?></h2>
    <?= (int)$c['enabled'] ? state_chip('enabled', 'Shown to customers') : state_chip('off', 'Hidden') ?></div>
  <form method="post">
    <?= csrf_field() ?><input type="hidden" name="code" value="<?= e($code) ?>">
    <div class="form-grid">
      <label class="field">Display name<input name="display_name" value="<?= e($c['display_name']) ?>" maxlength="80"></label>
      <label class="field"><?= e($handleLabel) ?> <?= tip('Used to build the link when the full URL is empty. WhatsApp: digits only. Telegram: username without @. Facebook: page name.') ?>
        <input name="handle" value="<?= e($c['handle']) ?>" maxlength="120"></label>
    </div>
    <label class="field">Full link <span class="hint">optional; overrides the field above</span>
      <input name="url" value="<?= e($c['url']) ?>" placeholder="https://…" maxlength="500"></label>
    <label class="field">Instructions shown to the customer
      <textarea name="instructions" rows="3" maxlength="1000"><?= e($c['instructions'] ?? '') ?></textarea></label>
    <label class="check"><input type="checkbox" name="enabled"<?= (int)$c['enabled'] ? ' checked' : '' ?>> Show this channel on the website and checkout</label>
    <label class="check"><input type="checkbox" name="manual_payments"<?= (int)$c['manual_payments'] ? ' checked' : '' ?>> Offer it at checkout as a way to arrange payment</label>
    <button class="btn btn-primary">Save <?= e($name) ?></button>
    <?php $preview = channel_link($c, 'ORD-EXAMPLE');
    if ($preview !== ''): ?><p class="small muted">Link preview: <a href="<?= e($preview) ?>" target="_blank" rel="noopener nofollow"><?= e($preview) ?></a></p><?php endif; ?>
  </form>
</section>
<?php endforeach; ?>
<?php layout_bottom(); ?>
