<?php
/**
 * Remote control of the desktop tool, per plan (v8).
 *
 *   1. PER-OPTION GATING   every option of every tool inside AutoPoster Pro
 *      (posting, accounts, browser settings, automatic mode, shorts, Free ID,
 *      Profiles, Invite ...) carries three switches: Free / Pro / Unlimited
 *      for team. An option switched off for a tier is locked in the tool for
 *      installations on that tier.
 *
 *   2. CONTROL ZIP LINKS   the ZIP posting feature only publishes a post
 *      whose link (comment.txt) points at an allowed domain. Allowed domains,
 *      enforcement and the message are set per tier from the dashboard.
 *
 * Both travel to the tool inside the Ed25519-signed check-in control block
 * (includes/checkin.php), so a fake server or an edited response cannot
 * unlock anything. Both are stored as JSON in the settings table, so no
 * schema change is needed and nothing existing is touched.
 *
 * DEFAULTS KEEP TODAY'S BEHAVIOUR: until the dashboard saves a change every
 * option is allowed on every tier, exactly as the tool works now.
 */
declare(strict_types=1);
require_once __DIR__ . '/helpers.php';

const TOOL_TIERS = ['free', 'pro', 'team'];
const TOOL_GATES_SETTING = 'tool_gates_json';
const ZIPLINKS_SETTING = 'ziplinks_json';
const ZIPLINKS_MAX_DOMAINS = 200;
const ZIPLINKS_DEFAULT_DOMAINS = ['usadealshub.shop', 'mavelylink.com', 'martdeals.shop', 'usathedeals.shop'];

/**
 * The catalogue. The ids are shared, character for character, with the
 * desktop tool (autoV2_FIXED_19.py, _V20_OPTIONS). Grouped and ordered the
 * way the tool itself lays them out, so the dashboard mirrors the tool.
 *
 * Each group: [key, title, icon, method, [[id, label, hint], ...]]
 */
function tool_option_catalog(): array
{
    return [
        ['config', 'Configuration', '⚙', 1, [
            ['posting.configuration', 'Configuration', 'Target (Group / FB Page), group/page URLs, multi-group mode, Start Posting.'],
            ['posting.target_page', 'Target: FB Page', 'Posting to Facebook Pages instead of groups.'],
            ['posting.multi_group', 'Multi-group mode: All (each post → all groups)', 'Posting every publication to every group.'],
            ['posting.time_between', 'Time between posts', 'Custom Min / Max delay between posts.'],
            ['posting.zip', 'Zip file from mavelylink', 'Posting from ZIP files (file mode, anti-duplicate memory, irregular delays).'],
            ['posting.csv', 'CSV / XLSX files', 'Posting from CSV / XLSX files, drag & drop.'],
            ['posting.mode', 'Posting mode', 'Coloured background, Text only and Cycle (Image + Text always works).'],
            ['posting.max_posts', 'Max number of posts', 'A custom limit of posts per run.'],
        ]],
        ['accounts', 'Facebook Accounts', '▦', 1, [
            ['accounts.panel', 'Facebook Accounts', 'Connecting accounts and posting with them.'],
            ['accounts.cookies', 'Import / Export cookies', 'Importing and exporting account cookies.'],
            ['accounts.proxy', 'Proxy per account', 'A dedicated proxy for each account (+ Proxy).'],
            ['accounts.fingerprint', 'Profiles fingerprint for accounts', 'Each Facebook account gets its own Profiles-engine fingerprint.'],
        ]],
        ['browser', 'Browser Settings', '◧', 1, [
            ['browser.hidden', 'Hidden browsers', 'Headless mode — invisible browsers.'],
            ['browser.grid', 'Visible Browsers Grid Tabs', 'Show browsers in a grid (1 → 4×4).'],
            ['browser.parallel', 'How many browsers at one time', 'More than one browser in parallel.'],
            ['browser.human_typing', 'Human typing', 'Slow start, typos fixed, links pasted.'],
            ['browser.human_variation', 'Human variation', '±20% random variation on delays.'],
            ['browser.watchdog', 'Watchdog', 'Restart a frozen browser automatically.'],
            ['browser.anonymous', 'Anonymous posts', 'Anonymous posting in groups.'],
        ]],
        ['extras', 'Tor & Proxies · Watermark · Working Hours', '◈', 1, [
            ['tor_proxies', 'Tor & Proxies', 'Tor network and the proxy list.'],
            ['watermark', 'Watermark (logo on images)', 'Adding a logo to posted images.'],
            ['working_hours', 'Working Hours', 'Posting only inside scheduled hours.'],
        ]],
        ['auto', 'Automatic mode', '⚡', 1, [
            ['tab.auto', 'Automatic mode (whole tab)', 'Opening the Automatic mode tab.'],
            ['auto.collect', 'Collect (scrape groups)', 'Collecting posts from watched groups.'],
            ['auto.comment', 'Comment', 'Commenting on group posts.'],
            ['auto.join', 'Join groups', 'Joining groups automatically.'],
            ['auto.like', 'Like', 'Liking posts automatically.'],
            ['auto.cleaner', 'Delete Post & Decline', 'Deleting own posts and declining in groups.'],
        ]],
        ['more', 'Edit Shorts Video Tool · Free ID · Log', '✂', 1, [
            ['tab.shorts', 'Edit Shorts Video Tool', 'The shorts video editor.'],
            ['tab.freeid', 'Free ID', 'The Free ID generator.'],
            ['tab.log', 'Log', 'The activity log tab.'],
        ]],
        ['profiles', 'Profiles (Method 2)', '◉', 2, [
            ['tab.profiles', 'Profiles (whole tab)', 'The Chrome Profile Generator.'],
            ['profiles.generate', 'Generate New Profile', 'Creating new isolated profiles.'],
            ['profiles.fingerprint', 'Fingerprint', 'The fingerprint engine (the plan entitlement still applies).'],
            ['profiles.desktop_icon', 'Desktop icon', 'A desktop shortcut for each profile.'],
            ['profiles.lang_screen', 'Language / Screen Size', 'Choosing languages and screen sizes.'],
        ]],
        ['invite', 'Invite (Method 2)', '✉', 2, [
            ['tab.invite', 'Invite', 'The referral programme tab.'],
        ]],
    ];
}

