<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';

$plans = plans_all(true);
$pro = plan_get('pro');
$proPrice = $pro ? money((float)$pro['current_price'], (string)$pro['currency']) : '$29';
$ic = static fn(string $p) => '<svg viewBox="0 0 24 24">' . $p . '</svg>';

page_top(SITE_NAME . ' — AutoPoster Pro: Facebook group posting and isolated Chrome profiles',
    'AutoPoster Pro for Windows: post to your Facebook groups on autopilot (Method 1) and build isolated Chrome profiles with their own fingerprints (Method 2). Start free, upgrade when you need more.',
    '/');
?>
<section class="hero">
  <div class="wrap hero-grid">
    <div>
      <span class="eyebrow">AutoPoster Pro 4.0 · Windows 10 &amp; 11</span>
      <h1>Post everywhere. <span class="grad">Stay separate.</span></h1>
      <p class="lead">One app, two methods. <b>Method 1</b> publishes your deals to Facebook groups on a schedule, with
         human-like typing and per-account fingerprints. <b>Method 2</b> builds isolated Chrome profiles, each with its
         own fingerprint, cookies and scripts.</p>
      <div class="hero-cta">
        <a class="btn btn-primary btn-lg" href="/docs.php#install">Download &amp; start free</a>
        <a class="btn btn-ghost btn-lg" href="/pricing.php">See plans</a>
      </div>
      <p class="hero-note"><?= $ic('<path d="M20 6L9 17l-5-5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>') ?>
         No account, no card, no trial timer — the Free plan just works.</p>
    </div>

    <div class="hero-figure" role="img" aria-label="The AutoPoster Pro window: posting configuration, accounts and browser settings">
      <div class="bar"><i></i><i></i><i></i></div>
      <div class="app-mock">
        <div class="side">
          <div class="brand"><i></i>AutoPoster Pro</div>
          <div class="grp">METHOD 1 · POSTING</div>
          <div class="nv on">Configuration</div>
          <div class="nv">Automatic mode</div>
          <div class="nv">Shorts</div>
          <div class="nv">Activity log</div>
          <div class="grp">METHOD 2 · PROFILES</div>
          <div class="nv">Profiles</div>
          <div class="nv">Invite</div>
          <div class="go">▶ Start posting</div>
        </div>
        <div class="main">
          <div class="pnl">
            <h5>Configuration</h5>
            <div class="ln m"></div><div class="ln s"></div>
            <div class="tg"><b></b>ZIP posts · comment.txt links</div>
            <div class="tg"><b></b>Multi-group posting</div>
            <div class="tg"><b class="off"></b>CSV / XLSX</div>
          </div>
          <div class="pnl">
            <h5>Browser</h5>
            <div class="tg"><b></b>Human typing</div>
            <div class="tg"><b></b>Profiles fingerprint</div>
            <div class="tg"><b class="off"></b>Hidden browsers</div>
            <div class="tg"><b></b>Watchdog</div>
          </div>
          <div class="pnl span2">
            <h5>Facebook accounts</h5>
            <div class="row"><span class="dot g"></span>deals_page_01<em>posted 12</em></div>
            <div class="row"><span class="dot b"></span>store_us_02<em>next 14:05</em></div>
            <div class="row"><span class="dot t"></span>group_admin_03<em>fingerprint on</em></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<section>
  <div class="wrap section-head">
    <span class="kicker">Two methods, one app</span>
    <h2>Everything you run, in one compact window</h2>
    <p>Pick the method you need from the sidebar. Both share your licence, your theme and your settings.</p>
  </div>
  <div class="wrap methods-grid">
    <div class="method-card">
      <span class="mnum">1</span>
      <h3>Posting</h3>
      <p>Publish to many Facebook groups from many accounts, on your schedule.</p>
      <ul>
        <li>ZIP, CSV and XLSX posts — text, image and link from each folder</li>
        <li>Multi-group posting with a delay between posts and a daily limit</li>
        <li>Human-like typing, working hours, Tor / proxies and a watermark</li>
        <li>Automatic mode: collect, comment, join and like</li>
      </ul>
    </div>
    <div class="method-card">
      <span class="mnum">2</span>
      <h3>Profiles</h3>
      <p>Generate isolated Chrome profiles that never bleed into each other.</p>
      <ul>
        <li>A coherent fingerprint per profile: screen, language, timezone, WebGL</li>
        <li>Own cookies, history and desktop shortcut for every profile</li>
        <li>Your scripts injected and kept up to date from the server</li>
        <li>The same fingerprint engine protects your posting accounts</li>
      </ul>
    </div>
  </div>
