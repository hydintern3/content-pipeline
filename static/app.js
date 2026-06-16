const form = document.querySelector("#materialForm");
const statusRow = document.querySelector("#statusRow");
const articleList = document.querySelector("#articleList");
const taskList = document.querySelector("#taskList");
const emptyState = document.querySelector("#emptyState");
const generateButton = document.querySelector("#generateButton");
const exportAllButton = document.querySelector("#exportAllButton");
const pullRecentButton = document.querySelector("#pullRecentButton");
const fillExampleButton = document.querySelector("#fillExampleButton");
const clearButton = document.querySelector("#clearButton");
const refreshTasksButton = document.querySelector("#refreshTasksButton");
const settingsButton = document.querySelector("#settingsButton");
const configPanel = document.querySelector("#configPanel");
const configForm = document.querySelector("#configForm");
const closeSettingsButton = document.querySelector("#closeSettingsButton");
const saveConfigButton = document.querySelector("#saveConfigButton");
const configNote = document.querySelector("#configNote");
const toast = document.querySelector("#toast");

let currentArticles = [];
let defaultConfigData = null;

const CONFIG_STORAGE_KEY = "contentPipeline.personalConfig.v1";

const platformLabels = {
  xiaohongshu: "小红书",
  zhihu: "知乎",
  official_account: "公众号",
};

const overrideLabels = {
  app_database_url: "本地数据库",
  llm_api_key: "大模型 API Key",
  llm_base_url: "大模型 Base URL",
  llm_model: "大模型名称",
  external_database_url: "外部素材数据库",
  pending_output_dir: "待发布目录",
  wechat_app_id: "公众号 App ID",
  wechat_app_secret: "公众号 App Secret",
  wechat_auto_publish: "公众号自动发布",
  wechat_enable_mass_send: "公众号群发",
  scheduler_enabled: "定时任务",
  scheduler_interval_minutes: "定时间隔",
};

const example = {
  title_hint: "商引-商机地图小程序上线",
  raw_content:
    "商引小程序可以通过地图精准定位企业，查看第三方信用档案、楼宇出租信息和周边商业线索。适合中小企业主、职场人、招商主管和物业管理者使用，帮助他们更快找到靠谱企业和业务机会。",
  keywords: "企业服务, 职场效率, 招商",
  image_paths: "",
};

function readLocalConfig() {
  try {
    const parsed = JSON.parse(localStorage.getItem(CONFIG_STORAGE_KEY) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeLocalConfig(config) {
  localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config));
}

function deepMerge(base, override) {
  const result = { ...base };
  Object.entries(override || {}).forEach(([key, value]) => {
    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      base[key] &&
      typeof base[key] === "object" &&
      !Array.isArray(base[key])
    ) {
      result[key] = deepMerge(base[key], value);
      return;
    }
    if (value !== undefined && value !== null && value !== "") {
      result[key] = value;
    }
  });
  return result;
}

function effectiveConfigData() {
  if (!defaultConfigData) {
    return null;
  }
  const localConfig = readLocalConfig();
  const mergedConfig = deepMerge(defaultConfigData.config, localConfig);
  return {
    ...defaultConfigData,
    config: {
      ...mergedConfig,
      llm: {
        ...mergedConfig.llm,
        api_key_configured: Boolean(
          localConfig.llm?.api_key || defaultConfigData.config.llm.api_key_configured,
        ),
      },
      database: {
        ...mergedConfig.database,
        configured: Boolean(localConfig.database?.url || defaultConfigData.config.database.configured),
      },
      wechat: {
        ...mergedConfig.wechat,
        app_secret_configured: Boolean(
          localConfig.wechat?.app_secret || defaultConfigData.config.wechat.app_secret_configured,
        ),
      },
    },
  };
}

function requestConfig() {
  return readLocalConfig();
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2200);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.success) {
    throw new Error(payload.message || "请求失败");
  }
  return payload;
}

function commaList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function selectedPlatforms() {
  return Array.from(form.querySelectorAll("input[name='platform']:checked")).map(
    (input) => input.value,
  );
}

function materialPayload() {
  const data = Object.fromEntries(new FormData(form).entries());
  return {
    title_hint: data.title_hint,
    raw_content: data.raw_content,
    keywords: commaList(data.keywords),
    image_paths: commaList(data.image_paths),
    target_platforms: selectedPlatforms(),
  };
}

