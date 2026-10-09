# THIRD-PARTY NOTICES（第三方依赖声明）

本项目为 Apache-2.0 许可的自研软件。以下第三方库仅以**普通动态链接/运行期调用**方式使用（未修改其源码、未静态链接、未再分发其源码），各库版权归其各自作者所有，按各自许可证条款使用。

## 一、Python 运行时依赖

| 库 | 版本要求 | 许可证 | 用途 |
| --- | --- | --- | --- |
| Flask | >= 3.0 | BSD-3-Clause | Web 框架 |
| ldap3 | >= 2.9 | LGPL-3.0 | AD 域登录（LDAP 协议） |
| Pillow | >= 10.0 | HPND（MIT 兼容） | 图片压缩处理 |

### 数据库驱动（按需安装；仅 SQLite 时无需任何驱动）

| 库 | 版本要求 | 许可证 | 目标数据库 |
| --- | --- | --- | --- |
| PyMySQL | 最新 | MIT | MySQL / MariaDB |
| psycopg2-binary | 最新 | LGPL-3.0 | PostgreSQL |
| pymssql | 最新 | LGPL-2.1 | SQL Server (MS SQL) |
| python-oracledb | 最新 | Apache-2.0 / UPL-1.0 | Oracle |

> LGPL 类库（ldap3 / psycopg2 / pymssql）均为**独立进程库的动态使用**，不修改、不静态链接、不并入本项目代码，符合 LGPL 对动态链接使用的许可要求，不构成对本项目 Apache-2.0 许可的传染。

## 二、运行时（Python 解释器）

| 组件 | 许可证 |
| --- | --- |
| Python 3.12 | PSF License Agreement（与 Apache-2.0 兼容） |

## 三、前端资源

本项目前端为**纯原生 HTML / CSS / JavaScript**，图表为自绘 Canvas（`static/js/charts.js`），未使用 jQuery / ECharts / Bootstrap 等任何第三方 JS/CSS 库，无 CDN 外链、无字体文件分发。

## 四、使用方注意

- 安装依赖：`pip install -r requirements.txt`（SQLite 即用）或 `pip install -r requirements-full.txt`（需要多数据库时）。
- 若部署环境还使用了本清单之外的任何库，请在使用方环境中另行核对其许可证。
- 本清单随版本更新；如发现遗漏或版本升级，请提交 Issue 告知。
