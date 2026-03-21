# Omni-InfoFlow 自动化信息处理引擎

Omni-InfoFlow 是一个“输入源任意、处理链条自选、输出端灵活”的自动化工作流系统。通过高度解耦的插件化架构，用户可以像拼图一样自由组合信息源、内容处理器、AI 总结引擎和多媒体分发渠道。

## 🌟 核心特性 (Features)

- **极度解耦的插件生态**：支持 Source（抓取）、Parser（解析清洗）、AI（智能处理）、Media（多媒体派生）、Dispatcher（分发）五大标准插槽。
- **现代化 WebUI 控制台**：Vue 3 + Vite 构建的实时监控与配置面板，支持自动探测插件、基于 Schema 的动态表单，以及 SSE 实时日志推流。
- **三重指纹去重墙**：SQLite 持久化保障（URL 哈希、内容哈希、外部 ID），确保不推送重复信息。
- **强大的调度层 (Pipeline Engine)**：支持指数退避重试 (Exponential Backoff)、异步并发控制 (Semaphore)、容错继续 (Continue on error) 与可选节点链路。
- **开箱即用的插件矩阵**：
  - **Source**: 🔄 RSS 订阅解析、🔥 Bilibili 热门榜单
  - **Parser**: 🧹 HTML 正文提取 (Readability 兜底)
  - **AI**: 🧠 OpenAI 兼容的大模型长文本分块摘要 (带 `soul.md` 人格注入)
  - **Media**: 🗣️ Edge-TTS 免费微软语音合成
  - **Dispatcher**: ✈️ Telegram 长图文/音频推送、🔔 飞书/Lark 卡片推送、📝 Markdown 本地存档

## 📂 架构与目录说明 (Directory Structure)

```text
Omni-InfoFlow/
├── backend/                  # FastAPI 核心处理后端
│   ├── app/
│   │   ├── api/routes.py     # REST API & SSE Endpoint
│   │   ├── core/             # 引擎大脑：配置、去重数据库、执行器、事件总线
│   │   ├── models/           # 核心数据协议与契约 (Pydantic)
│   │   └── plugins/          # 业务插件库 (核心解耦层)
│   ├── data/                 # SQLite 库、日志、全局配置及导出成果
│   └── tests/                # 集成用例与单元测试套件
├── frontend/                 # Vue 3 SPA 控制面板 (Vite)
│   ├── src/views/            # Setup (全局配置), Dashboard (监控大屏), Plugins (插件集市)
│   └── package.json
├── docker-compose.yml        # 一键容器化编排文件
└── Dockerfile                # 多阶段构建文件 (NodeUI -> PythonServer)
```

## 🚀 启动与部署 (Deployment)

### 选项 A：使用 Docker 一键部署 (推荐)

此方法适合部署到 NAS 或云服务器，全自动包含前后端，守护态运行。

1. **配置环境变量**  
   复制 `.env.example` 为 `.env` 并填入必要信息，例如 `OPENAI_API_KEY` 和 `TELEGRAM_BOT_TOKEN`。
   ```bash
   cp backend/.env.example .env
   # 编辑 .env 文件
   ```

2. **一键启动**
   ```bash
   docker-compose up -d --build
   ```

3. **访问界面**  
   容器成功运行后，打开浏览器访问 `http://localhost:8000/` 或 `http://IP:8000/`。

### 选项 B：本地流式开发启动 (Dev Mode)

如果你想二次修改代码：

1. **后端启动**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env
   uvicorn app.main:app --reload --port 8000
   ```

2. **前端启动**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   然后访问 `http://localhost:5173`。

## ⚙️ 管理与使用指南 (Usage Guide)

1. **进入 Setup 面板**  
   在这里定义你的 **Workflow Policy（工作流策略）**：设置处理步骤（比如 `source, parser, ai, media, dispatch`），定义哪些是可选步骤，配置重试次数限制和长驻的 Cron 定时任务时间窗。
   在这里还可以编辑 `soul.md` 来设定 AI 的专属人格（System Prompt）。

2. **进入 Plugins 市场**  
   所有放入 `backend/app/plugins/` 目录的合规插件都会在此自定发现。
   * 点击 **启用** 开始使用该插件。
   * 填写各个插件生成的独特定制表单（如 RSS 的 Feed 订阅链接列表，AI 的模型名等）。

3. **查看 Dashboard 大盘**  
   点击“触发工作流”按钮或等待定时任务启动。  
   开启“实时推送(SSE)”开关，即可肉眼看到系统如何在你的四大件插件中流转运作。遇到错误将会高亮染色并在底座触发重试补偿调度。

## 💡 如何编写自己的插件？

只需继承 `app/plugins/base.py` 里的基类，定义好 `manifest` 的元数据和 `config_schema` 数据约束，实现对应的 `run()` 或 `fetch()` 函数即可。控制台界面会 **完全无感自反射** 出配置项表单供你操作！
