<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/license.php';

/**
 * Admin shell (v7): grouped sidebar, a status pill that always shows the
 * real master-switch state, and the small UI helpers every page shares.
 * layout_top() / layout_bottom() keep their original names and arguments.
 */
function admin_nav(): array
{
    return [
        ['', [['index.php', 'Overview', 'dash']]],
        ['Sales', [['payments.php', 'Payments', 'card'], ['coupons.php', 'Coupons', 'tag'],
                   ['plans.php', 'Pricing plans', 'price']]],
        ['Customers', [['licenses.php', 'Licences', 'key'],
                       ['customers.php', 'Customers & referrals', 'user'],
                       ['referrals.php', 'Referral events', 'share']]],
        ['Desktop app', [['status.php', 'Application status', 'power'], ['scripts.php', 'User scripts', 'code'],
                         // v7.0.0: server-controlled Python tabs. The title is
                         // the one the brief specifies, character for character.
                         ['tabs.php', 'ADD Tabs *Py in Your Tool', 'tabs'],
                         ['update.php', 'App updates', 'up']]],
        ['Website', [['channels.php', 'Contact channels', 'chat'], ['settings.php', 'Settings', 'gear']]],
        ['System', [['logs.php', 'Audit & error logs', 'log'], ['upgrade.php', 'Database', 'db']]],
    ];
}

function icon(string $name): string
{
    $p = [
        'dash'  => '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
        'card'  => '<rect x="2.5" y="5" width="19" height="14" rx="2"/><path d="M2.5 10h19M6 15h4"/>',
        'tag'   => '<path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
        'price' => '<path d="M12 3v18M16.5 7.5c0-1.7-2-3-4.5-3s-4.5 1.3-4.5 3 2 2.6 4.5 3 4.5 1.3 4.5 3-2 3-4.5 3-4.5-1.3-4.5-3"/>',
        'key'   => '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3M14 9l2 2"/>',
        'power' => '<path d="M12 3v8"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
        'code'  => '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>',
        'up'    => '<path d="M12 19V5M5 12l7-7 7 7"/><path d="M4 21h16"/>',
        'chat'  => '<path d="M4 5h16v11H9l-5 4z"/>',
        'gear'  => '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
        'log'   => '<path d="M6 3h9l4 4v14H6z"/><path d="M9 11h7M9 15h7M9 7h3"/>',
        'db'    => '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.5"/><path d="M4.5 5.5v13c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5v-13M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5"/>',
        'out'   => '<path d="M10 4H5v16h5M15 8l4 4-4 4M19 12H9"/>',
        'menu'  => '<path d="M4 7h16M4 12h16M4 17h16"/>',
        'copy'  => '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
        // v7.0.0: server-controlled Python tabs (a tab strip over a panel)
        'tabs'  => '<path d="M3 8h6V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3h6"/><rect x="3" y="8" width="18" height="12" rx="1.5"/><path d="M8 13h8M8 16h5"/>',
        // v6.3: referral programme
        'user'  => '<circle cx="12" cy="8" r="3.5"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
        'share' => '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.2 10.8l7.6-3.6M8.2 13.2l7.6 3.6"/>',
    ][$name] ?? '<circle cx="12" cy="12" r="8"/>';
    return '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' . $p . '</svg>';
}

function plan_badge(string $code): string
{
    $code = in_array($code, PLAN_CODES, true) ? $code : 'free';
    $label = ['free' => 'Free', 'pro' => 'Pro', 'team' => 'Team'][$code];
    return '<span class="plan plan-' . $code . '" title="' . e(plan_name($code)) . '">' . $label . '</span>';
}

