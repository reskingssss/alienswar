<?php
declare(strict_types=1);
require_once __DIR__ . '/helpers.php';

/**
 * Fixed-window limiter backed by MySQL. Keeps brute force off the
 * activation and login endpoints without needing Redis on shared hosting.
 *
 * Returns true when the caller is ALLOWED to proceed.
 */
function rate_ok(string $bucket, string $identifier, int $max, int $windowSeconds): bool
{
    $key = hash_hmac('sha256', $bucket . '|' . $identifier, APP_SECRET);
    $pdo = db();

    $pdo->prepare('DELETE FROM rate_limits WHERE window_start < ?')
        ->execute([gmdate('Y-m-d H:i:s', time() - 86400)]);

    $st = $pdo->prepare('SELECT hits, window_start FROM rate_limits WHERE k = ?');
    $st->execute([$key]);
    $row = $st->fetch();

    $windowStart = gmdate('Y-m-d H:i:s', (int)(floor(time() / $windowSeconds) * $windowSeconds));

    if (!$row || $row['window_start'] !== $windowStart) {
        $pdo->prepare(
            'INSERT INTO rate_limits (k, hits, window_start) VALUES (?, 1, ?)
             ON DUPLICATE KEY UPDATE hits = 1, window_start = VALUES(window_start)'
        )->execute([$key, $windowStart]);
        return true;
    }
    if ((int)$row['hits'] >= $max) {
        return false;
    }
    $pdo->prepare('UPDATE rate_limits SET hits = hits + 1 WHERE k = ?')->execute([$key]);
    return true;
}


/** Hits recorded in the current window, WITHOUT adding one. */
function rate_count(string $bucket, string $identifier, int $windowSeconds): int
{
    $key = hash_hmac('sha256', $bucket . '|' . $identifier, APP_SECRET);
    $st = db()->prepare('SELECT hits, window_start FROM rate_limits WHERE k = ?');
    $st->execute([$key]);
    $row = $st->fetch();
    $windowStart = gmdate('Y-m-d H:i:s', (int)(floor(time() / $windowSeconds) * $windowSeconds));
    return ($row && $row['window_start'] === $windowStart) ? (int)$row['hits'] : 0;
}

/** Record one hit, e.g. a failed password. */
function rate_hit(string $bucket, string $identifier, int $windowSeconds): void
{
    rate_ok($bucket, $identifier, PHP_INT_MAX, $windowSeconds);
}
