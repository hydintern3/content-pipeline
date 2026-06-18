<template>
  <el-card class="panel-card result-panel" shadow="never">
    <template #header>
      <div class="panel-heading">
        <div>
          <p>结果</p>
          <h2>平台稿件</h2>
        </div>
        <el-button :disabled="!workspace.articles.length" :icon="FolderOpened" @click="exportAll">
          导出全部
        </el-button>
      </div>
    </template>

    <el-empty
      v-if="!workspace.articles.length && !workspace.generatingPlatforms.length && !errorPlatforms.length"
      description="等待生成"
    />

    <div v-else class="article-grid">
      <article v-for="article in workspace.articles" :key="article.id" class="article-card">
        <header>
          <el-tag effect="dark">{{ platformLabels[article.platform] || article.platform }}</el-tag>
          <small>{{ workspace.source === "llm" ? "大模型生成" : "模板兜底" }} · {{ article.format }}</small>
          <el-tag
            v-if="articleComplianceResult(article.id)"
            :type="riskTagType(articleComplianceResult(article.id)?.risk_count || 0)"
            size="small"
          >
            {{ riskTagText(articleComplianceResult(article.id)?.risk_count || 0) }}
          </el-tag>
        </header>
        <h3>{{ article.title }}</h3>

        <el-tabs v-model="modes[article.id]" class="article-tabs">
          <el-tab-pane label="预览" name="preview">
            <div
              class="rendered-preview"
              v-html="articlePreviewHtml(article)"
              @pointerleave="hideRiskTooltip"
              @pointermove="moveRiskTooltip"
              @pointerover="showRiskTooltip"
            />
          </el-tab-pane>
          <el-tab-pane label="源码" name="source">
            <pre>{{ article.content }}</pre>
          </el-tab-pane>
        </el-tabs>

        <footer>
          <el-button :icon="CopyDocument" @click="copy(article.content)">复制</el-button>
          <el-button :icon="Download" @click="publish([article.id], 'file')">导出</el-button>
          <el-button :loading="checkingCompliance[article.id]" @click="runCompliance(article)">
            合规检查
          </el-button>
          <el-button
            v-if="article.platform === 'official_account'"
            type="primary"
            plain
            @click="publish([article.id], 'wechat_draft')"
          >
            提交草稿
          </el-button>
          <el-button
            v-if="article.platform === 'official_account'"
            type="primary"
            @click="confirmPublish(article.id)"
          >
            发布
          </el-button>
        </footer>
      </article>

      <article
        v-for="platform in workspace.generatingPlatforms"
        :key="`loading-${platform}`"
        class="article-card state-card"
      >
        <header>
          <el-tag effect="dark">{{ platformLabels[platform] || platform }}</el-tag>
          <small>生成中</small>
        </header>
        <el-skeleton :rows="8" animated />
      </article>

      <article
        v-for="platform in errorPlatforms"
        :key="`error-${platform}`"
        class="article-card state-card error-card"
      >
        <header>
          <el-tag type="danger" effect="dark">{{ platformLabels[platform] || platform }}</el-tag>
          <small>生成失败</small>
        </header>
        <p>{{ workspace.generationErrors[platform] }}</p>
      </article>
    </div>

    <div
      v-if="riskTooltip.visible"
      class="risk-tooltip"
      :class="`risk-tooltip-${riskTooltip.level}`"
      :style="{ left: `${riskTooltip.x}px`, top: `${riskTooltip.y}px` }"
    >
      <div class="risk-tooltip-head">
        <span>合规风险</span>
        <strong>{{ riskLevelLabel(riskTooltip.level) }}</strong>
      </div>
      <div class="risk-tooltip-body">
        <p>
          <span>风险类型</span>
          {{ riskTooltip.category }}
        </p>
        <p>
          <span>修改建议</span>
          {{ riskTooltip.suggestion }}
        </p>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import { CopyDocument, Download, FolderOpened } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { checkArticleCompliance } from "@/api/client";
import { platformLabels } from "@/constants";
import { useWorkspaceStore } from "@/stores/workspace";
import type { Article, ComplianceResult, Platform } from "@/types";
import { previewHtmlWithRisks } from "@/utils/text";

