<?php
/**
 * Central configuration.
 * EDIT THIS FILE after uploading, then delete install/ from the server.
 */
declare(strict_types=1);

// ---- database (Hostinger: hPanel -> Databases -> MySQL) ----------------
const DB_HOST = 'localhost';
const DB_NAME = 'your_database_name';
const DB_USER = 'your_database_user';
const DB_PASS = 'CHANGE_ME';   // never commit the real password

// ---- site -------------------------------------------------------------
const SITE_NAME  = 'MavelyLink';
/**
 * Leave SITE_URL empty to auto-detect the domain from the incoming request.
 * The whole project is domain-independent: upload it to any domain and it
 * works with no edit here. Set SITE_URL only if you must force a canonical
 * address (for example when the site sits behind a proxy that rewrites the
 * Host header). No trailing slash.
 */
const SITE_URL   = '';
const SUPPORT_EMAIL = 'support@example.com';

// ---- licensing --------------------------------------------------------
const TRIAL_DAYS        = 7;
const SUBSCRIPTION_DAYS = 30;
const LICENSE_TTL_HOURS = 24;   // life of one signed session token
const GRACE_DAYS        = 7;    // offline tolerance before the tool stops
const DEVICE_RESET_MAX  = 3;    // self-service device changes per licence

/**
 * Ed25519 signing key, base64. Generate once with install/keygen.php and
 * paste here. The desktop client embeds only the PUBLIC half.
 */
const LICENSE_SECRET_KEY = '';   // <- paste from keygen
const LICENSE_PUBLIC_KEY = '';   // <- paste from keygen

// Fallback secret used for CSRF and rate-limit hashing. Any long random string.
const APP_SECRET = 'CHANGE_ME_to_a_long_random_string';

// ---- environment ------------------------------------------------------
const DEBUG = false;   // NEVER true on a live site

if (DEBUG) {
    ini_set('display_errors', '1');
    error_reporting(E_ALL);
} else {
    ini_set('display_errors', '0');
    error_reporting(0);
}

// ---- v7 (all optional: defaults apply when a line is missing) -----------
const AUTO_MIGRATE           = true;   // upgrade the database (with backup) on first request
const CHECKIN_SECONDS        = 180;    // desktop check-in interval; the dashboard can override it
const TOKEN_RENEW_GRACE_DAYS = 45;     // an expired genuine session token may still be renewed
const MAIL_FROM              = '';     // e.g. 'MavelyLink <no-reply@your-domain.com>'; empty = SUPPORT_EMAIL
const PAYPAL_API_BASE_OVERRIDE = '';   // testing only - leave empty
const CRYPTO_API_BASE_OVERRIDE = '';   // testing only - leave empty
