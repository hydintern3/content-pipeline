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
const toast = document.querySelector("#toast");

let currentArticles = [];

const platformLabels = {
  xiaohongshu: "小红书",
  zhihu: "知乎",
  official_account: "公众号",
};

const example = {
  title_hint: "商引-商机地图小程序上线",
  raw_content:
    "商引小程序可以通过地图精准定位企业，查看第三方信用档案、楼宇出租信息和周边商业线索。适合中小企业主、职场人、招商主管和物业管理者使用，帮助他们更快找到靠谱企业和业务机会。",
  keywords: "企业服务, 职场效率, 招商",
  image_paths: "",
};

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
  const body = { article_ids: articleIds };
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
  const payload = await requestJson("/api/config/status");
  const data = payload.data;
  const chips = [
    data.llm.configured ? "LLM 已配置" : "模板模式",
    data.database.configured ? "外部数据库已配置" : "未配置外部数据库",
    data.wechat.configured ? "公众号已配置" : "公众号文件草稿",
    data.wechat.auto_publish_enabled ? "公众号自动发布开启" : "公众号发布需手动触发",
    data.scheduler.enabled ? "定时任务开启" : "手动任务",
  ];
  statusRow.innerHTML = chips.map((chip) => `<span>${chip}</span>`).join("");
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
      body: JSON.stringify({ material }),
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
      body: JSON.stringify({ limit: 5 }),
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

loadStatus().catch((error) => showToast(error.message));
loadTasks().catch(() => {});