</section>

<section class="alt">
  <div class="wrap section-head">
    <span class="kicker">Why it's different</span>
    <h2>Fingerprints that agree with themselves</h2>
    <p>Most tools set values that contradict each other. Here everything is generated as one coherent identity.</p>
  </div>
  <div class="wrap feature-grid">
    <div class="card"><div class="ficon"><?= $ic('<path d="M12 2a10 10 0 100 20 10 10 0 000-20zM2 12h20M12 2c3 3 3 17 0 20M12 2c-3 3-3 17 0 20"/>') ?></div>
      <h3>Coherent fingerprints</h3><p>Screen, timezone, language, cores, memory, WebGL and fonts are generated together, so they agree instead of contradicting.</p></div>
    <div class="card"><div class="ficon"><?= $ic('<path d="M12 8v4l3 2"/><circle cx="12" cy="12" r="9"/>') ?></div>
      <h3>Stable across sessions</h3><p>Canvas and audio noise come from a seeded generator, so a profile keeps the same identity every time rather than drifting.</p></div>
    <div class="card"><div class="ficon"><?= $ic('<path d="M4 4h16v12H5.2L4 17.2z"/><path d="M8 9h8M8 12h5"/>') ?></div>
      <h3>Posting on autopilot</h3><p>Queue a folder of posts, choose your groups and accounts, and let the scheduler publish them at a human pace.</p></div>
    <div class="card"><div class="ficon"><?= $ic('<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>') ?></div>
      <h3>Your scripts, everywhere</h3><p>Scripts are managed centrally and injected into every profile you generate, updated without reinstalling anything.</p></div>
    <div class="card"><div class="ficon"><?= $ic('<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6v6H9z"/>') ?></div>
      <h3>Real isolation</h3><p>Every profile and every posting account lives in its own directory with its own cookie store. Your everyday browser is never touched.</p></div>
    <div class="card"><div class="ficon"><?= $ic('<path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z"/><path d="M9 12l2 2 4-4"/>') ?></div>
      <h3>Signed licence</h3><p>Your plan and its options are delivered in a signed check-in, so they are applied the same way on every computer.</p></div>
  </div>
</section>

<section>
  <div class="wrap section-head"><span class="kicker">How it works</span><h2>From install to running in three steps</h2></div>
  <div class="wrap steps">
    <div class="step"><h3>Install &amp; open</h3><p>Download for Windows and launch. The app opens on the Free plan immediately — nothing to sign up for.</p></div>
    <div class="step"><h3>Post or generate</h3><p>Method 1: add your accounts and a folder of posts, then press Start posting. Method 2: pick a language and screen size and click Generate New Profile.</p></div>
    <div class="step"><h3>Upgrade if you need more</h3><p>Need every option, unlimited profiles and Script 2? Click <b>Register licence</b> in the app, paste your Pro key and it unlocks at once.</p></div>
  </div>
</section>

<section class="alt">
  <div class="wrap section-head"><span class="kicker">Simple pricing</span><h2>Free to start, <?= e($proPrice) ?> for Pro</h2>
    <p>A one-time 30-day purchase for paid plans — no subscription and no automatic renewal.</p></div>
  <div class="wrap"><div class="cta-band">
    <h2 style="margin-bottom:6px">Ready when you are</h2>
    <p class="muted" style="max-width:52ch;margin:10px auto 22px">Start on the Free plan today, or go straight to Pro or Unlimited for Team.</p>
    <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
      <a class="btn btn-primary btn-lg" href="/docs.php#install">Get started free</a>
      <a class="btn btn-ghost btn-lg" href="/pricing.php">Compare plans</a>
    </div>
  </div></div>
</section>
<?php page_bottom(); ?>
