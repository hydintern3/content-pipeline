<template>
  <el-card class="panel-card history-panel" shadow="never">
    <template #header>
      <div class="panel-heading history-heading">
        <div>
          <p>历史记录</p>
          <h2>生成历史</h2>
        </div>
        <div class="history-actions">
          <el-input
            v-model="query"
            clearable
            placeholder="搜索选题或素材"
            @clear="loadHistory"
            @keyup.enter="loadHistory"
          />
          <el-select
            v-model="platformFilter"
            clearable
            placeholder="平台"
            @change="loadHistory"
            @clear="loadHistory"
          >
            <el-option
              v-for="platform in platformOptions"
              :key="platform.value"
              :label="platform.label"
              :value="platform.value"
            />
          </el-select>
          <el-button @click="loadHistory">刷新</el-button>
        </div>
      </div>
    </template>

    <el-table v-loading="loading" :data="items" class="history-table" empty-text="暂无生成历史">
      <el-table-column label="选题" min-width="240">
        <template #default="{ row }">
          <button class="history-title" type="button" @click="openDetail(row.id)">
            {{ row.title_hint || "未命名选题" }}
          </button>
          <p class="history-meta">
            {{ formatTime(row.created_at) }} · {{ row.article_count }} 篇稿件
          </p>
        </template>
      </el-table-column>
      <el-table-column label="目标平台" min-width="220">
        <template #default="{ row }">
          <div class="history-tags">
            <el-tag v-for="platform in row.target_platforms" :key="platform" size="small" effect="plain">
              {{ platformLabels[platform] || platform }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="已生成" min-width="220">
        <template #default="{ row }">
          <div class="history-tags">
            <el-tag v-for="platform in row.generated_platforms" :key="platform" size="small" type="success">
              {{ platformLabels[platform] || platform }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column align="right" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="openDetail(row.id)">查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="detailOpen" size="52%" title="生成历史详情">
      <div v-loading="detailLoading" class="history-detail">
        <template v-if="selectedDetail">
          <section class="history-detail-section">
            <div class="risk-title">
              <h3>{{ selectedDetail.title_hint || "未命名选题" }}</h3>
              <el-button type="primary" @click="restoreToWorkspace">复用到工作台</el-button>
            </div>
            <p class="history-meta">
              {{ formatTime(selectedDetail.created_at) }} · {{ selectedDetail.article_count }} 篇稿件
            </p>
            <p class="history-content">{{ selectedDetail.material.raw_content }}</p>
            <div class="history-tags">
              <el-tag v-for="keyword in selectedDetail.material.keywords" :key="keyword" size="small">
                {{ keyword }}
              </el-tag>
            </div>
          </section>

          <section class="history-detail-section">
            <h3>平台稿件</h3>
            <article v-for="article in selectedDetail.articles" :key="article.id" class="history-article">
              <header>
                <el-tag effect="dark">{{ platformLabels[article.platform] || article.platform }}</el-tag>
                <small>{{ article.format }}</small>
              </header>
              <h4>{{ article.title }}</h4>
              <pre>{{ article.content }}</pre>
            </article>
          </section>
        </template>
      </div>
    </el-drawer>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import { fetchGenerationHistory, fetchGenerationHistoryDetail } from "@/api/client";
import { platformLabels, platformOptions } from "@/constants";
import { useWorkspaceStore } from "@/stores/workspace";
import type { GenerationHistoryDetail, GenerationHistoryItem } from "@/types";

const workspace = useWorkspaceStore();
const items = ref<GenerationHistoryItem[]>([]);
const selectedDetail = ref<GenerationHistoryDetail | null>(null);
const query = ref("");
const platformFilter = ref("");
const loading = ref(false);
const detailLoading = ref(false);
const detailOpen = ref(false);

onMounted(loadHistory);

watch(
  () => workspace.historyRevision,
  () => loadHistory(),
);

async function loadHistory() {
  loading.value = true;
  try {
    items.value = await fetchGenerationHistory({
      limit: 20,
      offset: 0,
      q: query.value.trim(),
      platform: platformFilter.value,
    });
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "历史记录加载失败");
  } finally {
    loading.value = false;
  }
}

async function openDetail(runId: string) {
  detailOpen.value = true;
  detailLoading.value = true;
  try {
    selectedDetail.value = await fetchGenerationHistoryDetail(runId);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "历史详情加载失败");
  } finally {
    detailLoading.value = false;
  }
}

function restoreToWorkspace() {
  if (!selectedDetail.value) {
    return;
  }
  workspace.restoreFromHistory(selectedDetail.value);
  detailOpen.value = false;
  ElMessage.success("已复用到工作台");
}

function formatTime(value: string) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
</script>
