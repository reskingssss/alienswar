<?php
declare(strict_types=1);
require_once __DIR__ . '/includes/page.php';
http_response_code(404);
page_top('Page not found — ' . SITE_NAME, 'That page does not exist.', '/404');
?>
<section class="wrap narrow" style="padding:60px 20px">
  <h1>Page not found</h1>
  <p class="lead">That link does not lead anywhere. Try the <a href="/">home page</a>
     or the <a href="/docs.php">documentation</a>.</p>
</section>
<?php page_bottom(); ?>
