<?php
/**
 * MavelyLink 6.3.1 — activation attempt limit (TASK 2).
 *
 * Three rejected keys, then a lockout. ADDITIVE: this file adds behaviour
 * around activate.php without changing how activation itself works.
 *
 * IDENTITY (your decision): keyed to the INSTALLATION — the device_hash
 * activate.php already receives. IP is recorded for the admin to look at but
 * is deliberately NOT part of the key, so an office behind one NAT cannot
 * lock each other out.
 *
 * Enforced here, server-side, so clearing local data or restarting the app
 * does not reset it, and a hand-crafted 4th request is still refused.
 *
 * What counts as an attempt (spec 2.2): a REJECTED KEY only. A network
 * failure or timeout never reaches this file. An empty field or a key that
 * fails local format validation is refused by the tool before it is sent,
 * and the 400 path in activate.php is not counted either.
 */
declare(strict_types=1);
require_once __DIR__ . '/license.php';

/**
 * v6.3.2 (TASK 1.4): one identical answer for every rejection reason.
 *
 * Without this, the status code and message tell an attacker whether a
 * serial exists, has expired, or is already bound to somebody else - which
 * turns this endpoint into a serial enumeration oracle. With it, "unknown",
 * "expired", "revoked" and "already bound" are indistinguishable from
 * outside. The real reason still goes to the audit log, where support can
 * see it.
 *
 * The `activation` block IS still returned. It describes only the CALLER'S
 * OWN installation, and anyone crafting requests already knows how many
 * they have sent, so it leaks nothing - and the tool needs it to hide the
 * button straight away rather than waiting for the next check-in.
 *
 * Gated on a setting, so the original detailed responses are one value away.
 */
function activation_generic_errors(): bool
{
    return setting_bool('activation_generic_errors', true);
}

/** The single response every rejected activation gets. */
function activation_reject(array $state, string $realReason = ''): array
{
    return [
        'ok'         => false,
        'state'      => 'rejected',
        'error'      => 'That licence key could not be activated.',
        'activation' => $state,
    ];
}

function activation_max_attempts(): int
{
    return max(1, min(20, (int)setting('activation_max_attempts', '3')));
}

function activation_lockout_hours(): int
{
    return max(1, min(720, (int)setting('activation_lockout_hours', '24')));
}

/** Never store a rejected key in plain text (spec 2.4). */
function activation_mask_serial(string $serial): string
{
    $s = normalise_serial($serial);
    if ($s === '') {
        return '(empty)';
    }
    if (strlen($s) <= 8) {
        return substr($s, 0, 2) . str_repeat('*', max(1, strlen($s) - 2));
    }
    return substr($s, 0, 4) . str_repeat('*', 6) . substr($s, -4);
}

/**
 * The current attempt state for one installation.
 * Returns: fails, remaining, locked (bool), locked_until (ISO or null),
 *          retry_after_seconds.
 */
