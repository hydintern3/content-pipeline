<template>
  <el-card class="panel-card compact-panel" shadow="never">
    <template #header>
      <div class="panel-heading tight">
        <div>
          <p>合规</p>
          <h2>风险检查</h2>
        </div>
        <el-button size="small" :disabled="!workspace.articles.length" :loading="loading" @click="runCheck">
          检查当前稿件
        </el-button>
      </div>
    </template>

    <el-empty v-if="!results.length" description="暂无风险结果" />
    <div v-else class="risk-list">
      <div v-for="result in results" :key="result.platform" class="risk-block">
        <div class="risk-title">
          <strong>{{ platformLabels[result.platform] || result.platform }}</strong>
          <el-tag :type="result.risk_count ? 'warning' : 'success'" size="small">
            {{ result.risk_count ? `${result.risk_count} 个风险` : "通过" }}
          </el-tag>
        </div>
        <el-table v-if="result.risks.length" :data="result.risks" size="small">
          <el-table-column prop="term" label="命中词" width="90" />
          <el-table-column prop="category" label="类型" width="110" />
          <el-table-column prop="level" label="等级" width="80" />
          <el-table-column prop="suggestion" label="建议" min-width="180" show-overflow-tooltip />
        </el-table>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";

import { checkCompliance } from "@/api/client";
import { platformLabels } from "@/constants";
import { useWorkspaceStore } from "@/stores/workspace";
import type { ComplianceResult } from "@/types";

const workspace = useWorkspaceStore();
const loading = ref(false);
const results = ref<ComplianceResult[]>([]);

async function runCheck() {
  loading.value = true;
  try {
    results.value = await checkCompliance(workspace.articles);
    ElMessage.success("合规检查完成");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "合规检查失败");
  } finally {
    loading.value = false;
  }
}
</script>
