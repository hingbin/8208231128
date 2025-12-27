-- Create syncdb if missing
IF DB_ID('syncdb') IS NULL
  CREATE DATABASE syncdb;
GO
USE syncdb;
GO

-- Core sync tables
IF OBJECT_ID('dbo.change_log','U') IS NULL
CREATE TABLE dbo.change_log(
  change_id BIGINT IDENTITY(1,1) PRIMARY KEY,
  table_name NVARCHAR(64) NOT NULL,
  pk_value NVARCHAR(64) NOT NULL,
  op_type NCHAR(1) NOT NULL,
  row_data NVARCHAR(MAX) NOT NULL,
  source_db NVARCHAR(16) NOT NULL,
  created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  processed BIT NOT NULL DEFAULT 0,
  processed_at DATETIME2 NULL,
  error NVARCHAR(MAX) NULL
);
GO

IF OBJECT_ID('dbo.conflicts','U') IS NULL
CREATE TABLE dbo.conflicts(
  conflict_id BIGINT IDENTITY(1,1) PRIMARY KEY,
  table_name NVARCHAR(64) NOT NULL,
  pk_value NVARCHAR(64) NOT NULL,
  source_db NVARCHAR(16) NOT NULL,
  target_db NVARCHAR(16) NOT NULL,
  source_row_data NVARCHAR(MAX) NOT NULL,
  target_row_data NVARCHAR(MAX) NOT NULL,
  status NVARCHAR(16) NOT NULL DEFAULT 'OPEN',
  created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  resolved_at DATETIME2 NULL,
  resolved_by NVARCHAR(64) NULL,
  winner_db NVARCHAR(16) NULL
);
GO

-- Business tables
IF OBJECT_ID('dbo.users','U') IS NULL
CREATE TABLE dbo.users(
  user_id NVARCHAR(36) NOT NULL PRIMARY KEY,
  username NVARCHAR(64) NOT NULL UNIQUE,
  password_hash NVARCHAR(255) NOT NULL,
  role NVARCHAR(20) NOT NULL DEFAULT 'normal',
  created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_by_db NVARCHAR(16) NOT NULL DEFAULT 'MSSQL',
  row_version INT NOT NULL DEFAULT 1
);
GO

IF OBJECT_ID('dbo.customers','U') IS NULL
CREATE TABLE dbo.customers(
  customer_id NVARCHAR(36) NOT NULL PRIMARY KEY,
  customer_name NVARCHAR(100) NOT NULL,
  email NVARCHAR(100) NULL,
  phone NVARCHAR(20) NULL,
  created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_by_db NVARCHAR(16) NOT NULL DEFAULT 'MSSQL',
  row_version INT NOT NULL DEFAULT 1
);
GO

IF OBJECT_ID('dbo.products','U') IS NULL
CREATE TABLE dbo.products(
  product_id NVARCHAR(36) NOT NULL PRIMARY KEY,
  product_name NVARCHAR(128) NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  stock INT NOT NULL,
  created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_by_db NVARCHAR(16) NOT NULL DEFAULT 'MSSQL',
  row_version INT NOT NULL DEFAULT 1
);
GO

IF OBJECT_ID('dbo.orders','U') IS NULL
CREATE TABLE dbo.orders(
  order_id NVARCHAR(36) NOT NULL PRIMARY KEY,
  customer_id NVARCHAR(36) NOT NULL,
  order_date DATETIME2 NOT NULL,
  total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  status NVARCHAR(32) NOT NULL DEFAULT 'CREATED',
  created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_by_db NVARCHAR(16) NOT NULL DEFAULT 'MSSQL',
  row_version INT NOT NULL DEFAULT 1,
  CONSTRAINT fk_orders_customer FOREIGN KEY(customer_id) REFERENCES dbo.customers(customer_id)
);
GO

