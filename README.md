# 🌀 Omni-InfoFlow

> **输入源任意 · 处理链自选 · 输出端灵活** —— 一个高度插件化、可视化的自动信息处理引擎

Omni-InfoFlow 让你像拼图一样自由组合：**信息抓取 → 内容清洗 → AI 智能摘要 → 语音合成 → 多渠道分发**，所有环节均为独立可插拔模块，通过 WebUI 一键配置、实时监控。

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🧩 **插件生态** | Source / Parser / AI / Media / Dispatcher 五大标准插槽，一个文件即一个插件 |
| 🖥️ **现代 WebUI** | Vue 3 暗色系控制台，支持实时 SSE 日志流、Schema 驱动的动态配置表单 |
| 🔁 **智能调度** | 指数退避重试 · Semaphore 并发控制 · 可选节点跳过 · 容错继续 |
| 🛡️ **三重去重** | URL 哈希 + 内容哈希 + 外部 ID，SQLite 持久化，杜绝重复推送 |
| 🐳 **Docker 一键部署** | 多阶段构建，`docker-compose up` 即可在 NAS / 云服务器上运行 |

## 📦 开箱即用的插件

| 类型 | 插件 | 功能 |
|------|------|------|
| Source | `RSSPlugin` | RSS / Atom 多源异步订阅 |
| Source | `BilibiliHotPlugin` | B 站每日热门视频榜单 |
| Parser | `HTMLCleanerPlugin` | HTML 正文智能提取 (Readability + 正则兜底) |
| AI | `LLMClientPlugin` | OpenAI 兼容 API 长文分块摘要 + `soul.md` 人格注入 |
| Media | `EdgeTTSPlugin` | 微软 Edge 免费语音合成 (MP3) |
| Dispatcher | `TelegramDispatcher` | Telegram Bot 长图文 + 音频推送 |
| Dispatcher | `LarkDispatcher` | 飞书 Webhook 交互式卡片 |
| Dispatcher | `MarkdownExportPlugin` | 本地 Markdown 文件归档 |

---

## 📂 项目结构

```
Omni-InfoFlow/
├── backend/
│   ├── app/
│   │   ├── api/routes.py          # REST + SSE + prompt 管理接口
│   │   ├── core/                  # 配置管理 · 去重数据库 · 运行时路径 · 管道引擎 · 事件总线
│   │   ├── models/workflow.py     # WorkflowItem · PluginResult · NodeEvent · RunContext
│   │   └── plugins/               # 所有业务插件（按类别分目录）
│   ├── data/
│   │   ├── config.example.json    # 打包内置配置模板
│   │   └── prompts/soul.md        # 打包内置 AI 人格提示词
│   ├── tests/                     # 46 个自动化测试
│   ├── requirements.txt
│   └── .env.example               # 环境变量模板
├── frontend/
│   ├── src/views/                 # Dashboard · Plugins · Setup 三大页面
│   └── package.json
├── data/                          # 运行时数据目录（首次启动自动创建）
├── Dockerfile                     # Node 构建 + Python 运行 多阶段镜像
├── docker-compose.yml             # 一键编排
└── README.md
```

---

## 🚀 部署与运行

### 方式一：Docker 部署（推荐用于 NAS / 服务器）

