<template>
  <el-card class="panel-card input-panel" shadow="never">
    <template #header>
      <div class="panel-heading">
        <div>
          <p>素材</p>
          <h2>统一输入</h2>
        </div>
        <el-button :icon="Download" @click="openMaterialPicker">选择小程序素材</el-button>
      </div>
    </template>

    <el-form label-position="top" @submit.prevent>
      <el-form-item label="标题提示">
        <el-input v-model="workspace.material.title_hint" placeholder="例如：商引羚航供需信息" />
      </el-form-item>

      <el-form-item label="素材正文">
        <el-input
          v-model="workspace.material.raw_content"
          type="textarea"
          :rows="8"
          resize="vertical"
          placeholder="粘贴产品介绍、活动信息、数据库素材或运营备注"
        />
      </el-form-item>

      <div class="two-col">
        <el-form-item label="关键词">
          <el-input v-model="workspace.material.keywords" placeholder="企业服务, 招商, 楼宇出租" />
        </el-form-item>
        <el-form-item label="图片路径">
          <el-input v-model="workspace.material.image_paths" placeholder="D:\\images\\cover.png" />
        </el-form-item>
      </div>

      <el-form-item label="生成模式">
        <el-radio-group v-model="workspace.generationMode">
          <el-radio-button label="standard">多平台生成</el-radio-button>
          <el-radio-button label="variants">内容变体</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <div v-if="materialImagePreviews.length" class="image-preview-grid material-image-preview">
        <figure v-for="item in materialImagePreviews" :key="item.path" class="image-preview-card">
          <el-image
            v-if="item.url"
            :src="item.url"
            :preview-src-list="materialPreviewUrls"
            fit="cover"
            loading="lazy"
          >
            <template #error>
              <div class="image-preview-fallback">{{ item.path }}</div>
            </template>
          </el-image>
          <div v-else class="image-preview-fallback">{{ item.path }}</div>
          <figcaption>{{ item.path }}</figcaption>
        </figure>
      </div>

      <div v-if="workspace.generationMode === 'variants'" class="two-col">
        <el-form-item label="变体平台">
          <el-select v-model="workspace.variantPlatform">
            <el-option
              v-for="platform in platformOptions"
              :key="platform.value"
              :label="platform.label"
              :value="platform.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="变体数量">
          <el-input-number v-model="workspace.variantCount" :min="1" :max="10" />
        </el-form-item>
      </div>

      <el-form-item v-else label="目标平台">
        <el-checkbox-group v-model="workspace.material.target_platforms">
          <el-checkbox-button
            v-for="platform in platformOptions"
            :key="platform.value"
            :label="platform.value"
          >
            {{ platform.label }}
          </el-checkbox-button>
        </el-checkbox-group>
      </el-form-item>

      <div v-if="workspace.generationTask" class="task-progress-inline">
        <div class="task-progress-meta">
          <span>{{ workspace.generationTask.progress.message || workspace.generationTask.status }}</span>
          <span>{{ workspace.generationTask.progress.current }}/{{ workspace.generationTask.progress.total }}</span>
        </div>
        <el-progress :percentage="workspace.generationTask.progress.percent" :stroke-width="8" />
      </div>

      <div class="button-row">
        <el-button @click="workspace.fillExample">示例</el-button>
        <el-button @click="workspace.clear">清空</el-button>
        <el-button type="primary" :icon="Promotion" :loading="workspace.generating" @click="generate">
          生成
        </el-button>
      </div>
    </el-form>
  </el-card>

  <el-drawer v-model="pickerOpen" title="小程序供需素材库" size="760px" @open="loadDatabaseMaterials">
    <el-form class="database-search-form" inline @submit.prevent>
      <el-form-item label="关键词">
        <el-input
          v-model="searchForm.q"
          clearable
          placeholder="标题、描述、地址、发布人"
          @keyup.enter="searchDatabase"
        />
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="searchForm.type" clearable placeholder="全部" style="width: 120px">
          <el-option label="供应" value="SUPPLY" />
          <el-option label="需求" value="DEMAND" />
        </el-select>
      </el-form-item>
      <el-form-item label="分类">
        <el-select v-model="searchForm.category" clearable placeholder="全部" style="width: 160px">
          <el-option label="人才招聘/求职" value="TALENT" />
          <el-option label="技术服务" value="TECH_SERVICE" />
          <el-option label="楼宇空间" value="BUILDING" />
          <el-option label="商品资源" value="GOODS" />
          <el-option label="服务资源" value="SERVICE" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="databaseLoading" @click="searchDatabase">搜索</el-button>
      </el-form-item>
    </el-form>

    <el-table
      :data="databaseItems"
      v-loading="databaseLoading"
      highlight-current-row
      size="small"
      @row-click="selectDatabaseItem"
    >
      <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
      <el-table-column prop="type_label" label="类型" width="80" />
      <el-table-column prop="category_label" label="分类" width="130" />
      <el-table-column prop="publisher_name" label="发布方" width="110" show-overflow-tooltip />
      <el-table-column prop="created_at" label="发布时间" width="150" />
      <el-table-column prop="address" label="地址" min-width="160" show-overflow-tooltip />
    </el-table>

    <div class="database-pagination">
      <el-pagination
        layout="prev, pager, next, total"
        :total="databaseTotal"
        :page-size="searchForm.limit"
        :current-page="currentPage"
        @current-change="changeDatabasePage"
      />
    </div>

    <el-empty v-if="!databaseLoading && !databaseItems.length" description="暂无匹配素材" />

    <section v-if="selectedDatabaseItem" class="database-preview">
      <div class="database-preview-heading">
        <div>
          <strong>{{ selectedDatabaseItem.title }}</strong>
          <small>{{ selectedDatabaseItem.type_label }} · {{ selectedDatabaseItem.category_label }}</small>
        </div>
        <el-button type="primary" @click="importSelectedMaterial">导入素材框</el-button>
      </div>
      <pre>{{ selectedDatabaseItem.material.raw_content }}</pre>
      <div v-if="selectedDatabaseImagePreviews.length" class="image-preview-grid">
        <figure v-for="item in selectedDatabaseImagePreviews" :key="item.path" class="image-preview-card">
          <el-image
            v-if="item.url"
            :src="item.url"
            :preview-src-list="selectedDatabasePreviewUrls"
            fit="cover"
            loading="lazy"
          >
            <template #error>
              <div class="image-preview-fallback">{{ item.path }}</div>
            </template>
          </el-image>
          <div v-else class="image-preview-fallback">{{ item.path }}</div>
          <figcaption>{{ item.path }}</figcaption>
        </figure>
      </div>
    </section>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { Download, Promotion } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { searchDatabaseMaterials } from "@/api/client";
