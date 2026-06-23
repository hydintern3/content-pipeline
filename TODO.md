# 优化待办清单

> 生成于 2026-06-23，基于 `content_pipeline` 项目当前状态分析。

---

## 高优先级

### 1. 合规检查 mock 模式
**问题**：4 个合规测试跑 30s+，因为每次都走真实 LLM 调用。
**方案**：加环境变量 `CONTENT_LLM_MOCK=1`，跳过 LLM 语义检查，仅跑 regex 预检。测试从 30s → 毫秒级。
**涉及文件**：`pipeline/compliance/checker.py`、`tests/test_pipeline.py`

### 2. 清理 git 追踪
**问题**：旧 `pipeline/compliance.py` 已删除但 git 仍追踪该文件。
**方案**：`git rm --cached pipeline/compliance.py`，并在 `.gitignore` 中确认不重现。
**涉及文件**：`.gitignore`

### 3. 合规独立 LLM 配置
**问题**：合规检查和内容生成共用同一套 `CONTENT_LLM_MODEL`。合规是分类任务（不需要创意），可以用更便宜/更快的模型。
**方案**：新增 `CONTENT_LLM_COMPLIANCE_MODEL` 环境变量，未设置时 fallback 到 `CONTENT_LLM_MODEL`。
**涉及文件**：`pipeline/compliance/checker.py`、`pipeline/config.py`

---

## 中优先级

### 4. 合规结果缓存
**问题**：相同文本 + 相同平台 = 相同合规结果，但目前每次都调 LLM。
**方案**：加内存 LRU 缓存（可选文件持久化），key = `(hash(text), platform)`。批量检查同一篇文章的不同平台时收益最大。
**涉及文件**：`pipeline/compliance/checker.py`

### 5. 规则清单覆盖验证
**问题**：`prompts.py` 中的精简清单是手动从 `doc/` 提取的，可能遗漏或过时。
**方案**：写一个 pytest case 或独立脚本，验证每个 `SUPPORTED_PLATFORMS` 都有对应的 checklist entry，且核心类别（广告法、导流、色情低俗等）在每个平台的清单中都有体现。
**涉及文件**：`tests/test_pipeline.py`、`pipeline/compliance/prompts.py`

### 6. 生成后自动合规检查
**问题**：用户需要先点"生成"，再手动点"合规检查"，多一步操作。
**方案**：生成完成后自动对每篇文章调用 `checkArticleCompliance`，结果直接展示在卡片中。保留手动检查按钮作为刷新入口。
**涉及文件**：`frontend/src/stores/workspace.ts`、`frontend/src/components/PlatformResultColumns.vue`

### 7. 并发数配置化
**问题**：前端 `withConcurrencyLimit` 的 limit=3 写死在代码里。
**方案**：抽到 `frontend/src/constants.ts` 或从服务端 `/api/config` 返回，方便不同环境调优。
**涉及文件**：`frontend/src/stores/workspace.ts`、`frontend/src/constants.ts`

---

## 低优先级

### 8. 前端代码分割
**问题**：构建产物 `index-DSl4gN0I.js` 达 1.1MB，Vite 构建时警告。
**方案**：
- Element Plus 改为按需导入（`unplugin-element-plus`）
- CompliancePanel、BatchJobPanel、ImageWorkflowPanel 改为 `defineAsyncComponent` 懒加载
- 预计首次加载减少 40-60%
**涉及文件**：`frontend/vite.config.ts`、`frontend/src/views/WorkspaceView.vue`

### 9. 批量任务实时进度
**问题**：批量生成用后台线程处理，前端需要手动刷新才能看到进度。
**方案**：加入 SSE 端点 (`/api/batch_jobs/<id>/events`) 或前端轮询，推送每行完成状态。
**涉及文件**：`app.py`、`pipeline/batch.py`、`frontend/src/components/BatchJobPanel.vue`

### 10. 前端单元测试
**问题**：当前零前端测试。
**方案**：Vitest 覆盖以下核心函数：
- `previewHtmlWithRisks` — 风险高亮注入逻辑
- `withConcurrencyLimit` — 并发控制逻辑
- 合规结果展示逻辑 — 卡片内的高亮渲染
**涉及文件**：`frontend/src/utils/text.ts`、`frontend/src/stores/workspace.ts`

---

## 备注

- 以上 10 项均不涉及架构变更，多为增量改进
- 高优先级项可在一个 session 内完成
- 中优先级项涉及前后端协调，建议分步进行
- 低优先级项是长期优化方向