/** Coloured chip that also carries a shape and a word, never colour alone. */
function state_chip(string $state, ?string $label = null): string
{
    $good = ['active', 'on', 'enabled', 'paid', 'completed', 'approved', 'current', 'ok', 'sent'];
    $warn = ['pending', 'review', 'awaiting_verification', 'expired', 'update_required', 'optional',
             'expiring', 'hidden', 'used_up', 'inactive'];
    $bad  = ['blocked', 'revoked', 'off', 'disabled', 'failed', 'rejected', 'refunded', 'mandatory',
             'removed', 'cancelled', 'error', 'device_removed'];
    $kind = in_array($state, $good, true) ? 'good' : (in_array($state, $warn, true) ? 'warn'
          : (in_array($state, $bad, true) ? 'bad' : 'muted'));
    $glyph = ['good' => '●', 'warn' => '▲', 'bad' => '■', 'muted' => '○'][$kind];
    $text = $label ?? ucfirst(str_replace('_', ' ', $state));
    return '<span class="chip chip-' . $kind . '"><span aria-hidden="true">' . $glyph . '</span> ' . e($text) . '</span>';
}

function rel_time(?string $dt): string
{
    if (!$dt) {
        return 'never';
    }
    $s = time() - (int)strtotime($dt . ' UTC');
    if ($s < 0) {
        $s = -$s;
        $in = true;
    }
    $txt = $s < 60 ? $s . ' s' : ($s < 3600 ? floor($s / 60) . ' min'
         : ($s < 86400 ? floor($s / 3600) . ' h' : floor($s / 86400) . ' d'));
    return empty($in) ? $txt . ' ago' : 'in ' . $txt;
}

function when(?string $dt): string
{
    return $dt ? '<time datetime="' . e(str_replace(' ', 'T', $dt)) . 'Z" title="' . e($dt) . ' UTC">'
        . e(rel_time($dt)) . '</time>' : '<span class="muted">never</span>';
}

function tip(string $text): string
{
    return '<span class="tip" tabindex="0" role="note" aria-label="' . e($text) . '" data-tip="' . e($text) . '">?</span>';
}

function confirm_attr(string $message): string
{
    return ' data-confirm="' . e($message) . '"';
}

function pager(int $total, int $per, int $page, array $params): string
{
    $pages = (int)ceil($total / max(1, $per));
    if ($pages <= 1) {
        return '';
    }
    $out = '<nav class="pager" aria-label="Pages">';
    $from = max(1, $page - 4);
    $to = min($pages, $from + 9);
    if ($page > 1) {
        $out .= '<a href="?' . e(http_build_query(['p' => $page - 1] + $params)) . '">Previous</a>';
    }
    for ($i = $from; $i <= $to; $i++) {
        $out .= '<a href="?' . e(http_build_query(['p' => $i] + $params)) . '"'
              . ($i === $page ? ' aria-current="page" class="here"' : '') . '>' . $i . '</a>';
    }
    if ($page < $pages) {
        $out .= '<a href="?' . e(http_build_query(['p' => $page + 1] + $params)) . '">Next</a>';
    }
    return $out . '</nav>';
}

/** The master switch, identical wherever it appears. Posts to status.php. */
function master_switch_card(bool $detailed = true): void
{
    $on = application_enabled();
    $changedAt = setting('app_status_changed_at');
    $changedBy = setting('app_status_changed_by');
    $interval = (int)setting('checkin_seconds', (string)cfg('CHECKIN_SECONDS', 180));
    ?>
    <section class="card switch-card <?= $on ? 'is-on' : 'is-off' ?>" aria-labelledby="ms-title">
      <div class="switch-state">
        <h2 id="ms-title">Master switch</h2>
        <p class="switch-now">Application is <?= state_chip($on ? 'on' : 'off', $on ? 'ON — installations can run' : 'OFF — installations are disabled') ?></p>
        <?php if ($changedAt): ?>
          <p class="muted small">Last changed <?= when($changedAt) ?><?= $changedBy ? ' by ' . e($changedBy) : '' ?>.</p>
        <?php endif; ?>
        <?php if ($detailed): ?>
        <p class="muted small">
          <?= $on
            ? 'Turning the application OFF stops every installation at its next check-in (about every ' . max(1, (int)round($interval / 60)) . ' min). Profiles, licences and settings are kept.'
            : 'Installations show “' . e(app_disabled_message()) . '” and stop working. Turning it ON lets them continue at their next check-in.' ?>
        </p>
        <?php endif; ?>
      </div>
      <form method="post" action="status.php">
        <?= csrf_field() ?>
        <input type="hidden" name="return" value="<?= e(basename($_SERVER['SCRIPT_NAME'] ?? 'status.php')) ?>">
        <?php if ($on): ?>
          <button class="btn btn-danger btn-lg" name="set_enabled" value="0"
            <?= confirm_attr('Turn the application OFF? Every installation stops at its next check-in. No data is deleted.') ?>>Turn application OFF</button>
        <?php else: ?>
          <button class="btn btn-good btn-lg" name="set_enabled" value="1"
            <?= confirm_attr('Turn the application ON? Installations resume at their next check-in.') ?>>Turn application ON</button>
        <?php endif; ?>
      </form>
    </section>
    <?php
}

