<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';

$plans = plans_all(true);   // visible plans, ordered
$check = static fn() => '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>';
$cross = static fn() => '<svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>';

page_top('Pricing — ' . SITE_NAME,
    'Start free with 5 profiles, or go Pro for unlimited profiles, the full fingerprint engine and Script 2. Simple 30-day access, no auto-renewal.',
    '/pricing.php');
?>
<section>
  <div class="wrap section-head">
    <span class="kicker">Pricing</span>
    <h1>Start free. Upgrade when you need more.</h1>
    <p>Every plan is a one-time 30-day purchase — no subscription traps and no automatic renewal.
       When a period ends you simply buy another if you want to continue.</p>
  </div>
  <div class="wrap">
    <div class="plans">
      <?php foreach ($plans as $p):
          $code = (string)$p['code'];
          $paid = plan_is_paid($code);
          $pop = $code === 'pro';
          $cur = (float)$p['current_price'];
          $prev = $p['previous_price'] !== null ? (float)$p['previous_price'] : null;
          $save = ($prev && $prev > $cur) ? (int)round(100 - ($cur / $prev * 100)) : 0;
          $feats = plan_features($p);
          $buyable = $paid && $p['status'] === 'active' && (int)$p['purchasable'];
      ?>
      <div class="plan <?= $pop ? 'pop' : '' ?>">
        <?php if ($pop): ?><span class="tag">Most popular</span><?php endif; ?>
        <div class="plan-name"><span class="plan-badge pb-<?= $code ?>"></span><?= e($p['name']) ?></div>
        <?php if (!empty($p['tagline'])): ?><p class="muted small" style="margin:.5em 0 0"><?= e($p['tagline']) ?></p><?php endif; ?>
        <div class="price">
          <?php if ($prev !== null && $prev > $cur): ?><span class="was"><?= e(money($prev, (string)$p['currency'])) ?></span><?php endif; ?>
          <span class="now"><?= $cur > 0 ? e(money($cur, (string)$p['currency'])) : '$0' ?></span>
          <span class="per"><?= (int)$p['period_days'] > 0 ? 'per ' . (int)$p['period_days'] . ' days' : 'free forever' ?></span>
        </div>
        <?php if ($save > 0): ?><span class="save">Save <?= $save ?>% right now</span><?php endif; ?>
        <ul>
          <?php foreach ($feats as $f):
              $off = str_starts_with($f, '!');
              $label = ltrim($f, '!'); ?>
            <li class="<?= $off ? 'off' : '' ?>"><?= $off ? $cross() : $check() ?><span><?= e($label) ?></span></li>
          <?php endforeach; ?>
        </ul>
        <div class="cta">
          <?php if ($buyable): ?>
            <a class="btn btn-primary btn-block" href="/buy.php?plan=<?= e($code) ?>">Buy <?= e($p['name']) ?></a>
            <p class="foot-note">30 days access · <?= (int)$p['device_limit'] ?> computer<?= (int)$p['device_limit'] === 1 ? '' : 's' ?> · no auto-renew</p>
          <?php elseif (!$paid): ?>
            <a class="btn btn-ghost btn-block" href="/docs.php#install">Download &amp; start free</a>
            <p class="foot-note">No account, card or trial timer — install and go</p>
          <?php else: ?>
            <span class="btn btn-ghost btn-block" aria-disabled="true">Currently unavailable</span>
          <?php endif; ?>
        </div>
      </div>
      <?php endforeach; ?>
    </div>
    <p class="pricing-note">Prices are shown in USD. Access lasts the number of days shown from the moment your
      payment is confirmed. There is no automatic renewal and nothing is stored to charge you again — when a
      period runs out you buy another only if you want to continue. Paid plans unlock inside the app the moment
      you register your licence key.</p>
  </div>
</section>

<section class="alt">
  <div class="wrap section-head"><span class="kicker">Compare</span><h2>What each plan unlocks</h2></div>
  <div class="wrap" style="max-width:900px">
    <div style="overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius)">
      <table style="width:100%;border-collapse:collapse;min-width:520px">
        <thead><tr style="background:var(--panel)">
          <th style="text-align:left;padding:14px 16px;font-family:var(--disp)">Feature</th>
          <?php foreach ($plans as $p): ?><th style="padding:14px 16px;font-family:var(--disp)"><?= e($p['name']) ?></th><?php endforeach; ?>
        </tr></thead>
        <tbody>
        <?php
        $ent = [];
        foreach ($plans as $p) { $ent[(string)$p['code']] = plan_entitlements((string)$p['code'], (int)$p['device_limit']); }
        $rows = [
          'Browser profiles' => fn($e) => (int)$e['max_profiles'] === 0 ? 'Unlimited' : (string)(int)$e['max_profiles'],
          'Fingerprint engine' => fn($e) => $e['fingerprint'] ? 'Full' : '—',
          'Languages' => fn($e) => in_array('*', $e['languages'], true) ? 'All ' . count(ALL_LANGUAGES) : (string)count($e['languages']),
          'Screen sizes' => fn($e) => in_array('*', $e['resolutions'], true) ? 'All ' . count(ALL_RESOLUTIONS) : (string)count($e['resolutions']),
          'Script 1' => fn($e) => 'Yes',
          'Script 2' => fn($e) => in_array('pro', $e['scripts'], true) ? 'Yes' : '—',
          'Computers per licence' => fn($e) => (string)(int)$e['max_devices'],
          'Script updates pushed automatically' => fn($e) => 'Yes',
        ];
        $i = 0;
        foreach ($rows as $label => $fn): $i++; ?>
          <tr style="border-top:1px solid var(--line);<?= $i % 2 ? '' : 'background:rgba(255,255,255,.02)' ?>">
            <td style="padding:12px 16px;color:var(--ink-2)"><?= e($label) ?></td>
            <?php foreach ($plans as $p): $v = $fn($ent[(string)$p['code']]); ?>
              <td style="padding:12px 16px;text-align:center;color:<?= $v === '—' ? 'var(--muted)' : 'var(--ink)' ?>"><?= e($v) ?></td>
            <?php endforeach; ?>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>
  </div>
</section>

<section>
  <div class="wrap"><div class="cta-band">
    <h2>Not sure yet? Start on Free.</h2>
    <p class="muted" style="max-width:52ch;margin:12px auto 22px">Install the app and use the Free plan straight away —
      5 profiles and Script 1, with no sign-up. Upgrade from inside the app whenever you are ready.</p>
    <a class="btn btn-primary btn-lg" href="/docs.php#install">Get started free</a>
  </div></div>
</section>
<?php page_bottom(); ?>
