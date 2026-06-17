<template>
  <el-card class="panel-card compact-panel" shadow="never">
    <template #header>
      <div class="panel-heading tight">
        <div>
          <p>批量</p>
          <h2>导入任务</h2>
        </div>
        <el-button size="small" :loading="loading" @click="loadJobs">刷新</el-button>
      </div>
    </template>

    <div class="upload-row">
      <input type="file" accept=".csv,.xlsx,.xlsm" @change="onFileChange" />
      <el-button type="primary" size="small" :disabled="!selectedFile" :loading="uploading" @click="upload">
        创建任务
      </el-button>
    </div>

    <el-empty v-if="!jobs.length" description="暂无批量任务" />
    <el-table v-else :data="jobs" size="small" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="filename" label="文件" min-width="130" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="110" />
      <el-table-column label="进度" width="130">
        <template #default="{ row }">{{ row.success_count + row.failed_count }}/{{ row.total_count }}</template>
      </el-table-column>
      <el-table-column prop="failed_count" label="失败" width="70" />
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { fetchBatchJobs, uploadBatchFile } from "@/api/client";
import { useConfigStore } from "@/stores/config";
import type { BatchJob } from "@/types";

const configStore = useConfigStore();
const jobs = ref<BatchJob[]>([]);
const selectedFile = ref<File | null>(null);
const loading = ref(false);
const uploading = ref(false);

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] || null;
}

async function upload() {
  if (!selectedFile.value) {
    return;
  }
  uploading.value = true;
  try {
    const job = await uploadBatchFile(selectedFile.value, configStore.requestConfig());
    jobs.value = [job, ...jobs.value.filter((item) => item.id !== job.id)];
    ElMessage.success("批量任务已创建");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "批量任务创建失败");
  } finally {
    uploading.value = false;
  }
}

async function loadJobs() {
  loading.value = true;
  try {
    jobs.value = await fetchBatchJobs(20);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "任务加载失败");
  } finally {
    loading.value = false;
  }
}

onMounted(loadJobs);
</script>
