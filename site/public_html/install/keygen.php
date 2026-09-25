<?php
/**
 * Run ONCE, in a browser, then paste the two values into includes/config.php
 * and DELETE the whole install folder.
 */
declare(strict_types=1);
header('Content-Type: text/plain; charset=utf-8');

if (!function_exists('sodium_crypto_sign_keypair')) {
    exit("This PHP build has no sodium extension. Ask Hostinger to enable it.\n");
}

$pair   = sodium_crypto_sign_keypair();
$secret = sodium_crypto_sign_secretkey($pair);
$public = sodium_crypto_sign_publickey($pair);

echo "Paste these into includes/config.php:\n\n";
echo "const LICENSE_SECRET_KEY = '" . base64_encode($secret) . "';\n";
echo "const LICENSE_PUBLIC_KEY = '" . base64_encode($public) . "';\n";
echo "const APP_SECRET         = '" . bin2hex(random_bytes(32)) . "';\n\n";
echo "The desktop client embeds ONLY the public key:\n";
echo base64_encode($public) . "\n\n";
echo "Keep the secret key on the server. If it leaks, anyone can mint licences.\n";
echo "DELETE the install folder now.\n";