function activation_state(string $device): array
{
    $max = activation_max_attempts();
    $device = clean_hex($device);
    $row = null;
    if (strlen($device) === 64) {
        $st = db()->prepare('SELECT activation_fails, activation_locked_until
                               FROM installations WHERE device_hash = ?');
        $st->execute([$device]);
        $row = $st->fetch() ?: null;
    }
    $fails = (int)($row['activation_fails'] ?? 0);
    $until = $row['activation_locked_until'] ?? null;
    $lockedUntilTs = $until ? strtotime((string)$until . ' UTC') : 0;
    $locked = $lockedUntilTs > time();
    if (!$locked) {
        $until = null;
    }
    return [
        'max'                 => $max,
        'fails'               => $locked ? $fails : ($lockedUntilTs > 0 ? 0 : $fails),
        'remaining'           => $locked ? 0 : max(0, $max - ($lockedUntilTs > 0 ? 0 : $fails)),
        'locked'              => $locked,
        'locked_until'        => $locked ? gmdate('c', $lockedUntilTs) : null,
        'retry_after_seconds' => $locked ? max(0, $lockedUntilTs - time()) : 0,
    ];
}

/**
 * Make sure a row exists to hold the counter, without disturbing anything
 * installation_touch() owns.
 */
function activation_ensure_row(string $device): void
{
    $device = clean_hex($device);
    if (strlen($device) !== 64) {
        return;
    }
    try {
        db()->prepare('INSERT IGNORE INTO installations (device_hash, plan, app_version, first_seen, last_seen)
                       VALUES (?, ?, ?, ?, ?)')
            ->execute([$device, 'free', '', now(), now()]);
    } catch (PDOException $e) {
        // column set differs on an older schema: the UPDATE below still works
        error_log('[mavelylink] activation_ensure_row: ' . $e->getMessage());
    }
}

/**
 * Record one rejected key. Returns the state AFTER the failure, so the
 * caller can tell the user how many tries are left.
 */
function activation_record_failure(string $device, string $serial, string $reason): array
{
    $device = clean_hex($device);
    if (strlen($device) !== 64) {
        return activation_state($device);
    }
    activation_ensure_row($device);
    $max = activation_max_attempts();
    $hours = activation_lockout_hours();

    // A single statement, so two racing requests cannot both read "2" and
    // both decide they are the second attempt.
    db()->prepare('UPDATE installations
                      SET activation_fails = CASE
                              WHEN activation_locked_until IS NOT NULL
                               AND activation_locked_until <= UTC_TIMESTAMP()
                              THEN 1 ELSE activation_fails + 1 END,
                          activation_locked_until = CASE
                              WHEN activation_locked_until IS NOT NULL
                               AND activation_locked_until <= UTC_TIMESTAMP()
                              THEN NULL ELSE activation_locked_until END,
                          activation_last_fail_at = ?,
                          activation_last_fail_ip = ?
                    WHERE device_hash = ?')
        ->execute([now(), client_ip(), $device]);

    $st = db()->prepare('SELECT activation_fails FROM installations WHERE device_hash = ?');
    $st->execute([$device]);
    $fails = (int)$st->fetchColumn();

    $masked = activation_mask_serial($serial);
    // spec 1.5: timestamp, installation id, IP HASH, user agent, masked key.
    // The raw IP is kept on the installation row for support to look at; the
    // audit trail carries only a hash of it.
    $ipHash = substr(hash_hmac('sha256', client_ip(), APP_SECRET), 0, 16);
    $ua = mb_substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 120);
    audit('activate.failed',
        'device ' . substr($device, 0, 12) . ' key ' . $masked
        . ' (' . $reason . ') attempt ' . $fails . '/' . $max
        . ' ip#' . $ipHash . ' ua=' . $ua);

    if ($fails >= $max) {
        db()->prepare('UPDATE installations
                          SET activation_locked_until = DATE_ADD(UTC_TIMESTAMP(), INTERVAL ? HOUR)
                        WHERE device_hash = ? AND (activation_locked_until IS NULL
                              OR activation_locked_until <= UTC_TIMESTAMP())')
            ->execute([$hours, $device]);
        audit('activate.locked',
            'device ' . substr($device, 0, 12) . ' locked for ' . $hours . 'h after '
            . $fails . ' rejected keys (ip ' . client_ip() . ')');
    }
    return activation_state($device);
}

/** A successful registration clears the counter immediately (spec 2.2). */
function activation_clear(string $device, string $why = 'successful activation'): void
{
    $device = clean_hex($device);
    if (strlen($device) !== 64) {
        return;
    }
    $st = db()->prepare('SELECT activation_fails, activation_locked_until
                           FROM installations WHERE device_hash = ?');
    $st->execute([$device]);
    $row = $st->fetch();
    if (!$row || ((int)$row['activation_fails'] === 0 && empty($row['activation_locked_until']))) {
        return;                     // nothing to clear, nothing to log
    }
    db()->prepare('UPDATE installations
                      SET activation_fails = 0, activation_locked_until = NULL
                    WHERE device_hash = ?')
        ->execute([$device]);
    audit('activate.attempts_reset', 'device ' . substr($device, 0, 12) . ': ' . $why);
}

/** Admin action: unlock a genuine customer (spec 2.4). */
function activation_admin_reset(string $device, string $by): bool
{
    $device = clean_hex($device);
    if (strlen($device) !== 64) {
        return false;
    }
    db()->prepare('UPDATE installations
                      SET activation_fails = 0, activation_locked_until = NULL
                    WHERE device_hash = ?')
        ->execute([$device]);
    audit('activate.unlocked_by_admin', 'device ' . substr($device, 0, 12) . ' by ' . $by);
    return true;
}
