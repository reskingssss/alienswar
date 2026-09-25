<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';
require_once __DIR__ . '/includes/tool_control.php';
$pro = plan_get('pro');
$zl = ziplinks_config();
$proPrice = $pro ? money((float)$pro['current_price'], (string)$pro['currency']) : '$29';
page_top('Setup guide — ' . SITE_NAME,
    'How to install, use the Free plan, register a Pro or Team licence and move it to another computer.',
    '/docs.php');
?>
<section class="wrap prose">
  <span class="kicker">Guide</span>
  <h1>Setup &amp; usage guide</h1>
  <p class="muted">Everything you need to install the app, work on the Free plan, and unlock a paid plan when you're ready.</p>

  <h2 id="install">Installing the app</h2>
  <ol>
    <li>Download the installer for Windows 10 or 11 from the link we provide (or in your purchase email).</li>
    <li>Run it. Windows SmartScreen may warn about a new publisher — choose <b>More info → Run anyway</b>.</li>
    <li>Launch <b>AutoPoster Pro</b>. It opens directly on the <b>Free plan</b> — no account, email or card needed.
        Method 1 (Posting) and Method 2 (Profiles) are both in the sidebar.</li>
  </ol>

  <h2 id="free">Using the Free plan</h2>
  <p>The Free plan is fully usable from the first launch. It includes up to <b>5 browser profiles</b>, the
     <b>en-US</b> and <b>fr-FR</b> languages, the <b>1920×1080</b> screen size, and <b>Script 1</b>, on one computer.
     Paid-only options are shown but clearly marked, so you always know what an upgrade adds.</p>

  <h2 id="posting">Method 1 · Posting</h2>
  <ol>
    <li>Open <b>Configuration</b> in the sidebar and add your Facebook accounts in the <b>Facebook accounts</b> table
        (cookies or the browser login). Turn on <b>🛡 Profiles fingerprint</b> to give every account its own stable fingerprint.</li>
    <li>Choose the target page or groups, the time between posts and the maximum number of posts.</li>
    <li>Pick your posts: a <b>ZIP</b> of folders (each with <code>comment.txt</code>, <code>description.txt</code> and
        <code>image.png</code>) or a <b>CSV / XLSX</b> file.</li>
    <li>Press <b>Start posting</b>. Progress is shown in the <b>Activity log</b>; <b>Automatic mode</b> adds collecting,
        commenting, joining and liking.</li>
  </ol>

  <h2 id="links">Supported links in ZIP posts</h2>
  <?php if ($zl['enabled'] && array_filter(array_map(static fn($t) => $zl['tiers'][$t]['enforce'], TOOL_TIERS))): ?>
    <p>Before a ZIP post is published, the app checks the link in its <code>comment.txt</code>. On the plans listed
       below only links from the supported sites are posted; a post with another link is skipped and the app tells you
       which links are supported.</p>
    <ul>
      <?php foreach (['free' => 'Free', 'pro' => 'Pro', 'team' => 'Unlimited for Team'] as $t => $tn): $tier = $zl['tiers'][$t]; ?>
        <li><b><?= e($tn) ?>:</b> <?= $tier['enforce']
            ? e(implode(', ', $tier['domains']) ?: 'no supported sites')
            : 'every link is supported' ?></li>
      <?php endforeach; ?>
    </ul>
    <p>Need links on a supported site? <a href="<?= e($zl['redirect_url']) ?>" rel="noopener"><?= e($zl['redirect_label']) ?></a>.</p>
  <?php else: ?>
    <p>Every link in <code>comment.txt</code> is supported on every plan.</p>
  <?php endif; ?>

  <h2 id="generate">Method 2 · Generating a profile</h2>
  <ol>
    <li>Type a name and how many profiles to create.</li>
    <li>Choose a language and screen size. On Free these are set to the included options.</li>
    <li>Optionally turn on <b>Fingerprint</b> (a Pro feature) and <b>Desktop icon</b>.</li>
    <li>Click <b>Generate New Profile</b>. Each profile gets its own folder, cookies and shortcut.</li>
  </ol>

  <h2 id="activate">Registering a Pro or Team licence</h2>
  <ol>
    <li>Buy a plan on the <a href="/pricing.php">pricing page</a>. Your licence key is emailed and shown on screen instantly.</li>
    <li>In the app, click <b>Register licence</b> in the top-right (next to <b>About</b>, your plan and <b>Upgrade</b>).</li>
    <li>Paste your key (<code>MVL-XXXXX-XXXXX-XXXXX-XXXXX</code>) and confirm.</li>
    <li>The app switches to your plan's theme and unlocks its features straight away.</li>
  </ol>
  <p class="muted small">Your licence is saved securely on the computer and loads automatically every time you open the
     app — you won't be asked for it again on that machine.</p>

  <h2 id="devices">Using more than one computer</h2>
  <p>A <b>Pro</b> licence activates on one computer; <b>Unlimited for Team</b> activates on up to three. To move a Pro
     licence to a different machine, open the app on the old one and choose <b>Release this computer</b>, then register
     the key on the new one. An administrator can also free up a computer for you.</p>

  <h2 id="scripts">Scripts &amp; updates</h2>
  <p>Scripts are delivered from the server and injected into the profiles you generate. <b>Script 1</b> is available on
     every plan; <b>Script 2</b> is included with Pro and Team. When we publish a script update it reaches your app
     automatically at its next check-in — there's nothing to reinstall. App updates work the same way: you'll be
     prompted when a new version is available.</p>

  <h2 id="pricing">Pricing</h2>
  <p>Paid plans are a one-time <b>30-day</b> purchase (Pro from <?= e($proPrice) ?>). There is no subscription and no
     automatic renewal — when a period ends you simply buy another if you want to continue. See the
     <a href="/pricing.php">pricing page</a> for the current plans and any active discounts.</p>

  <div class="note info" style="margin-top:30px"><b>Need help?</b> Email
     <a href="mailto:<?= e(SUPPORT_EMAIL) ?>"><?= e(SUPPORT_EMAIL) ?></a> and we'll get you sorted.</div>
</section>
<?php page_bottom(); ?>
