<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/status_page.php';
require_once __DIR__ . '/includes/ratelimit.php';

$order = status_load_order();
if ($order === null) {
    page_top('Order — ' . SITE_NAME, 'Order status.', '/thanks.php', ['noindex' => true]);
    echo '<section class="status-wrap">' . status_badge('bad') . '<h1>Order not found</h1>'
       . '<p class="muted">This link is invalid or has expired. If you have paid, check the email you used at '
       . 'checkout for your licence key, or contact support.</p>'
       . '<p style="margin-top:22px"><a class="btn btn-ghost" href="/pricing.php">Back to pricing</a></p></section>';
    page_bottom();
    exit;
}

// v8: back from the card page -> ask Stripe straight away, so the key is on
// this page at once instead of after the webhook.
if ($order['provider'] === 'stripe' && !$order['license_id'] && in_array($order['status'], ORDER_OPEN, true)
    && stripe_ready() && rate_ok('stripe_sync', (string)$order['ref'], 1, 4)) {
    try {
        stripe_sync_order($order);
        $order = order_by_id((int)$order['id']) ?: $order;
    } catch (Throwable $e) {
        error_log('[mavelylink] stripe_sync_order: ' . $e->getMessage());
    }
}
$cardReturn = $order['provider'] === 'stripe' && get_str('paid', 10) === 'card';
$lic = $order['license_id'] ? license_by_id((int)$order['license_id']) : null;
$status = (string)$order['status'];
$paid = $status === 'paid' && $lic;
$currency = (string)$order['currency'];
$method = get_str('m', 30);
$urls = order_urls($order);
$check = '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>';

// details for a manual method chosen at checkout (USDT / channel)
$usdtAddr = (string)setting('usdt_address', '');
$usdtNet = (string)setting('usdt_network', 'TRC20');
$isManual = $method === 'usdt' || str_starts_with($method, 'manual:')
    || in_array((string)$order['provider'], ['manual', 'usdt'], true)
    || str_starts_with((string)$order['provider'], 'manual');
$isUsdt = $method === 'usdt' || ($method === '' && $isManual && $usdtAddr !== '');
$channel = null;
if (str_starts_with($method, 'manual:')) {
    $code = substr($method, 7);
    foreach (channels_enabled() as $c) {
        if ($c['code'] === $code) { $channel = $c; break; }
    }
}

page_top(($paid ? 'Your licence key' : 'Your order') . ' — ' . SITE_NAME,
    'Order status and your licence key.', '/thanks.php', ['noindex' => true]);
?>
<section class="status-wrap" id="status-root"
         data-ref="<?= e($order['ref']) ?>" data-t="<?= e($order['access_token']) ?>"
         data-status="<?= e($status) ?>">
<?php if ($paid): ?>
  <?= status_badge('good') ?>
  <h1>You're all set</h1>
  <p class="muted">Payment confirmed for the <b style="color:var(--ink)"><?= e(plan_name((string)$order['plan_code'])) ?></b> plan.
     We've emailed your licence key to <b style="color:var(--ink)"><?= e($order['email']) ?></b>.</p>
  <div class="keybox">
    <code id="lic-key"><?= e($lic['serial']) ?></code>
    <button class="copybtn" type="button" data-copy="<?= e($lic['serial']) ?>">Copy</button>
  </div>
  <p class="muted small">Access until <?= e(substr((string)$lic['expires_at'], 0, 10)) ?> ·
     up to <?= (int)$lic['max_devices'] ?> computer<?= (int)$lic['max_devices'] === 1 ? '' : 's' ?></p>
  <div class="note info" style="text-align:left;margin-top:26px">
    <b>How to activate</b>
    <ol style="margin:8px 0 0;padding-left:20px;color:var(--ink-2)">
      <li>Open the app and click <b>Register licence</b> in the top-right.</li>
      <li>Paste the key above and confirm.</li>
      <li>The app switches to your plan and unlocks its features straight away.</li>
    </ol>
  </div>
  <div style="margin-top:24px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
    <a class="btn btn-primary" href="<?= e($urls['receipt']) ?>">View receipt</a>
    <a class="btn btn-ghost" href="/docs.php#activate">Activation guide</a>
  </div>

