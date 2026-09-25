<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';
$pro = plan_get('pro');
$proPrice = $pro ? money((float)$pro['current_price'], (string)$pro['currency']) : '$29';
$team = plan_get('team');
$teamPrice = $team ? money((float)$team['current_price'], (string)$team['currency']) : '$49';

$faqs = [
  ['Do I need to pay or sign up to start?',
   'No. The app opens on the Free plan the moment you install it — no account, email, card or trial timer. '
   . 'The Free plan gives you 5 profiles, two languages, one screen size and Script 1 on one computer.'],
  ['What does the Free plan include?',
   'Up to 5 browser profiles, the en-US and fr-FR languages, the 1920×1080 screen size, and Script 1, on one computer. '
   . 'Paid features are visible in the app but clearly marked so you know what Pro adds.'],
  ['What do I get with Pro?',
   'Unlimited profiles, the full fingerprint engine, every language and screen size, and both Script 1 and Script 2, on one computer. '
   . 'Pro is ' . $proPrice . ' for 30 days.'],
  ['What is Unlimited for Team?',
   'Everything in Pro, but one licence key works on up to three computers. It is ' . $teamPrice . ' for 30 days.'],
  ['Is this a subscription?',
   'No. Paid plans are a one-time 30-day purchase with no automatic renewal. When the period ends you simply buy '
   . 'another if you want to keep the paid features. Nothing is stored to charge you again.'],
  ['How do I activate a paid plan?',
   'Buy on the pricing page, then click Register licence in the app and paste your key. It unlocks immediately and '
   . 'is remembered on that computer, so you are not asked again.'],
  ['Can I move my licence to another computer?',
   'Yes. On Pro, choose Release this computer in the app on the old machine, then register the key on the new one. '
   . 'Team keys cover three computers at once. An administrator can also free a seat for you.'],
  ['Which payment methods can I use?',
   'PayPal and card (through PayPal) when enabled, and USDT or a contact channel such as WhatsApp or Telegram for '
   . 'manual payments. With a manual payment your licence is issued once we verify the transfer.'],
  ['Do coupons work at checkout?',
   'Yes. Enter your code in the coupon box and the discount is calculated and shown before you pay. The final price '
   . 'is always worked out on our server.'],
  ['Does it work on macOS or Linux?',
   'The desktop app is built for Windows 10 and 11. The profiles it creates use Google Chrome.'],
];
page_top('FAQ — ' . SITE_NAME, 'Answers about the Free plan, Pro and Team, payments, coupons and licences.', '/faq.php');
?>
<section>
  <div class="wrap section-head"><span class="kicker">FAQ</span><h1>Frequently asked questions</h1></div>
  <div class="wrap faq">
    <?php foreach ($faqs as [$q, $a]): ?>
      <details><summary><?= e($q) ?></summary><p><?= e($a) ?></p></details>
    <?php endforeach; ?>
  </div>
  <div class="wrap" style="text-align:center;margin-top:34px">
    <p class="muted">Still have a question?</p>
    <a class="btn btn-ghost" href="mailto:<?= e(SUPPORT_EMAIL) ?>">Email <?= e(SUPPORT_EMAIL) ?></a>
  </div>
</section>
<?php page_bottom(); ?>
