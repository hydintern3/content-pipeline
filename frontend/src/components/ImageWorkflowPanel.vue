<template>
  <el-card class="panel-card compact-panel" shadow="never">
    <template #header>
      <div class="panel-heading tight">
        <div>
          <p>图片</p>
          <h2>处理流水线</h2>
        </div>
        <el-button size="small" type="primary" :disabled="!files.length" :loading="processing" @click="run">
          开始处理
        </el-button>
      </div>
    </template>

    <el-input v-model="topic" placeholder="选题/归档名称" class="mb-10" />
    <el-checkbox-group v-model="platforms" class="mb-10">
      <el-checkbox-button v-for="platform in platformOptions" :key="platform.value" :label="platform.value">
        {{ platform.label }}
      </el-checkbox-button>
    </el-checkbox-group>
    <input type="file" accept=".jpg,.jpeg,.png" multiple @change="onFilesChange" />

    <el-empty v-if="!assets.length" description="暂无图片产物" />
    <div v-else class="image-asset-list">
      <div v-for="asset in assets" :key="asset.id" class="image-asset">
        <strong>{{ asset.original_name }}</strong>
        <el-table :data="asset.variants" size="small">
          <el-table-column label="平台" width="90">
            <template #default="{ row }">{{ platformLabels[row.platform] || row.platform }}</template>
          </el-table-column>
          <el-table-column prop="usage" label="用途" width="80" />
          <el-table-column label="尺寸" width="110">
            <template #default="{ row }">{{ row.width }}x{{ row.height }}</template>
          </el-table-column>
          <el-table-column label="大小" width="90">
            <template #default="{ row }">{{ Math.round(row.file_size / 1024) }}KB</template>
          </el-table-column>
          <el-table-column prop="output_path" label="输出路径" min-width="180" show-overflow-tooltip />
        </el-table>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";

import { processImages } from "@/api/client";
import { platformLabels, platformOptions } from "@/constants";
import type { ImageAsset, Platform } from "@/types";

const topic = ref("");
const platforms = ref<Platform[]>(["official_account", "xiaohongshu", "zhihu", "toutiao", "shipinhao"]);
const files = ref<File[]>([]);
const assets = ref<ImageAsset[]>([]);
const processing = ref(false);

function onFilesChange(event: Event) {
  const input = event.target as HTMLInputElement;
  files.value = Array.from(input.files || []);
}

async function run() {
  processing.value = true;
  try {
    assets.value = await processImages(files.value, topic.value || "未命名选题", platforms.value);
    ElMessage.success("图片处理完成");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "图片处理失败");
  } finally {
    processing.value = false;
  }
}
</script>
