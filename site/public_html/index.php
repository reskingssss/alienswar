<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';

$plans = plans_all(true);
$pro = plan_get('pro');
$proPrice = $pro ? money((float)$pro['current_price'], (string)$pro['currency']) : '$29';
$ic = static fn(string $p) => '<svg viewBox="0 0 24 24">' . $p . '</svg>';

page_top(SITE_NAME . ' — isolated Chrome profiles with unique fingerprints',
    'Create isolated Chrome profiles, each with its own fingerprint, icon and scripts. Start free with 5 profiles; upgrade to Pro for unlimited.',
    '/');
?>
<section class="hero">
  <div class="wrap">
    <span class="eyebrow">Windows 10 &amp; 11 · Free plan included</span>
    <h1>One browser. Many profiles. Each genuinely separate.</h1>
    <p class="lead">Generate isolated Chrome profiles, each with its own fingerprint, cookies, history and scripts —
       then run them side by side without them bleeding into each other.</p>
    <div class="hero-cta">
      <a class="btn btn-primary btn-lg" href="/docs.php#install">Download &amp; start free</a>
      <a class="btn btn-ghost btn-lg" href="/pricing.php">See plans</a>
    </div>
    <p class="hero-note"><?= $ic('<path d="M20 6L9 17l-5-5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>') ?>
       No account, no card, no trial timer — the Free plan just works.</p>

    <div class="hero-figure" role="img" aria-label="The app generating separate browser profiles">
      <div class="bar"><i></i><i></i><i></i></div>
      <div class="mock">
        <div class="cardlet">
          <h4>facebook_01</h4>
          <div class="row"><span class="dot b"></span> Fingerprint: on · en-US · 1920×1080</div>
          <div class="row"><span class="dot g"></span> Script 1 &amp; Script 2 active</div>
        </div>
        <div class="cardlet">
          <h4>store_us_02</h4>
          <div class="row"><span class="dot t"></span> Own cookies &amp; history</div>
          <div class="row"><span class="dot g"></span> Separate desktop shortcut</div>
        </div>
        <div class="cardlet">
          <h4>research_03</h4>
          <div class="row"><span class="dot b"></span> Seeded canvas &amp; audio</div>
          <div class="row"><span class="dot g"></span> Stable across restarts</div>
        </div>
        <div class="cardlet">
          <h4>+ new profile</h4>
          <div class="row muted">Pick language &amp; screen size</div>
          <div class="row muted">Generate in one click</div>
        </div>
      </div>
    </div>
  </div>
</section>

<section>
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
    <div class="card"><div class="ficon"><?= $ic('<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>') ?></div>
      <h3>Your scripts, everywhere</h3><p>Scripts are managed centrally and injected into every profile you generate, updated without reinstalling anything.</p></div>
    <div class="card"><div class="ficon"><?= $ic('<path d="M12 3v18M5 12l7 7 7-7"/>') ?></div>
      <h3>Runs in the background</h3><p>Worker-based timers and a keep-alive heartbeat keep your scripts working even when the window is minimised.</p></div>
    <div class="card"><div class="ficon"><?= $ic('<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6v6H9z"/>') ?></div>
      <h3>Real isolation</h3><p>Every profile lives in its own directory with its own cookie store. Your everyday browser is never touched or read.</p></div>
    <div class="card"><div class="ficon"><?= $ic('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>') ?></div>
      <h3>One-click profiles</h3><p>Each profile gets its own desktop shortcut and generated icon, so you can tell them apart at a glance.</p></div>
  </div>
</section>

<section class="alt">
  <div class="wrap section-head"><span class="kicker">How it works</span><h2>From install to running in three steps</h2></div>
  <div class="wrap steps">
    <div class="step"><h3>Install &amp; open</h3><p>Download for Windows and launch. The app opens on the Free plan immediately — nothing to sign up for.</p></div>
    <div class="step"><h3>Generate a profile</h3><p>Pick a language and screen size, choose whether to add a fingerprint, and click Generate. A ready-to-use profile appears.</p></div>
    <div class="step"><h3>Upgrade if you need more</h3><p>Want unlimited profiles, the full fingerprint engine and Script 2? Register a Pro key from inside the app and it unlocks at once.</p></div>
  </div>
</section>

<section>
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
