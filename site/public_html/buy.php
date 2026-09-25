<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';
require_once __DIR__ . '/includes/orders.php';
require_once __DIR__ . '/includes/csrf.php';
public_session_start();

$planCode = preg_replace('/[^a-z]/', '', strtolower((string)($_GET['plan'] ?? 'pro'))) ?: 'pro';
$plan = plan_get($planCode);
$methods = checkout_methods();
$check = '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>';
$lock = '<svg viewBox="0 0 24 24"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>';

// plan not purchasable -> explain and offer the alternatives
if (!$plan || !plan_is_paid($planCode) || $plan['status'] !== 'active' || !(int)$plan['purchasable']) {
    page_top('Checkout — ' . SITE_NAME, 'Choose a plan to continue.', '/buy.php', ['noindex' => true]);
    echo '<section class="status-wrap"><h1>That plan is not available</h1>'
       . '<p class="muted">It may have been turned off. See the current plans and pick one that fits.</p>'
       . '<p style="margin-top:22px"><a class="btn btn-primary" href="/pricing.php">View pricing</a></p></section>';
    page_bottom();
    exit;
}

$q = price_quote($planCode, '', '');
$currency = (string)$plan['currency'];
$paypalClientId = paypal_ready() ? (string)setting('paypal_client_id', '') : '';
$paypalLive = setting_bool('paypal_live');
$paypalCards = setting_bool('paypal_cards', true);
$hasAutomatic = isset($methods['paypal']) || isset($methods['crypto']) || isset($methods['card']);
$manualChannels = channels_enabled();

page_top('Checkout · ' . $plan['name'] . ' — ' . SITE_NAME,
    'Secure checkout for the ' . $plan['name'] . ' plan.', '/buy.php', ['noindex' => true]);
?>
<div class="wrap">
  <div class="checkout">
    <!-- left: form -->
    <div class="pay-form">
      <h1 style="font-size:clamp(1.7rem,3.5vw,2.3rem)">Checkout</h1>
      <p class="muted">You are buying the <b style="color:var(--ink)"><?= e($plan['name']) ?></b> plan.
        Your licence key is emailed and shown on screen the moment your payment is confirmed.</p>

      <?php if (!$methods): ?>
        <div class="note warn" role="status"><b>Online payment is being set up.</b> Please contact us to complete your
          purchase and we will activate your licence by hand.
          <?php if ($manualChannels): ?><div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap">
            <?php foreach ($manualChannels as $c): $l = channel_link($c); if ($l === '') { continue; } ?>
              <a class="btn btn-ghost btn-sm" href="<?= e($l) ?>" target="_blank" rel="noopener nofollow"><?= e($c['display_name']) ?></a>
            <?php endforeach; ?></div><?php endif; ?>
        </div>
      <?php endif; ?>

      <form id="checkout-form" novalidate>
        <input type="hidden" name="plan" value="<?= e($planCode) ?>">
        <label class="field" id="f-email">
          <span>Email address</span>
          <input type="email" name="email" autocomplete="email" required placeholder="you@email.com" inputmode="email">
          <span class="err">Enter a valid email — your licence key is sent here.</span>
        </label>
        <label class="field" id="f-name">
          <span>Name <span class="muted" style="font-weight:400">(optional)</span></span>
          <input type="text" name="name" autocomplete="name" maxlength="120" placeholder="For your receipt">
        </label>

        <label class="field" id="f-coupon">
          <span>Coupon code <span class="muted" style="font-weight:400">(optional)</span></span>
          <div class="coupon-row">
            <input type="text" name="coupon" maxlength="40" placeholder="e.g. SAVE20" autocapitalize="characters" spellcheck="false">
            <button type="button" class="btn btn-ghost" id="apply-coupon">Apply</button>
          </div>
          <span class="hint" id="coupon-msg"></span>
        </label>

        <?php if ($methods): ?>
        <h3 style="margin:26px 0 12px">Payment method</h3>
        <div class="methods">
          <?php $first = true; foreach ($methods as $key => $m): ?>
            <label class="method">
              <input type="radio" name="method" value="<?= e($key) ?>"<?= $first ? ' checked' : '' ?>
                     data-kind="<?= e($m['kind']) ?>"<?= isset($m['channel']) ? ' data-channel="' . e($m['channel']['code']) . '"' : '' ?>>
              <span>
                <span class="m-name"><?= e($m['label']) ?><?php if (!empty($m['cards'])): ?>
                  <span class="cardmarks" aria-label="VISA and Mastercard accepted"><?= card_marks() ?></span><?php endif; ?></span>
                <?php if (!empty($m['hint'])): ?><span class="m-hint"><?= e($m['hint']) ?></span><?php endif; ?>
              </span>
            </label>
          <?php $first = false; endforeach; ?>
        </div>

        <div id="pay-actions" class="pay-note">
          <div id="paypal-box" hidden></div>
          <button type="submit" class="btn btn-primary btn-lg btn-block" id="continue-btn">Continue</button>
          <div class="trust"><?= $lock ?> <span>Payments are processed securely. We never see or store card details.</span></div>
        </div>
        <p class="err" id="form-error" style="color:var(--bad);display:none;margin-top:12px"></p>
        <?php endif; ?>
      </form>
    </div>

    <!-- right: order summary -->
    <aside class="summary">
      <div class="order">
        <h3>Order summary</h3>
        <div class="line"><span><?= e($plan['name']) ?> plan</span>
          <span class="v" id="sum-original"><?= e(money((float)$q['original'], $currency)) ?></span></div>
        <div class="line discount" id="sum-discount-row" hidden>
          <span>Coupon <span id="sum-coupon-code" class="muted"></span></span>
          <span class="v" id="sum-discount">−<?= e(money(0, $currency)) ?></span></div>
        <div class="line total"><span>Total</span>
          <span class="v" id="sum-total"><?= e(money((float)$q['final'], $currency)) ?></span></div>
        <p class="muted small" style="margin:10px 0 0">Access for <?= (int)$plan['period_days'] ?> days ·
          <?= (int)$plan['device_limit'] ?> computer<?= (int)$plan['device_limit'] === 1 ? '' : 's' ?> · no auto-renewal</p>

        <ul class="incl">
          <?php foreach (array_slice(array_values(array_filter(plan_features($plan), fn($f) => !str_starts_with($f, '!'))), 0, 6) as $f): ?>
            <li><?= $check ?><span><?= e($f) ?></span></li>
          <?php endforeach; ?>
        </ul>
      </div>
      <div class="trust" style="justify-content:center;margin-top:16px">
        <?= $lock ?> <span>30-day access · licence emailed instantly</span>
      </div>
    </aside>
  </div>