function fillForm(values) {
  Object.entries(values).forEach(([key, value]) => {
    if (form.elements[key]) {
      form.elements[key].value = value;
    }
  });
}

function fillConfigForm(data) {
  const config = data.config;
  const localConfig = readLocalConfig();
  configForm.elements.app_database_url.value = config.app_database_url || "";
  configForm.elements.llm_base_url.value = config.llm.base_url || "";
  configForm.elements.llm_model.value = config.llm.model || "";
  configForm.elements.llm_api_key.value = "";
  configForm.elements.llm_api_key.placeholder = localConfig.llm?.api_key
    ? "已保存在本浏览器，留空保持不变"
    : config.llm.api_key_configured
      ? "服务器默认已配置，留空使用默认值"
      : "未配置";
  configForm.elements.database_url.value = "";
  configForm.elements.database_url.placeholder = localConfig.database?.url
    ? "已保存在本浏览器，留空保持不变"
    : config.database.configured
      ? "服务器默认已配置，留空使用默认值"
      : "未配置";
  configForm.elements.pending_output_dir.value = config.publish.pending_output_dir || "";
  configForm.elements.wechat_app_id.value = config.wechat.app_id || "";
  configForm.elements.wechat_app_secret.value = "";
  configForm.elements.wechat_app_secret.placeholder = localConfig.wechat?.app_secret
    ? "已保存在本浏览器，留空保持不变"
    : config.wechat.app_secret_configured
      ? "服务器默认已配置，留空使用默认值"
      : "未配置";
  configForm.elements.wechat_auto_publish.checked = Boolean(config.wechat.auto_publish);
  configForm.elements.wechat_enable_mass_send.checked = Boolean(config.wechat.enable_mass_send);

  const overrides = Object.entries(data.env_overrides || {})
    .filter(([, enabled]) => enabled)
    .map(([key]) => overrideLabels[key] || key);
  const notes = [];
  if (Object.keys(localConfig).length) {
    notes.push("设置已保存在当前浏览器");
  } else {
    notes.push("设置将保存在当前浏览器");
  }
  if (overrides.length) {
    notes.push(`环境变量正在接管：${overrides.join("、")}`);
  }
  configNote.textContent = notes.join("；");
}

function configPayload(existing = {}) {
  const data = Object.fromEntries(new FormData(configForm).entries());
  return {
    app_database_url: data.app_database_url,
    llm: {
      base_url: data.llm_base_url,
      model: data.llm_model,
      api_key: data.llm_api_key || existing.llm?.api_key || "",
    },
    database: {
      url: data.database_url || existing.database?.url || "",
    },
    publish: {
      pending_output_dir: data.pending_output_dir,
    },
    wechat: {
      app_id: data.wechat_app_id,
      app_secret: data.wechat_app_secret || existing.wechat?.app_secret || "",
      auto_publish: configForm.elements.wechat_auto_publish.checked,
      enable_mass_send: configForm.elements.wechat_enable_mass_send.checked,
    },
  };
}

