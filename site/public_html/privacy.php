<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';
page_top('Privacy Policy — ' . SITE_NAME, 'Exactly what data we collect and what we do not.', '/privacy.php');
?>
<section class="wrap narrow doc">
  <h1>Privacy Policy</h1>
  <p class="muted">Last updated <?= date('j F Y') ?>. Have a lawyer review this before relying on it.</p>

  <h2>What we collect</h2>
  <ul>
    <li>Your email address, to send your serial and support replies.</li>
    <li>Your licence serial, tier and expiry.</li>
    <li>A one-way hash identifying your computer, so a serial works on one machine.</li>
    <li>Application version, last check-in time, IP address and the <em>number</em> of profiles.</li>
    <li>Payment references from PayPal or the crypto gateway. We never see card details.</li>
  </ul>

  <h2>What we do not collect</h2>
  <p>We do not collect, receive or store the names of your profiles, your cookies, the sites you
     visit, the accounts you use, your scripts' output, or anything you do inside a browser
     profile. That information never leaves your computer.</p>

  <h2>Why</h2>
  <p>Licensing and support, and nothing else. We do not sell or share your data, and we run no
     third-party advertising or tracking on this site.</p>

  <h2>Retention</h2>
  <p>Licence and payment records are kept while your licence is active and for as long as tax law
     requires afterwards. Check-in records older than 90 days are deleted.</p>

  <h2>Your rights</h2>
  <p>Email <a href="mailto:<?= e(SUPPORT_EMAIL) ?>"><?= e(SUPPORT_EMAIL) ?></a> to request a copy
     of your data or its deletion. Deleting your data ends your licence.</p>
</section>
<?php page_bottom(); ?>
