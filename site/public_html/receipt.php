<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/status_page.php';

$order = status_load_order();
if ($order === null) {
    page_top('Receipt — ' . SITE_NAME, 'Receipt.', '/receipt.php', ['noindex' => true]);
    echo '<section class="status-wrap">' . status_badge('bad') . '<h1>Receipt not found</h1>'
       . '<p class="muted">This link is invalid or has expired.</p></section>';
    page_bottom();
    exit;
}
$lic = $order['license_id'] ? license_by_id((int)$order['license_id']) : null;
$currency = (string)$order['currency'];
$statusPill = ['paid' => ['paid', 'Paid'], 'awaiting_verification' => ['pend', 'Pending'],
               'pending' => ['pend', 'Pending'], 'refunded' => ['fail', 'Refunded'],
               'failed' => ['fail', 'Not paid'], 'cancelled' => ['fail', 'Cancelled']][(string)$order['status']] ?? ['pend', ucfirst((string)$order['status'])];

page_top('Receipt ' . $order['ref'] . ' — ' . SITE_NAME, 'Your receipt.', '/receipt.php', ['noindex' => true]);
?>
<div class="wrap receipt">
  <div class="noprint" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap">
    <a href="<?= e(order_urls($order)['status']) ?>">&larr; Back to order</a>
    <button class="btn btn-ghost btn-sm" onclick="window.print()">Print / save PDF</button>
  </div>
  <div class="paper">
    <div class="rhead">
      <div>
        <h1 style="font-size:1.5rem;margin:0"><?= e(SITE_NAME) ?></h1>
        <p style="color:#5b6b86;margin:4px 0 0">Receipt</p>
      </div>
      <div style="text-align:right">
        <span class="pill <?= $statusPill[0] ?>"><?= e($statusPill[1]) ?></span>
        <p style="color:#5b6b86;margin:8px 0 0;font-size:.9rem">Order <b><?= e($order['ref']) ?></b></p>
      </div>
    </div>
    <div style="display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;margin-bottom:20px;font-size:.92rem;color:#40506a">
      <div><b>Billed to</b><br><?= e($order['customer_name'] ?: $order['email']) ?><br><?= e($order['email']) ?></div>
      <div style="text-align:right"><b>Date</b><br><?= e(substr((string)($order['paid_at'] ?: $order['created_at']), 0, 16)) ?> UTC</div>
    </div>
    <div class="rrow"><span><?= e(plan_name((string)$order['plan_code'])) ?> plan — <?= (int)$order['period_days'] ?> days access</span>
      <span><?= e(money((float)$order['original_amount'], $currency)) ?></span></div>
    <?php if ((float)$order['discount_amount'] > 0): ?>
      <div class="rrow"><span>Coupon <?= $order['coupon_code'] ? '(' . e($order['coupon_code']) . ', ' . (int)$order['coupon_percent'] . '%)' : '' ?></span>
        <span style="color:#0a7d47">−<?= e(money((float)$order['discount_amount'], $currency)) ?></span></div>
    <?php endif; ?>
    <div class="rrow tot"><span>Total</span><span><?= e(money((float)$order['final_amount'], $currency)) ?></span></div>
    <div style="margin-top:18px;font-size:.9rem;color:#40506a">
      <div class="rrow" style="border:0;padding:4px 0"><span>Payment method</span><span><?= e(ucfirst((string)($order['provider'] ?: 'n/a'))) ?></span></div>
      <div class="rrow" style="border:0;padding:4px 0"><span>Computers allowed</span><span><?= (int)$order['device_limit'] ?></span></div>
      <?php if ($lic): ?><div class="rrow" style="border:0;padding:4px 0"><span>Licence key</span><span style="font-family:monospace"><?= e($lic['serial']) ?></span></div><?php endif; ?>
    </div>
    <p style="margin-top:24px;color:#7181a0;font-size:.82rem">No automatic renewal. Access ends
      <?= $lic ? e(substr((string)$lic['expires_at'], 0, 10)) : 'when the period elapses' ?>.
      Questions? <?= e(SUPPORT_EMAIL) ?></p>
  </div>
</div>
<?php page_bottom(); ?>
