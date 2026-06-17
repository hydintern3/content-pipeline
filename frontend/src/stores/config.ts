import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { fetchConfig } from "@/api/client";
import type { ConfigEnvelope, RuntimeConfig } from "@/types";

const storageKey = "contentPipeline.personalConfig.v1";

function readLocalConfig(): Partial<RuntimeConfig> {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeLocalConfig(config: Partial<RuntimeConfig>) {
  localStorage.setItem(storageKey, JSON.stringify(config));
}

function deepMerge<T extends Record<string, unknown>>(base: T, override: Record<string, unknown>): T {
  const result: Record<string, unknown> = { ...base };
  Object.entries(override || {}).forEach(([key, value]) => {
    const baseValue = result[key];
    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      baseValue &&
      typeof baseValue === "object" &&
      !Array.isArray(baseValue)
    ) {
      result[key] = deepMerge(baseValue as Record<string, unknown>, value as Record<string, unknown>);
      return;
    }
    if (value !== undefined && value !== null && value !== "") {
      result[key] = value;
    }
  });
  return result as T;
}

export const useConfigStore = defineStore("config", () => {
  const defaults = ref<ConfigEnvelope | null>(null);
  const localConfig = ref<Partial<RuntimeConfig>>(readLocalConfig());
  const loading = ref(false);

  const effective = computed<ConfigEnvelope | null>(() => {
    if (!defaults.value) {
      return null;
    }
    const mergedConfig = deepMerge(
      defaults.value.config as unknown as Record<string, unknown>,
      localConfig.value as Record<string, unknown>,
    ) as unknown as RuntimeConfig;
    return {
      ...defaults.value,
      config: {
        ...mergedConfig,
        llm: {
          ...mergedConfig.llm,
          api_key_configured: Boolean(localConfig.value.llm?.api_key || defaults.value.config.llm.api_key_configured),
        },
        database: {
          ...mergedConfig.database,
          configured: Boolean(localConfig.value.database?.url || defaults.value.config.database.configured),
        },
        wechat: {
          ...mergedConfig.wechat,
          app_secret_configured: Boolean(
            localConfig.value.wechat?.app_secret || defaults.value.config.wechat.app_secret_configured,
          ),
        },
      },
    };
  });

  async function loadDefaults() {
    loading.value = true;
    try {
      defaults.value = await fetchConfig();
    } finally {
      loading.value = false;
    }
  }

  function saveConfig(config: Partial<RuntimeConfig>) {
    localConfig.value = config;
    writeLocalConfig(config);
  }

  function requestConfig() {
    return localConfig.value;
  }

  return {
    defaults,
    effective,
    localConfig,
    loading,
    loadDefaults,
    requestConfig,
    saveConfig,
  };
});
