-- NOTE: This script is for demo/scaffold; adjust constraints/indexes as needed.
DO $$ BEGIN
  PERFORM set_config('TimeZone', 'UTC', true);
END $$;

-- Core sync tables
CREATE TABLE IF NOT EXISTS change_log (
  change_id BIGSERIAL PRIMARY KEY,
  table_name VARCHAR(64) NOT NULL,
  pk_value VARCHAR(64) NOT NULL,
  op_type CHAR(1) NOT NULL,
  row_data TEXT NOT NULL,
  source_db VARCHAR(16) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  processed SMALLINT NOT NULL DEFAULT 0,
  processed_at TIMESTAMPTZ NULL,
  error TEXT NULL
);

CREATE TABLE IF NOT EXISTS conflicts (
  conflict_id BIGSERIAL PRIMARY KEY,
  table_name VARCHAR(64) NOT NULL,
  pk_value VARCHAR(64) NOT NULL,
  source_db VARCHAR(16) NOT NULL,
  target_db VARCHAR(16) NOT NULL,
  source_row_data TEXT NOT NULL,
  target_row_data TEXT NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
  created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  resolved_at TIMESTAMPTZ NULL,
  resolved_by VARCHAR(64) NULL,
  winner_db VARCHAR(16) NULL
);

-- Business tables
CREATE TABLE IF NOT EXISTS users (
  user_id VARCHAR(36) PRIMARY KEY,
  username VARCHAR(64) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'normal',
  created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'POSTGRES',
  row_version INT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS customers (
  customer_id VARCHAR(36) PRIMARY KEY,
  customer_name VARCHAR(100) NOT NULL,
  email VARCHAR(100),
  phone VARCHAR(20),
  created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'POSTGRES',
  row_version INT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products (
  product_id VARCHAR(36) PRIMARY KEY,
  product_name VARCHAR(128) NOT NULL,
  price NUMERIC(10,2) NOT NULL,
  stock INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'POSTGRES',
  row_version INT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
  order_id VARCHAR(36) PRIMARY KEY,
  customer_id VARCHAR(36) NOT NULL REFERENCES customers(customer_id),
  order_date TIMESTAMPTZ NOT NULL,
  total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'CREATED',
  created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'POSTGRES',
  row_version INT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS order_items (
  item_id VARCHAR(36) PRIMARY KEY,
  order_id VARCHAR(36) NOT NULL REFERENCES orders(order_id),
  product_id VARCHAR(36) NOT NULL REFERENCES products(product_id),
  quantity INT NOT NULL,
  price NUMERIC(10,2) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_by_db VARCHAR(16) NOT NULL DEFAULT 'POSTGRES',
  row_version INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_oi_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_oi_product ON order_items(product_id);

-- ---------- Triggers ----------
CREATE OR REPLACE FUNCTION trg_bump_version() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = (NOW() AT TIME ZONE 'UTC');
  IF NEW.updated_by_db = 'POSTGRES' THEN
    NEW.row_version = OLD.row_version + 1;
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_default_meta() RETURNS trigger AS $$
BEGIN
  NEW.created_at := COALESCE(NEW.created_at, NOW() AT TIME ZONE 'UTC');
  NEW.updated_at := COALESCE(NEW.updated_at, NOW() AT TIME ZONE 'UTC');
  NEW.updated_by_db := COALESCE(NEW.updated_by_db, 'POSTGRES');
  NEW.row_version := COALESCE(NEW.row_version, 1);
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_log(table_name text, pk_value text, op_type char, payload json) RETURNS VOID AS $$
BEGIN
  INSERT INTO change_log(table_name, pk_value, op_type, row_data, source_db)
  VALUES (table_name, pk_value, op_type, payload::text, 'postgres');
END; $$ LANGUAGE plpgsql SECURITY DEFINER;

-- Users
DROP TRIGGER IF EXISTS trg_users_bi ON users;
CREATE TRIGGER trg_users_bi BEFORE INSERT ON users
FOR EACH ROW EXECUTE FUNCTION trg_default_meta();

DROP TRIGGER IF EXISTS trg_users_bu ON users;
CREATE TRIGGER trg_users_bu BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION trg_bump_version();

CREATE OR REPLACE FUNCTION trg_log_users() RETURNS trigger AS $$
BEGIN
  IF NEW.updated_by_db = 'POSTGRES' THEN
    PERFORM trg_log('users', NEW.user_id, TG_OP::char(1), json_build_object(
      'user_id', NEW.user_id, 'username', NEW.username, 'password_hash', NEW.password_hash, 'role', NEW.role,
      'created_at', NEW.created_at, 'updated_at', NEW.updated_at, 'updated_by_db', NEW.updated_by_db, 'row_version', NEW.row_version
    ));
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_ai ON users;
CREATE TRIGGER trg_users_ai AFTER INSERT OR UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION trg_log_users();

-- Customers
DROP TRIGGER IF EXISTS trg_customers_bi ON customers;
CREATE TRIGGER trg_customers_bi BEFORE INSERT ON customers
FOR EACH ROW EXECUTE FUNCTION trg_default_meta();

DROP TRIGGER IF EXISTS trg_customers_bu ON customers;
CREATE TRIGGER trg_customers_bu BEFORE UPDATE ON customers
FOR EACH ROW EXECUTE FUNCTION trg_bump_version();

CREATE OR REPLACE FUNCTION trg_log_customers() RETURNS trigger AS $$
BEGIN
  IF NEW.updated_by_db = 'POSTGRES' THEN
    PERFORM trg_log('customers', NEW.customer_id, TG_OP::char(1), json_build_object(
      'customer_id', NEW.customer_id, 'customer_name', NEW.customer_name, 'email', NEW.email, 'phone', NEW.phone,
      'created_at', NEW.created_at, 'updated_at', NEW.updated_at, 'updated_by_db', NEW.updated_by_db, 'row_version', NEW.row_version
    ));
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_customers_ai ON customers;
CREATE TRIGGER trg_customers_ai AFTER INSERT OR UPDATE ON customers
FOR EACH ROW EXECUTE FUNCTION trg_log_customers();

-- Products
DROP TRIGGER IF EXISTS trg_products_bi ON products;
CREATE TRIGGER trg_products_bi BEFORE INSERT ON products
FOR EACH ROW EXECUTE FUNCTION trg_default_meta();

DROP TRIGGER IF EXISTS trg_products_bu ON products;
CREATE TRIGGER trg_products_bu BEFORE UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION trg_bump_version();

CREATE OR REPLACE FUNCTION trg_log_products() RETURNS trigger AS $$
BEGIN
  IF NEW.updated_by_db = 'POSTGRES' THEN
    PERFORM trg_log('products', NEW.product_id, TG_OP::char(1), json_build_object(
      'product_id', NEW.product_id, 'product_name', NEW.product_name, 'price', NEW.price, 'stock', NEW.stock,
      'created_at', NEW.created_at, 'updated_at', NEW.updated_at, 'updated_by_db', NEW.updated_by_db, 'row_version', NEW.row_version
    ));
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_products_ai ON products;
CREATE TRIGGER trg_products_ai AFTER INSERT OR UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION trg_log_products();

-- Orders
DROP TRIGGER IF EXISTS trg_orders_bi ON orders;
CREATE TRIGGER trg_orders_bi BEFORE INSERT ON orders
FOR EACH ROW EXECUTE FUNCTION trg_default_meta();

DROP TRIGGER IF EXISTS trg_orders_bu ON orders;
CREATE TRIGGER trg_orders_bu BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION trg_bump_version();

CREATE OR REPLACE FUNCTION trg_log_orders() RETURNS trigger AS $$
BEGIN
  IF NEW.updated_by_db = 'POSTGRES' THEN
    PERFORM trg_log('orders', NEW.order_id, TG_OP::char(1), json_build_object(
      'order_id', NEW.order_id, 'customer_id', NEW.customer_id, 'order_date', NEW.order_date,
      'total_amount', NEW.total_amount, 'status', NEW.status,
      'created_at', NEW.created_at, 'updated_at', NEW.updated_at, 'updated_by_db', NEW.updated_by_db, 'row_version', NEW.row_version
    ));
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_orders_ai ON orders;
CREATE TRIGGER trg_orders_ai AFTER INSERT OR UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION trg_log_orders();

-- Order items
DROP TRIGGER IF EXISTS trg_order_items_bi ON order_items;
CREATE TRIGGER trg_order_items_bi BEFORE INSERT ON order_items
FOR EACH ROW EXECUTE FUNCTION trg_default_meta();

DROP TRIGGER IF EXISTS trg_order_items_bu ON order_items;
CREATE TRIGGER trg_order_items_bu BEFORE UPDATE ON order_items
FOR EACH ROW EXECUTE FUNCTION trg_bump_version();

CREATE OR REPLACE FUNCTION trg_log_order_items() RETURNS trigger AS $$
BEGIN
  IF NEW.updated_by_db = 'POSTGRES' THEN
    PERFORM trg_log('order_items', NEW.item_id, TG_OP::char(1), json_build_object(
      'item_id', NEW.item_id, 'order_id', NEW.order_id, 'product_id', NEW.product_id,
      'quantity', NEW.quantity, 'price', NEW.price,
      'created_at', NEW.created_at, 'updated_at', NEW.updated_at,
      'updated_by_db', NEW.updated_by_db, 'row_version', NEW.row_version
    ));
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_order_items_ai ON order_items;
CREATE TRIGGER trg_order_items_ai AFTER INSERT OR UPDATE ON order_items
FOR EACH ROW EXECUTE FUNCTION trg_log_order_items();

