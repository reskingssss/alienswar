<?php
declare(strict_types=1);
require_once __DIR__ . '/helpers.php';
require_once __DIR__ . '/orders.php';

/**
 * Public site shell (v7). page_top() / page_bottom() keep their original
 * names and first three arguments; $opts is optional:
 *   'noindex' => true      keep a page out of search engines (checkout, orders)
 *   'body'    => 'class'   extra class on <body>
 */
function page_top(string $title, string $description, string $path = '/', array $opts = []): void
{
    // v6.3 REFERRAL: remember ?ref=CODE before a single byte of HTML goes
    // out, because it sets a cookie. Silent and cheap: it does nothing at
    // all unless the query string carries a code that resolves to a real
    // customer, so an ordinary visit is untouched and gets no new cookie.
    try {
        if (function_exists('referral_capture_from_request')) {
            referral_capture_from_request();
        }
    } catch (Throwable $e) {
        error_log('[mavelylink] referral capture: ' . $e->getMessage());
    }
    $canonical = site_url() . $path;
    $offers = [];
    foreach (plans_all(true) as $p) {
        if (plan_is_paid((string)$p['code']) && (int)$p['purchasable']) {
            $offers[] = ['@type' => 'Offer', 'name' => $p['name'], 'price' => (string)$p['current_price'],
                         'priceCurrency' => $p['currency'], 'url' => site_url('buy.php?plan=' . $p['code'])];
        }
    }
    $here = $path === '/' ? '/' : '/' . ltrim($path, '/');
    $nav = [['/', 'Home'], ['/pricing.php', 'Pricing'], ['/docs.php', 'Guide'], ['/faq.php', 'FAQ']];
    ?><!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title><?= e($title) ?></title>
<meta name="description" content="<?= e($description) ?>">
<?php if (!empty($opts['noindex'])): ?><meta name="robots" content="noindex,nofollow"><?php endif; ?>
<link rel="canonical" href="<?= e($canonical) ?>">
<meta property="og:type" content="website">
<meta property="og:title" content="<?= e($title) ?>">
<meta property="og:description" content="<?= e($description) ?>">
<meta property="og:url" content="<?= e($canonical) ?>">
<meta name="theme-color" content="#0f1b33">
<link rel="stylesheet" href="/assets/css/site.css?v=7">
<script type="application/ld+json">
<?= json_encode([
  '@context' => 'https://schema.org',
  '@type'    => 'SoftwareApplication',
  'name'     => SITE_NAME,
  'applicationCategory' => 'BrowserApplication',
  'operatingSystem'     => 'Windows 10, Windows 11',
  'offers'   => $offers ?: ['@type' => 'Offer', 'price' => '0', 'priceCurrency' => 'USD'],
], JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT) ?>
</script>
</head><body class="<?= e((string)($opts['body'] ?? '')) ?>">
<a class="skip" href="#main">Skip to content</a>
<header class="nav">
  <div class="wrap nav-row">
    <a class="logo" href="/" aria-label="<?= e(SITE_NAME) ?> home"><span class="logo-mark" aria-hidden="true"></span><?= e(SITE_NAME) ?></a>
    <input type="checkbox" id="navtog" class="navtog" aria-label="Show menu">
    <label for="navtog" class="burger" aria-hidden="true"><span></span><span></span><span></span></label>
    <nav aria-label="Main">
      <?php foreach ($nav as [$href, $label]): ?>
        <a href="<?= $href ?>"<?= $here === $href ? ' aria-current="page"' : '' ?>><?= e($label) ?></a>
      <?php endforeach; ?>
      <a class="btn btn-primary btn-sm" href="/pricing.php">Get Pro</a>
    </nav>
  </div>
</header>
<main id="main" tabindex="-1"><?php
}

/** Small generic glyphs for contact channels (text label always shown). */
function channel_glyph(string $code): string
{
    $paths = [
        'whatsapp' => '<path d="M4 20l1.3-3.9A8 8 0 1 1 8 18.7z"/><path d="M9 9.5c.3 2 2.2 4 4.5 4.6l1-1 1.6.8-.5 1.4c-3.3.2-7-3.4-6.9-6.7l1.4-.5.8 1.6z"/>',
        'telegram' => '<path d="M21 4L3 11l6 2 2 6 3-4 4 3z"/><path d="M9 13l8-6"/>',
        'facebook' => '<path d="M12 3a8.5 8 0 0 0-5 14.5V21l3-1.7a9 9 0 0 0 2 .2 8.5 8 0 0 0 0-16.5z"/><path d="M8 13l3-3 2 2 3-3"/>',
    ];
    return '<svg class="glyph" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        . ($paths[$code] ?? '<circle cx="12" cy="12" r="8"/>') . '</svg>';
}

function page_bottom(): void
{
    $y = date('Y');
    $channels = channels_enabled();
    ?>
</main>
<footer class="foot">
  <div class="wrap foot-grid">
    <div class="foot-brand">
      <a class="logo" href="/"><span class="logo-mark" aria-hidden="true"></span><?= e(SITE_NAME) ?></a>
      <p class="muted">Isolated Chrome profiles with per-profile fingerprints and managed scripts, for Windows 10 and 11.</p>
    </div>
    <div><h2 class="foot-h">Product</h2>
      <a href="/pricing.php">Plans and pricing</a><a href="/docs.php">Setup guide</a><a href="/faq.php">FAQ</a></div>
    <div><h2 class="foot-h">Legal</h2>
      <a href="/terms.php">Terms</a><a href="/privacy.php">Privacy</a><a href="/refund.php">Refunds</a></div>
    <div><h2 class="foot-h">Support</h2>
      <a href="mailto:<?= e(SUPPORT_EMAIL) ?>"><?= e(SUPPORT_EMAIL) ?></a>
      <?php foreach ($channels as $c): $link = channel_link($c); if ($link === '') { continue; } ?>
        <a class="chan" href="<?= e($link) ?>" target="_blank" rel="noopener nofollow"><?= channel_glyph((string)$c['code']) ?><?= e($c['display_name']) ?></a>
      <?php endforeach; ?>
    </div>
  </div>
  <div class="wrap foot-legal muted small">&copy; <?= $y ?> <?= e(SITE_NAME) ?>. You are responsible for
    complying with the terms of any third-party service you use this software with.</div>
</footer>
</body></html><?php
}
