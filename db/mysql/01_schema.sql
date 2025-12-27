-- NOTE: This script is for demo/scaffold; adjust constraints/indexes as needed.
SET NAMES utf8mb4;
SET time_zone = '+00:00';
SET GLOBAL log_bin_trust_function_creators = 1;

-- Core sync tables
CREATE TABLE IF NOT EXISTS change_log (
  change_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  table_name VARCHAR(64) NOT NULL,
  pk_value VARCHAR(64) NOT NULL,
  op_type CHAR(1) NOT NULL,
  row_data TEXT NOT NULL,
  source_db VARCHAR(16) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  processed TINYINT NOT NULL DEFAULT 0,
  processed_at DATETIME NULL,
  error TEXT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS conflicts (
  conflict_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  table_name VARCHAR(64) NOT NULL,
  pk_value VARCHAR(64) NOT NULL,
  source_db VARCHAR(16) NOT NULL,
  target_db VARCHAR(16) NOT NULL,
  source_row_data TEXT NOT NULL,
  target_row_data TEXT NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at DATETIME NULL,
  resolved_by VARCHAR(64) NULL,
  winner_db VARCHAR(16) NULL
) ENGINE=InnoDB;

-- Business tables
CREATE TABLE IF NOT EXISTS users (
  user_id VARCHAR(36) PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'normal',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'MYSQL',
  row_version INT NOT NULL DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS customers (
  customer_id VARCHAR(36) PRIMARY KEY,
  customer_name VARCHAR(100) NOT NULL,
  email VARCHAR(100),
  phone VARCHAR(20),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'MYSQL',
  row_version INT NOT NULL DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS products (
  product_id VARCHAR(36) PRIMARY KEY,
  product_name VARCHAR(128) NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  stock INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'MYSQL',
  row_version INT NOT NULL DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS orders (
  order_id VARCHAR(36) PRIMARY KEY,
  customer_id VARCHAR(36) NOT NULL,
  order_date DATETIME NOT NULL,
  total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'CREATED',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'MYSQL',
  row_version INT NOT NULL DEFAULT 1,
  CONSTRAINT fk_orders_customer FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS order_items (
  item_id VARCHAR(36) PRIMARY KEY,
  order_id VARCHAR(36) NOT NULL,
  product_id VARCHAR(36) NOT NULL,
  quantity INT NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'MYSQL',
  row_version INT NOT NULL DEFAULT 1,
  CONSTRAINT fk_oi_order FOREIGN KEY(order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_oi_product FOREIGN KEY(product_id) REFERENCES products(product_id)
) ENGINE=InnoDB;

-- Helpful indexes
SET @idx := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='orders' AND index_name='idx_orders_customer');
SET @sql := IF(@idx=0, 'CREATE INDEX idx_orders_customer ON orders(customer_id);', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='order_items' AND index_name='idx_oi_order');
SET @sql := IF(@idx=0, 'CREATE INDEX idx_oi_order ON order_items(order_id);', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='order_items' AND index_name='idx_oi_product');
SET @sql := IF(@idx=0, 'CREATE INDEX idx_oi_product ON order_items(product_id);', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------- Triggers ----------
DELIMITER $$

CREATE TRIGGER trg_users_bi BEFORE INSERT ON users
FOR EACH ROW
BEGIN
  SET NEW.created_at = IFNULL(NEW.created_at, UTC_TIMESTAMP());
  SET NEW.updated_at = IFNULL(NEW.updated_at, UTC_TIMESTAMP());
  SET NEW.updated_by_db = IFNULL(NEW.updated_by_db, 'MYSQL');
  SET NEW.row_version = IFNULL(NEW.row_version, 1);
END$$

CREATE TRIGGER trg_users_bu BEFORE UPDATE ON users
FOR EACH ROW
BEGIN
  SET NEW.updated_at = UTC_TIMESTAMP();
  IF NEW.updated_by_db = 'MYSQL' THEN
    SET NEW.row_version = OLD.row_version + 1;
  END IF;
END$$

CREATE TRIGGER trg_users_ai AFTER INSERT ON users
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('users', NEW.user_id, 'I',
      CAST(JSON_OBJECT('user_id',NEW.user_id,'username',NEW.username,'password_hash',NEW.password_hash,'role',NEW.role,
        'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

CREATE TRIGGER trg_users_au AFTER UPDATE ON users
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('users', NEW.user_id, 'U',
      CAST(JSON_OBJECT('user_id',NEW.user_id,'username',NEW.username,'password_hash',NEW.password_hash,'role',NEW.role,
        'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

CREATE TRIGGER trg_customers_bi BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
  SET NEW.created_at = IFNULL(NEW.created_at, UTC_TIMESTAMP());
  SET NEW.updated_at = IFNULL(NEW.updated_at, UTC_TIMESTAMP());
  SET NEW.updated_by_db = IFNULL(NEW.updated_by_db, 'MYSQL');
  SET NEW.row_version = IFNULL(NEW.row_version, 1);
END$$

CREATE TRIGGER trg_customers_bu BEFORE UPDATE ON customers
FOR EACH ROW
BEGIN
  SET NEW.updated_at = UTC_TIMESTAMP();
  IF NEW.updated_by_db = 'MYSQL' THEN
    SET NEW.row_version = OLD.row_version + 1;
  END IF;
END$$

CREATE TRIGGER trg_customers_ai AFTER INSERT ON customers
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('customers', NEW.customer_id, 'I',
      CAST(JSON_OBJECT('customer_id',NEW.customer_id,'customer_name',NEW.customer_name,'email',NEW.email,'phone',NEW.phone,
        'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

CREATE TRIGGER trg_customers_au AFTER UPDATE ON customers
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('customers', NEW.customer_id, 'U',
      CAST(JSON_OBJECT('customer_id',NEW.customer_id,'customer_name',NEW.customer_name,'email',NEW.email,'phone',NEW.phone,
        'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

CREATE TRIGGER trg_products_bi BEFORE INSERT ON products
FOR EACH ROW
BEGIN
  SET NEW.created_at = IFNULL(NEW.created_at, UTC_TIMESTAMP());
  SET NEW.updated_at = IFNULL(NEW.updated_at, UTC_TIMESTAMP());
  SET NEW.updated_by_db = IFNULL(NEW.updated_by_db, 'MYSQL');
  SET NEW.row_version = IFNULL(NEW.row_version, 1);
END$$

CREATE TRIGGER trg_products_bu BEFORE UPDATE ON products
FOR EACH ROW
BEGIN
  SET NEW.updated_at = UTC_TIMESTAMP();
  IF NEW.updated_by_db = 'MYSQL' THEN
    SET NEW.row_version = OLD.row_version + 1;
  END IF;
END$$

CREATE TRIGGER trg_products_ai AFTER INSERT ON products
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('products', NEW.product_id, 'I',
      CAST(JSON_OBJECT('product_id',NEW.product_id,'product_name',NEW.product_name,'price',NEW.price,'stock',NEW.stock,
        'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

CREATE TRIGGER trg_products_au AFTER UPDATE ON products
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('products', NEW.product_id, 'U',
      CAST(JSON_OBJECT('product_id',NEW.product_id,'product_name',NEW.product_name,'price',NEW.price,'stock',NEW.stock,
        'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

CREATE TRIGGER trg_orders_bi BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
  SET NEW.created_at = IFNULL(NEW.created_at, UTC_TIMESTAMP());
  SET NEW.updated_at = IFNULL(NEW.updated_at, UTC_TIMESTAMP());
  SET NEW.updated_by_db = IFNULL(NEW.updated_by_db, 'MYSQL');
  SET NEW.row_version = IFNULL(NEW.row_version, 1);
END$$

CREATE TRIGGER trg_orders_bu BEFORE UPDATE ON orders
FOR EACH ROW
BEGIN
  SET NEW.updated_at = UTC_TIMESTAMP();
  IF NEW.updated_by_db = 'MYSQL' THEN
    SET NEW.row_version = OLD.row_version + 1;
  END IF;
END$$

CREATE TRIGGER trg_orders_ai AFTER INSERT ON orders
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('orders', NEW.order_id, 'I',
      CAST(JSON_OBJECT('order_id',NEW.order_id,'customer_id',NEW.customer_id,'order_date',NEW.order_date,'total_amount',NEW.total_amount,
        'status',NEW.status,'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

CREATE TRIGGER trg_orders_au AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('orders', NEW.order_id, 'U',
      CAST(JSON_OBJECT('order_id',NEW.order_id,'customer_id',NEW.customer_id,'order_date',NEW.order_date,'total_amount',NEW.total_amount,
        'status',NEW.status,'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

CREATE TRIGGER trg_order_items_bi BEFORE INSERT ON order_items
FOR EACH ROW
BEGIN
  SET NEW.created_at = IFNULL(NEW.created_at, UTC_TIMESTAMP());
  SET NEW.updated_at = IFNULL(NEW.updated_at, UTC_TIMESTAMP());
  SET NEW.updated_by_db = IFNULL(NEW.updated_by_db, 'MYSQL');
  SET NEW.row_version = IFNULL(NEW.row_version, 1);
END$$

CREATE TRIGGER trg_order_items_bu BEFORE UPDATE ON order_items
FOR EACH ROW
BEGIN
  SET NEW.updated_at = UTC_TIMESTAMP();
  IF NEW.updated_by_db = 'MYSQL' THEN
    SET NEW.row_version = OLD.row_version + 1;
  END IF;
END$$

CREATE TRIGGER trg_order_items_ai AFTER INSERT ON order_items
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('order_items', NEW.item_id, 'I',
      CAST(JSON_OBJECT('item_id',NEW.item_id,'order_id',NEW.order_id,'product_id',NEW.product_id,'quantity',NEW.quantity,'price',NEW.price,
        'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

CREATE TRIGGER trg_order_items_au AFTER UPDATE ON order_items
FOR EACH ROW
BEGIN
  IF NEW.updated_by_db = 'MYSQL' THEN
    INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
    VALUES ('order_items', NEW.item_id, 'U',
      CAST(JSON_OBJECT('item_id',NEW.item_id,'order_id',NEW.order_id,'product_id',NEW.product_id,'quantity',NEW.quantity,'price',NEW.price,
        'created_at',NEW.created_at,'updated_at',NEW.updated_at,'updated_by_db',NEW.updated_by_db,'row_version',NEW.row_version) AS CHAR),
      'mysql'
    );
  END IF;
END$$

DELIMITER ;
