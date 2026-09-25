<?php
declare(strict_types=1);
require_once __DIR__ . '/helpers.php';
require_once __DIR__ . '/orders.php';

/**
 * Public site shell (v8, "Indigo" - the design of AutoPoster Pro 4.0, light and
 * dark). page_top() / page_bottom() keep their original
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
<meta name="theme-color" content="#f5f6fa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0b0d12" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
<link rel="stylesheet" href="/assets/css/site.css?v=8">
<script src="/assets/js/theme.js?v=8"></script>
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
      <button type="button" class="theme-toggle" data-theme-toggle aria-pressed="false" aria-label="Dark mode">
        <svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
        <svg class="moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
      </button>
    </nav>
  </div>
</header>
<main id="main" tabindex="-1"><?php
}

/**
 * Accepted-card marks (VISA, Mastercard) for the checkout and the footer.
 * Plain inline SVG: no request to a third party, sized by CSS.
 */
function card_marks(): string
{
    $visa = '<svg viewBox="0 0 48 30" role="img" aria-label="VISA"><rect width="48" height="30" rx="4" fill="#1a1f71"/>'
        . '<text x="24" y="20" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="12.5" font-weight="800"'
        . ' font-style="italic" fill="#ffffff" letter-spacing=".5">VISA</text></svg>';
    $mc = '<svg viewBox="0 0 48 30" role="img" aria-label="Mastercard"><rect width="48" height="30" rx="4" fill="#111827"/>'
        . '<circle cx="19.5" cy="15" r="8" fill="#eb001b"/><circle cx="28.5" cy="15" r="8" fill="#f79e1b"/>'
        . '<path d="M24 8.4a8 8 0 0 1 0 13.2 8 8 0 0 1 0-13.2z" fill="#ff5f00"/></svg>';
    return $visa . $mc;
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
      <p class="muted">AutoPoster Pro for Windows 10 and 11 — Method 1 posts to your Facebook groups on autopilot,
        Method 2 builds isolated Chrome profiles with their own fingerprints.</p>
      <?php if (checkout_card_enabled()): ?><div class="paymarks" aria-label="Cards accepted"><?= card_marks() ?></div><?php endif; ?>
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
