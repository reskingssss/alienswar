<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';
page_top('Terms of Service — ' . SITE_NAME, 'Licence terms and acceptable use.', '/terms.php');
?>
<section class="wrap narrow doc">
  <h1>Terms of Service</h1>
  <p class="muted">Last updated <?= date('j F Y') ?>. This is a starting point — have a lawyer
     in your jurisdiction review it before you rely on it.</p>

  <h2>1. Licence</h2>
  <p>We grant you a non-exclusive, non-transferable licence to use the software on one computer
     for the period you have paid for. You may not resell, sublicense, rent or redistribute it.</p>

  <h2>2. Acceptable use</h2>
  <p>You are solely responsible for how you use the software and for complying with the terms of
     any third-party website or service you use it with. Using it in a way that breaches another
     party's terms is your responsibility, not ours.</p>

  <h2>3. Suspension</h2>
  <p>We may suspend or revoke a licence that is shared, resold, used to attack our services, or
     used in a way that exposes us to legal liability.</p>

  <h2>4. No warranty</h2>
  <p>The software is provided "as is", without warranty of any kind. We do not guarantee that it
     will be uninterrupted, error-free, or fit for any particular purpose.</p>

  <h2>5. Limitation of liability</h2>
  <p>To the maximum extent permitted by law, our total liability is limited to the amount you
     paid in the twelve months before the claim.</p>

  <h2>6. Changes</h2>
  <p>We may change these terms. Continued use after a change means you accept it.</p>

  <h2>7. Contact</h2>
  <p><a href="mailto:<?= e(SUPPORT_EMAIL) ?>"><?= e(SUPPORT_EMAIL) ?></a></p>
</section>
<?php page_bottom(); ?>
