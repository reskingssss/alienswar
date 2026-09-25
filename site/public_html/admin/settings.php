<?php
declare(strict_types=1);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/csrf.php';
require_once __DIR__ . '/../includes/orders.php';
// v6.2.1: the signing-key helpers live in license.php. orders.php already
// pulls it in, but this page depends on it directly, so say so.
require_once __DIR__ . '/../includes/license.php';
require_once __DIR__ . '/_layout.php';
require_admin();

/**
 * Settings: payment providers and general options. Pricing lives on the
 * Pricing plans page and the master switch on Application status; this page
 * keeps their older keys working but points to those pages for them.
 */
$textKeys = ['paypal_client_id', 'paypal_secret', 'paypal_webhook_id',
             'stripe_publishable_key', 'stripe_secret_key', 'stripe_webhook_secret',
             'crypto_provider', 'crypto_api_key', 'crypto_ipn_secret', 'crypto_merchant_id',
             'usdt_network', 'usdt_address'];
$boolKeys = ['paypal_enabled', 'paypal_live', 'crypto_enabled', 'stripe_enabled', 'paypal_cards'];

if (admin_post()) {
    if (isset($_POST['save_payments'])) {
        foreach ($boolKeys as $k) {
            set_setting($k, isset($_POST[$k]) ? '1' : '0');
        }
        foreach ($textKeys as $k) {
            if (array_key_exists($k, $_POST)) {
                set_setting($k, mb_substr(trim((string)$_POST[$k]), 0, 2000));
            }
        }
        $addr = (string)setting('usdt_address', '');
        if (setting_bool('crypto_enabled') && setting('crypto_provider') === 'manual' && $addr === '') {
            audit('settings.payments', 'crypto enabled without an address');
        }
        $sk = (string)setting('stripe_secret_key', '');
        if (setting_bool('stripe_enabled') && !stripe_ready()) {
            back_to('settings.php', 'Card payments stay off: the Stripe secret key must start with sk_live_ or sk_test_ (or rk_).', false);
        }
        audit('settings.payments', 'paypal=' . setting('paypal_enabled') . ' crypto=' . setting('crypto_enabled')
            . ' card=' . setting('stripe_enabled') . ($sk !== '' ? (str_contains($sk, '_live_') ? ' (live)' : ' (test)') : ''));
        back_to('settings.php', 'Payment settings saved.');
    }
    if (isset($_POST['save_general'])) {
        set_setting('trial_enabled', isset($_POST['trial_enabled']) ? '1' : '0');
        audit('settings.general');
        back_to('settings.php', 'Settings saved.');
    }

    // ---- v6.3.2 (TASK 1.5): licence registration limits ---------------
    if (isset($_POST['save_activation'])) {
        $max = max(1, min(20, (int)($_POST['activation_max_attempts'] ?? 3)));
        $hrs = max(1, min(720, (int)($_POST['activation_lockout_hours'] ?? 24)));
        set_setting('activation_max_attempts', (string)$max);
        set_setting('activation_lockout_hours', (string)$hrs);
        set_setting('activation_generic_errors', isset($_POST['activation_generic_errors']) ? '1' : '0');
        set_setting('site_public_url', trim((string)($_POST['site_public_url'] ?? '')));
        audit('settings.activation', $max . ' attempts / ' . $hrs . 'h lockout');
        back_to('settings.php#activation', 'Registration settings saved.');
    }

    // ---- v6.2.1: database connection (5.1) ---------------------------
    if (isset($_POST['test_db']) || isset($_POST['save_db'])) {
        $creds = db_creds_from_post($_POST);
        $result = db_test_connection($creds);

        if (isset($_POST['test_db'])) {
            back_to('settings.php#dbconn',
                    $result['ok'] ? 'Connection succeeded. Nothing was saved — press "Save and switch over" to use these details.'
                                  : 'Connection failed: ' . db_safe_error($result['error']),
                    $result['ok']);
        }

        // Save refuses unless the details actually work, so the dashboard
        // cannot lock itself (and the whole site) out of the database.
        if (!$result['ok']) {
            back_to('settings.php#dbconn',
                    'Nothing was saved — these details do not connect: ' . db_safe_error($result['error']), false);
        }
        $written = db_write_local_config($creds);
        if (!$written['ok']) {
            back_to('settings.php#dbconn', $written['error'], false);
        }
        audit('settings.database', 'host=' . $creds['DB_HOST'] . ' db=' . $creds['DB_NAME'] . ' user=' . $creds['DB_USER']);
        back_to('settings.php#dbconn', 'Database connection saved and in use from the next request.');
    }

    // ---- v6.2.1: admin account (5.2) ---------------------------------
    if (isset($_POST['save_admin_password'])) {
        $res = admin_change_password(
            (int)($_SESSION['admin_id'] ?? 0),
            (string)($_POST['current_password'] ?? ''),
            (string)($_POST['new_password'] ?? ''),
            (string)($_POST['confirm_password'] ?? '')
        );
        back_to('settings.php#account',
                $res['ok'] ? 'Password changed. Your other browsers have been signed out.' : $res['error'],
                $res['ok']);
    }
    if (isset($_POST['save_admin_username'])) {
        $res = admin_change_username(
            (int)($_SESSION['admin_id'] ?? 0),
            (string)($_POST['current_password_u'] ?? ''),
            (string)($_POST['new_username'] ?? '')
        );
        back_to('settings.php#account',
                $res['ok'] ? 'Username changed. Your other browsers have been signed out.' : $res['error'],
                $res['ok']);
    }

    // ---- v6.2.1: licence signing keypair (5.3) -----------------------
    if (isset($_POST['generate_keypair'])) {
        $already = license_signing_ready();
        // replacing a working key is destructive for installed apps, so it
        // needs the typed confirmation from the form
        if ($already && strtoupper(trim((string)($_POST['confirm_regenerate'] ?? ''))) !== 'REPLACE') {
            back_to('settings.php#signing',
                    'Nothing was changed. To replace a working key, type REPLACE in the confirmation box first.', false);
        }
        $res = license_keypair_generate();
        if (!$res['ok']) {
            back_to('settings.php#signing', $res['error'], false);
        }
        back_to('settings.php#signing',
                ($already ? 'New keypair generated. Every installed app must be rebuilt with the new public key below.'
                          : 'Keypair generated. Copy LICENSE_PUBLIC_KEY_B64 below into the desktop tool and rebuild it.'));
    }
}