/** Flat list of every option id. */
function tool_option_ids(): array
{
    $ids = [];
    foreach (tool_option_catalog() as $g) {
        foreach ($g[4] as $it) {
            $ids[] = $it[0];
        }
    }
    return $ids;
}

/**
 * The gate matrix: [id => ['free' => bool, 'pro' => bool, 'team' => bool]].
 * Missing ids (a newer tool, or nothing saved yet) default to allowed.
 */
function tool_gates_matrix(): array
{
    $saved = json_decode((string)setting(TOOL_GATES_SETTING, ''), true);
    $saved = is_array($saved) ? $saved : [];
    $out = [];
    foreach (tool_option_ids() as $id) {
        $row = isset($saved[$id]) && is_array($saved[$id]) ? $saved[$id] : [];
        foreach (TOOL_TIERS as $t) {
            $out[$id][$t] = array_key_exists($t, $row) ? (bool)$row[$t] : true;
        }
    }
    return $out;
}

/** Save the matrix from the dashboard form (gate[id][tier] = '1'). */
function tool_gates_save(array $posted): int
{
    $before = tool_gates_matrix();
    $ids = tool_option_ids();
    $out = [];
    $changed = 0;
    foreach ($ids as $id) {
        $row = isset($posted[$id]) && is_array($posted[$id]) ? $posted[$id] : [];
        foreach (TOOL_TIERS as $t) {
            $on = !empty($row[$t]) && (string)$row[$t] === '1';
            $out[$id][$t] = $on;
            if (($before[$id][$t] ?? true) !== $on) {
                $changed++;
            }
        }
    }
    set_setting(TOOL_GATES_SETTING, json_encode($out, JSON_UNESCAPED_SLASHES));
    set_setting('tool_control_updated_at', now());
    audit('tool.gates.saved', $changed . ' switch(es) changed');
    return $changed;
}

/** Compact form for the signed control block: id => [free, pro, team] as 0/1. */
function tool_gates_compact(): array
{
    $out = [];
    foreach (tool_gates_matrix() as $id => $row) {
        $out[$id] = [(int)$row['free'], (int)$row['pro'], (int)$row['team']];
    }
    return $out;
}

