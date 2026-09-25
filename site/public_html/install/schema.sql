-- MavelyLink licensing schema. Import once via phpMyAdmin.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS admins (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(64)  NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  last_login    DATETIME     NULL,
  created_at    DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS licenses (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  serial             VARCHAR(32)  NOT NULL UNIQUE,
  email              VARCHAR(190) NOT NULL,
  tier               ENUM('free','pro') NOT NULL DEFAULT 'free',
  status             ENUM('active','blocked','revoked') NOT NULL DEFAULT 'active',
  expires_at         DATETIME     NOT NULL,
  device_hash        VARCHAR(64)  NULL,
  device_label       VARCHAR(120) NULL,
  device_resets      INT          NOT NULL DEFAULT 0,
  app_version        VARCHAR(32)  NULL,
  last_seen          DATETIME     NULL,
  last_ip            VARCHAR(45)  NULL,
  profile_count      INT          NOT NULL DEFAULT 0,
  source             VARCHAR(32)  NOT NULL DEFAULT 'manual',
  external_id        VARCHAR(190) NULL,
  notes              TEXT         NULL,
  created_at         DATETIME     NOT NULL,
  updated_at         DATETIME     NOT NULL,
  UNIQUE KEY uq_external (external_id),
  KEY idx_email  (email),
  KEY idx_device (device_hash),
  KEY idx_status (status, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS scripts (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  slug        VARCHAR(64)  NOT NULL UNIQUE,
  name        VARCHAR(120) NOT NULL,
  min_tier    ENUM('free','pro') NOT NULL DEFAULT 'free',
  enabled     TINYINT(1)   NOT NULL DEFAULT 1,
  version     INT          NOT NULL DEFAULT 1,
  source      MEDIUMTEXT   NOT NULL,
  updated_at  DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS payments (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  provider     VARCHAR(24)  NOT NULL,
  external_id  VARCHAR(190) NOT NULL,
  email        VARCHAR(190) NULL,
  amount       DECIMAL(12,2) NOT NULL DEFAULT 0,
  currency     VARCHAR(12)  NOT NULL DEFAULT 'USD',
  status       VARCHAR(32)  NOT NULL,
  license_id   INT          NULL,
  raw          MEDIUMTEXT   NULL,
  created_at   DATETIME     NOT NULL,
  UNIQUE KEY uq_provider_ext (provider, external_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS settings (
  k VARCHAR(64) PRIMARY KEY,
  v TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rate_limits (
  k            VARCHAR(64) PRIMARY KEY,
  hits         INT      NOT NULL DEFAULT 0,
  window_start DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS audit_log (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  action     VARCHAR(64)  NOT NULL,
  detail     VARCHAR(500) NULL,
  license_id INT          NULL,
  ip         VARCHAR(45)  NULL,
  created_at DATETIME     NOT NULL,
  KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO settings (k, v) VALUES
  ('kill_switch',       '0'),
  ('kill_message',      'The service is temporarily unavailable. Please try again later.'),
  ('paypal_enabled',    '1'),
  ('paypal_client_id',  ''),
  ('paypal_secret',     ''),
  ('paypal_webhook_id', ''),
  ('paypal_live',       '0'),
  ('crypto_enabled',    '1'),
  ('crypto_provider',   'manual'),
  ('crypto_api_key',    ''),
  ('crypto_ipn_secret', ''),
  ('usdt_network',      'TRC20'),
  ('usdt_address',      ''),
  ('price_usd',         '29.00'),
  ('trial_enabled',     '1'),
  -- ---- remote application control (the ONLY three things the site steers) ---
  -- 1) application block / kill switch is 'kill_switch' above.
  -- 2) mandatory application update:
  ('latest_version',    '1.0.0'),   -- newest build you have published
  ('min_version',       '1.0.0'),   -- clients older than this MUST update
  ('download_url',      ''),        -- where "Download Update" sends the user
  ('force_update',      '0'),       -- master on/off for the update requirement
  -- 3) an explicit application-enabled flag, mirrors kill_switch inverted so
  --    the Application Status page reads naturally (ON = usable):
  ('app_enabled',       '1'),
  ('blocked_message',   'This application has been disabled by the administrator. Please contact support.');

-- The two managed user scripts. Names are exactly "Script 1" / "Script 2".
-- Sources start EMPTY: paste your real script bodies in the dashboard. Saving
-- there bumps the version, which is how the desktop knows to re-download.
INSERT IGNORE INTO scripts (slug, name, min_tier, enabled, version, source, updated_at) VALUES
  ('script1', 'Script 1', 'free', 1, 1, '', UTC_TIMESTAMP()),
  ('script2', 'Script 2', 'pro',  1, 1, '', UTC_TIMESTAMP());