IF OBJECT_ID('dbo.order_items','U') IS NULL
CREATE TABLE dbo.order_items(
  item_id NVARCHAR(36) NOT NULL PRIMARY KEY,
  order_id NVARCHAR(36) NOT NULL,
  product_id NVARCHAR(36) NOT NULL,
  quantity INT NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  updated_by_db NVARCHAR(16) NOT NULL DEFAULT 'MSSQL',
  row_version INT NOT NULL DEFAULT 1,
  CONSTRAINT fk_oi_order FOREIGN KEY(order_id) REFERENCES dbo.orders(order_id),
  CONSTRAINT fk_oi_prod FOREIGN KEY(product_id) REFERENCES dbo.products(product_id)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_orders_customer' AND object_id = OBJECT_ID('dbo.orders'))
  CREATE INDEX idx_orders_customer ON dbo.orders(customer_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_oi_order' AND object_id = OBJECT_ID('dbo.order_items'))
  CREATE INDEX idx_oi_order ON dbo.order_items(order_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_oi_prod' AND object_id = OBJECT_ID('dbo.order_items'))
  CREATE INDEX idx_oi_prod ON dbo.order_items(product_id);
GO

-- ---------- Triggers ----------
IF OBJECT_ID('dbo.trg_users_bu','TR') IS NOT NULL DROP TRIGGER dbo.trg_users_bu;
GO
CREATE TRIGGER dbo.trg_users_bu ON dbo.users
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  UPDATE u
  SET updated_at = SYSUTCDATETIME(),
      row_version = CASE WHEN i.updated_by_db='MSSQL' THEN u.row_version + 1 ELSE i.row_version END
  FROM dbo.users u
  JOIN inserted i ON i.user_id = u.user_id;
END
GO

IF OBJECT_ID('dbo.trg_users_log','TR') IS NOT NULL DROP TRIGGER dbo.trg_users_log;
GO
CREATE TRIGGER dbo.trg_users_log ON dbo.users
AFTER INSERT, UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  INSERT INTO dbo.change_log(table_name, pk_value, op_type, row_data, source_db)
  SELECT
    'users',
    i.user_id,
    CASE WHEN EXISTS(SELECT 1 FROM deleted d WHERE d.user_id = i.user_id) THEN 'U' ELSE 'I' END,
    (SELECT i.user_id, i.username, i.password_hash, i.role, i.created_at, i.updated_at, i.updated_by_db, i.row_version
     FOR JSON PATH, WITHOUT_ARRAY_WRAPPER),
    'mssql'
  FROM inserted i
  WHERE i.updated_by_db = 'MSSQL';
END
GO

-- Customers
IF OBJECT_ID('dbo.trg_customers_bu','TR') IS NOT NULL DROP TRIGGER dbo.trg_customers_bu;
GO
CREATE TRIGGER dbo.trg_customers_bu ON dbo.customers
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  UPDATE c
  SET updated_at = SYSUTCDATETIME(),
      row_version = CASE WHEN i.updated_by_db='MSSQL' THEN c.row_version + 1 ELSE i.row_version END
  FROM dbo.customers c
  JOIN inserted i ON i.customer_id = c.customer_id;
END
GO

IF OBJECT_ID('dbo.trg_customers_log','TR') IS NOT NULL DROP TRIGGER dbo.trg_customers_log;
GO
CREATE TRIGGER dbo.trg_customers_log ON dbo.customers
AFTER INSERT, UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  INSERT INTO dbo.change_log(table_name, pk_value, op_type, row_data, source_db)
  SELECT
    'customers',
    i.customer_id,
    CASE WHEN EXISTS(SELECT 1 FROM deleted d WHERE d.customer_id = i.customer_id) THEN 'U' ELSE 'I' END,
    (SELECT i.customer_id, i.customer_name, i.email, i.phone, i.created_at, i.updated_at, i.updated_by_db, i.row_version
     FOR JSON PATH, WITHOUT_ARRAY_WRAPPER),
    'mssql'
  FROM inserted i
  WHERE i.updated_by_db = 'MSSQL';
END
GO

-- Products
IF OBJECT_ID('dbo.trg_products_bu','TR') IS NOT NULL DROP TRIGGER dbo.trg_products_bu;
GO
CREATE TRIGGER dbo.trg_products_bu ON dbo.products
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  UPDATE p
  SET updated_at = SYSUTCDATETIME(),
      row_version = CASE WHEN i.updated_by_db='MSSQL' THEN p.row_version + 1 ELSE i.row_version END
  FROM dbo.products p
  JOIN inserted i ON i.product_id = p.product_id;
END
GO

IF OBJECT_ID('dbo.trg_products_log','TR') IS NOT NULL DROP TRIGGER dbo.trg_products_log;
GO
CREATE TRIGGER dbo.trg_products_log ON dbo.products
AFTER INSERT, UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  INSERT INTO dbo.change_log(table_name, pk_value, op_type, row_data, source_db)
  SELECT
    'products',
    i.product_id,
    CASE WHEN EXISTS(SELECT 1 FROM deleted d WHERE d.product_id = i.product_id) THEN 'U' ELSE 'I' END,
    (SELECT i.product_id, i.product_name, i.price, i.stock, i.created_at, i.updated_at, i.updated_by_db, i.row_version
     FOR JSON PATH, WITHOUT_ARRAY_WRAPPER),
    'mssql'
  FROM inserted i
  WHERE i.updated_by_db = 'MSSQL';
END
GO

-- Orders
IF OBJECT_ID('dbo.trg_orders_bu','TR') IS NOT NULL DROP TRIGGER dbo.trg_orders_bu;
GO
CREATE TRIGGER dbo.trg_orders_bu ON dbo.orders
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  UPDATE o
  SET updated_at = SYSUTCDATETIME(),
      row_version = CASE WHEN i.updated_by_db='MSSQL' THEN o.row_version + 1 ELSE i.row_version END
  FROM dbo.orders o
  JOIN inserted i ON i.order_id = o.order_id;
END
GO

IF OBJECT_ID('dbo.trg_orders_log','TR') IS NOT NULL DROP TRIGGER dbo.trg_orders_log;
GO
CREATE TRIGGER dbo.trg_orders_log ON dbo.orders
AFTER INSERT, UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  INSERT INTO dbo.change_log(table_name, pk_value, op_type, row_data, source_db)
  SELECT
    'orders',
    i.order_id,
    CASE WHEN EXISTS(SELECT 1 FROM deleted d WHERE d.order_id = i.order_id) THEN 'U' ELSE 'I' END,
    (SELECT i.order_id, i.customer_id, i.order_date, i.total_amount, i.status,
            i.created_at, i.updated_at, i.updated_by_db, i.row_version
     FOR JSON PATH, WITHOUT_ARRAY_WRAPPER),
    'mssql'
  FROM inserted i
  WHERE i.updated_by_db = 'MSSQL';
END
GO

-- Order items
IF OBJECT_ID('dbo.trg_order_items_bu','TR') IS NOT NULL DROP TRIGGER dbo.trg_order_items_bu;
GO
CREATE TRIGGER dbo.trg_order_items_bu ON dbo.order_items
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  UPDATE oi
  SET updated_at = SYSUTCDATETIME(),
      row_version = CASE WHEN i.updated_by_db='MSSQL' THEN oi.row_version + 1 ELSE i.row_version END
  FROM dbo.order_items oi
  JOIN inserted i ON i.item_id = oi.item_id;
END
GO

IF OBJECT_ID('dbo.trg_order_items_log','TR') IS NOT NULL DROP TRIGGER dbo.trg_order_items_log;
GO
CREATE TRIGGER dbo.trg_order_items_log ON dbo.order_items
AFTER INSERT, UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  INSERT INTO dbo.change_log(table_name, pk_value, op_type, row_data, source_db)
  SELECT
    'order_items',
    i.item_id,
    CASE WHEN EXISTS(SELECT 1 FROM deleted d WHERE d.item_id = i.item_id) THEN 'U' ELSE 'I' END,
    (SELECT i.item_id, i.order_id, i.product_id, i.quantity, i.price,
            i.created_at, i.updated_at, i.updated_by_db, i.row_version
     FOR JSON PATH, WITHOUT_ARRAY_WRAPPER),
    'mssql'
  FROM inserted i
  WHERE i.updated_by_db = 'MSSQL';
END
GO