import { platformOptions } from "@/constants";
import { useConfigStore } from "@/stores/config";
import { useWorkspaceStore } from "@/stores/workspace";
import { commaList } from "@/utils/text";
import type { DatabaseMaterialItem } from "@/types";

const workspace = useWorkspaceStore();
const configStore = useConfigStore();
const pickerOpen = ref(false);
const databaseLoading = ref(false);
const databaseItems = ref<DatabaseMaterialItem[]>([]);
const databaseTotal = ref(0);
const selectedDatabaseItem = ref<DatabaseMaterialItem | null>(null);
const searchForm = ref({
  q: "",
  type: "",
  category: "",
  limit: 10,
  offset: 0,
});
const currentPage = computed(() => Math.floor(searchForm.value.offset / searchForm.value.limit) + 1);
const imageBaseUrl = computed(() => configStore.effective?.config.database.image_base_url || "");

function resolveImageUrl(path: string, explicitUrl = "") {
  const trimmedPath = String(path || "").trim();
  const trimmedUrl = String(explicitUrl || "").trim();
  if (trimmedUrl) {
    return trimmedUrl;
  }
  if (!trimmedPath) {
    return "";
  }
  if (trimmedPath.startsWith("http://") || trimmedPath.startsWith("https://") || trimmedPath.startsWith("//")) {
    return trimmedPath;
  }
  const baseUrl = imageBaseUrl.value.trim();
  if (!baseUrl) {
    return "";
  }
  return `${baseUrl.replace(/\/+$/, "")}/${trimmedPath.replace(/^\/+/, "")}`;
}

const materialImagePreviews = computed(() =>
  commaList(workspace.material.image_paths).map((path) => ({
    path,
    url: resolveImageUrl(path),
  })),
);
const materialPreviewUrls = computed(() => materialImagePreviews.value.map((item) => item.url).filter(Boolean));
const selectedDatabaseImagePreviews = computed(() => {
  const item = selectedDatabaseItem.value;
  if (!item) {
    return [];
  }
  return item.image_paths.map((path, index) => ({
    path,
    url: resolveImageUrl(path, (item.image_urls || [])[index] || ""),
  }));
});
const selectedDatabasePreviewUrls = computed(() =>
  selectedDatabaseImagePreviews.value.map((item) => item.url).filter(Boolean),
);

async function generate() {
  if (!workspace.material.title_hint || !workspace.material.raw_content) {
    ElMessage.warning("标题和素材正文不能为空");
    return;
  }
  if (workspace.generationMode === "standard" && !workspace.material.target_platforms.length) {
    ElMessage.warning("至少选择一个平台");
    return;
  }
  try {
    const result = await workspace.generate();
    if (result?.failedCount) {
      ElMessage.warning(`已生成，${result.failedCount} 个平台失败`);
    } else {
      ElMessage.success(workspace.generationMode === "variants" ? "内容变体已生成" : "稿件已生成");
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "生成失败");
  }
}

function openMaterialPicker() {
  pickerOpen.value = true;
}

async function loadDatabaseMaterials() {
  databaseLoading.value = true;
  try {
    const payload = await searchDatabaseMaterials(searchForm.value, configStore.requestConfig());
    databaseItems.value = payload.items;
    databaseTotal.value = payload.total;
    selectedDatabaseItem.value = payload.items[0] || null;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "素材库搜索失败");
  } finally {
    databaseLoading.value = false;
  }
}

async function searchDatabase() {
  searchForm.value.offset = 0;
  await loadDatabaseMaterials();
}

async function changeDatabasePage(page: number) {
  searchForm.value.offset = Math.max(0, page - 1) * searchForm.value.limit;
  await loadDatabaseMaterials();
}

function selectDatabaseItem(item: DatabaseMaterialItem) {
  selectedDatabaseItem.value = item;
}

function importSelectedMaterial() {
  if (!selectedDatabaseItem.value) {
    return;
  }
  workspace.importDatabaseMaterial(selectedDatabaseItem.value);
  pickerOpen.value = false;
  ElMessage.success("已导入素材框，可编辑后生成");
}
</script>
