<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/helpers.php';
header('Content-Type: application/xml; charset=utf-8');
$pages = [
    ['', '1.0', 'weekly'],
    ['pricing.php', '0.9', null],
    ['docs.php', '0.8', null],
    ['faq.php', '0.7', null],
    ['terms.php', '0.3', null],
    ['referral-terms.php', '0.3', null],   // v6.3 referral programme terms
    ['privacy.php', '0.3', null],
    ['refund.php', '0.3', null],
];
echo '<?xml version="1.0" encoding="UTF-8"?>' . "\n";
echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' . "\n";
foreach ($pages as [$p, $prio, $freq]) {
    $loc = e(site_url($p));
    echo '  <url><loc>' . $loc . '</loc>';
    if ($freq) { echo '<changefreq>' . $freq . '</changefreq>'; }
    echo '<priority>' . $prio . '</priority></url>' . "\n";
}
echo '</urlset>' . "\n";
