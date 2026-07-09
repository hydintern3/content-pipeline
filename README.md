# Content Pipeline 运营内容工作台

`content_pipeline` 是一个面向 B 端运营团队的内容生产后台，当前采用 **Flask API 后端 + Vue 3/Vite 前端** 的前后端分离结构。它支持素材录入、多平台文案生成、单篇合规检查、Excel/CSV 批量生成、图片裁切压缩归档，以及微信公众号草稿/文件导出。

## 功能概览

- 多平台文案生成：公众号、小红书、知乎、知乎 Q&A、头条、视频号。
- 账号人设 Prompt：按“商引羚航 / Jade一城探访记 / 一城探访手记 / Jade一城探访”等账号定位生成不同风格内容。
- 合规检查：支持单篇稿件卡片内检查，风险词高亮，并显示风险等级、原因和修改建议。
- 批量导入：支持 CSV/XLSX 上传，后台任务队列异步生成。
- 图片工作流：上传图片后按平台输出尺寸，自动裁切、压缩到 2MB 以内并归档。
- 发布与导出：支持导出待发布文件、创建微信公众号草稿，配置完整时可提交发布。
- 无 LLM Key 兜底：没有大模型密钥时会使用本地模板生成基础稿件，方便部署验证。

## 项目结构

```text
content_pipeline/
  app.py                    # Flask API 与生产静态文件托管
  config.example.json       # 配置模板
  requirements.txt          # Python 依赖
  pipeline/                 # 文案生成、合规、批量、图片、发布等后端模块
  frontend/                 # Vue 3 + Vite + TypeScript 运营工作台
  tests/                    # pytest 后端测试
  data/                     # 本地 SQLite、导出文件、图片产物等运行数据
```

## 环境要求

- Python 3.10 或更高版本。
- Node.js 20 或更高版本。
- Windows PowerShell、macOS Terminal 或 Linux Shell 均可。
- 可选：大模型 API Key、微信公众号 App ID/App Secret、外部素材数据库。

## 快速启动：开发环境

后端：

```powershell
cd E:\workspace\work\运营agent\content_pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.json config.json
python app.py
```

前端：

```powershell
cd E:\workspace\work\运营agent\content_pipeline\frontend
npm install
npm run dev
```

打开：

- 前端工作台：`http://127.0.0.1:5173`
- Flask API：`http://127.0.0.1:5000`

开发环境下由 Vite 提供前端页面，前端请求会访问 Flask API。后端启动后即使没有 LLM Key，也可以用模板兜底验证流程。

## 生产部署

1. 安装后端依赖：

```powershell
cd E:\workspace\work\运营agent\content_pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.json config.json
```

2. 构建前端：

```powershell
cd E:\workspace\work\运营agent\content_pipeline\frontend
npm install
npm run build
```

3. 启动 Flask：

```powershell
cd E:\workspace\work\运营agent\content_pipeline
.\.venv\Scripts\Activate.ps1
python app.py
```

构建完成后，Flask 会自动托管 `frontend/dist`，直接打开 `http://127.0.0.1:5000` 即可使用生产版工作台。

> 如果在 Windows PowerShell 中运行 `npm run build` 遇到脚本策略限制，可改用 `npm.cmd run build`。

## 配置方式

项目支持三类配置来源：

- `config.json`：服务器默认配置，适合私有化部署。
- 环境变量：适合容器、服务器或 CI 环境覆盖配置。
- 页面右上角“设置”：保存在当前浏览器本地，用于临时调试或不同运营人员使用不同模型配置。

敏感信息不会从服务器配置完整回显到前端，例如 LLM API Key、外部数据库 URL、微信公众号 App Secret。浏览器本地配置只保存在当前浏览器，换电脑或清理浏览器数据后需要重新填写。

### config.json 示例

```json
{
  "app_database_url": "sqlite:///data/pipeline.db",
  "llm": {
    "api_key": "",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini"
  },
  "database": {
    "url": ""
  },
  "publish": {
    "pending_output_dir": "data/pending"
  },
  "wechat": {
    "app_id": "",
    "app_secret": "",
    "auto_publish": false,
    "enable_mass_send": false
  },
  "scheduler": {
    "enabled": false,
    "interval_minutes": 240
  }
}
```

### 常用环境变量

```text
CONTENT_PIPELINE_CONFIG=E:\workspace\work\运营agent\content_pipeline\config.json
CONTENT_PIPELINE_ENV=.env
APP_DATABASE_URL=postgresql+psycopg://content_pipeline:replace-with-password@postgres:5432/content_pipeline
CONTENT_LLM_API_KEY=sk-...
CONTENT_LLM_BASE_URL=https://api.openai.com/v1
CONTENT_LLM_MODEL=gpt-4o-mini
DATABASE_URL=mysql+pymysql://pipeline_reader:replace-with-password@81.68.133.54:3306/shangying_mvp?charset=utf8mb4
WECHAT_APP_ID=...
WECHAT_APP_SECRET=...
WECHAT_AUTO_PUBLISH=false
WECHAT_ENABLE_MASS_SEND=false
PENDING_OUTPUT_DIR=data/pending
SCHEDULER_ENABLED=false
SCHEDULER_INTERVAL_MINUTES=240
CONTENT_LLM_TIMEOUT_SECONDS=120
CONTENT_LLM_MAX_RETRIES=1
```

如果没有设置 `DATABASE_URL`，旧版外部素材库也可以通过 `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME`、`DB_CHARSET` 组合生成连接。

## 平台说明

默认生成平台为：