> **前提**：目标机器已安装 [Docker](https://docs.docker.com/get-docker/) 和 Docker Compose。
> 不需要安装 Python 或 Node.js。

**1. 获取代码**

```bash
git clone https://github.com/kemaral/Omni-Infoflow.git
cd Omni-Infoflow
```

**2. 配置密钥**

```bash
# 复制环境变量模板
cp backend/.env.example .env

# 编辑填入你的真实密钥
nano .env   # 或用 vim / VS Code
```

需要填写的关键变量：

| 变量 | 用途 | 必填？ |
|------|------|--------|
| `OPENAI_API_KEY` | LLM 按需摘要（支持 DeepSeek 等兼容 API） | 仅启用 AI 插件时 |
| `TELEGRAM_BOT_TOKEN` | Telegram 推送 | 仅启用 Telegram 分发时 |
| `TELEGRAM_CHAT_ID` | 目标聊天/频道 ID | 同上 |
| `LARK_WEBHOOK_URL` | 飞书群机器人 Webhook | 仅启用飞书分发时 |
| `OMNIFLOW_ADMIN_TOKEN` | 保护配置写入、手动触发工作流和人格编辑的管理口令 | 可选，公网部署建议设置 |
| `OMNIFLOW_DATA_DIR` | 运行时数据目录根路径 | 可选，Docker 默认 `/app/data` |
| `runtime.scheduler_enabled` | 是否启用内置调度器 | 通过 WebUI 配置 |

**3. 一键构建并启动**

```bash
docker-compose up -d --build
```

> 首次构建约需 2-5 分钟（下载基础镜像、安装依赖、编译前端）。后续重启秒级完成。

**4. 验证运行**

```bash
# 查看容器状态
docker-compose ps

# 查看实时日志
docker-compose logs -f --tail 50
```

**5. 访问控制台**

浏览器打开 `http://你的IP:8000`，即可看到 Omni-InfoFlow 控制台：
- `/dashboard`  — 实时监控大盘（状态、日志、最近运行记录）
- `/plugins`    — 插件市场（启用/配置插件）
- `/setup`      — 全局策略设定 / 调度配置 / Admin Token / Prompt

**6. 数据持久化说明**

```
./data/                  # 宿主机挂载目录（自动创建）
├── config.example.json  # 首次启动时自动种入的模板
├── config.json          # 通过 WebUI 保存的配置（首次启动自动生成）
├── db.sqlite            # 去重数据库
├── exports/             # Markdown 导出文件
├── media/               # TTS 生成的音频文件
└── prompts/
   └── soul.md           # AI 人格提示词（首次启动自动生成）
```

所有数据都在宿主机 `./data/` 目录中。**容器重建或升级代码后数据不会丢失。**
如果未设置 `OMNIFLOW_DATA_DIR`，本地开发默认也使用项目根目录下的 `./data/`。
当前版本已支持按 `runtime.scheduler_enabled + schedule_cron + timezone` 自动调度 workflow。

**7. 升级版本**

```bash
git pull origin main
docker-compose up -d --build
```

---

### 方式二：本地开发模式（推荐用于二次开发）

> **前提**：已安装 Python 3.11+ 和 Node.js 18+。

**1. 启动后端**

```bash
cd backend

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 复制并编辑环境变量
cp .env.example .env

# 启动 FastAPI 开发服务器（热重载）
uvicorn app.main:app --reload --port 8000
```

> 默认会在项目根目录的 `./data/` 下创建 `config.json`、`db.sqlite`、`prompts/soul.md` 等运行时文件。
> 如需自定义，可在 `.env` 或环境变量中设置 `OMNIFLOW_DATA_DIR`。
>
> 如设置了 `OMNIFLOW_ADMIN_TOKEN`，前端 Setup 页面需要先填写 Admin Token，才能保存配置、触发运行和编辑 `soul.md`。
>
> 如开启 `scheduler_enabled` 且配置了有效的 `schedule_cron` / `timezone`，服务会在运行期间自动调度 workflow。

后端启动后，API 文档自动可用：`http://localhost:8000/docs`

**2. 启动前端（另开一个终端）**

```bash
cd frontend

# 安装前端依赖
npm install

# 启动 Vite 开发服务器（热重载 + API 代理）
npm run dev
```

前端开发服务器默认运行在 `http://localhost:5173`，已自动配置 API 代理到后端的 8000 端口。

**3. 运行测试**

```bash
cd backend
python -m pytest tests/ -v
```

当前测试已覆盖：
- 核心 pipeline engine
- 配置与数据库
- 事件总线
- scheduler 的 next-run 计算

---

## 🔧 如何编写自定义插件

只需 3 步即可扩展新功能：

1. 在 `backend/app/plugins/<类别>/` 下创建一个 `.py` 文件
2. 继承 `BasePlugin`（或 `BaseSourcePlugin`），定义 `manifest` 和 `config_schema`
3. 实现 `async run()` 或 `async fetch()` 方法

控制台 Plugins 页面会**自动发现**你的插件并渲染出配置表单 —— **零前端代码改动**。

详细示例见 `backend/app/plugins/_templates/` 目录。

---

## 🔄 Git 更新指南

修改代码后，将更新同步到 GitHub：

```bash
# 查看变更文件
git status

# 添加所有变更
git add .

# 提交（附带有意义的提交信息）
git commit -m "feat: 新增xx功能 / fix: 修复xx问题"

# 推送到 GitHub
git push origin main
```

---

## 📄 License

MIT