<?php elseif ($status === 'pending' && $isManual): ?>
  <?= status_badge('wait') ?>
  <h1>Complete your payment</h1>
  <p class="muted">Your order <b style="color:var(--ink)"><?= e($order['ref']) ?></b> is reserved. Pay
     <b style="color:var(--ink)"><?= e(money((float)$order['final_amount'], $currency)) ?></b>, then send us the payment
     reference below. Your licence key is emailed to <b style="color:var(--ink)"><?= e($order['email']) ?></b>
     as soon as the payment is verified.</p>
  <?php if ($isUsdt && $usdtAddr !== ''): ?>
    <div class="note info" style="text-align:left">
      <b>Send exactly <?= e(money((float)$order['final_amount'], $currency)) ?> in USDT (<?= e($usdtNet) ?>)</b> to:
      <div class="keybox" style="margin:12px 0 0"><code style="font-size:1rem"><?= e($usdtAddr) ?></code>
        <button class="copybtn" type="button" data-copy="<?= e($usdtAddr) ?>">Copy</button></div>
      <p class="small" style="margin:12px 0 0">Use the <?= e($usdtNet) ?> network only. After sending, paste the transaction hash below.</p>
    </div>
  <?php elseif ($channel): $link = channel_link($channel, (string)$order['ref']); ?>
    <div class="note info" style="text-align:left">
      <b>Pay through <?= e($channel['display_name']) ?></b>
      <?php if (!empty($channel['instructions'])): ?><p class="small" style="margin:6px 0"><?= e($channel['instructions']) ?></p><?php endif; ?>
      <p class="small" style="margin:6px 0">Mention your order reference <b><?= e($order['ref']) ?></b> in the message.</p>
      <?php if ($link !== ''): ?><p style="margin:12px 0 0"><a class="btn btn-primary btn-sm" href="<?= e($link) ?>" target="_blank" rel="noopener nofollow">Open <?= e($channel['display_name']) ?></a></p><?php endif; ?>
    </div>
  <?php endif; ?>
  <form id="claim-form" data-method="<?= e($method !== '' ? $method : 'manual') ?>" style="max-width:440px;margin:22px auto 0;text-align:left">
    <label class="field"><span>Payment reference / transaction hash</span>
      <input name="reference" required placeholder="Paste your payment reference" maxlength="150">
      <span class="hint" id="claim-msg"></span>
    </label>
    <button class="btn btn-primary btn-block" type="submit">I've paid — submit reference</button>
  </form>
  <p class="muted small" style="margin-top:16px">This page updates by itself once your payment is confirmed.</p>

<?php elseif ($status === 'awaiting_verification'): ?>
  <?= status_badge('wait') ?>
  <h1>We're verifying your payment</h1>
  <p class="muted">Thanks — we have your payment reference for order <b style="color:var(--ink)"><?= e($order['ref']) ?></b>.
     As soon as the payment is confirmed we'll email your licence key to
     <b style="color:var(--ink)"><?= e($order['email']) ?></b>, and it will also appear on this page.</p>
  <div class="note info" style="text-align:left"><b>What happens next</b>
    <p class="small" style="margin:6px 0 0">Manual payments are usually checked within a few hours. If it takes longer,
       contact <?= e(SUPPORT_EMAIL) ?> with your order reference.</p></div>
  <p class="muted small" style="margin-top:16px">This page updates by itself once your payment is confirmed.</p>