const workspace = useWorkspaceStore();
const modes = reactive<Record<number, "preview" | "source">>({});
const complianceByArticle = reactive<Record<number, ComplianceResult>>({});
const checkingCompliance = reactive<Record<number, boolean>>({});
const riskTooltip = reactive({
  visible: false,
  x: 0,
  y: 0,
  level: "low",
  category: "",
  suggestion: "",
});
const errorPlatforms = computed(() => Object.keys(workspace.generationErrors) as Platform[]);

watch(
  () => workspace.articles.map((article) => article.id),
  (articleIds) => {
    const currentIds = new Set(articleIds);
    articleIds.forEach((articleId) => {
      modes[articleId] = modes[articleId] || "preview";
    });
    Object.keys(complianceByArticle).forEach((articleId) => {
      if (!currentIds.has(Number(articleId))) {
        delete complianceByArticle[Number(articleId)];
        delete checkingCompliance[Number(articleId)];
      }
    });
  },
  { immediate: true },
);

function articleComplianceResult(articleId: number) {
  return complianceByArticle[articleId];
}

function articlePreviewHtml(article: Article) {
  return previewHtmlWithRisks(article.content, article.format, complianceByArticle[article.id]?.risks || []);
}

function riskTagType(riskCount: number) {
  return riskCount > 0 ? "danger" : "success";
}

function riskTagText(riskCount: number) {
  return riskCount > 0 ? `${riskCount} 个风险` : "合规通过";
}

function riskLevelLabel(level: string) {
  const labels: Record<string, string> = {
    high: "高风险",
    medium: "中风险",
    low: "低风险",
  };
  return labels[level] || "待复核";
}

function riskTarget(event: PointerEvent) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return null;
  }
  return target.closest(".compliance-risk") as HTMLElement | null;
}

function updateTooltipPosition(event: PointerEvent) {
  const width = 320;
  const height = 150;
  riskTooltip.x = Math.min(event.clientX + 16, window.innerWidth - width - 12);
  riskTooltip.y = Math.min(event.clientY + 18, window.innerHeight - height - 12);
}

function showRiskTooltip(event: PointerEvent) {
  const target = riskTarget(event);
  if (!target) {
    riskTooltip.visible = false;
    return;
  }
  riskTooltip.visible = true;
  riskTooltip.level = target.dataset.riskLevel || "low";
  riskTooltip.category = target.dataset.riskCategory || "疑似风险";
  riskTooltip.suggestion = target.dataset.riskSuggestion || "建议人工复核后改写";
  updateTooltipPosition(event);
}

function moveRiskTooltip(event: PointerEvent) {
  if (!riskTooltip.visible) {
    return;
  }
  if (!riskTarget(event)) {
    riskTooltip.visible = false;
    return;
  }
  updateTooltipPosition(event);
}

function hideRiskTooltip() {
  riskTooltip.visible = false;
}

async function copy(content: string) {
  await navigator.clipboard.writeText(content);
  ElMessage.success("已复制");
}

async function runCompliance(article: Article) {
  checkingCompliance[article.id] = true;
  try {
    const result = await checkArticleCompliance(`${article.title}\n${article.content}`, article.platform);
    complianceByArticle[article.id] = result;
    if (result.risk_count > 0) {
      ElMessage.warning(`发现 ${result.risk_count} 个风险词，已在预览中标记`);
    } else {
      ElMessage.success("合规检查通过");
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "合规检查失败");
  } finally {
    checkingCompliance[article.id] = false;
  }
}

async function publish(articleIds: number[], mode: string) {
  try {
    const tasks = await workspace.publishArticles(articleIds, mode);
    const failed = tasks.filter((task) => task.status !== "success");
    if (failed.length) {
      ElMessage.warning("部分任务失败");
    } else {
      ElMessage.success("任务已提交");
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "提交失败");
  }
}

function exportAll() {
  publish(
    workspace.articles.map((article) => article.id),
    "file",
  );
}

async function confirmPublish(articleId: number) {
  await ElMessageBox.confirm("确认直接发布到微信公众号吗？", "发布确认", {
    type: "warning",
    confirmButtonText: "发布",
    cancelButtonText: "取消",
  });
  publish([articleId], "wechat_publish");
}
</script>
