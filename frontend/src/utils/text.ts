export function commaList(value: string): string[] {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function escapeHtml(value: string): string {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function sanitizeHtml(value: string): string {
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

export function markdownToHtml(value: string): string {
  const lines = String(value || "").split(/\r?\n/);
  const html: string[] = [];
  let listType: "ul" | "ol" | null = null;

  function closeList(nextType: "ul" | "ol" | null = null) {
    if (listType && listType !== nextType) {
      html.push(`</${listType}>`);
      listType = null;
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
      const level = Math.min(3, line.match(/^#+/)?.[0].length || 1);
      html.push(`<h${level}>${formatInlineMarkdown(line.replace(/^#{1,3}\s+/, ""))}</h${level}>`);
      return;
    }
    if (/^[-*]\s+/.test(line)) {
      closeList("ul");
      if (!listType) {
        html.push("<ul>");
        listType = "ul";
      }
      html.push(`<li>${formatInlineMarkdown(line.replace(/^[-*]\s+/, ""))}</li>`);
      return;
    }
    if (/^\d+[.)]\s+/.test(line)) {
      closeList("ol");
      if (!listType) {
        html.push("<ol>");
        listType = "ol";
      }
      html.push(`<li>${formatInlineMarkdown(line.replace(/^\d+[.)]\s+/, ""))}</li>`);
      return;
    }
    closeList();
    html.push(`<p>${formatInlineMarkdown(line)}</p>`);
  });
  closeList();
  return html.join("");
}

function formatInlineMarkdown(value: string): string {
  return restoreAllowedInlineHtml(escapeHtml(value))
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/_([^_]+)_/g, "<em>$1</em>");
}

function restoreAllowedInlineHtml(value: string): string {
  return value
    .replace(/&lt;(\/?)(strong|b|em|i|code)&gt;/gi, "<$1$2>")
    .replace(/&lt;br\s*\/?&gt;/gi, "<br>");
}

export function previewHtml(content: string, format: string): string {
  if (format.toLowerCase() === "html") {
    return sanitizeHtml(content);
  }
  return markdownToHtml(content);
}
