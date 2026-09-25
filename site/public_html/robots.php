<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/helpers.php';
header('Content-Type: text/plain; charset=utf-8');
echo "User-agent: *\n";
echo "Allow: /\n";
echo "Disallow: /admin/\n";
echo "Disallow: /api/\n";
echo "Disallow: /install/\n";
echo "Disallow: /includes/\n\n";
echo "Sitemap: " . site_url('sitemap.xml') . "\n";
