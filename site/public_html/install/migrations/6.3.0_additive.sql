-- ---------------------------------------------------------------------
-- MavelyLink 6.3.0 - additive migration (referral programme)
--
-- You do NOT normally need to run this by hand. With AUTO_MIGRATE left at
-- its default (true in includes/config.php) the same changes are applied
-- automatically, with a full table backup first, the next time any page of
-- the site is opened. This file is here for administrators who prefer to
-- run the SQL themselves, or whose host disables automatic migration.
--
-- Everything below is ADDITIVE and IDEMPOTENT:
--   * no table is dropped, renamed or emptied
--   * no column is dropped, renamed or retyped
--   * no existing row is modified
--   * running it twice is harmless
--
-- Apply in phpMyAdmin: select your database, open the SQL tab, paste, Go.
-- ---------------------------------------------------------------------

-- 1. customers ------------------------------------------------------------
-- The durable buyer identity this project did not have. It is keyed on the
-- SAME normalised email that licenses.email and orders.email already carry,
-- so it lines up with what is already stored instead of replacing it.
CREATE TABLE IF NOT EXISTS `customers` (
  `id`                          INT AUTO_INCREMENT PRIMARY KEY,
  `email`                       VARCHAR(190) NOT NULL UNIQUE,
  `referral_code`               VARCHAR(16)  NOT NULL UNIQUE,
  `referred_by`                 VARCHAR(16)  NULL,
  `referred_by_customer_id`     INT          NULL,
  `referral_count_confirmed`    INT          NOT NULL DEFAULT 0,
  `reward_status`               ENUM('none','eligible','pro_granted','cash_paid') NOT NULL DEFAULT 'none',
  `reward_granted_at`           DATETIME     NULL,
  `reward_license_id`           INT          NULL,
  `reward_popup_seen_at`        DATETIME     NULL,
  `last_referral_popup_seen_at` DATETIME     NULL,
  `flagged`                     TINYINT(1)   NOT NULL DEFAULT 0,
  `flag_reason`                 VARCHAR(255) NULL,
  `payout_note`                 VARCHAR(255) NULL,
  `source`                      VARCHAR(32)  NOT NULL DEFAULT 'site',
  `created_at`                  DATETIME     NOT NULL,
  `updated_at`                  DATETIME     NOT NULL,
  KEY `idx_code` (`referral_code`),
  KEY `idx_referred_by` (`referred_by`),
  KEY `idx_reward` (`reward_status`),
  KEY `idx_flagged` (`flagged`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. customer_devices -----------------------------------------------------
-- Which installations belong to a customer. This is what lets a FREE user,
-- who has no licence and no serial, be recognised at all - and what lets a
-- self-referral across two email addresses be spotted.
CREATE TABLE IF NOT EXISTS `customer_devices` (
  `id`          INT AUTO_INCREMENT PRIMARY KEY,
  `customer_id` INT          NOT NULL,
  `device_hash` VARCHAR(64)  NOT NULL,
  `first_seen`  DATETIME     NOT NULL,
  `last_seen`   DATETIME     NOT NULL,
  `last_ip`     VARCHAR(45)  NULL,
  UNIQUE KEY `uq_cust_device` (`customer_id`, `device_hash`),
  KEY `idx_device` (`device_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. referrals ------------------------------------------------------------
-- One row per referral EVENT. uq_referrer_buyer is what makes "one buyer
-- counts once, however many licences they buy" true in the database rather
-- than only in application code.
CREATE TABLE IF NOT EXISTS `referrals` (
  `id`                   INT AUTO_INCREMENT PRIMARY KEY,
  `referrer_customer_id` INT           NOT NULL,
  `referred_customer_id` INT           NULL,
  `referred_email`       VARCHAR(190)  NOT NULL,
  `referral_code`        VARCHAR(16)   NOT NULL,
  `order_id`             INT           NULL,
  `license_id`           INT           NULL,
  `license_serial`       VARCHAR(32)   NULL,
  `amount`               DECIMAL(10,2) NULL,
  `currency`             CHAR(3)       NULL,
  `status`               ENUM('pending','confirmed','reverted','rejected') NOT NULL DEFAULT 'pending',
  `flagged`              TINYINT(1)    NOT NULL DEFAULT 0,
  `flag_reason`          VARCHAR(255)  NULL,
  `notes`                VARCHAR(500)  NULL,
  `ip`                   VARCHAR(45)   NULL,
  `seen_by_referrer`     TINYINT(1)    NOT NULL DEFAULT 0,
  `created_at`           DATETIME      NOT NULL,
  `confirmed_at`         DATETIME      NULL,
  `reverted_at`          DATETIME      NULL,
  UNIQUE KEY `uq_referrer_buyer` (`referrer_customer_id`, `referred_email`),
  UNIQUE KEY `uq_order` (`order_id`),
  KEY `idx_status` (`status`, `created_at`),
  KEY `idx_referrer` (`referrer_customer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. orders.referred_by ---------------------------------------------------
SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `orders` ADD COLUMN `referred_by` VARCHAR(16) NULL',
    'SELECT ''orders.referred_by already present''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'referred_by'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 5. orders.referrer_customer_id ------------------------------------------
SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `orders` ADD COLUMN `referrer_customer_id` INT NULL',
    'SELECT ''orders.referrer_customer_id already present''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'referrer_customer_id'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 6. settings -------------------------------------------------------------
-- The dashboard and the API read these; the defaults match the offer copy.
INSERT IGNORE INTO `settings` (`k`, `v`) VALUES
  ('referral_enabled',     '1'),
  ('referral_threshold',   '5'),
  ('referral_cookie_days', '30'),
  ('referral_reward_plan', 'pro'),
  ('referral_cash_amount', '15');

-- 7. backfill -------------------------------------------------------------
-- Give every email this site already knows a customer row and an invite
-- code, so existing buyers can start inviting immediately.
--
-- NOTE: the automatic migration does this in PHP and retries on a code
-- collision. Pure SQL cannot retry, so a colliding code is skipped by
-- INSERT IGNORE. Run block 7 again if the check in block 8 is not 0 - each
-- run only fills the rows still missing, so repeating is safe.
INSERT IGNORE INTO `customers` (`email`, `referral_code`, `source`, `created_at`, `updated_at`)
SELECT e.email,
       CONCAT(
         SUBSTRING('23456789ABCDEFGHJKLMNPQRSTVWXYZ', FLOOR(1 + RAND() * 31), 1),
         SUBSTRING('23456789ABCDEFGHJKLMNPQRSTVWXYZ', FLOOR(1 + RAND() * 31), 1),
         SUBSTRING('23456789ABCDEFGHJKLMNPQRSTVWXYZ', FLOOR(1 + RAND() * 31), 1),
         SUBSTRING('23456789ABCDEFGHJKLMNPQRSTVWXYZ', FLOOR(1 + RAND() * 31), 1),
         SUBSTRING('23456789ABCDEFGHJKLMNPQRSTVWXYZ', FLOOR(1 + RAND() * 31), 1),
         SUBSTRING('23456789ABCDEFGHJKLMNPQRSTVWXYZ', FLOOR(1 + RAND() * 31), 1),
         SUBSTRING('23456789ABCDEFGHJKLMNPQRSTVWXYZ', FLOOR(1 + RAND() * 31), 1),
         SUBSTRING('23456789ABCDEFGHJKLMNPQRSTVWXYZ', FLOOR(1 + RAND() * 31), 1)
       ),
       'backfill', UTC_TIMESTAMP(), UTC_TIMESTAMP()
FROM (
  SELECT DISTINCT LOWER(TRIM(`email`)) AS email FROM `licenses`
   WHERE `email` IS NOT NULL AND TRIM(`email`) <> ''
  UNION
  SELECT DISTINCT LOWER(TRIM(`email`)) FROM `orders`
   WHERE `email` IS NOT NULL AND TRIM(`email`) <> ''
) e
WHERE CHAR_LENGTH(e.email) BETWEEN 3 AND 190
  AND NOT EXISTS (SELECT 1 FROM `customers` c WHERE c.`email` = e.email);

-- 8. check ----------------------------------------------------------------
-- Expect 0. A non-zero number means a code collision skipped that many
-- rows; run block 7 again.
SELECT COUNT(*) AS `emails_still_without_a_customer_row`
FROM (
  SELECT DISTINCT LOWER(TRIM(`email`)) AS email FROM `licenses`
   WHERE `email` IS NOT NULL AND TRIM(`email`) <> ''
  UNION
  SELECT DISTINCT LOWER(TRIM(`email`)) FROM `orders`
   WHERE `email` IS NOT NULL AND TRIM(`email`) <> ''
) e
WHERE CHAR_LENGTH(e.email) BETWEEN 3 AND 190
  AND NOT EXISTS (SELECT 1 FROM `customers` c WHERE c.`email` = e.email);

-- 9. record the schema version --------------------------------------------
INSERT INTO `settings` (`k`, `v`) VALUES ('schema_version', '10')
  ON DUPLICATE KEY UPDATE `v` = '10';
