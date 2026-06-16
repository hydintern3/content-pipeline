# 内容生成与分发管线

这是整合 `mvp` 和 `demo2` 后的新项目，提供一套统一的“素材获取 -> 多平台生成 -> 格式化 -> 草稿/发布分发 -> 结果记录”流程。

## 启动

```powershell
cd E:\workspace\work\运营agent\content_pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.json config.json
python app.py
```

打开 `http://127.0.0.1:5000`。

## 配置

密钥只在服务端读取。可以使用页面右上角的“设置”保存到 `config.json`，也可以使用 `.env` 或环境变量覆盖。

页面设置会保存：

- 本地数据库 URL
- 大模型 API Key、Base URL 和模型名称
- 外部素材数据库 URL
- 待发布目录
- 公众号 App ID、App Secret、自动发布和群发开关
- 定时任务开关和间隔

API Key、数据库 URL、公众号 App Secret 不会回显到前端；再次打开设置时留空保存会保留原值。服务器部署后，首次在页面配置完成即可复用；本地部署也会读取已保存的 `config.json`，不用每次重新填写。

常用环境变量：

```text
CONTENT_LLM_API_KEY=sk-...
CONTENT_LLM_BASE_URL=https://api.openai.com/v1
CONTENT_LLM_MODEL=gpt-4o-mini
DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/operation_agent?charset=utf8mb4
WECHAT_APP_ID=...
WECHAT_APP_SECRET=...
WECHAT_AUTO_PUBLISH=false
PENDING_OUTPUT_DIR=data/pending
SCHEDULER_ENABLED=false
SCHEDULER_INTERVAL_MINUTES=240
```

## API

- `GET /api/config/status`：查看配置状态。
- `POST /api/materials/generate`：输入一份素材并生成平台稿件。
- `POST /api/materials/pull_recent`：从外部数据库拉取最近素材。
- `POST /api/publish`：导出待发布文件或创建公众号草稿。
- `GET /api/tasks`：查看最近发布任务。

生成示例：

```json
{
  "material": {
    "title_hint": "商引-商机地图小程序上线",
    "raw_content": "通过地图精准定位企业，查看信用档案和楼宇出租信息。",
    "keywords": ["企业服务", "招商"],
    "target_platforms": ["xiaohongshu", "zhihu", "official_account"],
    "image_paths": []
  }
}
```

发布示例：

```json
{
  "article_ids": [1, 2, 3],
  "mode": "file"
}
```

公众号草稿可用时，`official_account` 默认会尝试 `wechat_draft`；没有封面图或配置不完整时建议继续使用 `file` 模式。

如果需要把草稿进一步提交为正式发布，可以显式传入：

```json
{
  "article_ids": [3],
  "mode": "wechat_publish"
}
```

也可以在配置中打开：

```json
{
  "wechat": {
    "auto_publish": true
  }
}
```

开启后，不传 `mode` 时公众号稿件会默认走 `wechat_publish`。建议生产使用时仍通过页面上的“发布”按钮人工触发。

## 当前边界

- 小红书和知乎默认生成待发布稿，保留人工确认。
- 第一版不做验证码破解、风控绕过或自动点击发布。
- 公众号支持创建草稿和提交发布，不默认群发推送。
- 无大模型密钥时会自动使用本地模板兜底。

## 测试

```powershell
pytest
```
