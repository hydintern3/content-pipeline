import { describe, expect, it } from "vitest";

import { commaList, escapeHtml, markdownToHtml } from "./text";

describe("text utilities", () => {
  it("normalizes comma separated values", () => {
    expect(commaList(" xiaohongshu, zhihu ,, toutiao ")).toEqual([
      "xiaohongshu",
      "zhihu",
      "toutiao",
    ]);
  });

  it("escapes unsafe html characters", () => {
    expect(escapeHtml(`<img src="x" onerror='alert(1)'>`)).toBe(
      "&lt;img src=&quot;x&quot; onerror=&#039;alert(1)&#039;&gt;",
    );
  });

  it("renders basic markdown without passing raw script tags through", () => {
    expect(markdownToHtml("# Title\n- **A** item")).toBe("<h1>Title</h1><ul><li><strong>A</strong> item</li></ul>");
  });
});
