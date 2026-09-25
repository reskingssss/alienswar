<?php
/**
 * MavelyLink 7.0.0 — server-controlled Python tabs for the desktop tool.
 *
 * WHAT THIS IS
 * ------------
 * The desktop tool ships a tab HOST. The tab CONTENT — a Python 3.7 module
 * that draws itself into a frame the tool supplies — lives here, in the
 * database, and is delivered at runtime to installations whose plan is
 * entitled to it. Nothing executable ships inside the distributed build, so
 * reading the local files of a cracked copy yields a host with nothing to
 * host.
 *
 * WHY THIS FILE IS SEPARATE FROM includes/features.php
 * ----------------------------------------------------
 * features.php deliberately sends DATA (rules, schedules, copy) and not
 * code, and its header explains why: shipping executable Python turns a
 * compromise of this dashboard or this database into remote code execution
 * across the whole install base. That reasoning has not changed, and
 * features.php is untouched — the USA Timer still travels as data.
 *
 * This file adds the code pipe the brief asks for, and it implements the
 * three prerequisites features.php named before code delivery is safe:
 *
 *   1. SIGNING  — every delivered module is covered by an Ed25519 signature
 *                 made with the licence signing key (includes/license.php).
 *                 The desktop verifies it against the public half embedded
 *                 in the build, so stolen database rows are not enough to
 *                 make a tool run anything: the attacker also needs the
 *                 signing key, which is not in this table.
 *   2. REVOCATION — setting `tool_tabs_enabled` is a master switch. Set it
 *                 to 0 and every installation stops loading remote tabs at
 *                 its next launch or Refresh, with no release needed.
 *   3. 2FA on the dashboard — NOT implemented here. It is the one remaining
 *                 prerequisite, and it is an admin-login concern rather than
 *                 a tab concern. Until it exists, the dashboard password is
 *                 the thing standing between an attacker and every
 *                 customer's machine, so it deserves to be long and unique.
 *
 * SEALING
 * -------
 * The module travels inside a sealed envelope on top of HTTPS:
 *
 *   prk    = HKDF-Extract(salt = nonce, ikm = device | serial | slug | ver)
 *   k_enc  = HKDF-Expand(prk, "mvl-tab-enc/v1", 32)
 *   k_mac  = HKDF-Expand(prk, "mvl-tab-mac/v1", 32)
 *   ct     = plaintext XOR HMAC-SHA256-CTR(k_enc)
 *   tag    = HMAC-SHA256(k_mac, aad | nonce | ct)        (encrypt-then-MAC)
 *   grant  = Ed25519(slug, version, sha256(plaintext), device, plan, exp)
 *
 * The brief suggested AES-GCM. It is not used because the desktop side must
 * run on Python 3.7.7 with the standard library only (hard rule 3), and the
 * standard library has no AES at any version. HMAC-SHA256 in counter mode
 * with encrypt-then-MAC is a standard construction, is expressible in both
 * PHP and stdlib Python, and gives the same two properties that matter here
 * (confidentiality of the payload at rest in the client cache, and
 * detection of any modification). hash_hkdf() needs PHP 7.1.2+.
 *
 * BE CLEAR ABOUT WHAT THE ENVELOPE BUYS
 * -------------------------------------
 * The key is derived from values the client legitimately holds, so it stops
 * the cached payload being read off disk by anything that is not the tool,
 * and it stops modification in flight or at rest. It does NOT stop the
 * owner of the machine attaching a debugger to their own copy and reading
 * the module after it is decrypted. Nothing that runs on someone else's
 * computer can. The protection that actually holds is that the module is
 * never sent at all to an installation whose plan is not entitled to it —
 * which is decided here, from the database, and never from anything the
 * client says.
 */
declare(strict_types=1);
require_once __DIR__ . '/license.php';

// ---------------------------------------------------------------------
// the content container in the desktop tool
//
// These are the real dimensions of the tab canvas in Google_Chrome.py at
// its default window size, and the floor it is allowed to shrink to. The
// admin size-fitter and mavely_tabs.py both read the same numbers, so the
// preview in the dashboard cannot drift from the tool.
// ---------------------------------------------------------------------
const TAB_CANVAS_W      = 1024;   // content width at the default 1060x680
const TAB_CANVAS_H      = 425;    // content height at the default 1060x680
const TAB_CANVAS_MIN_W  = 964;    // at the enforced minimum window size
const TAB_CANVAS_MIN_H  = 360;
const TAB_ADVISED_W     = 960;    // what a script should declare to be safe
const TAB_ADVISED_H     = 340;

const TAB_SCRIPT_MAX_BYTES = 262144;    // 256 KB of source per tab
const TAB_GRANT_TTL        = 86400;     // signed execution grant lifetime

/** Plan ranking, so required_plan is a threshold and not an exact match. */
function tab_plan_rank(string $plan): int
{
    return ['free' => 0, 'pro' => 1, 'team' => 2][$plan] ?? 0;
}

/**
 * Does $plan satisfy $required?
 *   free -> everyone
 *   pro  -> Pro and Unlimited for Team
 *   team -> Unlimited for Team only
 */
