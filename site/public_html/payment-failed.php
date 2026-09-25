<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/status_page.php';
$order = status_load_order();
$reason = $order['failure_reason'] ?? '';
page_top('Payment problem — ' . SITE_NAME, 'Payment problem.', '/payment-failed.php', ['noindex' => true]);
?>
<section class="status-wrap">
  <?= status_badge('bad') ?>
  <h1>We couldn't complete your payment</h1>
  <p class="muted"><?= e($reason ?: 'The payment did not go through, so no licence was issued and you have not been charged.') ?></p>
  <div class="note info" style="text-align:left;margin-top:22px">
    <b>What you can do</b>
    <ul style="margin:8px 0 0;padding-left:20px;color:var(--ink-2)">
      <li>Try again — a different card or PayPal balance often works.</li>
      <li>Choose another payment method at checkout.</li>
      <li>Still stuck? Email <?= e(SUPPORT_EMAIL) ?> and we'll help.</li>
    </ul>
  </div>
  <div style="margin-top:22px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
    <a class="btn btn-primary" href="/buy.php?plan=<?= e($order['plan_code'] ?? 'pro') ?>">Try again</a>
    <a class="btn btn-ghost" href="mailto:<?= e(SUPPORT_EMAIL) ?>">Contact support</a>
  </div>
</section>
<?php page_bottom(); ?>
