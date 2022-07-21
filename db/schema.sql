/*
 Navicat Premium Data Transfer

 Source Server         : darkweb-search-engine
 Source Server Type    : MySQL
 Source Server Version : 100244
 Source Host           : localhost:3307
 Source Schema         : tor

 Target Server Type    : MySQL
 Target Server Version : 100244
 File Encoding         : 65001

 Date: 21/07/2022 17:34:57
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for allowed_domain
-- ----------------------------
DROP TABLE IF EXISTS `allowed_domain`;
CREATE TABLE `allowed_domain`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `domain` varchar(1024) CHARACTER SET utf8 COLLATE utf8_unicode_ci NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 28 CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of allowed_domain
-- ----------------------------
INSERT INTO `allowed_domain` VALUES (1, 'onion');

-- ----------------------------
-- Table structure for bitcoin_address
-- ----------------------------
DROP TABLE IF EXISTS `bitcoin_address`;
CREATE TABLE `bitcoin_address`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `address` varchar(100) CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL,
  `page_url` varchar(1024) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `address`(`page_url`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 693575 CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of bitcoin_address
-- ----------------------------

-- ----------------------------
-- Table structure for bitcoin_address_link
-- ----------------------------
DROP TABLE IF EXISTS `bitcoin_address_link`;
CREATE TABLE `bitcoin_address_link`  (
  `bitcoin_address` int(11) NOT NULL,
  `page` int(11) NOT NULL,
  PRIMARY KEY (`bitcoin_address`, `page`) USING BTREE,
  INDEX `idx_bitcoin_address_link`(`page`) USING BTREE,
  CONSTRAINT `fk_bitcoin_address_link__bitcoin_address` FOREIGN KEY (`bitcoin_address`) REFERENCES `bitcoin_address` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_bitcoin_address_link__page` FOREIGN KEY (`page`) REFERENCES `page` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of bitcoin_address_link
-- ----------------------------

-- ----------------------------
-- Table structure for blocked_domain
-- ----------------------------
DROP TABLE IF EXISTS `blocked_domain`;
CREATE TABLE `blocked_domain`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `domain` varchar(1024) CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of blocked_domain
-- ----------------------------

-- ----------------------------
-- Table structure for category
-- ----------------------------
DROP TABLE IF EXISTS `category`;
CREATE TABLE `category`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(64) CHARACTER SET utf8 COLLATE utf8_unicode_ci NOT NULL,
  `is_auto` tinyint(1) NULL DEFAULT 1,
  `created_at` datetime(0) NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 7 CHARACTER SET = utf8 COLLATE = utf8_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of category
-- ----------------------------

-- ----------------------------
-- Table structure for category_link
-- ----------------------------
DROP TABLE IF EXISTS `category_link`;
CREATE TABLE `category_link`  (
  `domain` int(11) NOT NULL,
  `category` int(11) NOT NULL,
  `is_confirmed` tinyint(1) NULL DEFAULT 0,
  `is_valid` tinyint(1) NULL DEFAULT 1,
  `created_at` datetime(0) NULL DEFAULT NULL,
  PRIMARY KEY (`domain`, `category`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8 COLLATE = utf8_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of category_link
-- ----------------------------

-- ----------------------------
-- Table structure for clone_group
-- ----------------------------
DROP TABLE IF EXISTS `clone_group`;
CREATE TABLE `clone_group`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 31365 CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of clone_group
-- ----------------------------

-- ----------------------------
-- Table structure for daily_stat
-- ----------------------------
DROP TABLE IF EXISTS `daily_stat`;
CREATE TABLE `daily_stat`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `created_at` datetime(0) NOT NULL,
  `unique_visitors` int(11) NOT NULL,
  `total_onions` int(11) NOT NULL,
  `total_onions_all` int(11) NOT NULL,
  `new_onions` int(11) NOT NULL,
  `new_onions_all` int(11) NOT NULL,
  `total_clones` int(11) NOT NULL,
  `banned` int(11) NOT NULL,
  `banned_up_last_24` int(11) NOT NULL,
  `up_right_now` int(11) NOT NULL,
  `up_right_now_all` int(11) NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of daily_stat
-- ----------------------------

-- ----------------------------
-- Table structure for domain
-- ----------------------------
DROP TABLE IF EXISTS `domain`;
CREATE TABLE `domain`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `host` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci NOT NULL,
  `port` int(11) NOT NULL,
  `ssl` tinyint(1) NOT NULL,
  `is_up` tinyint(1) NOT NULL,
  `created_at` datetime(0) NOT NULL,
  `visited_at` datetime(0) NOT NULL,
  `title` mediumtext CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL,
  `last_alive` datetime(0) NULL DEFAULT NULL,
  `is_crap` tinyint(1) NULL DEFAULT 0,
  `is_genuine` tinyint(1) NULL DEFAULT 0,
  `is_fake` tinyint(1) NULL DEFAULT 0,
  `ssh_fingerprint` int(11) NULL DEFAULT NULL,
  `is_subdomain` tinyint(1) NULL DEFAULT 0,
  `server` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT '',
  `powered_by` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT '',
  `dead_in_a_row` int(11) NULL DEFAULT 0,
  `next_scheduled_check` datetime(0) NULL DEFAULT current_timestamp(0),
  `is_banned` tinyint(1) NULL DEFAULT 0,
  `portscanned_at` datetime(0) NULL DEFAULT '1969-12-31 19:00:00',
  `path_scanned_at` datetime(0) NULL DEFAULT '1969-12-31 19:00:00',
  `useful_404_scanned_at` datetime(0) NULL DEFAULT '1969-12-31 19:00:00',
  `useful_404` tinyint(1) NULL DEFAULT 0,
  `useful_404_php` tinyint(1) NULL DEFAULT 0,
  `useful_404_dir` tinyint(1) NULL DEFAULT 0,
  `clone_group` int(11) NULL DEFAULT NULL,
  `new_clone_group` int(11) NULL DEFAULT NULL,
  `ban_exempt` tinyint(1) NULL DEFAULT 0,
  `manual_genuine` tinyint(1) NULL DEFAULT 0,
  `language` varchar(32) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT '',
  `description_json` varchar(10240) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  `description_json_at` datetime(0) NULL DEFAULT '1969-12-31 19:00:00',
  `whatweb_at` datetime(0) NULL DEFAULT '1969-12-31 19:00:00',
  `category_label` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  `master_domain_id` int(11) NULL DEFAULT NULL,
  `clone_similarity` float NULL DEFAULT NULL,
  PRIMARY KEY (`id`, `host`) USING BTREE,
  INDEX `created_at_idx`(`created_at`) USING BTREE,
  INDEX `last_alive_idx`(`last_alive`) USING BTREE,
  INDEX `host_idx`(`host`) USING BTREE,
  INDEX `idx_domain__ssh_fingerprint`(`ssh_fingerprint`) USING BTREE,
  INDEX `idx_domain__clone_group`(`clone_group`) USING BTREE,
  INDEX `idx_domain__new_clone_group`(`new_clone_group`) USING BTREE,
  INDEX `language_idx`(`language`) USING BTREE,
  INDEX `idx_domain_title`(`title`(255)) USING BTREE,
  CONSTRAINT `fk_domain__clone_group` FOREIGN KEY (`clone_group`) REFERENCES `clone_group` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_domain__new_clone_group` FOREIGN KEY (`new_clone_group`) REFERENCES `clone_group` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_domain__ssh_fingerprint` FOREIGN KEY (`ssh_fingerprint`) REFERENCES `ssh_fingerprint` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1237159 CHARACTER SET = utf8 COLLATE = utf8_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of domain
-- ----------------------------

-- ----------------------------
-- Table structure for email
-- ----------------------------
DROP TABLE IF EXISTS `email`;
CREATE TABLE `email`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `address` varchar(100) CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL,
  `password` varchar(100) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT '',
  `text_id` int(11) NULL DEFAULT 0,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `address`(`address`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 16429665 CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of email
-- ----------------------------

-- ----------------------------
-- Table structure for email_link
-- ----------------------------
DROP TABLE IF EXISTS `email_link`;
CREATE TABLE `email_link`  (
  `email` int(11) NOT NULL,
  `page` int(11) NOT NULL,
  PRIMARY KEY (`email`, `page`) USING BTREE,
  INDEX `idx_email_link`(`page`) USING BTREE,
  CONSTRAINT `fk_email_link__email` FOREIGN KEY (`email`) REFERENCES `email` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_email_link__page` FOREIGN KEY (`page`) REFERENCES `page` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of email_link
-- ----------------------------

-- ----------------------------
-- Table structure for headless_bot
-- ----------------------------
DROP TABLE IF EXISTS `headless_bot`;
CREATE TABLE `headless_bot`  (
  `uuid` varchar(36) CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL,
  `kind` varchar(128) CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL,
  `created_at` datetime(0) NOT NULL,
  PRIMARY KEY (`uuid`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of headless_bot
-- ----------------------------

-- ----------------------------
-- Table structure for open_port
-- ----------------------------
DROP TABLE IF EXISTS `open_port`;
CREATE TABLE `open_port`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `port` int(11) NOT NULL,
  `domain` int(11) NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_open_port__domain`(`domain`) USING BTREE,
  CONSTRAINT `fk_open_port__domain` FOREIGN KEY (`domain`) REFERENCES `domain` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of open_port
-- ----------------------------

-- ----------------------------
-- Table structure for page
-- ----------------------------
DROP TABLE IF EXISTS `page`;
CREATE TABLE `page`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `url` varchar(1024) CHARACTER SET utf8 COLLATE utf8_unicode_ci NOT NULL,
  `title` varchar(1024) CHARACTER SET utf8 COLLATE utf8_unicode_ci NOT NULL,
  `code` int(11) NOT NULL,
  `domain` int(11) NOT NULL,
  `created_at` datetime(0) NOT NULL,
  `visited_at` datetime(0) NOT NULL,
  `is_frontpage` tinyint(1) NULL DEFAULT 0,
  `size` int(11) NULL DEFAULT 0,
  `path` varchar(1024) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT '',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `url`(`url`) USING BTREE,
  INDEX `idx_page__domain`(`domain`) USING BTREE,
  INDEX `page_path_idx`(`path`(255)) USING BTREE,
  INDEX `idx_path_code`(`code`, `path`(255)) USING BTREE,
  CONSTRAINT `fk_page__domain` FOREIGN KEY (`domain`) REFERENCES `domain` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 307375357 CHARACTER SET = utf8 COLLATE = utf8_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of page
-- ----------------------------

-- ----------------------------
-- Table structure for page_link
-- ----------------------------
DROP TABLE IF EXISTS `page_link`;
CREATE TABLE `page_link`  (
  `link_from` int(11) NOT NULL DEFAULT 0,
  `link_to` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`link_from`, `link_to`) USING BTREE,
  INDEX `idx_page_link`(`link_to`) USING BTREE,
  CONSTRAINT `fk_page_link__link_from` FOREIGN KEY (`link_from`) REFERENCES `page` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_page_link__link_to` FOREIGN KEY (`link_to`) REFERENCES `page` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of page_link
-- ----------------------------

-- ----------------------------
-- Table structure for request_log
-- ----------------------------
DROP TABLE IF EXISTS `request_log`;
CREATE TABLE `request_log`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `uuid` varchar(36) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT '',
  `uuid_is_fresh` tinyint(1) NULL DEFAULT 1,
  `created_at` datetime(0) NULL DEFAULT NULL,
  `agent` varchar(256) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  `path` varchar(1024) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  `full_path` varchar(1024) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  `referrer` varchar(1024) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_reqlog_created_at`(`created_at`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 8242177 CHARACTER SET = utf8 COLLATE = utf8_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of request_log
-- ----------------------------

-- ----------------------------
-- Table structure for search_log
-- ----------------------------
DROP TABLE IF EXISTS `search_log`;
CREATE TABLE `search_log`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `created_at` datetime(0) NOT NULL,
  `request_log` int(11) NOT NULL,
  `has_searchterms` tinyint(1) NOT NULL,
  `searchterms` varchar(256) CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL,
  `raw_searchterms` varchar(256) CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL,
  `context` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `is_json` tinyint(1) NOT NULL,
  `is_firstpage` tinyint(1) NOT NULL,
  `has_raw_searchterms` tinyint(1) NOT NULL,
  `results` int(11) NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_search_log__request_log`(`request_log`) USING BTREE,
  CONSTRAINT `fk_search_log__request_log` FOREIGN KEY (`request_log`) REFERENCES `request_log` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of search_log
-- ----------------------------

-- ----------------------------
-- Table structure for ssh_fingerprint
-- ----------------------------
DROP TABLE IF EXISTS `ssh_fingerprint`;
CREATE TABLE `ssh_fingerprint`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fingerprint` varchar(450) CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `fingerprint`(`fingerprint`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 157 CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of ssh_fingerprint
-- ----------------------------

-- ----------------------------
-- Table structure for web_component
-- ----------------------------
DROP TABLE IF EXISTS `web_component`;
CREATE TABLE `web_component`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(128) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  `version` varchar(128) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  `account` varchar(128) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  `string` varchar(512) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_web_component_name`(`name`) USING BTREE,
  INDEX `idx_web_component_version`(`version`) USING BTREE,
  INDEX `idx_web_component_account`(`account`) USING BTREE,
  INDEX `idx_web_component_string`(`string`) USING BTREE,
  INDEX `idx_web_component_name_version`(`name`, `version`) USING BTREE,
  INDEX `idx_web_component_name_account`(`name`, `account`) USING BTREE,
  INDEX `idx_web_component_name_string`(`name`, `string`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1395 CHARACTER SET = utf8 COLLATE = utf8_unicode_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of web_component
-- ----------------------------

-- ----------------------------
-- Table structure for web_component_link
-- ----------------------------
DROP TABLE IF EXISTS `web_component_link`;
CREATE TABLE `web_component_link`  (
  `domain` int(11) NOT NULL,
  `web_component` int(11) NOT NULL,
  PRIMARY KEY (`domain`, `web_component`) USING BTREE,
  INDEX `idx_web_component_link`(`web_component`) USING BTREE,
  CONSTRAINT `fk_web_component_link__domain` FOREIGN KEY (`domain`) REFERENCES `domain` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_web_component_link__web_component` FOREIGN KEY (`web_component`) REFERENCES `web_component` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = latin1 COLLATE = latin1_swedish_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of web_component_link
-- ----------------------------

SET FOREIGN_KEY_CHECKS = 1;