/**
 * v6.2.1: read the connection form, falling back to what is in use now.
 * An empty password box means "keep the current password" — the real
 * password is never rendered into the page, so it cannot be echoed back.
 */
function db_creds_from_post(array $post): array
{
    $port = (int)($post['db_port'] ?? 0);
    $pass = (string)($post['db_pass'] ?? '');
    return [
        'DB_HOST'    => trim((string)($post['db_host'] ?? '')) ?: db_conf('DB_HOST', 'localhost'),
        'DB_PORT'    => (string)($port > 0 && $port <= 65535 ? $port : (int)db_conf('DB_PORT', '3306')),
        'DB_NAME'    => trim((string)($post['db_name'] ?? '')) ?: db_conf('DB_NAME', ''),
        'DB_USER'    => trim((string)($post['db_user'] ?? '')) ?: db_conf('DB_USER', ''),
        'DB_PASS'    => $pass !== '' ? $pass : db_conf('DB_PASS', ''),
        'DB_CHARSET' => preg_match('/^[a-z0-9_]{1,32}$/i', (string)($post['db_charset'] ?? ''))
                        ? (string)$post['db_charset'] : db_conf('DB_CHARSET', 'utf8mb4'),
    ];
}

/**
 * Driver messages can quote the DSN. Strip anything that looks like a
 * credential before it reaches the page or the audit log.
 */
function db_safe_error(string $message): string
{
    $message = preg_replace('/\b(password|pass|pwd)\s*=\s*\S+/i', '$1=***', $message) ?? $message;
    return mb_substr(trim($message), 0, 300);
}

/**
 * Write includes/config.local.php. Returns ['ok' => bool, 'error' => string].
 *
 * includes/config.php is never touched: it keeps whatever the site owner
 * put there and remains the fallback for every value, so an upgrade cannot
 * clobber working credentials and deleting config.local.php always restores
 * the previous connection.
 */
