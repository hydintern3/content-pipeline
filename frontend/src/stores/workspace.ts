import { ref } from "vue";
import { defineStore } from "pinia";

import {
  fetchTasks,
  generateMaterial,
  publishArticles as publishArticlesRequest,
  pullRecentMaterials,
} from "@/api/client";
import type { Article, MaterialPayload, Platform, PublishTask } from "@/types";
import { commaList } from "@/utils/text";
import { useConfigStore } from "./config";

export const useWorkspaceStore = defineStore("workspace", () => {
  const material = ref({
    title_hint: "",
    raw_content: "",
    keywords: "",
    image_paths: "",
    target_platforms: ["xiaohongshu", "zhihu", "official_account", "toutiao", "shipinhao"] as Platform[],
  });
  const articles = ref<Article[]>([]);
  const tasks = ref<PublishTask[]>([]);
  const source = ref("");
  const generating = ref(false);
  const generatingPlatforms = ref<Platform[]>([]);
  const generationErrors = ref<Partial<Record<Platform, string>>>({});
  const loadingTasks = ref(false);

  function materialPayload(): MaterialPayload {
    return {
      title_hint: material.value.title_hint,
      raw_content: material.value.raw_content,
      keywords: commaList(material.value.keywords),
      image_paths: commaList(material.value.image_paths),
      target_platforms: material.value.target_platforms,
    };
  }

  function sortArticlesByPlatform(nextArticles: Article[], platforms: Platform[]) {
    return [...nextArticles].sort(
      (left, right) => platforms.indexOf(left.platform) - platforms.indexOf(right.platform),
    );
  }

  // Run async tasks with a concurrency cap so the browser, server, and
  // LLM API are not overwhelmed.  Results stream in incrementally as
  // each task completes — the UI updates platform-by-platform.
  async function withConcurrencyLimit<T, R>(
    items: T[],
    limit: number,
    fn: (item: T) => Promise<R>,
    onProgress: (item: T) => void,
  ): Promise<R[]> {
    const results: R[] = [];
    const queue = [...items];
    async function worker() {
      while (queue.length) {
        const item = queue.shift()!;
        const result = await fn(item);
        results.push(result);
        onProgress(item);
      }
    }
    await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
    return results;
  }

  async function generate() {
    const configStore = useConfigStore();
    const baseMaterial = materialPayload();
    const platforms = [...baseMaterial.target_platforms];
    generating.value = true;
    generatingPlatforms.value = [...platforms];
    generationErrors.value = {};
    articles.value = [];
    source.value = "";
    try {
      await withConcurrencyLimit(
        platforms,
        3,
        async (platform) => {
          try {
            const payload = await generateMaterial(
              { ...baseMaterial, target_platforms: [platform] },
              configStore.requestConfig(),
            );
            const returnedArticles = (payload.articles || []) as Article[];
            source.value = source.value || String(payload.source || "");
            articles.value = sortArticlesByPlatform(
              [
                ...articles.value.filter((article) => article.platform !== platform),
                ...returnedArticles,
              ],
              platforms,
            );
          } catch (error) {
            generationErrors.value = {
              ...generationErrors.value,
              [platform]: error instanceof Error ? error.message : "生成失败",
            };
          } finally {
            generatingPlatforms.value = generatingPlatforms.value.filter((item) => item !== platform);
          }
        },
        (_platform) => {
          // UI reactively updates via the store mutations above
        },
      );
      const failedCount = Object.keys(generationErrors.value).length;
      if (!articles.value.length && failedCount) {
        throw new Error("全部平台生成失败");
      }
      return { failedCount };
    } finally {
      generating.value = false;
      generatingPlatforms.value = [];
    }
  }

  async function pullRecent() {
    const configStore = useConfigStore();
    const payload = await pullRecentMaterials(5, configStore.requestConfig());
    const first = payload.materials?.[0];
    if (!first) {
      return false;
    }
    material.value = {
      title_hint: first.title_hint,
      raw_content: first.raw_content,
      keywords: first.keywords.join(", "),
      image_paths: first.image_paths.join(", "),
      target_platforms: first.target_platforms,
    };
    return true;
  }

  async function publishArticles(articleIds: number[], mode = "file") {
    const configStore = useConfigStore();
    const payload = await publishArticlesRequest(articleIds, mode, configStore.requestConfig());
    await loadTasks();
    return payload.tasks as PublishTask[];
  }

  async function loadTasks() {
    loadingTasks.value = true;
    try {
      tasks.value = await fetchTasks(20);
    } finally {
      loadingTasks.value = false;
    }
  }

  function fillExample() {
    material.value = {
      title_hint: "商引-商机地图小程序上线",
      raw_content:
        "商引小程序可以通过地图精准定位企业，查看第三方信用档案、楼宇出租信息和周边商业线索。适合中小企业主、职场人、招商主管和物业管理者使用，帮助他们更快找到可靠企业和业务机会。",
      keywords: "企业服务, 职场效率, 招商",
      image_paths: "",
      target_platforms: ["xiaohongshu", "zhihu", "official_account", "toutiao", "shipinhao"],
    };
  }

  function clear() {
    material.value = {
      title_hint: "",
      raw_content: "",
      keywords: "",
      image_paths: "",
      target_platforms: ["xiaohongshu", "zhihu", "official_account", "toutiao", "shipinhao"],
    };
    articles.value = [];
    source.value = "";
    generationErrors.value = {};
    generatingPlatforms.value = [];
  }

  return {
    material,
    articles,
    tasks,
    source,
    generating,
    generatingPlatforms,
    generationErrors,
    loadingTasks,
    clear,
    fillExample,
    generate,
    loadTasks,
    publishArticles,
    pullRecent,
  };
});