function tab_plan_satisfies(string $plan, string $required): bool
{
    return tab_plan_rank($plan) >= tab_plan_rank($required);
}

/** Master switch for the whole remote-tab system (the revocation lever). */
function tabs_enabled(): bool
{
    return setting('tool_tabs_enabled', '1') === '1';
}

function tabs_set_enabled(bool $on): void
{
    set_setting('tool_tabs_enabled', $on ? '1' : '0');
    set_setting('tool_tabs_changed_at', now());
    set_setting('tool_tabs_changed_by', admin_actor_safe());
}

/** admin_actor() without requiring auth.php to be loaded (API context). */
function admin_actor_safe(): string
{
    if (session_status() === PHP_SESSION_ACTIVE && !empty($_SESSION['admin_user'])) {
        return (string)$_SESSION['admin_user'];
    }
    return 'system';
}

// ---------------------------------------------------------------------
// reading
// ---------------------------------------------------------------------

/** Every tab row, dashboard order. */
function tabs_all(): array
{
    if (!table_exists('tool_tabs')) {
        return [];
    }
    return db()->query('SELECT * FROM tool_tabs ORDER BY sort_order, id')->fetchAll();
}

function tab_by_id(int $id): ?array
{
    if (!table_exists('tool_tabs')) {
        return null;
    }
    $st = db()->prepare('SELECT * FROM tool_tabs WHERE id = ?');
    $st->execute([$id]);
    return $st->fetch() ?: null;
}

function tab_by_slug(string $slug): ?array
{
    if (!table_exists('tool_tabs')) {
        return null;
    }
    $st = db()->prepare('SELECT * FROM tool_tabs WHERE slug = ?');
    $st->execute([$slug]);
    return $st->fetch() ?: null;
}

/**
 * The tab list one installation should see.
 *
 * EVERY enabled tab is listed for EVERY plan, exactly as the brief
 * requires: the tab is always visible, and gating changes the CONTENT, not
 * the presence. `locked` says whether this installation may have the code;
 * the source itself is never in this answer.
 */