- `xiaohongshu`：小红书，账号“Jade一城探访记”。
- `zhihu`：知乎长文/专栏，账号“Jade一城探访”。
- `official_account`：公众号，账号“商引羚航”。
- `toutiao`：今日头条，账号“一城探访手记”。
- `shipinhao`：视频号脚本。

可选平台：

- `zhihu_qa`：知乎 Q&A 问答式内容。该平台不会默认生成，用户在前端勾选或批量表中指定后才会生成。

批量导入支持的常见平台别名包括：`小红书`、`知乎`、`知乎问答`、`知乎Q&A`、`公众号`、`头条`、`今日头条`、`视频号`。

## 批量导入格式

支持 `.csv`、`.xlsx`、`.xlsm`。推荐表头：

```text
标题,素材正文,关键词,目标平台,图片路径
```

示例：

```csv
标题,素材正文,关键词,目标平台
上海办公室选址避坑,企业选址前需要先看通勤、租金、楼宇配套和招商政策,办公租赁;招商,小红书;知乎问答;头条
```

每行会创建一个批量任务项。任务创建后，后台线程会逐条生成，前端任务面板可以查看进度和结果。

## 图片工作流

图片处理接口会根据平台生成不同规格变体，并进行压缩归档。默认覆盖：

- 公众号/头条：横图比例。
- 小红书/视频号：竖图比例。
- 知乎：内容配图比例。

输出文件会写入 `data/image_outputs`，上传原图会写入 `data/uploads/images/YYYY-MM-DD`。

## API 摘要

### 配置

- `GET /api/config/status`：查看服务器配置是否已启用。
- `GET /api/config`：获取前端可展示的配置摘要。
- `POST /api/config`：预览配置摘要，不会写入服务器配置。

### 文案生成

- `POST /api/materials/generate`：生成单条素材的多平台稿件。
- `POST /api/materials/pull_recent`：从外部素材数据库拉取最新素材。

生成请求示例：

```json
{
  "material": {
    "title_hint": "上海办公室选址避坑",
    "raw_content": "企业选址前需要先看通勤、租金、楼宇配套和招商政策。",
    "keywords": ["办公租赁", "招商"],
    "target_platforms": ["xiaohongshu", "zhihu_qa", "toutiao"],
    "image_paths": []
  }
}
```

### 合规检查

- `POST /api/compliance/check`：检查单篇文本或文章列表。

单篇请求：

```json
{
  "text": "这是待检查的标题和正文",
  "platform": "toutiao"
}
```

返回中包含 `risk_count` 和 `risks`，前端会在文章卡片中高亮风险词。

### 批量任务

- `POST /api/materials/batch_generate`：上传 CSV/XLSX 并创建批量生成任务。
- `GET /api/batch_jobs?limit=20`：查看批量任务列表。
- `GET /api/batch_jobs/<job_id>`：查看任务详情和每行结果。

### 图片处理

- `POST /api/images/process`：上传图片并生成平台规格变体。

表单字段：

- `files`：一个或多个图片文件。
- `topic`：选题名称，用于归档命名。
- `platforms`：逗号分隔的平台列表，可选。

### 发布与导出

- `POST /api/publish`：导出文件、创建微信公众号草稿或提交发布。
- `GET /api/tasks?limit=20`：查看最近发布/导出任务。

发布请求示例：

```json
{
  "article_ids": [1, 2, 3],
  "mode": "file"
}
```

可用 `mode`：

- `file`：导出为本地待发布文件。
- `wechat_draft`：创建微信公众号草稿。
- `wechat_publish`：提交微信公众号发布。

## 运行测试

后端测试：

```powershell
cd E:\workspace\work\运营agent\content_pipeline
.\.venv\Scripts\Activate.ps1
pytest tests\test_pipeline.py -q
```

前端构建检查：

```powershell
cd E:\workspace\work\运营agent\content_pipeline\frontend
npm.cmd run build
```

如果当前工作目录权限限制导致 Vite 不能写入 `frontend/dist`，可先确认代码本身：

```powershell
node .\node_modules\vite\bin\vite.js build --configLoader runner --outDir "$env:TEMP\content-pipeline-dist"
```

## 常见问题

### 没有大模型 Key 能启动吗？

可以。系统会使用本地模板兜底生成稿件，适合部署验收和功能演示。

### 为什么开发时要开两个地址？

开发环境下，Vue 由 Vite 提供热更新页面，Flask 只提供 API。生产环境构建 `frontend/dist` 后，Flask 会统一托管前端页面和 API。

### 公众号发布失败怎么办？

先确认 `WECHAT_APP_ID`、`WECHAT_APP_SECRET` 或 `config.json` 中的公众号配置已填写。没有封面图、接口权限不足或账号未认证时，建议先使用 `file` 模式导出人工发布。

### 批量任务会并发生成吗？

当前是后台线程异步处理任务，避免阻塞前端请求。后续如果任务量很大，可以迁移到 Celery、Redis Queue 或其他独立任务队列。

### 本地 SQLite 无法写入怎么办？

确认 `data/` 目录存在且当前用户有写权限。项目在部分受限环境下会尝试使用临时目录兜底，但正式部署建议明确配置可写的 `app_database_url` 和数据目录。

## 当前边界

- 小红书、知乎、头条等平台默认生成待发布稿件，不做自动登录或自动点击发布。
- 公众号支持草稿与提交发布，但生产环境建议保留人工确认。
- 合规检查是规则库辅助，不替代最终人工审核。
- 图片裁切当前偏通用自动化，复杂主体保护和 AI 修图可作为后续增强。
