<?php
/**
 * Loaded by every API endpoint, webhook, admin page and public page.
 * Brings the database schema up to date (with a backup first) before
 * any v7 code touches it, so uploading new files never breaks the site.
 */
declare(strict_types=1);
require_once __DIR__ . '/helpers.php';
require_once __DIR__ . '/migrate.php';
require_once __DIR__ . '/plans.php';

migrate_if_needed();
