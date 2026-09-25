<?php
/**
 * MavelyLink 6.3.1 — social channels and theme defaults (TASK 3).
 *
 * ADDITIVE. It reuses the EXISTING `channels` table rather than adding a
 * second one, because the admin page for it already exists.
 *
 * Important: that table already holds manual PAYMENT channels. The new
 * `show_on` column defaults to 'none', so an existing payment channel can
 * never silently become a social button on the website and in the tool. An
 * admin opts each one in, and `manual_payments` keeps the two roles apart.
 *
 * URLs are validated here, server-side, so a mistyped or hostile value in
 * the dashboard cannot be pushed to every installation (spec 3.4).
 */
declare(strict_types=1);
require_once __DIR__ . '/helpers.php';

const THEME_CHOICES = ['light', 'dark', 'system'];

/** https only (spec 3.4). Anything else is refused, not silently shown. */
function channel_url_ok(string $url): bool
{
    $url = trim($url);
    if ($url === '' || mb_strlen($url) > 500) {
        return false;
    }
    if (!preg_match('~^https://~i', $url)) {
        return false;
    }
    $parts = parse_url($url);
    return !empty($parts['host']) && filter_var($url, FILTER_VALIDATE_URL) !== false;
}

/**
 * The social buttons for one surface.
 *
 * @param string $where 'website' or 'tool'
 * @return array<int,array{code:string,label:string,url:string,icon:string,tooltip:string}>
 */
function channels_for_client(string $where): array
{
    $where = in_array($where, ['website', 'tool'], true) ? $where : 'website';
    try {
        $st = db()->prepare("SELECT code, display_name, url, icon, tooltip, sort_order
                               FROM channels
                              WHERE enabled = 1
                                AND show_on IN ('both', ?)
                                AND url <> ''
                              ORDER BY sort_order, code");
        $st->execute([$where]);
        $rows = $st->fetchAll();
    } catch (Throwable $e) {
        return [];      // not migrated yet, or database unavailable
    }
    $out = [];
    foreach ($rows as $r) {
        $url = (string)$r['url'];
        if (!channel_url_ok($url)) {
            continue;   // never hand a bad link to a client
        }
        $out[] = [
            'code'    => (string)$r['code'],
            'label'   => (string)$r['display_name'],
            'url'     => $url,
            'icon'    => (string)($r['icon'] ?: $r['code']),
            'tooltip' => (string)($r['tooltip'] ?? '') ?: (string)$r['display_name'],
        ];
    }
    return $out;
}

/** Theme defaults for new visitors and fresh installations (spec 3.3). */
function theme_defaults(): array
{
    $d = (string)setting('theme_default', 'system');
    return [
        'default' => in_array($d, THEME_CHOICES, true) ? $d : 'system',
        'toggle_visible' => setting_bool('theme_toggle_visible', true),
        'choices' => THEME_CHOICES,
    ];
}

/**
 * Inline SVG for a channel icon. Kept here so the website header and the
 * admin preview use one set, and an unknown code still renders something
 * rather than breaking the layout.
 */
function channel_icon_svg(string $code): string
{
    $paths = [
        'whatsapp' => '<path d="M12 2a10 10 0 0 0-8.6 15L2 22l5.2-1.4A10 10 0 1 0 12 2Zm5.3 14.1c-.2.6-1.3 1.2-1.8 1.2-.5.1-1 .1-1.6-.1-.4-.1-.9-.3-1.5-.6-2.6-1.1-4.3-3.8-4.4-4-.1-.2-1-1.4-1-2.6s.6-1.8.9-2.1c.2-.2.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.8 1.9c.1.2 0 .4-.1.5l-.3.4c-.1.1-.3.3-.1.6.1.3.6 1.1 1.4 1.7 1 .9 1.8 1.1 2 1.2.3.1.4.1.6-.1l.8-.9c.2-.2.4-.2.6-.1l1.7.8c.2.1.4.2.5.3.1.2.1.6-.1 1.2Z"/>',
        'facebook' => '<path d="M14 9h2.5V6H14c-2 0-3.5 1.5-3.5 3.5V11H8v3h2.5v7h3v-7H16l.5-3h-3V9.8c0-.5.4-.8 1-.8Z"/>',
        'telegram' => '<path d="m21 4-3 16-5.5-4-2.8 2.7L9 13 4 11l17-7Zm-9.4 9.6 6-6-8 5 .3 4 1.7-3Z"/>',
        'youtube'  => '<path d="M22 12s0-3.2-.4-4.7c-.2-.8-.9-1.5-1.7-1.7C18.4 5.2 12 5.2 12 5.2s-6.4 0-7.9.4c-.8.2-1.5.9-1.7 1.7C2 8.8 2 12 2 12s0 3.2.4 4.7c.2.8.9 1.5 1.7 1.7 1.5.4 7.9.4 7.9.4s6.4 0 7.9-.4c.8-.2 1.5-.9 1.7-1.7.4-1.5.4-4.7.4-4.7ZM10 15V9l5.2 3L10 15Z"/>',
        'x'        => '<path d="M17.5 3h3l-6.6 7.6L21.8 21h-5.9l-4.3-5.6L6.5 21h-3l7-8-6.8-10h6l3.9 5.2L17.5 3Z"/>',
        'instagram' => '<path d="M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6Zm0 6.3a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5ZM16.5 3h-9A4.5 4.5 0 0 0 3 7.5v9A4.5 4.5 0 0 0 7.5 21h9a4.5 4.5 0 0 0 4.5-4.5v-9A4.5 4.5 0 0 0 16.5 3Zm3.2 13.5a3.2 3.2 0 0 1-3.2 3.2h-9a3.2 3.2 0 0 1-3.2-3.2v-9a3.2 3.2 0 0 1 3.2-3.2h9a3.2 3.2 0 0 1 3.2 3.2v9Z"/>',
        'discord'  => '<path d="M19.3 5.6A16 16 0 0 0 15.5 4l-.3.5a12 12 0 0 1 3.3 1.7 14 14 0 0 0-11-.1A12 12 0 0 1 10.8 4.5L10.5 4a16 16 0 0 0-3.8 1.6C4 9.5 3.3 13.3 3.6 17a16 16 0 0 0 4.9 2.5l.9-1.4a10 10 0 0 1-1.6-.8l.4-.3a11 11 0 0 0 9.6 0l.4.3a10 10 0 0 1-1.6.8l.9 1.4a16 16 0 0 0 4.9-2.5c.4-4.3-.6-8-2.9-11.4ZM9.4 14.8c-1 0-1.7-.9-1.7-2s.8-2 1.7-2c1 0 1.8.9 1.7 2 0 1.1-.8 2-1.7 2Zm5.2 0c-1 0-1.7-.9-1.7-2s.8-2 1.7-2c1 0 1.8.9 1.7 2 0 1.1-.7 2-1.7 2Z"/>',
        'email'    => '<path d="M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm8 7L5.2 7h13.6L12 12Zm0 2L5 9v8h14V9l-7 5Z"/>',
    ];
    $d = $paths[$code] ?? '<circle cx="12" cy="12" r="8"/>';
    return '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">'
         . $d . '</svg>';
}
