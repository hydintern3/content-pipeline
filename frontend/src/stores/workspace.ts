import { ref } from "vue";
import { defineStore } from "pinia";

import {
  checkArticleCompliance,
  createGenerationJob,
  createVariantGenerationJob,
  fetchTasks,
  followUpArticle as followUpArticleRequest,
  generateMaterial,
  publishArticles as publishArticlesRequest,
  pullRecentMaterials,
  watchTaskJob,
} from "@/api/client";
import type {
  Article,
  ArticleFollowUp,
  ComplianceResult,
  DatabaseMaterialItem,
  GenerationHistoryDetail,
  MaterialPayload,
  Platform,
  PublishTask,
  TaskJob,
} from "@/types";
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
  const generationMode = ref<"standard" | "variants">("standard");
  const variantPlatform = ref<Platform>("xiaohongshu");
  const variantCount = ref(3);
  const articles = ref<Article[]>([]);
  const tasks = ref<PublishTask[]>([]);
  const source = ref("");
  const generating = ref(false);
  const generatingPlatforms = ref<Platform[]>([]);
  const generationTask = ref<TaskJob | null>(null);
  const generationErrors = ref<Partial<Record<Platform, string>>>({});
  const loadingTasks = ref(false);
  const historyRevision = ref(0);
  const complianceByArticle = ref<Record<number, ComplianceResult>>({});
  const checkingCompliance = ref<Record<number, boolean>>({});
  const followUpsByArticle = ref<Record<number, ArticleFollowUp[]>>({});
  const followingUpArticleIds = ref<Record<number, boolean>>({});
  let complianceQueue: Article[] = [];
  let activeComplianceWorkers = 0;
  let complianceEpoch = 0;

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

  function configuredNumber(value: unknown, fallback: number) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return fallback;
    }
    return Math.max(1, Math.min(10, Math.floor(parsed)));
  }

  function generationConcurrency() {
    const configStore = useConfigStore();
    return configuredNumber(configStore.effective?.config.generation?.concurrency, 3);
  }

  function complianceConcurrency() {
    const configStore = useConfigStore();
    return configuredNumber(configStore.effective?.config.compliance?.concurrency, 2);
  }

  function autoComplianceEnabled() {
    const configStore = useConfigStore();
    return configStore.effective?.config.compliance?.auto_check ?? true;
  }

  function articleComplianceResult(articleId: number) {
    return complianceByArticle.value[articleId];
  }

  function isCheckingCompliance(articleId: number) {
    return Boolean(checkingCompliance.value[articleId]);
  }

  function setCheckingCompliance(articleId: number, value: boolean) {
    checkingCompliance.value = {
      ...checkingCompliance.value,
      [articleId]: value,
    };
  }

  function pruneComplianceState() {
    const currentIds = new Set(articles.value.map((article) => article.id));
    complianceByArticle.value = Object.fromEntries(
      Object.entries(complianceByArticle.value).filter(([articleId]) => currentIds.has(Number(articleId))),
    );
    checkingCompliance.value = Object.fromEntries(
      Object.entries(checkingCompliance.value).filter(([articleId]) => currentIds.has(Number(articleId))),
    );
  }

  function resetComplianceState() {
    complianceEpoch += 1;
    complianceQueue = [];
    activeComplianceWorkers = 0;
    complianceByArticle.value = {};
    checkingCompliance.value = {};
  }

  function clearArticleCompliance(articleId: number) {
    const { [articleId]: _removedCompliance, ...nextCompliance } = complianceByArticle.value;
    const { [articleId]: _removedChecking, ...nextChecking } = checkingCompliance.value;
    complianceByArticle.value = nextCompliance;
    checkingCompliance.value = nextChecking;
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

  async function runArticleCompliance(
    article: Article,
    options: { forceRefresh?: boolean; notify?: boolean } = {},
  ) {
    const configStore = useConfigStore();
    setCheckingCompliance(article.id, true);
    try {
      const result = await checkArticleCompliance(
        `${article.title}\n${article.content}`,
        article.platform,
        configStore.requestConfig(),
        Boolean(options.forceRefresh),
      );
      if (articles.value.some((item) => item.id === article.id)) {
        complianceByArticle.value = {
          ...complianceByArticle.value,
          [article.id]: result,
        };
      }
      return result;
    } finally {
      setCheckingCompliance(article.id, false);
    }
  }

  async function runCompliance(article: Article) {
    return runArticleCompliance(article, { forceRefresh: true, notify: true });
  }

  function articleFollowUps(articleId: number) {
    return followUpsByArticle.value[articleId] || [];
  }

  function isFollowingUp(articleId: number) {
    return Boolean(followingUpArticleIds.value[articleId]);
  }

  async function followUpArticle(article: Article, instruction: string) {
    const configStore = useConfigStore();
    followingUpArticleIds.value = {
      ...followingUpArticleIds.value,
      [article.id]: true,
    };
    try {
      const payload = await followUpArticleRequest(article.id, instruction, configStore.requestConfig());
      const revisedArticle = payload.article;
      const previousFollowUps = articleFollowUps(article.id);
      const returnedFollowUps = payload.follow_ups?.length
        ? payload.follow_ups
        : [payload.follow_up].filter(Boolean);
      const nextFollowUps = Array.from(
        new Map([...previousFollowUps, ...returnedFollowUps].map((item) => [item.id, item])).values(),
      );
      articles.value = articles.value.map((item) => (item.id === article.id ? revisedArticle : item));
      clearArticleCompliance(article.id);
      clearArticleCompliance(revisedArticle.id);
      followUpsByArticle.value = {
        ...followUpsByArticle.value,
        [revisedArticle.id]: nextFollowUps,
      };
      const { [article.id]: _oldFollowUps, ...remainingFollowUps } = followUpsByArticle.value;
      followUpsByArticle.value = {
        ...remainingFollowUps,
        [revisedArticle.id]: nextFollowUps,
      };
      enqueueCompliance([revisedArticle]);
      return payload;
    } finally {
      const { [article.id]: _removed, ...remaining } = followingUpArticleIds.value;
      followingUpArticleIds.value = remaining;
    }
  }

  function startComplianceWorkers() {
    const limit = complianceConcurrency();
    while (activeComplianceWorkers < limit && complianceQueue.length) {
      const workerEpoch = complianceEpoch;
      activeComplianceWorkers += 1;
      void (async () => {
        try {
          while (workerEpoch === complianceEpoch && complianceQueue.length) {
            const article = complianceQueue.shift()!;
            if (!articles.value.some((item) => item.id === article.id)) {
              continue;
            }
            try {
              await runArticleCompliance(article);
            } catch {
              // Auto-check failures should not block generation; manual checks still surface messages.
            }
          }
        } finally {
          if (workerEpoch !== complianceEpoch) {
            return;
          }
          activeComplianceWorkers -= 1;
          if (complianceQueue.length) {
            startComplianceWorkers();
          }
        }
      })();
    }
  }

  function enqueueCompliance(nextArticles: Article[]) {
    if (!autoComplianceEnabled()) {
      return;
    }
    const queuedIds = new Set(complianceQueue.map((article) => article.id));
    nextArticles.forEach((article) => {
      if (articleComplianceResult(article.id) || isCheckingCompliance(article.id) || queuedIds.has(article.id)) {
        return;
      }
      complianceQueue.push(article);
      queuedIds.add(article.id);
      setCheckingCompliance(article.id, true);
    });
    startComplianceWorkers();
  }

  async function generateLegacy() {
    const configStore = useConfigStore();
    const baseMaterial = materialPayload();
    const platforms = [...baseMaterial.target_platforms];
    const historyRunId = createHistoryRunId();
    generating.value = true;
    generatingPlatforms.value = [...platforms];
    generationErrors.value = {};
    articles.value = [];
    source.value = "";
    resetComplianceState();
    followUpsByArticle.value = {};
    followingUpArticleIds.value = {};
    try {
      await withConcurrencyLimit(
        platforms,
        generationConcurrency(),
        async (platform) => {
          try {
            const payload = await generateMaterial(
              { ...baseMaterial, target_platforms: [platform] },
              configStore.requestConfig(),
              { runId: historyRunId, expectedPlatforms: platforms },
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
            pruneComplianceState();
            enqueueCompliance(returnedArticles);
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
      if (articles.value.length) {
        historyRevision.value += 1;
      }
      return { failedCount };
    } finally {
      generating.value = false;
      generatingPlatforms.value = [];
    }
  }

  async function generate() {
    const configStore = useConfigStore();
    const baseMaterial = materialPayload();
    const platforms = generationMode.value === "variants" ? [variantPlatform.value] : [...baseMaterial.target_platforms];
    const historyRunId = createHistoryRunId();
    generating.value = true;
    generatingPlatforms.value = [...platforms];
    generationTask.value = null;
    generationErrors.value = {};
    articles.value = [];
    source.value = "";
    resetComplianceState();
    followUpsByArticle.value = {};
    followingUpArticleIds.value = {};
    try {
      const task =
        generationMode.value === "variants"
          ? await createVariantGenerationJob(
              { ...baseMaterial, target_platforms: [variantPlatform.value] },
              variantPlatform.value,
              variantCount.value,
              configStore.requestConfig(),
              { runId: historyRunId },
            )
          : await createGenerationJob(
              baseMaterial,
              configStore.requestConfig(),
              { runId: historyRunId, expectedPlatforms: platforms },
            );
      generationTask.value = task;
      const completedTask = await waitForGenerationTask(task.id);
      if (completedTask.status === "failed") {
        throw new Error(completedTask.error_message || "生成任务失败");
      }
      const result = completedTask.result as {
        source?: string;
        articles?: Article[];
        errors?: Partial<Record<Platform, string>>;
      };
      const returnedArticles = result.articles || [];
      source.value = result.source || "";
      articles.value = sortArticlesByPlatform(returnedArticles, platforms);
      generationErrors.value = result.errors || {};
      pruneComplianceState();
      enqueueCompliance(returnedArticles);
      const failedCount = Object.keys(generationErrors.value).length;
      if (!articles.value.length && failedCount) {
        throw new Error("全部平台生成失败");
      }
      if (articles.value.length) {
        historyRevision.value += 1;
      }
      return { failedCount };
    } finally {
      generating.value = false;
      generatingPlatforms.value = [];
    }
  }

  function waitForGenerationTask(taskId: string) {
    return new Promise<TaskJob>((resolve, reject) => {
      const stop = watchTaskJob(
        taskId,
        (task) => {
          generationTask.value = task;
          if (["success", "failed"].includes(task.status)) {
            stop();
            resolve(task);
          }
        },
        (error) => {
          stop();
          reject(error);
        },
      );
    });
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

  function importDatabaseMaterial(item: DatabaseMaterialItem) {
    material.value = {
      title_hint: item.material.title_hint,
      raw_content: item.material.raw_content,
      keywords: item.material.keywords.join(", "),
      image_paths: item.material.image_paths.join(", "),
      target_platforms: item.material.target_platforms,
    };
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
    generationMode.value = "standard";
    variantPlatform.value = "xiaohongshu";
    variantCount.value = 3;
    articles.value = [];
    source.value = "";
    generationErrors.value = {};
    generatingPlatforms.value = [];
    generationTask.value = null;
    resetComplianceState();
    followUpsByArticle.value = {};
    followingUpArticleIds.value = {};
  }

  function restoreFromHistory(detail: GenerationHistoryDetail) {
    material.value = {
      title_hint: detail.material.title_hint,
      raw_content: detail.material.raw_content,
      keywords: detail.material.keywords.join(", "),
      image_paths: detail.material.image_paths.join(", "),
      target_platforms: detail.material.target_platforms,
    };
    articles.value = sortArticlesByPlatform(detail.articles, detail.material.target_platforms);
    source.value = "history";
    generationErrors.value = {};
    generatingPlatforms.value = [];
    generationTask.value = null;
    generating.value = false;
    resetComplianceState();
    followUpsByArticle.value = {};
    followingUpArticleIds.value = {};
    enqueueCompliance(detail.articles);
  }

  function createHistoryRunId() {
    if (globalThis.crypto?.randomUUID) {
      return globalThis.crypto.randomUUID();
    }
    return `history-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  return {
    material,
    generationMode,
    variantPlatform,
    variantCount,
    articles,
    tasks,
    source,
    generating,
    generatingPlatforms,
    generationTask,
    generationErrors,
    loadingTasks,
    historyRevision,
    complianceByArticle,
    checkingCompliance,
    followUpsByArticle,
    followingUpArticleIds,
    articleComplianceResult,
    articleFollowUps,
    clear,
    fillExample,
    followUpArticle,
    generate,
    importDatabaseMaterial,
    isCheckingCompliance,
    isFollowingUp,
    loadTasks,
    publishArticles,
    pullRecent,
    runCompliance,
    restoreFromHistory,
  };
});