function db_write_local_config(array $creds): array
{
    $path = dirname(__DIR__) . '/includes/config.local.php';
    $body = "<?php\n"
          . "/**\n"
          . " * Written by the MavelyLink dashboard (Settings -> Database connection).\n"
          . " * Values here override the matching constants in includes/config.php.\n"
          . " * Delete this file to go back to the settings in config.php.\n"
          . " * Generated: " . now() . " UTC\n"
          . " */\n"
          . "return " . var_export($creds, true) . ";\n";

    $tmp = $path . '.tmp' . bin2hex(random_bytes(4));
    if (@file_put_contents($tmp, $body, LOCK_EX) === false) {
        @unlink($tmp);
        return ['ok' => false, 'error' => 'Nothing was saved — includes/ is not writable by PHP. '
            . 'Give it write permission in your host file manager, or paste the values into includes/config.php by hand.'];
    }
    @chmod($tmp, 0600);
    if (!@rename($tmp, $path)) {
        @unlink($tmp);
        return ['ok' => false, 'error' => 'Nothing was saved — includes/config.local.php could not be replaced.'];
    }
    // a cached copy of the OLD file would keep the old connection alive
    if (function_exists('opcache_invalidate')) {
        @opcache_invalidate($path, true);
    }
    mvl_local_config(true);
    return ['ok' => true, 'error' => ''];
}

$methods = checkout_methods();
$webhookPaypal = site_url('api/webhooks/paypal.php');
$webhookStripe = site_url('api/webhooks/stripe.php');
$stripeKey = (string)setting('stripe_secret_key', '');
$webhookCrypto = site_url('api/webhooks/crypto.php');
layout_top('Settings', 'Payment providers and general options.');
?>
<section class="card" aria-labelledby="live">
  <div class="card-head"><h2 id="live">Checkout right now</h2></div>
  <?php if (!$methods): ?>
    <div class="alert alert-warn" role="status">No payment method is active, so the checkout page is closed. Turn on
      card payments, PayPal or crypto below, or enable a contact channel under <a href="channels.php">Contact channels</a>.</div>
  <?php else: ?>
    <p>Customers can pay with: <?php foreach ($methods as $m) {
        echo '<span class="chip chip-good"><span aria-hidden="true">●</span> ' . e($m['label']) . '</span> ';
    } ?></p>
  <?php endif; ?>
  <p class="muted small">Prices are set on <a href="plans.php">Pricing plans</a>. The application on/off switch is on
    <a href="status.php">Application status</a>.</p>
</section>