function compactConfig(config) {
  return {
    app_database_url: config.app_database_url,
    llm: {
      base_url: config.llm.base_url,
      model: config.llm.model,
      ...(config.llm.api_key ? { api_key: config.llm.api_key } : {}),
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

function setConfigSaving(isSaving) {
  saveConfigButton.disabled = isSaving;
  saveConfigButton.textContent = isSaving ? "保存中" : "保存设置";
}

function setLoading(isLoading) {
  generateButton.disabled = isLoading;
  generateButton.textContent = isLoading ? "生成中" : "生成";
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function sanitizeHtml(value) {
  const template = document.createElement("template");
  template.innerHTML = value || "";
  template.content.querySelectorAll("script, iframe, object, embed, link, meta").forEach((node) => {
    node.remove();
  });
  template.content.querySelectorAll("*").forEach((node) => {
    Array.from(node.attributes).forEach((attribute) => {
      const name = attribute.name.toLowerCase();
      const rawValue = attribute.value.trim().toLowerCase();
      if (name.startsWith("on")) {
        node.removeAttribute(attribute.name);
      }
      if ((name === "href" || name === "src") && rawValue.startsWith("javascript:")) {
        node.removeAttribute(attribute.name);
      }
    });
  });
  return template.innerHTML;
}

function markdownToHtml(value) {
  const lines = String(value || "").split(/\r?\n/);
  const html = [];
  let inList = false;

  function closeList() {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      return;
    }
    if (/^#{1,3}\s+/.test(line)) {
      closeList();
      const level = Math.min(3, line.match(/^#+/)[0].length);
      html.push(`<h${level}>${escapeHtml(line.replace(/^#{1,3}\s+/, ""))}</h${level}>`);
      return;
    }
    if (/^[-*]\s+/.test(line)) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${formatInlineMarkdown(escapeHtml(line.replace(/^[-*]\s+/, "")))}</li>`);
      return;
    }
    closeList();
    html.push(`<p>${formatInlineMarkdown(escapeHtml(line))}</p>`);
  });
  closeList();
  return html.join("");
}

function formatInlineMarkdown(value) {
  return value
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>");
}

function previewHtml(article) {
  const format = String(article.format || "").toLowerCase();
  if (format === "html") {
    return sanitizeHtml(article.content);
  }
  if (format === "markdown") {
    return markdownToHtml(article.content);
  }
  return markdownToHtml(article.content);
}

function setArticleMode(card, mode) {
  card.querySelector(".preview-pane").classList.toggle("hidden", mode !== "preview");
  card.querySelector(".source-pane").classList.toggle("hidden", mode !== "source");
  card.querySelector("[data-mode='preview']").classList.toggle("active", mode === "preview");
  card.querySelector("[data-mode='source']").classList.toggle("active", mode === "source");
}

function renderArticles(articles, source) {
  currentArticles = articles;
  articleList.innerHTML = "";
  emptyState.classList.toggle("hidden", articles.length > 0);
  exportAllButton.disabled = articles.length === 0;

  articles.forEach((article) => {
    const card = document.createElement("article");
    card.className = `article-card platform-${article.platform}`;
    card.innerHTML = `
      <div class="article-head">
        <div>
          <span>${platformLabels[article.platform] || article.platform}</span>
          <h3>${article.title}</h3>
        </div>
        <small>${source === "llm" ? "大模型生成" : "模板兜底"} · ${article.format}</small>
      </div>
      <div class="article-mode-tabs">
        <button type="button" class="mode-button active" data-mode="preview">预览</button>
        <button type="button" class="mode-button" data-mode="source">源码</button>
      </div>
      <div class="rendered-preview preview-pane"></div>
      <pre class="source-pane hidden"></pre>
      <div class="article-actions">
        <button type="button" class="ghost-button copy-button">复制</button>
        <button type="button" class="secondary-button export-button">导出</button>
        ${
          article.platform === "official_account"
            ? '<button type="button" class="secondary-button draft-button">提交草稿</button><button type="button" class="primary-button publish-button">发布</button>'
            : ""
        }
      </div>
    `;
    card.querySelector(".preview-pane").innerHTML = previewHtml(article);
    card.querySelector(".source-pane").textContent = article.content;
    card.querySelectorAll(".mode-button").forEach((button) => {
      button.addEventListener("click", () => setArticleMode(card, button.dataset.mode));
    });
    card.querySelector(".copy-button").addEventListener("click", async () => {
      await navigator.clipboard.writeText(article.content);
      showToast("已复制");
    });
    card.querySelector(".export-button").addEventListener("click", () => {
      publishArticles([article.id]);
    });
    const draftButton = card.querySelector(".draft-button");
    if (draftButton) {
      draftButton.addEventListener("click", () => {
        publishArticles([article.id], "wechat_draft");
      });
    }
    const publishButton = card.querySelector(".publish-button");
    if (publishButton) {
      publishButton.addEventListener("click", () => {
        if (window.confirm("确认直接发布到微信公众号吗？发布后会进入微信发布流程。")) {
          publishArticles([article.id], "wechat_publish");
        }
      });
    }
    articleList.appendChild(card);
  });
}

async function publishArticles(articleIds, mode = "file") {
  const body = { article_ids: articleIds, config: requestConfig() };
  if (mode) {
    body.mode = mode;
  }
  const payload = await requestJson("/api/publish", {
    method: "POST",
    body: JSON.stringify(body),
  });
  const failed = payload.tasks.filter((task) => task.status !== "success");
  const successMessage = mode === "wechat_publish"
    ? "公众号发布已提交"
    : mode === "wechat_draft"
      ? "公众号草稿已提交"
      : "已导出待发布文件";
  showToast(failed.length ? "部分任务失败" : successMessage);
  loadTasks();
}

async function loadStatus() {
  if (!defaultConfigData) {
    await loadConfigDefaults();
  }
  const data = effectiveConfigData().config;
  const chips = [
    data.llm.api_key_configured ? "LLM 已配置" : "模板模式",
    data.database.configured ? "外部数据库已配置" : "未配置外部数据库",
    data.wechat.app_id && data.wechat.app_secret_configured ? "公众号已配置" : "公众号文件草稿",
    data.wechat.auto_publish ? "公众号自动发布开启" : "公众号发布需手动触发",
    data.scheduler.enabled ? "定时任务开启" : "手动任务",
  ];
  statusRow.innerHTML = chips.map((chip) => `<span>${chip}</span>`).join("");
}

async function loadConfigDefaults() {
  const payload = await requestJson("/api/config");
  defaultConfigData = payload.data;
  return payload.data;
}

async function loadConfig() {
  await loadConfigDefaults();
  fillConfigForm(effectiveConfigData());
}

async function loadTasks() {
  const payload = await requestJson("/api/tasks?limit=20");
  const tasks = payload.tasks;
  if (!tasks.length) {
    taskList.innerHTML = `<div class="empty-line">暂无任务记录</div>`;
    return;
  }
  taskList.innerHTML = tasks
    .map(
      (task) => `
        <div class="task-row">
          <span>${platformLabels[task.platform] || task.platform}</span>
          <strong>${task.mode}</strong>
          <em class="status-${task.status}">${task.status}</em>
          <small>${task.output_path || task.result_message || ""}</small>
        </div>
      `,
    )
    .join("");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const material = materialPayload();
  if (!material.title_hint || !material.raw_content) {
    showToast("标题和素材正文不能为空");
    return;
  }
  if (!material.target_platforms.length) {
    showToast("至少选择一个平台");
    return;
  }
  setLoading(true);
  try {
    const payload = await requestJson("/api/materials/generate", {
      method: "POST",
      body: JSON.stringify({ material, config: requestConfig() }),
    });
    renderArticles(payload.articles, payload.source);
    showToast("稿件已生成");
  } catch (error) {
    showToast(error.message);
  } finally {
    setLoading(false);
  }
});

exportAllButton.addEventListener("click", () => {
  if (currentArticles.length) {
    publishArticles(currentArticles.map((article) => article.id));
  }
});

pullRecentButton.addEventListener("click", async () => {
  try {
    const payload = await requestJson("/api/materials/pull_recent", {
      method: "POST",
      body: JSON.stringify({ limit: 5, config: requestConfig() }),
    });
    if (!payload.materials.length) {
      showToast("暂无最近数据");
      return;
    }
    fillForm(payload.materials[0]);
    showToast("已填入最近一条素材");
  } catch (error) {
    showToast(error.message);
  }
});

fillExampleButton.addEventListener("click", () => {
  fillForm(example);
  showToast("示例已填入");
});

clearButton.addEventListener("click", () => {
  form.reset();
  currentArticles = [];
  articleList.innerHTML = "";
  emptyState.classList.remove("hidden");
  exportAllButton.disabled = true;
  showToast("已清空");
});

refreshTasksButton.addEventListener("click", loadTasks);

settingsButton.addEventListener("click", async () => {
  configPanel.classList.toggle("hidden");
  if (!configPanel.classList.contains("hidden")) {
    try {
      await loadConfig();
    } catch (error) {
      showToast(error.message);
    }
  }
});

closeSettingsButton.addEventListener("click", () => {
  configPanel.classList.add("hidden");
});

configForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setConfigSaving(true);
  try {
    const nextConfig = compactConfig(configPayload(readLocalConfig()));
    writeLocalConfig(nextConfig);
    fillConfigForm(effectiveConfigData());
    await loadStatus();
    showToast("设置已保存在本浏览器");
  } catch (error) {
    showToast(error.message);
  } finally {
    setConfigSaving(false);
  }
});

loadStatus().catch((error) => showToast(error.message));
loadTasks().catch(() => {});