function tabs_manifest(string $plan, string $toolVersion = ''): array
{
    $plan = in_array($plan, PLAN_CODES, true) ? $plan : 'free';
    $out = [];
    if (!tabs_enabled() || !table_exists('tool_tabs')) {
        return $out;
    }
    $rows = db()->query('SELECT id, slug, title, sort_order, required_plan, version,
                                min_tool_version, ui_width, ui_height, checksum, updated_at
                           FROM tool_tabs WHERE enabled = 1 ORDER BY sort_order, id')->fetchAll();
    foreach ($rows as $r) {
        $minVer = trim((string)($r['min_tool_version'] ?? ''));
        // An old build that cannot host this tab is told so, rather than
        // being handed a module whose contract it does not implement.
        $tooOld = ($minVer !== '' && $toolVersion !== '' && version_cmp($toolVersion, $minVer) < 0);
        $allowed = tab_plan_satisfies($plan, (string)$r['required_plan']);
        $out[] = [
            'slug'          => (string)$r['slug'],
            'title'         => (string)$r['title'],
            'order'         => (int)$r['sort_order'],
            'version'       => (int)$r['version'],
            'required_plan' => (string)$r['required_plan'],
            'locked'        => !$allowed,
            'too_old'       => $tooOld,
            'min_tool_version' => $minVer,
            'ui_width'      => (int)$r['ui_width'],
            'ui_height'     => (int)$r['ui_height'],
            // the checksum lets the tool skip a download it already holds;
            // it is a hash of source it is entitled to, or '' when it is not
            'sha256'        => $allowed ? (string)$r['checksum'] : '',
        ];
    }
    return $out;
}

// ---------------------------------------------------------------------
// writing
// ---------------------------------------------------------------------

/** URL/identifier-safe slug, stable across renames. */
function tab_slugify(string $raw): string
{
    $s = strtolower(trim($raw));
    $s = preg_replace('/[^a-z0-9]+/', '_', $s) ?? '';
    $s = trim($s, '_');
    return $s === '' ? 'tab_' . substr(bin2hex(random_bytes(4)), 0, 8) : substr($s, 0, 64);
}

/** A slug nobody is using yet. */
function tab_unique_slug(string $base, int $exceptId = 0): string
{
    $slug = tab_slugify($base);
    $try = $slug;
    $n = 2;
    while (true) {
        $st = db()->prepare('SELECT id FROM tool_tabs WHERE slug = ?');
        $st->execute([$try]);
        $row = $st->fetch();
        if (!$row || (int)$row['id'] === $exceptId) {
            return $try;
        }
        $try = substr($slug, 0, 58) . '_' . $n;
        $n++;
    }
}

/**
 * Create or update one tab.
 *
 * $in keys: id, title, slug, order, enabled, required_plan, script,
 *           min_tool_version, ui_width, ui_height, notes
 * Returns ['ok' => bool, 'id' => int, 'error' => string, 'version' => int].
 *
 * The version is bumped only when the SOURCE changes, so renaming a tab or
 * moving it does not force every installation to re-download a module it
 * already holds.
 */
function tab_save(array $in): array
{
    $id = (int)($in['id'] ?? 0);
    $existing = $id > 0 ? tab_by_id($id) : null;

    $title = mb_substr(trim((string)($in['title'] ?? '')), 0, 80);
    if ($title === '') {
        return ['ok' => false, 'id' => $id, 'error' => 'Give the tab a title — it is the label shown in the tool.'];
    }

    $slug = trim((string)($in['slug'] ?? ''));
    if ($slug === '') {
        // On a rename the slug is deliberately NOT recomputed from the new
        // title: it is the stable internal key, and changing it would look
        // like a different tab to every installation.
        $slug = $existing ? (string)$existing['slug'] : tab_unique_slug($title);
    } else {
        $slug = tab_unique_slug($slug, $id);
    }

    $plan = (string)($in['required_plan'] ?? 'free');
    if (!in_array($plan, PLAN_CODES, true)) {
        $plan = 'free';
    }

    $script = (string)($in['script'] ?? '');
    $script = str_replace("\r\n", "\n", $script);
    if (strlen($script) > TAB_SCRIPT_MAX_BYTES) {
        return ['ok' => false, 'id' => $id,
                'error' => 'That script is larger than ' . number_format(TAB_SCRIPT_MAX_BYTES / 1024) . ' KB.'];
    }

    $order  = (int)($in['order'] ?? ($existing['sort_order'] ?? 0));
    $order  = max(0, min(9999, $order));
    $enabled = !empty($in['enabled']) ? 1 : 0;
    $minVer = mb_substr(trim((string)($in['min_tool_version'] ?? '')), 0, 32);
    if ($minVer !== '' && !preg_match('/^\d+(\.\d+){0,3}$/', $minVer)) {
        return ['ok' => false, 'id' => $id, 'error' => 'Minimum tool version must look like 6.2.0.'];
    }
    $w = max(320, min(4096, (int)($in['ui_width']  ?? TAB_ADVISED_W)));
    $h = max(200, min(4096, (int)($in['ui_height'] ?? TAB_ADVISED_H)));
    $notes = mb_substr(trim((string)($in['notes'] ?? '')), 0, 2000);
    $sum = hash('sha256', $script);

    if ($existing) {
        $sourceChanged = ((string)$existing['checksum'] !== $sum);
        $version = (int)$existing['version'] + ($sourceChanged ? 1 : 0);
        db()->prepare('UPDATE tool_tabs SET title = ?, slug = ?, sort_order = ?, enabled = ?,
                        required_plan = ?, script = ?, checksum = ?, version = ?, min_tool_version = ?,
                        ui_width = ?, ui_height = ?, notes = ?, published_by = ?, published_at = ?,
                        updated_at = ? WHERE id = ?')
            ->execute([$title, $slug, $order, $enabled, $plan, $script, $sum, $version,
                       $minVer !== '' ? $minVer : null, $w, $h, $notes !== '' ? $notes : null,
                       admin_actor_safe(), $sourceChanged ? now() : ($existing['published_at'] ?? now()),
                       now(), $id]);
        audit('tab.saved', $slug . ' v' . $version . ' ' . $plan . ' ' . ($enabled ? 'enabled' : 'disabled')
            . ' ' . strlen($script) . ' bytes' . ($sourceChanged ? ' (source changed)' : ''));
        return ['ok' => true, 'id' => $id, 'error' => '', 'version' => $version];
    }

    db()->prepare('INSERT INTO tool_tabs (slug, title, sort_order, enabled, required_plan, script,
                    checksum, version, min_tool_version, ui_width, ui_height, notes, published_by,
                    published_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?)')
        ->execute([$slug, $title, $order, $enabled, $plan, $script, $sum,
                   $minVer !== '' ? $minVer : null, $w, $h, $notes !== '' ? $notes : null,
                   admin_actor_safe(), now(), now(), now()]);
    $newId = (int)db()->lastInsertId();
    audit('tab.created', $slug . ' ' . $plan);
    return ['ok' => true, 'id' => $newId, 'error' => '', 'version' => 1];
}

function tab_set_enabled(int $id, bool $on): bool
{
    $row = tab_by_id($id);
    if (!$row) {
        return false;
    }
    db()->prepare('UPDATE tool_tabs SET enabled = ?, updated_at = ? WHERE id = ?')
        ->execute([$on ? 1 : 0, now(), $id]);
    audit('tab.' . ($on ? 'enabled' : 'disabled'), (string)$row['slug']);
    return true;
}

function tab_duplicate(int $id): ?int
{
    $row = tab_by_id($id);
    if (!$row) {
        return null;
    }
    $slug = tab_unique_slug($row['slug'] . '_copy');
    db()->prepare('INSERT INTO tool_tabs (slug, title, sort_order, enabled, required_plan, script,
                    checksum, version, min_tool_version, ui_width, ui_height, notes, published_by,
                    published_at, created_at, updated_at)
                   VALUES (?,?,?,0,?,?,?,1,?,?,?,?,?,?,?,?)')
        ->execute([$slug, mb_substr($row['title'] . ' (copy)', 0, 80), (int)$row['sort_order'] + 1,
                   $row['required_plan'], $row['script'], $row['checksum'],
                   $row['min_tool_version'], (int)$row['ui_width'], (int)$row['ui_height'],
                   $row['notes'], admin_actor_safe(), now(), now(), now()]);
    $newId = (int)db()->lastInsertId();
    audit('tab.duplicated', $row['slug'] . ' -> ' . $slug);
    return $newId;
}

function tab_delete(int $id): bool
{
    $row = tab_by_id($id);
    if (!$row) {
        return false;
    }
    db()->prepare('DELETE FROM tool_tabs WHERE id = ?')->execute([$id]);
    audit('tab.deleted', (string)$row['slug']);
    return true;
}

/** Apply a whole new order at once (drag-and-drop, or the order fields). */
function tabs_reorder(array $idsInOrder): int
{
    $st = db()->prepare('UPDATE tool_tabs SET sort_order = ?, updated_at = ? WHERE id = ?');
    $n = 0;
    foreach (array_values($idsInOrder) as $i => $id) {
        $id = (int)$id;
        if ($id > 0) {
            $st->execute([$i * 10, now(), $id]);
            $n++;
        }
    }
    if ($n) {
        audit('tab.reordered', $n . ' tabs');
    }
    return $n;
}

// ---------------------------------------------------------------------
// validation — the "Validate script" button
// ---------------------------------------------------------------------

/**
 * A python interpreter on this host, or '' when there is none.
 * Shared hosting usually has one; the checker below does not need it.
 */
function tabs_python_binary(): string
{
    static $found = null;
    if ($found !== null) {
        return $found;
    }
    $found = '';
    if (!function_exists('proc_open')) {
        return $found;
    }
    $disabled = array_map('trim', explode(',', (string)ini_get('disable_functions')));
    if (in_array('proc_open', $disabled, true)) {
        return $found;
    }
    foreach (['python3', 'python3.7', 'python'] as $bin) {
        $out = [];
        $code = 1;
        @exec(escapeshellcmd($bin) . ' -c "print(1)" 2>/dev/null', $out, $code);
        if ($code === 0 && trim(implode('', $out)) === '1') {
            $found = $bin;
            break;
        }
    }
    return $found;
}

/**
 * Structural check that needs no interpreter.
 *
 * It is deliberately conservative: it reports what it is SURE about and
 * stays quiet otherwise, so it can never block a valid module. Strings and
 * comments are stripped first so a keyword inside a docstring is not
 * mistaken for code.
 */
function tabs_lint_php(string $code): array
{
    $errors = [];
    $warnings = [];

    if (trim($code) === '') {
        return ['errors' => ['The script is empty.'], 'warnings' => []];
    }
    if (strpos($code, "\t") !== false && preg_match('/^[ ]+\S/m', $code)) {
        $warnings[] = 'The file mixes tabs and spaces for indentation. Python 3 rejects that; use 4 spaces.';
    }

    // strip comments and string literals so keyword checks see only code
    $bare = preg_replace('/("""|\'\'\')(?s:.*?)\1/', '""', $code) ?? $code;
    $bare = preg_replace('/(?<!\\\\)"(?:[^"\\\\\n]|\\\\.)*"/', '""', $bare) ?? $bare;
    $bare = preg_replace("/(?<!\\\\)'(?:[^'\\\\\n]|\\\\.)*'/", "''", $bare) ?? $bare;
    $bare = preg_replace('/#.*$/m', '', $bare) ?? $bare;

    // ---- Python 3.8+ syntax that 3.7.7 cannot parse -------------------
    $py38 = [
        ['/(?<![=!<>:+\-*\/%&|^])\:\=(?!=)/', 'Walrus operator “:=” — needs Python 3.8. Assign on its own line instead.'],
        ['/^\s*(?:async\s+)?def\s+[A-Za-z_]\w*\s*\([^)]*,\s*\/\s*[,)]/m', 'Positional-only parameter marker “/” — needs Python 3.8.'],
        ['/^\s*match\s+.+:\s*$/m', 'match statement — needs Python 3.10.'],
        ['/f(["\'])[^"\']*\{[^{}]*=\s*\}/', 'f-string “{x=}” self-documenting form — needs Python 3.8.'],
        ['/->\s*[A-Za-z_][\w\.\[\], ]*\s*\|\s*[A-Za-z_]/', '“X | Y” type union — needs Python 3.10. Use typing.Optional / typing.Union.'],
        ['/:\s*(?:list|dict|set|tuple|type)\s*\[/', 'Builtin generics like list[int] — need Python 3.9. Use typing.List / typing.Dict.'],
        ['/from\s+__future__\s+import\s+annotations/', 'from __future__ import annotations — needs Python 3.7.0+, which is fine, but it is not needed here.'],
        ['/\bzoneinfo\b/', 'zoneinfo is stdlib only from Python 3.9. Bundle a fallback, as mavely_timer.py does.'],
        ['/\bmath\.(?:lcm|prod|dist|comb|perm)\b/', 'math.lcm / prod / dist / comb / perm — need Python 3.8 or 3.9.'],
        ['/\bfunctools\.cached_property\b/', 'functools.cached_property — needs Python 3.8.'],
        ['/\bimportlib\.metadata\b/', 'importlib.metadata — needs Python 3.8.'],
        ['/\bstr\.removeprefix|\.removeprefix\(|\.removesuffix\(/', 'str.removeprefix / removesuffix — need Python 3.9.'],
        ['/\bdict\s*\|\s*dict\b|\}\s*\|\s*\{/', 'dict | dict merge — needs Python 3.9. Use a copy() then update().'],
    ];
    foreach ($py38 as [$re, $msg]) {
        if (preg_match($re, $bare)) {
            $errors[] = $msg;
        }
    }

    // ---- the tab-module contract --------------------------------------
    if (!preg_match('/^\s*TAB_META\s*=\s*\{/m', $bare)) {
        $errors[] = 'No TAB_META dictionary at module level. Every tab module must declare one.';
    }
    if (!preg_match('/^\s*def\s+build\s*\(\s*parent\s*,\s*ctx\s*\)\s*:/m', $bare)) {
        $errors[] = 'No “def build(parent, ctx):” at module level. That is the entry point the tool calls.';
    }

    // ---- things a hosted module must never do -------------------------
    $forbidden = [
        ['/\btk\.Tk\s*\(|\bTk\s*\(\s*\)/', 'Creates a Tk() root. The tool already owns the root window — build into `parent`.'],
        ['/\.mainloop\s*\(/', 'Calls mainloop(). The tool runs the event loop; a second one freezes the window.'],
        ['/\bsys\.exit\s*\(/', 'Calls sys.exit(), which would close the whole tool. Return from build() instead.'],
        ['/\bos\._exit\s*\(/', 'Calls os._exit(), which kills the tool with no cleanup.'],
        ['/\bquit\s*\(\s*\)|\bexit\s*\(\s*\)/', 'Calls exit()/quit(). Return from build() instead.'],
        ['/\bwhile\s+True\s*:(?![\s\S]{0,400}?\b(?:break|return)\b)/', 'Has a “while True:” with no visible break or return. A blocking loop on the UI thread freezes the tool — use a thread plus parent.after().'],
        ['/\bmavely_config\.json\b/', 'Touches mavely_config.json. Remote modules must not write the tool’s configuration.'],
        ['/\blicense_client\b/', 'Imports license_client. Use ctx["plan"] and ctx["licence"] instead of reaching into the licensing module.'],
        ['/\bos\.remove\s*\(|\bshutil\.rmtree\s*\(/', 'Deletes files. If that is intended, keep it strictly inside ctx["paths"]["work"].'],
    ];
    foreach ($forbidden as [$re, $msg]) {
        if (preg_match($re, $bare)) {
            $errors[] = $msg;
        }
    }

    // ---- cheap balance check ------------------------------------------
    foreach ([['(', ')'], ['[', ']'], ['{', '}']] as [$open, $close]) {
        $a = substr_count($bare, $open);
        $b = substr_count($bare, $close);
        if ($a !== $b) {
            $errors[] = 'Unbalanced ' . $open . $close . ' — ' . $a . ' opening, ' . $b . ' closing.';
        }
    }

    if (!preg_match('/\bdef\s+teardown\s*\(/', $bare) && preg_match('/\bthreading\.(?:Thread|Timer)\b/', $bare)) {
        $warnings[] = 'The module starts threads but has no teardown(). Add one so the threads stop when the tool closes.';
    }
    if (preg_match('/\bprint\s*\(/', $bare)) {
        $warnings[] = 'Uses print(). In a frozen build there is no console — use ctx["log"](...) so the message reaches the tool’s log.';
    }

    return ['errors' => $errors, 'warnings' => $warnings];
}

/**
 * The real thing when a python binary exists: compile() plus an AST walk
 * that reports the feature-version the code needs.
 */
function tabs_lint_python(string $code): ?array
{
    $bin = tabs_python_binary();
    if ($bin === '') {
        return null;
    }
    // The checker runs on the SOURCE ONLY. It compiles, it never executes:
    // compile() builds a code object and stops, so nothing in the module
    // body runs on this server.
    $checker = <<<'PYCHK'
import ast, json, sys
src = sys.stdin.read()
out = {"ok": True, "errors": [], "warnings": [], "engine": "python"}
try:
    compile(src, "<tab>", "exec")
except SyntaxError as e:
    out["ok"] = False
    out["errors"].append("Line %s: %s" % (e.lineno, e.msg))
    print(json.dumps(out)); raise SystemExit(0)
except Exception as e:
    out["ok"] = False
    out["errors"].append(str(e))
    print(json.dumps(out)); raise SystemExit(0)
try:
    tree = ast.parse(src)
except Exception as e:
    out["ok"] = False
    out["errors"].append(str(e))
    print(json.dumps(out)); raise SystemExit(0)
names = set()
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        names.add(node.name)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                names.add(t.id)
if "TAB_META" not in names:
    out["ok"] = False
    out["errors"].append("No module-level TAB_META dictionary.")
if "build" not in names:
    out["ok"] = False
    out["errors"].append("No module-level build(parent, ctx) function.")
else:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "build":
            args = [a.arg for a in node.args.args]
            if args[:2] != ["parent", "ctx"]:
                out["ok"] = False
                out["errors"].append(
                    "build() must be build(parent, ctx); found build(%s)." % ", ".join(args))
# 3.8+ node types that 3.7.7 cannot parse at all
for node in ast.walk(tree):
    n = type(node).__name__
    if n == "NamedExpr":
        out["ok"] = False
        out["errors"].append("Walrus operator ':=' needs Python 3.8.")
    elif n == "Match":
        out["ok"] = False
        out["errors"].append("match statement needs Python 3.10.")
    elif n == "arguments" and getattr(node, "posonlyargs", []):
        out["ok"] = False
        out["errors"].append("Positional-only parameters ('/') need Python 3.8.")
print(json.dumps(out))
PYCHK;

    $descriptors = [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']];
    $pipes = [];
    $cmd = escapeshellcmd($bin) . ' -c ' . escapeshellarg($checker);
    $proc = @proc_open($cmd, $descriptors, $pipes);
    if (!is_resource($proc)) {
        return null;
    }
    fwrite($pipes[0], $code);
    fclose($pipes[0]);
    $stdout = stream_get_contents($pipes[1]) ?: '';
    fclose($pipes[1]);
    fclose($pipes[2]);
    proc_close($proc);

    $parsed = json_decode(trim($stdout), true);
    return is_array($parsed) ? $parsed : null;
}

/** Both checkers, merged. Always returns errors + warnings + engine. */
function tabs_validate_script(string $code): array
{
    $php = tabs_lint_php($code);
    $py  = tabs_lint_python($code);
    $errors = $php['errors'];
    $warnings = $php['warnings'];
    $engine = 'structural check only (no python interpreter on this host)';
    if ($py !== null) {
        $engine = 'python compile() + AST, plus the structural check';
        foreach (($py['errors'] ?? []) as $e) {
            if (!in_array($e, $errors, true)) {
                $errors[] = (string)$e;
            }
        }
        foreach (($py['warnings'] ?? []) as $w) {
            if (!in_array($w, $warnings, true)) {
                $warnings[] = (string)$w;
            }
        }
    }
    return ['ok' => empty($errors), 'errors' => $errors, 'warnings' => $warnings, 'engine' => $engine];
}

/** Declared size vs the real container: what the size-fitter reports. */
function tab_size_verdict(int $w, int $h): array
{
    $problems = [];
    if ($w > TAB_CANVAS_W) {
        $problems[] = 'Width ' . $w . ' px is wider than the tab canvas (' . TAB_CANVAS_W
            . ' px at the default window). The tab will scroll sideways.';
    }
    if ($h > TAB_CANVAS_H) {
        $problems[] = 'Height ' . $h . ' px is taller than the tab canvas (' . TAB_CANVAS_H
            . ' px at the default window). The tab will scroll vertically.';
    }
    if ($w > TAB_CANVAS_MIN_W && $w <= TAB_CANVAS_W) {
        $problems[] = 'Width ' . $w . ' px fits the default window but not the smallest allowed one ('
            . TAB_CANVAS_MIN_W . ' px).';
    }
    if ($h > TAB_CANVAS_MIN_H && $h <= TAB_CANVAS_H) {
        $problems[] = 'Height ' . $h . ' px fits the default window but not the smallest allowed one ('
            . TAB_CANVAS_MIN_H . ' px).';
    }
    return [
        'ok' => empty($problems),
        'problems' => $problems,
        'advised_w' => TAB_ADVISED_W,
        'advised_h' => TAB_ADVISED_H,
    ];
}

// ---------------------------------------------------------------------
// sealing the payload
// ---------------------------------------------------------------------

/** HMAC-SHA256 counter-mode keystream, XORed over $data. */
function tab_ctr_xor(string $key, string $data): string
{
    $out = '';
    $n = strlen($data);
    $blocks = (int)ceil($n / 32);
    for ($i = 0; $i < $blocks; $i++) {
        $out .= hash_hmac('sha256', pack('N', $i), $key, true);
    }
    return $data ^ substr($out, 0, $n);
}

/**
 * Input key material. Everything in it is already known to the legitimate
 * client, and nothing in it is in this table, so a stolen database row
 * still cannot be turned into a payload a tool will run — the Ed25519
 * grant below is what the tool actually checks.
 */
function tab_ikm(string $device, string $serial, string $slug, int $version): string
{
    return implode("\x1f", [$device, $serial, $slug, (string)$version, 'mvl-tab/v1']);
}

/**
 * Seal one module for one installation.
 * Returns the JSON-ready envelope; the plaintext never leaves this call.
 */
function tab_seal(array $row, string $device, string $serial, string $plan): array
{
    $plaintext = (string)$row['script'];
    $sha = hash('sha256', $plaintext);
    $version = (int)$row['version'];
    $slug = (string)$row['slug'];

    $nonce = random_bytes(16);
    $ikm = tab_ikm($device, $serial, $slug, $version);
    $kEnc = hash_hkdf('sha256', $ikm, 32, 'mvl-tab-enc/v1', $nonce);
    $kMac = hash_hkdf('sha256', $ikm, 32, 'mvl-tab-mac/v1', $nonce);

    $aad = $slug . '|' . $version . '|' . $device . '|' . $plan;
    $ct = tab_ctr_xor($kEnc, $plaintext);
    $tag = hash_hmac('sha256', $aad . '|' . $nonce . '|' . $ct, $kMac, true);

    // The Ed25519 grant is the part that matters: the tool refuses to run
    // anything whose grant does not verify against the public key baked
    // into the build, so neither a fake server nor a modified database row
    // is enough on its own.
    $grant = sign_control([
        'typ'    => 'tab',
        'slug'   => $slug,
        'ver'    => $version,
        'sha256' => $sha,
        'sub'    => $device,
        'ser'    => $serial,   // serial used in the IKM, so the client derives identical keys
        'plan'   => $plan,
        'w'      => (int)$row['ui_width'],
        'h'      => (int)$row['ui_height'],
    ], TAB_GRANT_TTL);

    return [
        'slug'      => $slug,
        'title'     => (string)$row['title'],
        'version'   => $version,
        'required_plan' => (string)$row['required_plan'],
        'ui_width'  => (int)$row['ui_width'],
        'ui_height' => (int)$row['ui_height'],
        'alg'       => 'HKDF-SHA256/HMAC-CTR/EtM',
        'nonce'     => base64_encode($nonce),
        'ct'        => base64_encode($ct),
        'tag'       => base64_encode($tag),
        'sha256'    => $sha,
        'grant'     => $grant,
    ];
}

// ---------------------------------------------------------------------
// the AI converter prompt
//
// ONE source of truth. The dashboard panel shows exactly this text, and it
// is built from the same constants the tool enforces, so the prompt can
// never drift from the contract.
// ---------------------------------------------------------------------
function tabs_ai_prompt(): string
{
    $w = TAB_ADVISED_W;
    $h = TAB_ADVISED_H;
    $cw = TAB_CANVAS_W;
    $ch = TAB_CANVAS_H;
    $mw = TAB_CANVAS_MIN_W;
    $mh = TAB_CANVAS_MIN_H;

    return <<<PROMPT
You are converting an existing Python script into a TAB MODULE for the
"Chrome Profile Generator" desktop tool (MavelyLink). Rewrite the script I
give you so it satisfies every rule below, then return ONLY the finished
module as a single Python file — no explanation, no markdown fence.

=====================================================================
1. TARGET ENVIRONMENT — non-negotiable
=====================================================================
* Python 3.7.7 exactly. Code that needs 3.8 or later will not even parse.
  FORBIDDEN: the walrus operator ":="; positional-only parameters ("/" in
  a def); the match statement; f-string self-documenting "{x=}"; builtin
  generics (list[int], dict[str, int]) — use typing.List / typing.Dict;
  "X | Y" type unions — use typing.Optional / typing.Union; dict | dict
  merging — use a copy() then update(); zoneinfo; math.prod / math.lcm /
  math.dist / math.comb / math.perm; functools.cached_property;
  importlib.metadata; str.removeprefix / str.removesuffix.
* Tkinter only for UI (import tkinter as tk, from tkinter import ttk).
* Imports: the Python standard library, plus anything the tool already
  bundles (tkinter, ssl, urllib, sqlite3, hashlib, hmac, json, threading,
  queue, ctypes, struct, base64, subprocess, zipfile, shutil, tempfile,
  platform, uuid, re, random, math, colorsys, calendar, datetime, pathlib,
  webbrowser, socket, pytz). NOTHING ELSE. No pip installs, no requests,
  no numpy, no pandas, no pillow. If the original script uses one of those,
  replace it with a standard-library equivalent (requests -> urllib.request,
  and so on) or drop the feature and say so in a comment.

=====================================================================
2. THE ENTRY POINT — exact shape
=====================================================================
The module MUST expose these module-level names:

    TAB_META = {
        "name": "My Tool",     # fallback label; the dashboard title wins
        "version": 1,
        "min_width": {$w},
        "min_height": {$h},
    }

    def build(parent, ctx):
        \"\"\"Called once when the tab is created.\"\"\"
        # build every widget inside `parent`
        return None

Optional, all called by the host if present, all must be safe to call
twice and safe to call when build() failed half-way:

    def on_show():   pass   # the tab gained focus
    def on_hide():   pass   # the tab lost focus
    def teardown():  pass   # the tool is closing: stop threads, close handles

build() MUST return quickly (well under a second) and MUST NOT block.

=====================================================================
3. THE CONTAINER
=====================================================================
`parent` is a tkinter Frame the tool has already created, sized, DPI-scaled
and made scrollable. Treat it as your whole world:

* Build everything inside `parent`. Never create a window of your own.
* The visible canvas is about {$cw} x {$ch} px at the tool's default window
  size, and can shrink to {$mw} x {$mh} px. Design for {$w} x {$h} px and it
  always fits. Anything larger still works — the container scrolls — but
  the user has to scroll, so keep the primary controls in the top-left
  {$w} x {$h} area.
* Use grid() or pack() inside `parent`, never place() with absolute
  coordinates — absolute coordinates break at 125% and 150% Windows DPI.
* Do not call parent.configure(width=...) / height=...; the host owns the
  geometry. Do not call parent.pack_propagate(False).
* Sizes in your code are logical pixels. If you need a scaled pixel value,
  use ctx["scale"] (a float, 1.0 at 100% DPI): int(24 * ctx["scale"]).

=====================================================================
4. STYLE — so the tab looks native
=====================================================================
ctx["style"] is a dict of the tool's live theme tokens. Use it instead of
hard-coded colours, so the tab follows the light/dark switch:

    s = ctx["style"]
    s["BG"], s["BG_CARD"], s["BG_CARD_2"], s["BORDER"]
    s["FG"], s["FG_MUTED"], s["ACCENT"], s["GREEN"], s["DANGER"]
    s["font"]        -> ("Segoe UI", 9)
    s["font_bold"]   -> ("Segoe UI", 9, "bold")
    s["font_title"]  -> ("Segoe UI", 11)
    s["font_mono"]   -> ("Consolas", 9)
    s["pad"]         -> 8     outer padding used across the tool
    s["gap"]         -> 6     gap between related controls

ttk styles already defined by the tool and safe to use:
    "Accent.TButton"  blue primary      "Go.TButton"    green action
    "Ghost.TButton"   quiet secondary   "Mini.TButton"  small
    "Danger.TButton"  destructive       "Card.TLabel" / "CardMuted.TLabel"
Plain tk widgets must be given bg= and fg= from the tokens above; a tk
widget with no bg= will show as a grey block on the dark theme.

=====================================================================
5. FORBIDDEN — these break or hijack the host
=====================================================================
* NO tk.Tk() — the root window already exists.
* NO mainloop() — the tool runs the event loop.
* NO sys.exit(), exit(), quit(), os._exit() — they close the whole tool.
* NO blocking loop on the UI thread: no "while True:" without a break, no
  time.sleep() longer than a few milliseconds, no urlopen() on the UI
  thread. Do slow work on a threading.Thread and come back to the UI with
  parent.after(0, callback). Only the main thread may touch widgets.
* NO messagebox that steals focus for routine messages — use ctx["toast"].
* NO writes to the tool's own configuration: never touch mavely_config.json,
  the MavelyLink state folder, or the profiles directory. Write only inside
  ctx["paths"]["work"].
* NO import of license_client, and no attempt to read or change the plan.
  Read ctx["plan"] and believe it. Gating is enforced on the server before
  this module is ever delivered; faking it locally achieves nothing.
* NO "-topmost", no grab_set() on a long-lived window, no withdraw() of the
  root, no changes to the root window's title, geometry or protocol
  handlers.
* NO subprocess call that opens a console window on Windows without
  creationflags=0x08000000 (CREATE_NO_WINDOW).

=====================================================================
6. HOST SERVICES — ctx
=====================================================================
    ctx["plan"]      -> "free" | "pro" | "team"
    ctx["licence"]   -> {"serial_masked": str, "plan_name": str,
                         "expires_at": str, "state": str}   read-only
    ctx["paths"]     -> {"work": str, "downloads": str}
                        "work" is a per-tab folder that already exists and
                        is the ONLY place this module may write.
    ctx["log"](msg)  -> one line into the tool's log panel and, when
                        online, the dashboard's error log. Use this
                        instead of print().
    ctx["toast"](msg)-> small non-modal popup, auto-dismissing.
    ctx["style"]     -> the token dict from section 4.
    ctx["scale"]     -> float DPI scale, 1.0 at 100%.
    ctx["tab"]       -> {"slug": str, "title": str, "version": int}
    ctx["open_url"](url) -> open a link in the default browser.

=====================================================================
7. ERRORS — how to report them
=====================================================================
* Wrap the body of build() so one failure cannot take down the tool:

      def build(parent, ctx):
          try:
              _build(parent, ctx)
          except Exception as exc:
              ctx["log"]("[mytab] build failed: %r" % (exc,))
              raise

  Re-raising is correct: the host catches it, shows an inline error inside
  the tab, and the rest of the tool keeps working.
* Never swallow an exception silently. Every "except" must either handle
  the case or call ctx["log"]().
* Never use a bare "except:" — always "except Exception:".

=====================================================================
8. CHECKLIST BEFORE YOU ANSWER
=====================================================================
[ ] TAB_META present, with name / version / min_width / min_height
[ ] def build(parent, ctx) present at module level, returns quickly
[ ] teardown() stops every thread and cancels every after() job
[ ] no Tk(), no mainloop(), no sys.exit(), no blocking loop
[ ] no 3.8+ syntax anywhere
[ ] no third-party import
[ ] every colour and font from ctx["style"]
[ ] grid()/pack() only, no place() with absolute coordinates
[ ] fits {$w} x {$h} px
[ ] every widget touched from the main thread only

=====================================================================
MY SCRIPT TO CONVERT
=====================================================================
<paste your existing Python script here>
PROMPT;
}