</div>

<script>
(function () {
  'use strict';
  var CSRF = <?= json_encode(csrf_token()) ?>;
  var CURRENCY = <?= json_encode($currency) ?>;
  var PLAN = <?= json_encode($planCode) ?>;
  var form = document.getElementById('checkout-form');
  if (!form) { return; }
  var emailEl = form.email, couponEl = form.coupon;
  var msg = document.getElementById('coupon-msg');
  var formErr = document.getElementById('form-error');
  var contBtn = document.getElementById('continue-btn');
  var ppBox = document.getElementById('paypal-box');
  var appliedCoupon = '';

  function money(n) {
    var s = CURRENCY === 'USD' ? '$' : (CURRENCY + ' ');
    return s + Number(n).toFixed(2);
  }
  function setField(id, bad) { document.getElementById(id).classList.toggle('bad', !!bad); }
  function currentMethod() {
    var r = form.querySelector('input[name=method]:checked');
    return r ? { value: r.value, kind: r.dataset.kind, channel: r.dataset.channel } : null;
  }

  // ---- coupon: validated on the server, never in the browser ----------
  function applyCoupon() {
    var code = (couponEl.value || '').trim();
    msg.style.color = ''; msg.textContent = code ? 'Checking…' : '';
    var body = { plan: PLAN, code: code, email: (emailEl.value || '').trim() };
    fetch('/api/v1/coupon.php', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (d) {
      var dRow = document.getElementById('sum-discount-row');
      if (d.ok && d.percent > 0) {
        appliedCoupon = code;
        document.getElementById('sum-original').textContent = money(d.original);
        document.getElementById('sum-discount').textContent = '−' + money(d.discount);
        document.getElementById('sum-coupon-code').textContent = '(' + d.percent + '% off)';
        document.getElementById('sum-total').textContent = money(d.final);
        dRow.hidden = false;
        msg.style.color = 'var(--good)'; msg.textContent = d.percent + '% off applied.';
      } else {
        appliedCoupon = '';
        dRow.hidden = true;
        document.getElementById('sum-total').textContent = money(d.final != null ? d.final : 0);
        if (code) { msg.style.color = 'var(--bad)'; msg.textContent = d.error || 'That coupon is not valid.'; }
        else { msg.textContent = ''; }
      }
    }).catch(function () { msg.style.color = 'var(--bad)'; msg.textContent = 'Could not check the coupon. Try again.'; });
  }
  var applyBtn = document.getElementById('apply-coupon');
  if (applyBtn) { applyBtn.addEventListener('click', applyCoupon); }
  if (couponEl) {
    couponEl.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); applyCoupon(); } });
    couponEl.addEventListener('blur', function () { if (couponEl.value.trim() !== appliedCoupon) { applyCoupon(); } });
  }

  function validEmail() {
    var v = (emailEl.value || '').trim();
    var ok = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v);
    setField('f-email', !ok);
    return ok;
  }
  emailEl.addEventListener('input', function () { if (emailEl.value) { setField('f-email', false); } });

  // ---- method switching: PayPal shows its buttons; others use Continue -
  var PAYPAL_ID = <?= json_encode($paypalClientId) ?>;
  var PAYPAL_CARDS = <?= $paypalCards && !isset($methods['card']) ? 'true' : 'false' ?>;
  var paypalLoaded = false, paypalRendered = false;

  function showFor(method) {
    formErr.style.display = 'none';
    if (!method) { return; }
    if (method.kind === 'paypal') {
      contBtn.style.display = 'none'; ppBox.hidden = false;
      loadPaypal();
    } else {
      contBtn.style.display = ''; ppBox.hidden = true;
      contBtn.textContent = method.kind === 'manual' ? 'Continue to payment instructions'
        : (method.value === 'card' ? 'Pay by card' : 'Continue to payment');
    }
  }
  form.querySelectorAll('input[name=method]').forEach(function (r) {
    r.addEventListener('change', function () { showFor(currentMethod()); });
  });

  function loadPaypal() {
    if (!PAYPAL_ID) { return; }
    if (paypalLoaded) { renderPaypal(); return; }
    var s = document.createElement('script');
    s.src = 'https://www.paypal.com/sdk/js?client-id=' + encodeURIComponent(PAYPAL_ID)
          + '&currency=' + encodeURIComponent(CURRENCY) + '&intent=capture&components=buttons'
          + (PAYPAL_CARDS ? '&enable-funding=card' : '&disable-funding=card');
    s.onload = function () { paypalLoaded = true; renderPaypal(); };
    s.onerror = function () { formErr.style.display = 'block'; formErr.textContent = 'PayPal could not load. Check your connection or pick another method.'; };
    document.head.appendChild(s);
  }

  function renderPaypal() {
    if (paypalRendered || !window.paypal) { return; }
    paypalRendered = true;
    ppBox.innerHTML = '';
    window.paypal.Buttons({
      style: { layout: 'vertical', color: 'blue', shape: 'pill', label: 'pay', height: 46 },
      onClick: function (data, actions) {
        if (!validEmail()) { formErr.style.display = 'block'; formErr.textContent = 'Enter your email above first.'; return actions.reject(); }
        formErr.style.display = 'none';
        return actions.resolve();
      },
      createOrder: function () {
        return fetch('/api/v1/checkout.php', {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
          body: JSON.stringify({ plan: PLAN, email: emailEl.value.trim(), name: form.name.value.trim(),
                                 coupon: appliedCoupon, method: 'paypal' })
        }).then(function (r) { return r.json().then(function (d) { return { status: r.status, d: d }; }); })
          .then(function (res) {
            if (!res.d.ok) { throw new Error(res.d.error || 'Could not start the order.'); }
            window.__mvlOrder = { ref: res.d.ref, t: res.d.t };
            return res.d.paypal_order_id;
          });
      },
      onApprove: function () {
        var o = window.__mvlOrder || {};
        return fetch('/api/v1/paypal_capture.php', {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
          body: JSON.stringify({ ref: o.ref, t: o.t })
        }).then(function (r) { return r.json(); }).then(function (d) {
          if (d.redirect) { window.location = d.redirect; }
          else if (d.ok) { window.location = '/thanks.php?ref=' + encodeURIComponent(o.ref) + '&t=' + encodeURIComponent(o.t); }
          else { formErr.style.display = 'block'; formErr.textContent = d.error || 'Payment could not be completed.'; }
        });
      },
      onError: function () {
        formErr.style.display = 'block';
        formErr.textContent = 'Something went wrong with PayPal. Please try again or choose another method.';
      }
    }).render('#paypal-box');
  }

  // ---- non-PayPal submit ---------------------------------------------
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var method = currentMethod();
    if (!method) { return; }
    if (!validEmail()) { formErr.style.display = 'block'; formErr.textContent = 'Enter a valid email address first.'; return; }
    formErr.style.display = 'none';
    contBtn.disabled = true; contBtn.textContent = 'Please wait…';
    fetch('/api/v1/checkout.php', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
      body: JSON.stringify({ plan: PLAN, email: emailEl.value.trim(), name: form.name.value.trim(),
                             coupon: appliedCoupon, method: method.value })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d.ok && d.redirect) { window.location = d.redirect; return; }
      contBtn.disabled = false; showFor(method);
      formErr.style.display = 'block';
      formErr.textContent = d.error || 'Could not continue. Please check your details and try again.';
      if (d.field === 'email') { setField('f-email', true); }
      if (d.field === 'coupon') { setField('f-coupon', true); }
    }).catch(function () {
      contBtn.disabled = false; showFor(method);
      formErr.style.display = 'block'; formErr.textContent = 'Network error. Please try again.';
    });
  });

  showFor(currentMethod());
})();
</script>
<?php page_bottom(); ?>