<?php elseif (($cardReturn && $status === 'pending') || ($order['provider'] === 'stripe' && $status === 'approved')): ?>
  <?= status_badge('wait') ?>
  <h1>Confirming your card payment</h1>
  <p class="muted">Thanks — the card payment for order <b style="color:var(--ink)"><?= e($order['ref']) ?></b> is being
     confirmed with the bank. This normally takes a few seconds. Your licence key will appear here and is also emailed to
     <b style="color:var(--ink)"><?= e($order['email']) ?></b>.</p>
  <p class="muted small" style="margin-top:16px">This page updates by itself once your payment is confirmed.</p>

<?php elseif (in_array($status, ['pending'], true)): ?>
  <?= status_badge('wait') ?>
  <h1>Waiting for payment</h1>
  <p class="muted">Your order is reserved. Complete the payment to receive your licence key. If you didn't mean to
     start this, you can simply ignore it.</p>
  <div style="margin-top:22px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
    <a class="btn btn-primary" href="/buy.php?plan=<?= e($order['plan_code']) ?>">Complete payment</a>
    <a class="btn btn-ghost" href="/pricing.php">Back to pricing</a>
  </div>

<?php else: /* failed / cancelled / refunded */ ?>
  <?= status_badge('bad') ?>
  <h1><?= $status === 'refunded' ? 'Order refunded' : 'Payment not completed' ?></h1>
  <p class="muted"><?= $status === 'refunded'
    ? 'This order was refunded. If you think this is a mistake, contact support.'
    : e($order['failure_reason'] ?: 'Your payment was not completed, so no licence was issued. You have not been charged.') ?></p>
  <div style="margin-top:22px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
    <a class="btn btn-primary" href="/buy.php?plan=<?= e($order['plan_code']) ?>">Try again</a>
    <a class="btn btn-ghost" href="mailto:<?= e(SUPPORT_EMAIL) ?>">Contact support</a>
  </div>
<?php endif; ?>
</section>

<script>
(function () {
  'use strict';
  var root = document.getElementById('status-root');
  if (!root) { return; }
  var CSRF = <?= json_encode(csrf_token()) ?>;
  var ref = root.dataset.ref, t = root.dataset.t, status = root.dataset.status;

  document.querySelectorAll('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      var txt = b.getAttribute('data-copy');
      if (navigator.clipboard) {
        navigator.clipboard.writeText(txt).then(function () {
          var o = b.textContent; b.textContent = 'Copied'; setTimeout(function () { b.textContent = o; }, 1500);
        });
      }
    });
  });

  // manual-claim submission
  var cf = document.getElementById('claim-form');
  if (cf) {
    var cmsg = document.getElementById('claim-msg');
    cf.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = cf.querySelector('button');
      btn.disabled = true; btn.textContent = 'Submitting…';
      fetch('/api/v1/claim.php', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
        body: JSON.stringify({ ref: ref, t: t, reference: cf.reference.value.trim(), method: cf.dataset.method || 'manual' })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.ok) {
          cf.innerHTML = '<div class="note good">' + (d.message || 'Thank you. We will verify your payment shortly.') + '</div>';
        } else {
          btn.disabled = false; btn.textContent = "I've paid — submit reference";
          cmsg.style.color = 'var(--bad)'; cmsg.textContent = d.error || 'Could not submit. Try again.';
        }
      }).catch(function () {
        btn.disabled = false; btn.textContent = "I've paid — submit reference";
        cmsg.style.color = 'var(--bad)'; cmsg.textContent = 'Network error. Try again.';
      });
    });
  }

  // poll for confirmation while pending, then reload to show the key
  if (status === 'pending' || status === 'awaiting_verification' || status === 'approved') {
    var tries = 0;
    var timer = setInterval(function () {
      tries++;
      if (tries > 120) { clearInterval(timer); return; }   // ~10 min
      fetch('/api/v1/order.php?ref=' + encodeURIComponent(ref) + '&t=' + encodeURIComponent(t))
        .then(function (r) { return r.json(); }).then(function (d) {
          if (d.ok && d.status !== status) { clearInterval(timer); window.location.reload(); }
        }).catch(function () {});
    }, 5000);
  }
})();
</script>
<?php page_bottom(); ?>
