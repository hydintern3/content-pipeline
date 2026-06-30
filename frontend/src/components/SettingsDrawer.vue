<template>
  <el-drawer v-model="visible" title="运行配置" size="520px" @open="open">
    <el-form v-if="form" label-position="top">
      <el-form-item label="本地数据库 URL">
        <el-input v-model="form.app_database_url" />
      </el-form-item>
      <div class="two-col">
        <el-form-item label="大模型 Base URL">
          <el-input v-model="form.llm.base_url" />
        </el-form-item>
        <el-form-item label="大模型名称">
          <el-input v-model="form.llm.model" />
        </el-form-item>
      </div>
      <el-form-item label="大模型 API Key">
        <el-input v-model="form.llm.api_key" type="password" show-password placeholder="留空保持不变" />
      </el-form-item>
      <div class="two-col">
        <el-form-item label="生成并发数">
          <el-input-number v-model="form.generation.concurrency" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="合规并发数">
          <el-input-number v-model="form.compliance.concurrency" :min="1" :max="10" />
        </el-form-item>
      </div>
      <div class="two-col">
        <el-form-item label="合规模型名称">
          <el-input v-model="form.compliance.llm_model" placeholder="留空则使用内容生成模型" />
        </el-form-item>
        <el-form-item label="合规缓存大小">
          <el-input-number v-model="form.compliance.cache_size" :min="0" :max="5000" />
        </el-form-item>
      </div>
      <el-form-item>
        <el-checkbox v-model="form.compliance.auto_check">生成后自动合规检查</el-checkbox>
        <el-checkbox v-model="form.compliance.mock">合规 mock 模式</el-checkbox>
      </el-form-item>
      <el-form-item label="外部素材数据库 URL">
        <el-input v-model="form.database.url" type="password" show-password placeholder="留空保持不变" />
      </el-form-item>
      <el-form-item label="待发布目录">
        <el-input v-model="form.publish.pending_output_dir" />
      </el-form-item>
      <div class="two-col">
        <el-form-item label="公众号 App ID">
          <el-input v-model="form.wechat.app_id" />
        </el-form-item>
        <el-form-item label="公众号 App Secret">
          <el-input v-model="form.wechat.app_secret" type="password" show-password placeholder="留空保持不变" />
        </el-form-item>
      </div>
      <el-form-item>
        <el-checkbox v-model="form.wechat.auto_publish">公众号自动发布</el-checkbox>
        <el-checkbox v-model="form.wechat.enable_mass_send">允许公众号群发</el-checkbox>
      </el-form-item>

      <el-alert v-if="note" :title="note" type="info" :closable="false" />
    </el-form>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" @click="save">保存设置</el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";

import { overrideLabels } from "@/constants";
import { useConfigStore } from "@/stores/config";
import type { RuntimeConfig } from "@/types";

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();

const configStore = useConfigStore();
const form = ref<RuntimeConfig | null>(null);

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

const note = computed(() => {
  const overrides = Object.entries(configStore.effective?.env_overrides || {})
    .filter(([, enabled]) => enabled)
    .map(([key]) => overrideLabels[key] || key);
  const notes = [Object.keys(configStore.localConfig).length ? "设置已保存在当前浏览器" : "设置将保存在当前浏览器"];
  if (overrides.length) {
    notes.push(`环境变量正在接管：${overrides.join("、")}`);
  }
  return notes.join("；");
});

async function open() {
  if (!configStore.effective) {
    await configStore.loadDefaults();
  }
  const config = configStore.effective?.config;
  if (config) {
    form.value = JSON.parse(JSON.stringify(config));
    form.value!.llm.api_key = configStore.localConfig.llm?.api_key || "";
    form.value!.database.url = configStore.localConfig.database?.url || "";
    form.value!.wechat.app_secret = configStore.localConfig.wechat?.app_secret || "";
  }
}

function compact(config: RuntimeConfig): Partial<RuntimeConfig> {
  return {
    app_database_url: config.app_database_url,
    llm: {
      base_url: config.llm.base_url,
      model: config.llm.model,
      ...(config.llm.api_key ? { api_key: config.llm.api_key } : {}),
    },
    generation: {
      concurrency: config.generation.concurrency,
    },
    compliance: {
      mock: config.compliance.mock,
      llm_model: config.compliance.llm_model,
      cache_size: config.compliance.cache_size,
      auto_check: config.compliance.auto_check,
      concurrency: config.compliance.concurrency,
    },
    database: {
      ...(config.database.url ? { url: config.database.url } : {}),
    },
    publish: {
      pending_output_dir: config.publish.pending_output_dir,
    },
    wechat: {
      app_id: config.wechat.app_id,
      ...(config.wechat.app_secret ? { app_secret: config.wechat.app_secret } : {}),
      auto_publish: config.wechat.auto_publish,
      enable_mass_send: config.wechat.enable_mass_send,
    },
  };
}

function save() {
  if (!form.value) {
    return;
  }
  configStore.saveConfig(compact(form.value));
  ElMessage.success("设置已保存");
  visible.value = false;
}
</script>
