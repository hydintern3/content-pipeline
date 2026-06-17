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
        </header>
        <h3>{{ article.title }}</h3>

        <el-tabs v-model="modes[article.id]" class="article-tabs">
          <el-tab-pane label="预览" name="preview">
            <div class="rendered-preview" v-html="previewHtml(article.content, article.format)" />
          </el-tab-pane>
          <el-tab-pane label="源码" name="source">
            <pre>{{ article.content }}</pre>
          </el-tab-pane>
        </el-tabs>

        <footer>
          <el-button :icon="CopyDocument" @click="copy(article.content)">复制</el-button>
          <el-button :icon="Download" @click="publish([article.id], 'file')">导出</el-button>
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
  </el-card>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import { CopyDocument, Download, FolderOpened } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { platformLabels } from "@/constants";
import { useWorkspaceStore } from "@/stores/workspace";
import type { Platform } from "@/types";
import { previewHtml } from "@/utils/text";

const workspace = useWorkspaceStore();
const modes = reactive<Record<number, "preview" | "source">>({});
const errorPlatforms = computed(() => Object.keys(workspace.generationErrors) as Platform[]);

watch(
  () => workspace.articles.map((article) => article.id),
  (articleIds) => {
    articleIds.forEach((articleId) => {
      modes[articleId] = modes[articleId] || "preview";
    });
  },
  { immediate: true },
);

async function copy(content: string) {
  await navigator.clipboard.writeText(content);
  ElMessage.success("已复制");
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
