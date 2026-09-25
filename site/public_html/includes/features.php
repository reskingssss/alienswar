<?php
/**
 * MavelyLink 6.3.4 — server-side feature definitions.
 *
 * THE SPLIT (project brief rule 2)
 * --------------------------------
 * A feature is cut in two:
 *
 *   SERVER  — what the feature KNOWS. The rules, thresholds, schedules,
 *             lists and copy. This is the part that took work to figure
 *             out and the part worth protecting.
 *   TOOL    — what the feature DRAWS. A generic renderer that has no idea
 *             what the numbers mean; it just paints what it is handed.
 *
 * A cracked copy of the desktop tool therefore contains a renderer with
 * nothing to render. The schedule only arrives for an installation the
 * server recognises and whose plan is entitled to it.
 *
 * WHY DATA AND NOT PYTHON SOURCE
 * ------------------------------
 * It would be possible to ship executable Python down this pipe. It is
 * deliberately not done, because it would mean every customer's machine
 * runs whatever this server sends - so a compromise of this database or
 * this dashboard would become remote code execution across the whole
 * install base. Sending the RULES instead gives the same anti-cracking
 * benefit with none of that risk: the valuable part still lives here and
 * still is not in the binary.
 *
 * If code delivery is ever genuinely needed, the prerequisites are an
 * offline signing key, 2FA on the dashboard, and a revocation switch.
 *
 * ADDING ANOTHER FEATURE LATER
 * ----------------------------
 * Add one entry to feature_definitions(). The tool needs no release: it
 * asks for features by id and renders whatever comes back.
 */
declare(strict_types=1);
require_once __DIR__ . '/license.php';

/**
 * Every server-side feature definition.
 *
 * Each entry: version, the plans entitled to it, and `data` — the whole
 * of what the tool does not know by itself.
 */
function feature_definitions(): array
{
    return [
        'usa_timer' => [
            'version' => 3,
            'plans'   => ['pro', 'team'],
            'data'    => [
                // the four zones these states actually span
                'zones' => [
                    ['state' => 'Arkansas',     'tz' => 'America/Chicago'],
                    ['state' => 'New York',     'tz' => 'America/New_York'],
                    ['state' => 'Texas',        'tz' => 'America/Chicago'],
                    ['state' => 'Florida',      'tz' => 'America/New_York'],
                    ['state' => 'California',   'tz' => 'America/Los_Angeles'],
                    ['state' => 'Tennessee',    'tz' => 'America/Chicago'],
                    ['state' => 'Ohio',         'tz' => 'America/New_York'],
                    ['state' => 'Oklahoma',     'tz' => 'America/Chicago'],
                    ['state' => 'Missouri',     'tz' => 'America/Chicago'],
                    ['state' => 'Pennsylvania', 'tz' => 'America/New_York'],
                    ['state' => 'Arizona',      'tz' => 'America/Phoenix'],
                ],
                // the scheduling research: the part worth keeping off the disk
                'golden_hours'  => [9, 10, 11, 13, 14, 15, 20, 21],
                'good_hours'    => [6, 7, 8, 12, 18, 19],
                'best_days'     => [1, 2, 3],
                'good_days'     => [0, 4],
                'avoid_days'    => [5, 6],
                'reference_tz'  => 'America/New_York',
                // the status ladder, as ordered rules the tool just walks
                'ladder' => [
                    ['if' => ['golden' => true, 'day' => 'best'],           'status' => 'GOLD'],
                    ['if' => ['golden' => true, 'day' => 'not_avoid'],      'status' => 'GOOD'],
                    ['if' => ['good' => true,   'day' => 'not_avoid'],      'status' => 'OK'],
                    ['if' => ['hour_between' => [8, 18], 'day' => 'not_avoid'], 'status' => 'OK'],
                    ['if' => [],                                            'status' => 'LOW'],
                ],
                'tips' => [
                    ['hours' => [9, 10, 11],  'key' => 'tip.morning'],
                    ['hours' => [13, 14, 15], 'key' => 'tip.lunch'],
                    ['hours' => [20, 21],     'key' => 'tip.evening'],
                    ['weekday' => 2,          'key' => 'tip.wednesday'],
                    ['weekdays' => [5, 6],    'key' => 'tip.weekend'],
                    ['key' => 'tip.default'],
                ],
            ],
        ],
    ];
}

/** One feature, if this plan is entitled to it. */
function feature_for_plan(string $id, string $plan): ?array
{
    $all = feature_definitions();
    if (!isset($all[$id])) {
        return null;
    }
    $f = $all[$id];
    $plan = in_array($plan, ['free', 'pro', 'team'], true) ? $plan : 'free';
    if (!in_array($plan, $f['plans'], true)) {
        return null;               // not entitled: nothing is sent at all
    }
    return ['id' => $id, 'version' => $f['version'], 'data' => $f['data']];
}

/** Which feature ids this plan may fetch, with versions, for the manifest. */
function feature_manifest(string $plan): array
{
    $out = [];
    foreach (feature_definitions() as $id => $f) {
        if (in_array($plan, $f['plans'], true)) {
            $out[] = ['id' => $id, 'version' => $f['version']];
        }
    }
    return $out;
}
