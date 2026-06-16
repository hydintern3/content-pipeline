from __future__ import annotations

import html
import re

from .schemas import ArticleDraft, MaterialInput


def compact_text(value: str, max_chars: int = 80) -> str:
    cleaned = " ".join((value or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars].rstrip()}..."


def keyword_tags(material: MaterialInput, defaults: list[str]) -> list[str]:
    tags = [*material.keywords, *defaults]
    return list(dict.fromkeys(tag for tag in tags if tag))


def xiaohongshu_fallback(material: MaterialInput) -> ArticleDraft:
    tags = " ".join(f"#{tag}" for tag in keyword_tags(material, ["运营工具", "职场效率", "商业增长"]))
    title = f"{material.title_hint}｜值得收藏"
    content = "\n".join(
        [
            f"🔥 {material.title_hint}",
            "",
            "最近整理到一个很适合运营/招商/职场人看的信息：",
            compact_text(material.raw_content, 260),
            "",
            "✅ 适合谁看",
            "需要快速理解业务机会、企业信息或内容素材的人。",
            "",
            "📌 可以怎么用",
            "先看核心信息，再结合自己的场景判断是否值得跟进。",
            "",
            tags,
        ]
    )
    return ArticleDraft("xiaohongshu", title, content, "text")


def zhihu_fallback(material: MaterialInput) -> ArticleDraft:
    title = f"如何看待「{material.title_hint}」？"
    content = "\n".join(
        [
            f"问题：如何看待「{material.title_hint}」？",
            "",
            "答：可以从信息价值和实际应用两个层面来看。",
            "",
            "一、核心信息",
            material.raw_content,
            "",
            "二、为什么值得关注",
            "这类内容的价值不在于单点信息本身，而在于它能帮助运营、招商或业务人员更快形成判断。",
            "",
            "三、行动建议",
            "建议先核验关键事实，再根据目标用户、地域、行业和时效性决定是否发布或跟进。",
        ]
    )
    return ArticleDraft("zhihu", title, content, "markdown")


def official_account_fallback(material: MaterialInput) -> ArticleDraft:
    title = material.title_hint
    escaped_title = html.escape(material.title_hint)
    paragraphs = [
        f"<h2>{escaped_title}</h2>",
        "<p>今天这条信息值得运营团队重点关注。</p>",
        f"<p>{html.escape(material.raw_content)}</p>",
        "<h3>为什么重要</h3>",
        "<p>它可以帮助团队把零散素材转化为可阅读、可分发、可沉淀的内容资产。</p>",
        "<h3>下一步建议</h3>",
        "<p>发布前建议补充真实案例、配图和明确的行动入口，提升读者信任感。</p>",
    ]
    return ArticleDraft("official_account", title, "\n".join(paragraphs), "html")


def fallback_draft(material: MaterialInput, platform: str) -> ArticleDraft:
    if platform == "xiaohongshu":
        return xiaohongshu_fallback(material)
    if platform == "zhihu":
        return zhihu_fallback(material)
    if platform == "official_account":
        return official_account_fallback(material)
    raise ValueError(f"不支持的平台：{platform}")


def sanitize_filename(value: str, max_chars: int = 40) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    return (cleaned or "draft")[:max_chars]

