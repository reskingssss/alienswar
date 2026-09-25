<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';
require_once __DIR__ . '/includes/referral.php';

$threshold = referral_threshold();
$cash      = referral_cash_amount();
$days      = referral_cookie_days();
$plan      = plan_name(referral_reward_plan());

page_top('Referral programme terms — ' . SITE_NAME,
    'How the invite programme works: what counts, when you are paid, and the rules.',
    '/referral-terms.php');
?>
<section class="wrap narrow doc">
  <h1>Referral programme terms</h1>
  <p class="muted">Last updated <?= date('j F Y') ?>. These terms apply to the offer
     &ldquo;Earn an extra $<?= e($cash) ?> or get a <?= e($plan) ?> licence &mdash; invite
     <?= $threshold ?> people&rdquo;.</p>

  <h2>1. Who can take part</h2>
  <p>Anyone with a <?= e(SITE_NAME) ?> invite link, on any plan, including Free. You need an email
     address on file so we know who to reward &mdash; you get your link from the
     <b>Invite</b> tab in the desktop tool.</p>

  <h2>2. What counts as a referral</h2>
  <p>A referral counts only when somebody you invited <b>buys a licence</b> through your link and
     their payment is confirmed. Clicks, downloads, sign-ups and Free installs do not count.</p>
  <p>Your link is remembered on the visitor&rsquo;s device for <b><?= $days ?> days</b>. If they buy
     after that window, or clear their cookies first, or buy through somebody else&rsquo;s link in the
     meantime, the referral cannot be attributed to you.</p>
  <p>The same buyer counts <b>once</b>, however many licences they go on to buy.</p>

  <h2>3. The reward</h2>
  <p>At <b><?= $threshold ?> confirmed referrals</b> a <?= e($plan) ?> licence is issued to your email
     address automatically. You do not need to enter a key &mdash; the desktop tool picks it up on its
     next check-in. The reward is issued once.</p>
  <p>The $<?= e($cash) ?> cash alternative is <b>not</b> automatic. Ask for it by email at
     <a href="mailto:<?= e(SUPPORT_EMAIL) ?>"><?= e(SUPPORT_EMAIL) ?></a>, quoting your invite code,
     instead of taking the licence. Payouts are made within 30 days of an approved request, to a
     destination you nominate and we can reach. Any fees charged by the payment method come out of
     the amount.</p>
  <p>If you already hold a paid plan, the reward licence is still issued to you; where you already
     have an active licence of the same type, its expiry is extended instead of issuing a second key.</p>

  <h2>4. Refunds and chargebacks</h2>
  <p>If a purchase you referred is refunded or charged back, that referral is reversed and your
     total goes down by one. If you had already been rewarded and your total then falls below
     <?= $threshold ?>, we do not take the reward back automatically &mdash; the case is reviewed by
     a person first, and we will contact you before anything changes.</p>

  <h2>5. What is not allowed</h2>
  <ul>
    <li>Referring yourself, including through a second email address, a second account or another
        computer you control.</li>
    <li>Buying through your own link, or arranging for a refund after the reward is issued.</li>
    <li>Paid search advertising on our brand name, spam, unsolicited bulk messaging, or posting
        your link where it breaks another site&rsquo;s rules.</li>
    <li>Misrepresenting what the software does, or who you are, to get somebody to buy.</li>
  </ul>
  <p>We may hold, reverse or cancel referrals and rewards obtained this way, and close the account
     involved. Where the evidence is unclear we review it by hand rather than acting automatically.</p>

  <h2>6. Changes and ending the programme</h2>
  <p>We may change the reward, the threshold or these terms, or end the programme, at any time.
     Referrals already confirmed before a change are honoured under the terms in force when they
     were confirmed.</p>

  <h2>7. Your data</h2>
  <p>We store your email address, your invite code, and the email address, order and amount of each
     purchase attributed to you, so we can count referrals and pay rewards. See our
     <a href="/privacy.php">privacy notice</a>.</p>

  <h2>8. Contact</h2>
  <p><a href="mailto:<?= e(SUPPORT_EMAIL) ?>"><?= e(SUPPORT_EMAIL) ?></a></p>
</section>
<?php page_bottom(); ?>