<form method="post">
  <?= csrf_field() ?>
  <section class="card" id="card" aria-labelledby="cardh">
    <div class="card-head"><h2 id="cardh">VISA / Mastercard (Stripe)</h2>
      <?= stripe_ready() ? state_chip('on', str_contains($stripeKey, '_live_') ? 'On · live' : 'On · test mode') : state_chip('off', 'Off') ?></div>
    <p class="muted small">Buyers pay by card on Stripe's secure hosted page; card numbers never reach this site. A licence
      is issued only after the server reads the payment back from Stripe (webhook, or the buyer's status page), for the
      exact order total. Refunds and chargebacks revoke what the payment bought.</p>
    <label class="check"><input type="checkbox" name="stripe_enabled"<?= setting_bool('stripe_enabled') ? ' checked' : '' ?>> Offer card payment (VISA, Mastercard) at checkout</label>
    <div class="form-grid">
      <label class="field">Secret key <span class="hint">sk_live_… or sk_test_… (a restricted key rk_… works too)</span>
        <input type="password" name="stripe_secret_key" value="<?= e($stripeKey) ?>" autocomplete="new-password" spellcheck="false"></label>
      <label class="field">Publishable key <span class="hint">optional, pk_…</span>
        <input name="stripe_publishable_key" value="<?= e(setting('stripe_publishable_key', '')) ?>" autocomplete="off" spellcheck="false"></label>
      <label class="field">Webhook signing secret <span class="hint">whsec_…</span>
        <input type="password" name="stripe_webhook_secret" value="<?= e(setting('stripe_webhook_secret', '')) ?>" autocomplete="new-password" spellcheck="false"></label>
    </div>
    <p class="muted small">Webhook URL to add in Stripe → Developers → Webhooks: <code><?= e($webhookStripe) ?></code>
      <button type="button" class="copy" data-copy="<?= e($webhookStripe) ?>" aria-label="Copy webhook URL" title="Copy"><?= icon('copy') ?></button><br>
      Events: <code>checkout.session.completed</code>, <code>checkout.session.async_payment_succeeded</code>,
      <code>checkout.session.async_payment_failed</code>, <code>checkout.session.expired</code>,
      <code>charge.refunded</code>, <code>charge.dispute.created</code>.</p>
  </section>

  <section class="card" aria-labelledby="pp">
    <div class="card-head"><h2 id="pp">PayPal</h2><?= setting_bool('paypal_enabled') ? state_chip('on', 'On') : state_chip('off', 'Off') ?></div>
    <p class="muted small">Orders are created and captured on the server and verified by webhook, so the amount charged
      always matches the order. Buyers are sent to PayPal; card details never reach this site.</p>
    <label class="check"><input type="checkbox" name="paypal_enabled"<?= setting_bool('paypal_enabled') ? ' checked' : '' ?>> Offer PayPal at checkout</label>
    <label class="check"><input type="checkbox" name="paypal_live"<?= setting_bool('paypal_live') ? ' checked' : '' ?>> Live mode <span class="muted small">&nbsp;(unticked = sandbox for testing)</span></label>
    <label class="check"><input type="checkbox" name="paypal_cards"<?= setting_bool('paypal_cards', true) ? ' checked' : '' ?>> <span>Show PayPal's
      <b>Debit or Credit Card</b> button (VISA / Mastercard without a PayPal account)</span></label>
    <div class="form-grid">
      <label class="field">Client ID<input name="paypal_client_id" value="<?= e(setting('paypal_client_id', '')) ?>" autocomplete="off"></label>
      <label class="field">Secret<input type="password" name="paypal_secret" value="<?= e(setting('paypal_secret', '')) ?>" autocomplete="new-password"></label>
      <label class="field">Webhook ID<input name="paypal_webhook_id" value="<?= e(setting('paypal_webhook_id', '')) ?>"></label>
    </div>
    <p class="muted small">Webhook URL to paste into PayPal: <code><?= e($webhookPaypal) ?></code>
      <button type="button" class="copy" data-copy="<?= e($webhookPaypal) ?>" aria-label="Copy webhook URL" title="Copy"><?= icon('copy') ?></button></p>
  </section>

  <section class="card" aria-labelledby="cr">
    <div class="card-head"><h2 id="cr">Crypto / USDT</h2><?= setting_bool('crypto_enabled') ? state_chip('on', 'On') : state_chip('off', 'Off') ?></div>
    <label class="check"><input type="checkbox" name="crypto_enabled"<?= setting_bool('crypto_enabled') ? ' checked' : '' ?>> Offer crypto at checkout</label>
    <label class="field">How payments are taken
      <select name="crypto_provider">
        <?php foreach (['manual' => 'Manual address — you confirm each payment by hand',
                        'nowpayments' => 'NOWPayments (automatic)', 'cryptomus' => 'Cryptomus (automatic)'] as $k => $v): ?>
          <option value="<?= $k ?>"<?= setting('crypto_provider') === $k ? ' selected' : '' ?>><?= e($v) ?></option>
        <?php endforeach; ?>
      </select></label>
    <div class="form-grid">
      <label class="field">USDT network
        <select name="usdt_network"><?php foreach (['TRC20' => 'USDT TRC-20 (TRON, cheapest)', 'BEP20' => 'USDT BEP-20 (BSC)',
            'ERC20' => 'USDT ERC-20 (Ethereum)'] as $k => $v): ?>
          <option value="<?= $k ?>"<?= setting('usdt_network', 'TRC20') === $k ? ' selected' : '' ?>><?= e($v) ?></option><?php endforeach; ?></select></label>
      <label class="field">Your USDT address <span class="hint">for the manual method</span><input name="usdt_address" value="<?= e(setting('usdt_address', '')) ?>" autocomplete="off"></label>
    </div>
    <div class="form-grid">
      <label class="field">Gateway API key <span class="hint">automatic providers</span><input type="password" name="crypto_api_key" value="<?= e(setting('crypto_api_key', '')) ?>" autocomplete="new-password"></label>
      <label class="field">Merchant / store ID <span class="hint">Cryptomus</span><input name="crypto_merchant_id" value="<?= e(setting('crypto_merchant_id', '')) ?>"></label>
      <label class="field">IPN secret<input type="password" name="crypto_ipn_secret" value="<?= e(setting('crypto_ipn_secret', '')) ?>" autocomplete="new-password"></label>
    </div>
    <p class="muted small">IPN / callback URL: <code><?= e($webhookCrypto) ?></code>
      <button type="button" class="copy" data-copy="<?= e($webhookCrypto) ?>" aria-label="Copy IPN URL" title="Copy"><?= icon('copy') ?></button></p>
    <div class="alert alert-info">On the <b>manual</b> method the buyer sends USDT and submits the transaction hash. Nothing
      is automatic — verify it on a block explorer, then approve it in Payments, which issues the key.</div>
  </section>

  <button class="btn btn-primary" name="save_payments" value="1">Save payment settings</button>
</form>

<form method="post">
  <?= csrf_field() ?>
  <section class="card" aria-labelledby="gen">
    <h2 id="gen">General</h2>
    <label class="check"><input type="checkbox" name="trial_enabled"<?= setting_bool('trial_enabled', true) ? ' checked' : '' ?>>
      Allow the legacy in-app trial endpoint <?= tip('New installs open directly on the Free plan and do not use this. It only affects older app builds that still call the trial endpoint.') ?></label>
    <button class="btn btn-primary" name="save_general" value="1">Save settings</button>
  </form>
</section>

<section class="card" id="activation" aria-labelledby="h-activation">
  <div class="card-head"><h2 id="h-activation">Licence registration</h2></div>
  <p class="muted small">How many licence keys a single installation may get wrong before the
    <b>Register licence</b> button disappears, and for how long. The limit is enforced on the server
    and keyed to the installation, so reinstalling the app does not reset it. Unlock a genuine
    customer from <a href="status.php#installs">Application status</a>.</p>
  <form method="post">
    <?= csrf_field() ?>
    <div class="grid grid-2">
      <label class="field">Attempts before lockout
        <input type="number" name="activation_max_attempts" min="1" max="20"
               value="<?= (int)setting('activation_max_attempts', '3') ?>"></label>
      <label class="field">Lockout length (hours)
        <input type="number" name="activation_lockout_hours" min="1" max="720"
               value="<?= (int)setting('activation_lockout_hours', '24') ?>"></label>
    </div>
    <label class="check"><input type="checkbox" name="activation_generic_errors"<?= setting_bool('activation_generic_errors', true) ? ' checked' : '' ?>>
      Give every rejected key the same answer
      <span class="muted small">&nbsp;(recommended &mdash; otherwise the error message tells an attacker whether a serial exists, has expired, or is already in use)</span></label>
    <label class="field" style="margin-top:10px">Public site address
      <input name="site_public_url" value="<?= e(setting('site_public_url', '')) ?>"
             placeholder="https://mavlink.click">
      <span class="hint">Used to build referral invite links. Leave blank to detect it automatically.</span></label>
    <button class="btn btn-primary" name="save_activation" value="1">Save registration settings</button>
  </section>
</form>

<?php
// =====================================================================
// v6.2.1 additions. Everything above is unchanged.
// =====================================================================
$keyStatus = license_key_status();
$publicB64 = $keyStatus['public_b64'];
$localCfg  = mvl_local_config();
$cfgPath   = dirname(__DIR__) . '/includes/config.local.php';
$cfgExists = is_file($cfgPath);
$includesWritable = is_writable(dirname($cfgPath));
?>

<section class="card" id="signing" aria-labelledby="sign-h">
  <div class="card-head">
    <h2 id="sign-h">Licence signing keys</h2>
    <?= $keyStatus['configured'] ? state_chip('on', 'Configured') : state_chip('off', 'Not configured') ?>
  </div>

  <?php if (!$keyStatus['configured']): ?>
    <div class="alert alert-warn" role="status">
      <b>Licence activation cannot work until this is done.</b> With no keypair the server cannot sign an
      activation response, so the desktop tool shows <i>“server signing key not configured”</i> and the licence is
      never activated. Application check-ins and the script manifest fail for the same reason, on every plan.
      Press <b>Generate signing keypair</b> below.
    </div>
  <?php else: ?>
    <dl class="kv">
      <dt>Status</dt><dd>Configured — the server can sign activations.</dd>
      <dt>Fingerprint</dt><dd><code><?= e($keyStatus['fingerprint']) ?></code></dd>
      <dt>Created</dt><dd><?= e($keyStatus['created_at'] !== '' ? $keyStatus['created_at'] . ' UTC' : 'unknown') ?></dd>
      <dt>Stored in</dt>
      <dd><?= $keyStatus['source'] === 'dashboard'
            ? 'the database (generated here)'
            : 'includes/config.php (LICENSE_SECRET_KEY / LICENSE_PUBLIC_KEY)' ?></dd>
    </dl>
  <?php endif; ?>

  <p class="muted small">The private half stays on this server and is used automatically by the activation
    endpoint. It is never shown on this page, never sent to a desktop app, and never written to a log.
    Only the public half below goes into the tool.</p>

  <?php if ($publicB64 !== ''): ?>
    <h3>LICENSE_PUBLIC_KEY_B64</h3>
    <p class="muted small">This exact string goes into the desktop tool. See the walkthrough below.</p>
    <p>
      <code class="break"><?= e($publicB64) ?></code>
      <button type="button" class="copy" data-copy="<?= e($publicB64) ?>"
              aria-label="Copy LICENSE_PUBLIC_KEY_B64" title="Copy"><?= icon('copy') ?></button>
    </p>
  <?php endif; ?>

  <form method="post">
    <?= csrf_field() ?>
    <?php if ($keyStatus['configured']): ?>
      <div class="alert alert-warn">
        <b>Replacing the keypair breaks every installed copy of the tool.</b> Tokens signed by the old key stop
        verifying, so every app must be rebuilt with the new public key and every user must re-register their
        licence key. Only do this if the private key has leaked. Licence keys themselves
        (<code>MVL-…</code>) are not affected and keep working.
      </div>
      <label class="field">Type <b>REPLACE</b> to confirm
        <input name="confirm_regenerate" autocomplete="off" placeholder="REPLACE"></label>
      <button class="btn" name="generate_keypair" value="1">Replace signing keypair</button>
    <?php else: ?>
      <button class="btn btn-primary" name="generate_keypair" value="1">Generate signing keypair</button>
    <?php endif; ?>
  </form>
</section>

<section class="card" id="guide" aria-labelledby="guide-h">
  <div class="card-head"><h2 id="guide-h">Step by step: from keypair to an activated licence</h2></div>
  <ol class="steps">
    <li><b>Generate the keypair.</b> Press <i>Generate signing keypair</i> in the section above. The private half
      is stored on this server and used automatically from that moment; nothing else on the server needs editing.</li>

    <li><b>Copy the public key.</b> Use the copy button next to <code>LICENSE_PUBLIC_KEY_B64</code> above. It is a
      base64 string of about 44 characters, ending in <code>=</code>. Do not copy the fingerprint — that is only a
      label for telling keys apart.</li>

    <li><b>Paste it into the desktop tool.</b> Open the file <code>license_client.py</code>, which sits in the same
      folder as <code>Google_Chrome.py</code>. Near the top, at <b>line 40</b>, find the variable
      <code>LICENSE_PUBLIC_KEY_B64</code> and replace the whole quoted value with what you copied:
      <pre class="code">LICENSE_PUBLIC_KEY_B64 = "PASTE_THE_COPIED_KEY_HERE"</pre>
      Change nothing else. Leave the quotation marks in place. In particular this variable is
      <b>not</b> the server address — that is <code>_DEFAULT_API_BASE</code>, a few lines below. Putting the site
      URL here is exactly what breaks activation.</li>

    <li><b>Rebuild and repackage the tool.</b> Build from <code>Google_Chrome.py</code> with
      <code>license_client.py</code> beside it, as in <code>docs/BUILD_AND_RELEASE.md</code>, then publish the new
      installer under <a href="update.php">App updates</a> with its SHA-256. Users on the old build keep working on
      Free but cannot activate until they update, because their copy still carries the old key.</li>

    <li><b>Create a licence.</b> Go to <a href="licenses.php">Licences</a> → <i>New licence</i>, choose Pro or
      Unlimited for Team and the customer's email. You get a key in the form
      <code>MVL-XXXXX-XXXXX-XXXXX-XXXXX</code>.</li>

    <li><b>Register it in the tool.</b> In the app, press <i>Register licence</i>, paste the key, press OK. It
      should report success within a second or two.</li>

    <li><b>Confirm the activation here.</b> Reload the licence on the <a href="licenses.php">Licences</a> page.
      <i>First activated</i> and <i>Last validation</i> now carry timestamps, <i>Computers</i> reads
      <i>1 of 1 in use</i> (or up to 3 of 3 for Team), and the machine is listed under <i>Computers</i> with its
      name and app version.</li>
  </ol>
  <div class="alert alert-info">
    If the tool still says <i>“server signing key not configured”</i>, the server has no keypair — repeat step 1.
    If it says <i>“The server response could not be verified”</i>, the key in the tool does not match the one here —
    repeat steps 2 to 4, and check you pasted into <code>LICENSE_PUBLIC_KEY_B64</code> and not next to it.
  </div>
</section>

<section class="card" id="account" aria-labelledby="acct-h">
  <div class="card-head"><h2 id="acct-h">Admin account</h2></div>
  <p class="muted small">Signed in as <b><?= e(admin_actor()) ?></b>. Both changes below need your current password,
    and both sign your other browsers out — this one stays signed in.</p>

  <form method="post" autocomplete="off">
    <?= csrf_field() ?>
    <h3>Change password</h3>
    <div class="form-grid">
      <label class="field">Current password
        <input type="password" name="current_password" autocomplete="current-password" required></label>
      <label class="field">New password <span class="hint">12 characters or more</span>
        <input type="password" name="new_password" autocomplete="new-password" required minlength="12"></label>
      <label class="field">Repeat new password
        <input type="password" name="confirm_password" autocomplete="new-password" required minlength="12"></label>
    </div>
    <button class="btn btn-primary" name="save_admin_password" value="1">Change password</button>
  </form>

  <form method="post" autocomplete="off">
    <?= csrf_field() ?>
    <h3>Change username</h3>
    <div class="form-grid">
      <label class="field">New username <span class="hint">3–64 letters, digits, dot, dash, underscore</span>
        <input name="new_username" value="" autocomplete="off" required></label>
      <label class="field">Current password
        <input type="password" name="current_password_u" autocomplete="current-password" required></label>
    </div>
    <button class="btn" name="save_admin_username" value="1">Change username</button>
  </form>
</section>

<section class="card" id="dbconn" aria-labelledby="db-h">
  <div class="card-head">
    <h2 id="db-h">Database connection</h2>
    <?= $cfgExists ? state_chip('on', 'Set here') : state_chip('off', 'From config.php') ?>
  </div>

  <div class="alert alert-warn">
    Wrong details here take the whole site offline, including this page. <b>Test connection</b> first — saving is
    refused unless the details actually connect. If you ever do get locked out, delete
    <code>includes/config.local.php</code> in your host's file manager and the site returns to the settings in
    <code>includes/config.php</code>.
  </div>

  <?php if (!$includesWritable): ?>
    <div class="alert alert-warn"><b>includes/ is not writable by PHP</b>, so changes here cannot be saved. Give the
      folder write permission in your host file manager, or edit <code>includes/config.php</code> by hand.</div>
  <?php endif; ?>

  <form method="post" autocomplete="off">
    <?= csrf_field() ?>
    <div class="form-grid">
      <label class="field">Host<input name="db_host" value="<?= e(db_conf('DB_HOST', 'localhost')) ?>" required></label>
      <label class="field">Port <span class="hint">3306 unless your host says otherwise</span>
        <input name="db_port" type="number" min="1" max="65535" value="<?= e(db_conf('DB_PORT', '3306')) ?>"></label>
      <label class="field">Database name<input name="db_name" value="<?= e(db_conf('DB_NAME', '')) ?>" required></label>
      <label class="field">Username<input name="db_user" value="<?= e(db_conf('DB_USER', '')) ?>" required></label>
      <label class="field">Password <span class="hint">leave empty to keep the current one</span>
        <input type="password" name="db_pass" value="" autocomplete="new-password" placeholder="•••••••• unchanged"></label>
      <label class="field">Charset
        <select name="db_charset">
          <?php foreach (['utf8mb4', 'utf8', 'latin1'] as $cs): ?>
            <option value="<?= $cs ?>"<?= db_conf('DB_CHARSET', 'utf8mb4') === $cs ? ' selected' : '' ?>><?= $cs ?></option>
          <?php endforeach; ?>
        </select></label>
    </div>
    <p class="muted small">The password is never rendered into this page, so it cannot be read from the page source
      and is never written to the audit log. Leaving the box empty keeps whatever is in use now.</p>
    <button class="btn" name="test_db" value="1">Test connection</button>
    <button class="btn btn-primary" name="save_db" value="1"
            onclick="return confirm('Save these details and switch the site over to them?');">Save and switch over</button>
  </form>

  <?php if ($cfgExists): ?>
    <p class="muted small">In use from <code>includes/config.local.php</code>. Values not set there fall back to
      <code>includes/config.php</code>, which this page never modifies.</p>
  <?php endif; ?>
</section>
<?php layout_bottom(); ?>
