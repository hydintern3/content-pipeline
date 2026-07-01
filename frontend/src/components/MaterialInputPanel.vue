<template>
  <el-card class="panel-card input-panel" shadow="never">
    <template #header>
      <div class="panel-heading">
        <div>
          <p>素材</p>
          <h2>统一输入</h2>
        </div>
        <el-button :icon="Download" @click="pullRecent">拉取最近数据</el-button>
      </div>
    </template>

    <el-form label-position="top" @submit.prevent>
      <el-form-item label="标题提示">
        <el-input v-model="workspace.material.title_hint" placeholder="例如：商引-商机地图小程序上线" />
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
</template>

<script setup lang="ts">
import { Download, Promotion } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { platformOptions } from "@/constants";
import { useWorkspaceStore } from "@/stores/workspace";

const workspace = useWorkspaceStore();

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

async function pullRecent() {
  try {
    const loaded = await workspace.pullRecent();
    if (loaded) {
      ElMessage.success("已填入最近一条素材");
    } else {
      ElMessage.warning("暂无最近数据");
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "拉取失败");
  }
}
</script>
