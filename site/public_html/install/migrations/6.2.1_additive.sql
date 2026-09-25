-- ---------------------------------------------------------------------
-- MavelyLink 6.2.1 - additive migration
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

-- 1. admins.session_epoch -------------------------------------------------
-- Backs "changing the password signs my other browsers out". Existing
-- sessions carry epoch 0 and the column defaults to 0, so applying this
-- does not sign anybody out on its own.
SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE `admins` ADD COLUMN `session_epoch` INT NOT NULL DEFAULT 0',
    'SELECT ''admins.session_epoch already present'''
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'admins'
    AND COLUMN_NAME  = 'session_epoch'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2. admins.password_changed_at ------------------------------------------
-- Informational only; nothing fails if it stays NULL.
SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE `admins` ADD COLUMN `password_changed_at` DATETIME NULL',
    'SELECT ''admins.password_changed_at already present'''
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'admins'
    AND COLUMN_NAME  = 'password_changed_at'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3. settings rows for the licence signing keypair ------------------------
-- Empty values mean "not configured yet". While they are empty the server
-- falls back to LICENSE_SECRET_KEY / LICENSE_PUBLIC_KEY in
-- includes/config.php, so an install that already pasted those keeps
-- working with no change at all.
INSERT IGNORE INTO `settings` (`k`, `v`) VALUES
  ('license_secret_key',      ''),
  ('license_public_key',      ''),
  ('license_key_created_at',  '');

-- 4. record the schema version -------------------------------------------
INSERT INTO `settings` (`k`, `v`) VALUES ('schema_version', '9')
  ON DUPLICATE KEY UPDATE `v` = '9';
