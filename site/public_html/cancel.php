<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/status_page.php';
$order = status_load_order();
// mark a still-open order as cancelled when the buyer backs out at the provider
if ($order !== null && in_array($order['status'], ['pending'], true)) {
    order_update((int)$order['id'], ['status' => 'cancelled', 'failure_reason' => 'Payment cancelled by the customer.']);
    audit('order.cancelled', (string)$order['ref']);
    $order['status'] = 'cancelled';
}
page_top('Payment cancelled — ' . SITE_NAME, 'Payment cancelled.', '/cancel.php', ['noindex' => true]);
?>
<section class="status-wrap">
  <?= status_badge('bad') ?>
  <h1>Payment cancelled</h1>
  <p class="muted">No payment was taken and no licence was issued. You can pick up where you left off whenever you like.</p>
  <div style="margin-top:22px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
    <a class="btn btn-primary" href="/buy.php?plan=<?= e($order['plan_code'] ?? 'pro') ?>">Try again</a>
    <a class="btn btn-ghost" href="/pricing.php">Back to pricing</a>
  </div>
</section>
<?php page_bottom(); ?>
