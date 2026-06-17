<template>
  <el-card class="panel-card" shadow="never">
    <template #header>
      <div class="panel-heading">
        <div>
          <p>记录</p>
          <h2>最近任务</h2>
        </div>
        <el-button :icon="Refresh" :loading="workspace.loadingTasks" @click="workspace.loadTasks">刷新</el-button>
      </div>
    </template>

    <el-table :data="workspace.tasks" empty-text="暂无任务记录" stripe>
      <el-table-column label="平台" min-width="100">
        <template #default="{ row }">{{ platformLabels[row.platform] || row.platform }}</template>
      </el-table-column>
      <el-table-column prop="mode" label="模式" min-width="120" />
      <el-table-column label="状态" min-width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'info'">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="结果" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">{{ row.output_path || row.result_message }}</template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { Refresh } from "@element-plus/icons-vue";

import { platformLabels } from "@/constants";
import { useWorkspaceStore } from "@/stores/workspace";

const workspace = useWorkspaceStore();
</script>
