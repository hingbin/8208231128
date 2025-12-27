# 手动验证用例（2025-12-21）

覆盖容器启动、触发器同步、冲突检测、邮件发送与冲突修复。

## 0. 准备
- 复制环境：`cp .env.example .env`（如已存在可跳过），确认 SMTP 指向 MailHog 或真实邮箱。
- 启动：`docker compose up -d --build`
- 打开入口：
  - Swagger: http://localhost:18000/docs
  - MailHog: http://localhost:8025
  - CloudBeaver: http://localhost:8978

## 1. 数据与触发器检查
1. CloudBeaver 连接三库（MySQL 13306/app/app_pw，PostgreSQL 15432/app/app_pw，SQL Server 14333/sa/YourStrong!Passw0rd）。
2. 分别运行 `db/mysql|postgres|mssql/01_schema.sql` 验证表/触发器存在（默认容器启动已自动执行，只需浏览确认）。
3. 在任意库运行 `SELECT table_name, trigger_schema FROM information_schema.triggers WHERE table_schema IN ('syncdb','dbo','public');` 确认五张业务表均有插入/更新触发器。

## 2. 导入样例数据
1. 在 CloudBeaver 选择目标库，执行根目录 `database_table` 脚本（已修正表名/中文）。
2. 观察 worker 日志：`docker compose logs -f worker` 应看到同步处理记录。
3. 用 CloudBeaver 查看其余两库对应表，数据应保持一致。

## 3. 同步回环验证
1. 在 MySQL 执行：  
   ```sql
   UPDATE products SET stock = stock - 1, updated_by_db='MYSQL' WHERE product_id='201';
   ```
2. 观察 worker 日志应出现变更，PostgreSQL / SQL Server `products` 对应行 stock 同步减少，`change_log.processed` 置 1。

## 4. 冲突制造与检测
1. 在 PostgreSQL 执行：  
   ```sql
   UPDATE orders SET status='PAID', row_version=row_version+1, updated_by_db='POSTGRES' WHERE order_id='301';
   ```
2. 在 MySQL 立即执行：  
   ```sql
   UPDATE orders SET status='CANCELLED', row_version=row_version+1, updated_by_db='MYSQL' WHERE order_id='301';
   ```
3. worker 处理 MySQL 变更到 PostgreSQL 时，因目标 `row_version` 更高且 `updated_by_db` 不同，会写入 `conflicts`。  
   在控制库（默认 Postgres）查询：`SELECT * FROM conflicts ORDER BY conflict_id DESC LIMIT 1;` 看到新冲突记录。

## 5. 邮件链路
1. 冲突生成后，在 MailHog Web UI 收到主题类似 “出错的内容 - 冲突 #<id>” 的邮件。
2. 打开邮件中的链接（形如 `http://localhost:18000/ui/conflicts/<id>?t=...`），应能直接查看冲突详情（无需登录，token 24h 内有效）。

## 6. 冲突修复
1. 登录前端 `/ui/login`（admin/admin123），进入 “冲突中心”，点击刚才的冲突。
2. 选择胜出库（如 PostgreSQL），点击“应用”。后台会对三库执行 upsert 并标记 `conflicts.status='RESOLVED'`。
3. 收件箱会收到“冲突解除通知”邮件，链接至冲突详情。
4. 在三库分别查询订单 `301`，状态应一致（取胜出库数据），`row_version` 与 `updated_by_db` 也一致。

## 7. 清理与回归
- 如需复测：删除三库数据或重建容器卷后重复步骤 2-6。
- 确认无遗留 OPEN 状态冲突：`SELECT COUNT(*) FROM conflicts WHERE status='OPEN';` 应为 0。
   docker compose stop backend worker
  docker compose down -v mysql   # 或直接删除 mysql_data 卷
  docker compose up -d mysql
  docker compose up -d backend worker