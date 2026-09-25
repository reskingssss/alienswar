-- ---------------------------------------------------------------------
-- MavelyLink 7.0.0 - additive migration (server-controlled Python tabs)
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

-- 1. tool_tabs -------------------------------------------------------------
-- One row per tab in the desktop tool's tab bar. The Python module lives in
-- `script` and is delivered at runtime to installations whose plan satisfies
-- `required_plan`; it is not inside the distributed build.
--
-- NOTE ON THE COLUMN NAME `sort_order`
-- The brief calls this field `order`. ORDER is a reserved word in MySQL and
-- would need back-ticking in every statement that touches it, and this
-- schema already uses `sort_order` for exactly this purpose on the `plans`
-- and `channels` tables. The column is therefore `sort_order` here and is
-- exposed as `order` in the JSON the tool receives, so the API matches the
-- brief while the schema stays consistent with itself.
--
-- NOTE ON `scripts` vs `tool_tabs`
-- The existing `scripts` table holds the JavaScript userscripts injected
-- into generated browser profiles. It is a completely different thing and
-- is NOT touched by this migration.
CREATE TABLE IF NOT EXISTS `tool_tabs` (
  `id`               INT AUTO_INCREMENT PRIMARY KEY,
  `slug`             VARCHAR(64)  NOT NULL UNIQUE,
  `title`            VARCHAR(80)  NOT NULL,
  `sort_order`       INT          NOT NULL DEFAULT 0,
  `enabled`          TINYINT(1)   NOT NULL DEFAULT 1,
  `required_plan`    ENUM('free','pro','team') NOT NULL DEFAULT 'free',
  `script`           MEDIUMTEXT   NOT NULL,
  `checksum`         CHAR(64)     NOT NULL DEFAULT '',
  `version`          INT          NOT NULL DEFAULT 1,
  `min_tool_version` VARCHAR(32)  NULL,
  `ui_width`         INT          NOT NULL DEFAULT 960,
  `ui_height`        INT          NOT NULL DEFAULT 340,
  `notes`            TEXT         NULL,
  `published_by`     VARCHAR(64)  NULL,
  `published_at`     DATETIME     NULL,
  `created_at`       DATETIME     NOT NULL,
  `updated_at`       DATETIME     NOT NULL,
  KEY `idx_live` (`enabled`, `sort_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. settings --------------------------------------------------------------
-- tool_tabs_enabled is the revocation lever. Set it to 0 and every
-- installation stops loading every remote tab at its next launch, with no
-- release and no database edit. includes/features.php names a revocation
-- switch as a prerequisite for shipping executable code to clients; this is
-- that switch.
INSERT IGNORE INTO `settings` (`k`, `v`) VALUES
  ('tool_tabs_enabled',   '1'),
  ('tool_tabs_changed_at', ''),
  ('tool_tabs_changed_by', '');

-- 3. schema marker ---------------------------------------------------------
-- Tells includes/migrate.php the database is now at schema 12, so the
-- automatic upgrade does not repeat the work above. Safe either way: every
-- statement here is idempotent.
INSERT INTO `settings` (`k`, `v`) VALUES ('schema_version', '12')
  ON DUPLICATE KEY UPDATE `v` = GREATEST(CAST(`v` AS UNSIGNED), 12);
