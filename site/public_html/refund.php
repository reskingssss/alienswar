<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';
page_top('Refund policy — ' . SITE_NAME, 'Our refund policy.', '/refund.php');
?>
<section class="wrap prose">
  <span class="kicker">Legal</span>
  <h1>Refund policy</h1>
  <p class="muted">Last updated <?= e(date('F Y')) ?>.</p>

  <h2>Try before you buy</h2>
  <p>The <b>Free plan</b> is the best way to decide if the app is right for you. It's available forever with no payment,
     so you can confirm the app installs, runs and generates profiles on your system before buying a paid plan.</p>

  <h2>Paid plans</h2>
  <p>Paid plans unlock digital features and licences immediately, so they are generally non-refundable once the licence
     key has been issued and activated. That said, we want you to be treated fairly:</p>
  <ul>
    <li>If the software does not work on your system and we cannot help you fix it, email us within <b>7 days</b> of your
        purchase and we'll arrange a refund of that period.</li>
    <li>If you were charged incorrectly or more than once, contact us and we'll put it right.</li>
    <li>Because there is no automatic renewal, you are never charged again for a following period — a plan simply ends.</li>
  </ul>

  <h2>How to request a refund</h2>
  <p>Email <a href="mailto:<?= e(SUPPORT_EMAIL) ?>"><?= e(SUPPORT_EMAIL) ?></a> with your order reference (from your
     receipt) and a short description of the problem. We aim to reply within a couple of business days.</p>

  <p class="muted small">This policy doesn't limit any statutory rights you may have under the consumer law that applies to you.</p>
</section>
<?php page_bottom(); ?>