// ---------------------------------------------------------------------
// Control ZIP Links
// ---------------------------------------------------------------------

/**
 * One domain as the tool compares it: lower case, no scheme, no path, no
 * port, no leading "www." or "*.". Returns '' when it is not a host name.
 */
function ziplinks_clean_domain(string $raw): string
{
    $d = strtolower(trim($raw));
    if ($d === '') {
        return '';
    }
    if (strpos($d, '://') !== false) {
        $d = (string)parse_url($d, PHP_URL_HOST);
    }
    $d = preg_replace('~[/?#].*$~', '', $d) ?? '';
    $d = preg_replace('~:\d+$~', '', $d) ?? '';
    $d = preg_replace('~^(\*\.|www\.)~', '', $d) ?? '';
    $d = rtrim($d, '.');
    if (strlen($d) > 253 || !preg_match('/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$/', $d)) {
        return '';
    }
    return $d;
}

/** Split a textarea (one domain per line, or commas) into clean, unique domains. */
function ziplinks_parse_domains(string $text, array &$rejected = []): array
{
    $out = [];
    foreach (preg_split('/[\s,;]+/', $text) ?: [] as $piece) {
        if (trim($piece) === '') {
            continue;
        }
        $d = ziplinks_clean_domain($piece);
        if ($d === '') {
            $rejected[] = mb_substr(trim($piece), 0, 80);
            continue;
        }
        $out[$d] = true;
        if (count($out) >= ZIPLINKS_MAX_DOMAINS) {
            break;
        }
    }
    return array_keys($out);
}

function ziplinks_defaults(): array
{
    return [
        'enabled' => true,
        'tiers' => [
            'free' => ['enforce' => true, 'domains' => ZIPLINKS_DEFAULT_DOMAINS],
            'pro'  => ['enforce' => false, 'domains' => ZIPLINKS_DEFAULT_DOMAINS],
            'team' => ['enforce' => false, 'domains' => ZIPLINKS_DEFAULT_DOMAINS],
        ],
        'check_description' => false,
        'apply_to_csv' => false,
        'message' => 'Your link is not supported in the {plan} version.',
        'redirect_url' => 'https://mavelylink.com/',
        'redirect_label' => 'Get supported links',
    ];
}

/** The stored configuration merged over the defaults, always complete. */
function ziplinks_config(): array
{
    $cfg = ziplinks_defaults();
    $saved = json_decode((string)setting(ZIPLINKS_SETTING, ''), true);
    if (!is_array($saved)) {
        return $cfg;
    }
    foreach (['enabled', 'check_description', 'apply_to_csv'] as $k) {
        if (array_key_exists($k, $saved)) {
            $cfg[$k] = (bool)$saved[$k];
        }
    }
    foreach (['message', 'redirect_url', 'redirect_label'] as $k) {
        if (isset($saved[$k]) && is_string($saved[$k])) {
            $cfg[$k] = $saved[$k];
        }
    }
    foreach (TOOL_TIERS as $t) {
        $row = $saved['tiers'][$t] ?? null;
        if (!is_array($row)) {
            continue;
        }
        if (array_key_exists('enforce', $row)) {
            $cfg['tiers'][$t]['enforce'] = (bool)$row['enforce'];
        }
        if (isset($row['domains']) && is_array($row['domains'])) {
            $list = [];
            foreach ($row['domains'] as $d) {
                $c = ziplinks_clean_domain((string)$d);
                if ($c !== '') {
                    $list[$c] = true;
                }
            }
            $cfg['tiers'][$t]['domains'] = array_slice(array_keys($list), 0, ZIPLINKS_MAX_DOMAINS);
        }
    }
    return $cfg;
}

/**
 * Validate and store the Control ZIP Links form. Returns a list of errors
 * (empty on success). Nothing is written when there is an error.
 */
