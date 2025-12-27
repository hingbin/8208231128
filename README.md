<<<<<<< HEAD
# 计科2307张鸿斌



## Getting started

To make it easy for you to get started with GitLab, here's a list of recommended next steps.

Already a pro? Just edit this README.md and make it your own. Want to make it easy? [Use the template at the bottom](#editing-this-readme)!

## Add your files

- [ ] [Create](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#create-a-file) or [upload](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#upload-a-file) files
- [ ] [Add files using the command line](https://docs.gitlab.com/ee/gitlab-basics/add-file.html#add-a-file-using-the-command-line) or push an existing Git repository with the following command:

```
cd existing_repo
git remote add origin http://vlab.csu.edu.cn/gitlab/8208231128/2307.git
git branch -M main
git push -uf origin main
```

## Integrate with your tools

- [ ] [Set up project integrations](http://192.168.1.99:3379/gitlab/8208231128/2307/-/settings/integrations)

## Collaborate with your team

- [ ] [Invite team members and collaborators](https://docs.gitlab.com/ee/user/project/members/)
- [ ] [Create a new merge request](https://docs.gitlab.com/ee/user/project/merge_requests/creating_merge_requests.html)
- [ ] [Automatically close issues from merge requests](https://docs.gitlab.com/ee/user/project/issues/managing_issues.html#closing-issues-automatically)
- [ ] [Enable merge request approvals](https://docs.gitlab.com/ee/user/project/merge_requests/approvals/)
- [ ] [Set auto-merge](https://docs.gitlab.com/ee/user/project/merge_requests/merge_when_pipeline_succeeds.html)

## Test and Deploy

Use the built-in continuous integration in GitLab.

- [ ] [Get started with GitLab CI/CD](https://docs.gitlab.com/ee/ci/quick_start/index.html)
- [ ] [Analyze your code for known vulnerabilities with Static Application Security Testing (SAST)](https://docs.gitlab.com/ee/user/application_security/sast/)
- [ ] [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/ee/topics/autodevops/requirements.html)
- [ ] [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/ee/user/clusters/agent/)
- [ ] [Set up protected environments](https://docs.gitlab.com/ee/ci/environments/protected_environments.html)

***

# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thanks to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README

Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name
Choose a self-explaining name for your project.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Badges
On some READMEs, you may see small images that convey metadata, such as whether or not all the tests are passing for the project. You can use Shields to add some to your README. Many services also have instructions for adding a badge.

## Visuals
Depending on what you are making, it can be a good idea to include screenshots or even a video (you'll frequently see GIFs rather than actual videos). Tools like ttygif can help, but check out Asciinema for a more sophisticated method.

## Installation
Within a particular ecosystem, there may be a common way of installing things, such as using Yarn, NuGet, or Homebrew. However, consider the possibility that whoever is reading your README is a novice and would like more guidance. Listing specific steps helps remove ambiguity and gets people to using your project as quickly as possible. If it only runs in a specific context like a particular programming language version or operating system or has dependencies that have to be installed manually, also add a Requirements subsection.

## Usage
Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.

## Support
Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address, etc.

## Roadmap
If you have ideas for releases in the future, it is a good idea to list them in the README.

## Contributing
State if you are open to contributions and what your requirements are for accepting them.

For people who want to make changes to your project, it's helpful to have some documentation on how to get started. Perhaps there is a script that they should run or some environment variables that they need to set. Make these steps explicit. These instructions could also be useful to your future self.

You can also document commands to lint the code or run tests. These steps help to ensure high code quality and reduce the likelihood that the changes inadvertently break something. Having instructions for running tests is especially helpful if it requires external setup, such as starting a Selenium server for testing in a browser.

## Authors and acknowledgment
Show your appreciation to those who have contributed to the project.

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
=======
# 多数据库同步实验平台（PyCharm 版）

一键拉起 MySQL / PostgreSQL / SQL Server、同步后台、冲突处理 UI、MailHog 以及 CloudBeaver，可快速验证三库间的触发器同步、冲突检测与邮件告警链路。

## 快速开始
- 复制环境变量：`cp .env.example .env`（或直接使用根目录 `.env` 已填默认值）。
- 启动容器：`docker compose up -d --build`  
  服务暴露端口：后台 18000、MySQL 13306、PostgreSQL 15432、SQL Server 14333、MailHog 8025、CloudBeaver 8978。
- 访问入口：
  - Swagger 文档：`http://localhost:18000/docs`
  - Web 登录/注册：`http://localhost:18000/ui/login`（默认管理员 `admin / admin123`，注册码 `aaa`）
  - 冲突中心：`http://localhost:18000/ui/conflicts`
  - MailHog：`http://localhost:8025`
  - CloudBeaver：`http://localhost:8978`（可直接运行 `database_table` 脚本导入样例数据）

## 同步与冲突逻辑
- 表范围：`users / customers / products / orders / order_items`，三库表结构保持一致（见 `db/mysql|postgres|mssql/01_schema.sql`）。
- 触发器：各库 INSERT/UPDATE 时，若 `updated_by_db` 为本库标识，则写入 `change_log`，并在本库自增 `row_version`。来自其他库的写入会带着源库标识，因而不会产生回环日志。
- worker：轮询每库 `change_log`，将变更应用到其他两库。若目标库 `row_version` 更高且 `updated_by_db` 不同，则记录到 `conflicts` 并发邮件。
- 冲突处理：管理端可在 UI 或接口 `/conflicts/{id}/resolve` 选择胜出库，也可用 `/resolve/custom` 直接提交 JSON，后台会统一落盘到三库并标记冲突已解决。

## 邮件告警
- `services/emailer.py` 先尝试 Resend（使用 `.env` 中 `RESEND_API_KEY`），失败则调用根目录 `send_email.py`，最后回落 SMTP（默认 MailHog）。
- 邮件正文附带带签名的 24h 链接，形如 `http://localhost:18000/ui/conflicts/{id}?t=...`，可直接跳到冲突详情。

## 开发/调试
- 只跑本地代码：`cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`；另开终端运行 `python -m app.sync.worker`。
- 切换控制库：修改 `.env` 中 `CONTROL_DB=postgres|mysql|mssql`，重启 backend/worker。

## 脚本与数据
- `database_table`：可在 CloudBeaver 一次性执行，插入一套基础演示数据（已修正表名、字段及中文字符）。
- `db/*/01_schema.sql`：包含建表、索引、触发器与行版本策略；SQL Server 由 `db/mssql/init.sh` 自动执行。

## 已知限制
- 目前未同步 DELETE 操作；如需可在触发器与 `replicator.py` 中补充。
- 冲突判定基于 `row_version`；若不同库同时写入且版本号相同，将按最后到达者覆盖，不会生成冲突记录。
>>>>>>> 62309b3 (upload project)
