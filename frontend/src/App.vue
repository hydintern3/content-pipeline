<template>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">Content Pipeline</p>
        <h1>运营 Agent 工作台</h1>
      </div>
      <div class="topbar-actions">
        <div class="status-row">
          <el-tag v-for="chip in statusChips" :key="chip" effect="plain">{{ chip }}</el-tag>
        </div>
        <el-button :icon="Setting" @click="settingsOpen = true">设置</el-button>
      </div>
    </header>

    <RouterView />
    <SettingsDrawer v-model="settingsOpen" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterView } from "vue-router";
import { Setting } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import SettingsDrawer from "@/components/SettingsDrawer.vue";
import { useConfigStore } from "@/stores/config";
import { useWorkspaceStore } from "@/stores/workspace";

const configStore = useConfigStore();
const workspaceStore = useWorkspaceStore();
const settingsOpen = ref(false);

const statusChips = computed(() => {
  const data = configStore.effective?.config;
  if (!data) {
    return ["配置读取中"];
  }
  return [
    data.llm.api_key_configured ? "LLM 已配置" : "模板模式",
    data.database.configured ? "外部数据库已配置" : "未配置外部数据库",
    data.wechat.app_id && data.wechat.app_secret_configured ? "公众号已配置" : "公众号文件草稿",
    data.wechat.auto_publish ? "公众号自动发布" : "手动发布",
  ];
});

onMounted(async () => {
  try {
    await configStore.loadDefaults();
    await workspaceStore.loadTasks();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "初始化失败");
  }
});
</script>