function ziplinks_save(array $in): array
{
    $errors = [];
    $cfg = ziplinks_defaults();
    $cfg['enabled'] = !empty($in['enabled']);
    $cfg['check_description'] = !empty($in['check_description']);
    $cfg['apply_to_csv'] = !empty($in['apply_to_csv']);
    $msg = trim(str_replace(["\r", "\n"], ' ', (string)($in['message'] ?? '')));
    if ($msg === '' || mb_strlen($msg) > 300) {
        $errors[] = 'The message is required (300 characters at most).';
    }
    $cfg['message'] = mb_substr($msg, 0, 300);
    $url = trim((string)($in['redirect_url'] ?? ''));
    if (!is_web_url($url, true)) {
        $errors[] = 'The "get supported links" address must be a full https:// address.';
    }
    $cfg['redirect_url'] = $url;
    $label = trim((string)($in['redirect_label'] ?? ''));
    $cfg['redirect_label'] = $label === '' ? 'Get supported links' : mb_substr($label, 0, 60);
    $shared = null;
    if (!empty($in['same_for_all'])) {
        $rej = [];
        $shared = ziplinks_parse_domains((string)($in['domains_all'] ?? ''), $rej);
        if ($rej) {
            $errors[] = 'Not a valid domain: ' . implode(', ', array_slice($rej, 0, 5));
        }
    }
    foreach (TOOL_TIERS as $t) {
        $cfg['tiers'][$t]['enforce'] = !empty($in['enforce'][$t]);
        if ($shared !== null) {
            $cfg['tiers'][$t]['domains'] = $shared;
            continue;
        }
        $rej = [];
        $cfg['tiers'][$t]['domains'] = ziplinks_parse_domains((string)($in['domains'][$t] ?? ''), $rej);
        if ($rej) {
            $errors[] = 'Not a valid domain (' . $t . '): ' . implode(', ', array_slice($rej, 0, 5));
        }
    }
    foreach (TOOL_TIERS as $t) {
        if ($cfg['enabled'] && $cfg['tiers'][$t]['enforce'] && !$cfg['tiers'][$t]['domains']) {
            $errors[] = 'Add at least one supported domain for ' . ['free' => 'Free', 'pro' => 'Pro', 'team' => 'Unlimited for team'][$t]
                . ', or turn its switch off (every link is then supported).';
        }
    }
    if ($errors) {
        return $errors;
    }
    set_setting(ZIPLINKS_SETTING, json_encode($cfg, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
    set_setting('tool_control_updated_at', now());
    audit('tool.ziplinks.saved', ($cfg['enabled'] ? 'ON' : 'OFF') . ' free=' . (int)$cfg['tiers']['free']['enforce']
        . ' pro=' . (int)$cfg['tiers']['pro']['enforce'] . ' team=' . (int)$cfg['tiers']['team']['enforce']);
    return [];
}

/** What the tool receives inside the signed control block. */
function ziplinks_for_client(): array
{
    $c = ziplinks_config();
    $tiers = [];
    foreach (TOOL_TIERS as $t) {
        $tiers[$t] = ['e' => (int)$c['tiers'][$t]['enforce'], 'd' => $c['tiers'][$t]['domains']];
    }
    return [
        'on' => (int)$c['enabled'],
        'tiers' => $tiers,
        'desc' => (int)$c['check_description'],
        'csv' => (int)$c['apply_to_csv'],
        'msg' => $c['message'],
        'url' => $c['redirect_url'],
        'label' => $c['redirect_label'],
    ];
}

/**
 * Server-side answer to "may this link be posted on this plan?". Used by the
 * dashboard's test box; the tool runs the same rule locally.
 */
function ziplinks_link_allowed(string $link, string $plan, ?array $cfg = null): bool
{
    $cfg = $cfg ?? ziplinks_config();
    $plan = in_array($plan, TOOL_TIERS, true) ? $plan : 'free';
    if (!$cfg['enabled'] || !$cfg['tiers'][$plan]['enforce']) {
        return true;
    }
    $link = trim($link);
    if (!preg_match('~^[a-z][a-z0-9+.-]*://~i', $link)) {
        $link = 'http://' . $link;
    }
    $host = strtolower((string)parse_url($link, PHP_URL_HOST));
    $host = preg_replace('~^www\.~', '', $host) ?? '';
    if ($host === '') {
        return false;
    }
    foreach ($cfg['tiers'][$plan]['domains'] as $d) {
        if ($host === $d || substr($host, -strlen('.' . $d)) === '.' . $d) {
            return true;
        }
    }
    return false;
}

/** Version stamp so the tool can tell the rules changed. */
function tool_control_version(): string
{
    return (string)setting('tool_control_updated_at', '');
}
