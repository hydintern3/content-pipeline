<template>
  <el-card class="panel-card compact-panel observability-panel" shadow="never">
    <template #header>
      <div class="panel-heading tight">
        <div>
          <p>Observability</p>
          <h2>运行监控</h2>
        </div>
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
      </div>
    </template>

    <el-empty v-if="!summary" description="暂无监控数据" />
    <template v-else>
      <div class="metric-grid">
        <div class="metric-tile">
          <span>API 请求</span>
          <strong>{{ summary.requests.count }}</strong>
          <small>错误 {{ summary.requests.error_count }} · 平均 {{ summary.requests.avg_latency_ms }} ms</small>
        </div>
        <div class="metric-tile">
          <span>LLM 调用</span>
          <strong>{{ summary.llm.count }}</strong>
          <small>失败 {{ summary.llm.error_count }} · 平均 {{ summary.llm.avg_latency_ms }} ms</small>
        </div>
        <div class="metric-tile">
          <span>Token</span>
          <strong>{{ summary.llm.total_tokens }}</strong>
          <small>估算 ${{ summary.llm.estimated_cost_usd }}</small>
        </div>
      </div>

      <el-table :data="summary.recent_llm_calls" size="small" class="mt-12">
        <el-table-column prop="operation" label="LLM" width="120" />
        <el-table-column prop="platform" label="平台" width="90" />
        <el-table-column prop="model" label="模型" min-width="120" show-overflow-tooltip />
        <el-table-column prop="latency_ms" label="耗时 ms" width="90" />
        <el-table-column prop="total_tokens" label="Token" width="90" />
        <el-table-column prop="estimated_cost_usd" label="成本 $" width="90" />
      </el-table>

      <el-table :data="summary.recent_logs" size="small" class="mt-12">
        <el-table-column prop="level" label="级别" width="70" />
        <el-table-column prop="method" label="方法" width="70" />
        <el-table-column prop="path" label="路径" min-width="160" show-overflow-tooltip />
        <el-table-column prop="status_code" label="状态" width="70" />
        <el-table-column prop="duration_ms" label="耗时 ms" width="90" />
      </el-table>
    </template>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { fetchObservabilitySummary } from "@/api/client";
import type { ObservabilitySummary } from "@/types";

const summary = ref<ObservabilitySummary | null>(null);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    summary.value = await fetchObservabilitySummary(24, 20);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "监控数据加载失败");
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>
