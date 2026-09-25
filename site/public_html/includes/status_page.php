<?php
declare(strict_types=1);
require_once __DIR__ . '/page.php';
require_once __DIR__ . '/orders.php';
require_once __DIR__ . '/csrf.php';

/** Load the order named in the query string, checking its access token
 *  (from the URL, or the session copy set at checkout). Null if not allowed. */
function status_load_order(): ?array
{
    public_session_start();
    $ref = get_str('ref', 24);
    $order = order_by_ref($ref);
    if ($order === null) {
        return null;
    }
    $t = get_str('t', 64);
    if ($t === '' && !empty($_SESSION['orders'][$ref])) {
        $t = (string)$_SESSION['orders'][$ref];
    }
    return order_access_ok($order, $t) ? $order : null;
}

function status_badge(string $kind): string
{
    $icons = [
        'good' => '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>',
        'wait' => '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
        'bad'  => '<svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>',
    ];
    return '<div class="status-badge sb-' . $kind . '">' . ($icons[$kind] ?? $icons['wait']) . '</div>';
}