function layout_top(string $title, string $subtitle = ''): void
{
    $active = basename($_SERVER['SCRIPT_NAME'] ?? '');
    $appOn = application_enabled();
    ?>
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title><?= e($title) ?> · <?= e(SITE_NAME) ?> Admin</title>
<link rel="stylesheet" href="../assets/css/admin.css?v=7">
</head><body>
<a class="skip" href="#main">Skip to content</a>
<input type="checkbox" id="navtoggle" hidden>
<div class="shell">
  <aside class="sidebar" aria-label="Admin navigation">
    <div class="side-brand"><span class="brand-mark" aria-hidden="true"></span><?= e(SITE_NAME) ?> <span>Admin</span></div>
    <nav class="side-nav">
      <?php foreach (admin_nav() as [$group, $items]): ?>
        <?php if ($group !== ''): ?><div class="side-group"><?= e($group) ?></div><?php endif; ?>
        <?php foreach ($items as [$href, $label, $ic]): ?>
          <a href="<?= $href ?>"<?= $active === $href ? ' class="here" aria-current="page"' : '' ?>><?= icon($ic) ?><span><?= e($label) ?></span></a>
        <?php endforeach; ?>
      <?php endforeach; ?>
    </nav>
    <form method="post" action="logout.php" class="side-logout">
      <?= csrf_field() ?>
      <button type="submit"><?= icon('out') ?><span>Log out <?= e($_SESSION['admin_user'] ?? '') ?></span></button>
    </form>
  </aside>
  <div class="content">
    <header class="topbar">
      <label for="navtoggle" class="burger" aria-label="Open menu"><?= icon('menu') ?></label>
      <div class="titles">
        <h1><?= e($title) ?></h1>
        <?php if ($subtitle !== ''): ?><p><?= e($subtitle) ?></p><?php endif; ?>
      </div>
      <a class="status-pill <?= $appOn ? 'is-on' : 'is-off' ?>" href="status.php">
        Application: <b><?= $appOn ? 'ON' : 'OFF' ?></b>
      </a>
    </header>
    <main id="main" tabindex="-1">
<?php
    if (!$appOn && $active !== 'status.php') {
        echo '<div class="alert alert-bad" role="status"><b>The application is OFF.</b> Installations are disabled at their next check-in. '
           . '<a href="status.php">Open Application status</a> to turn it back ON.</div>';
    }
    if (schema_pending() && $active !== 'upgrade.php') {
        echo '<div class="alert alert-warn" role="status"><b>Database upgrade pending.</b> <a href="upgrade.php">Review and run it</a>.</div>';
    }
    foreach (['ok' => ['good', 'status'], 'err' => ['bad', 'alert']] as $k => [$cls, $role]) {
        if (!empty($_GET[$k]) && is_string($_GET[$k])) {
            echo '<div class="alert alert-' . $cls . '" role="' . $role . '">' . e(mb_substr($_GET[$k], 0, 400)) . '</div>';
        }
    }
}

function layout_bottom(): void
{
    ?>
    </main>
  </div>
</div>
<dialog id="confirm-dialog" class="confirm" aria-labelledby="confirm-title">
  <form method="dialog">
    <h2 id="confirm-title">Please confirm</h2>
    <p id="confirm-text"></p>
    <div class="actions">
      <button value="cancel" class="btn btn-ghost">Cancel</button>
      <button value="ok" class="btn btn-primary" id="confirm-ok">Confirm</button>
    </div>
  </form>
</dialog>
<script src="../assets/js/admin.js?v=7"></script>
</body></html>
<?php }
