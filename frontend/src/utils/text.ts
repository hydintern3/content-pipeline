import type { ComplianceRisk } from "@/types";

export function commaList(value: string): string[] {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function escapeHtml(value: string): string {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
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

export function previewHtmlWithRisks(content: string, format: string, risks: ComplianceRisk[] = []): string {
  const safeHtml = previewHtml(content, format);
  const validRisks = risks.filter((risk) => risk.term?.trim());
  if (!validRisks.length) {
    return safeHtml;
  }

  const template = document.createElement("template");
  template.innerHTML = safeHtml;
  const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  let node = walker.nextNode();
  while (node) {
    const parent = node.parentElement;
    if (!parent?.closest("mark, code, pre, script, style")) {
      textNodes.push(node as Text);
    }
    node = walker.nextNode();
  }

  textNodes.forEach((textNode) => {
    const text = textNode.nodeValue || "";
    const fragment = document.createDocumentFragment();
    let cursor = 0;

    while (cursor < text.length) {
      const match = findNextRiskMatch(text, validRisks, cursor);
      if (!match) {
        fragment.append(document.createTextNode(text.slice(cursor)));
        break;
      }

      if (match.index > cursor) {
        fragment.append(document.createTextNode(text.slice(cursor, match.index)));
      }

      const marked = document.createElement("mark");
      const level = ["high", "medium", "low"].includes(match.risk.level) ? match.risk.level : "low";
      marked.className = `compliance-risk risk-${level}`;
      marked.dataset.riskCategory = match.risk.category || "疑似风险";
      marked.dataset.riskLevel = match.risk.level || "unknown";
      marked.dataset.riskSuggestion = match.risk.suggestion || "建议人工复核后改写";
      marked.textContent = text.slice(match.index, match.index + match.risk.term.length);
      fragment.append(marked);
      cursor = match.index + match.risk.term.length;
    }

    textNode.parentNode?.replaceChild(fragment, textNode);
  });

  return template.innerHTML;
}

interface RiskMatch {
  index: number;
  risk: ComplianceRisk;
}

function findNextRiskMatch(text: string, risks: ComplianceRisk[], fromIndex: number): RiskMatch | null {
  let best: { index: number; risk: ComplianceRisk } | null = null;
  const haystack = text.toLowerCase();

  for (const risk of risks) {
    const term = risk.term.trim();
    if (!term) {
      continue;
    }
    const index = haystack.indexOf(term.toLowerCase(), fromIndex);
    if (index < 0) {
      continue;
    }
    if (
      !best ||
      index < best.index ||
      (index === best.index && term.length > best.risk.term.length)
    ) {
      best = { index, risk };
    }
  }

  return best;
}
