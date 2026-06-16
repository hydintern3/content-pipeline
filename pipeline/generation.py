from __future__ import annotations

import asyncio
import json
import logging
import re

from openai import AsyncOpenAI

from .config import AppConfig
from .formatters import fallback_draft
from .schemas import ArticleDraft, MaterialInput


LOGGER = logging.getLogger(__name__)
LLM_TIMEOUT_SECONDS = 45


def build_system_prompt() -> str:
    return (
        "你是资深中文内容运营专家。请把同一份素材改写成多个平台适配稿。"
        "必须严格输出 JSON 对象，不要 Markdown 代码块，不要解释。"
        "每个平台对象包含 title、content、format 三个字段。"
    )


def build_user_prompt(material: MaterialInput) -> str:
    platforms = ", ".join(material.target_platforms)
    keywords = ", ".join(material.keywords) or "无"
    return f"""请基于素材生成平台文案。

目标平台：{platforms}
标题提示：{material.title_hint}
关键词：{keywords}
素材正文：
{material.raw_content}

平台要求：
- xiaohongshu：标题吸睛，正文轻盈，允许 emoji 和话题标签，适合复制到小红书。
- zhihu：结构理性，弱营销，适合回答或专栏摘要，可用 Markdown。
- official_account：适合微信公众号草稿，输出基础 HTML，避免复杂样式。

返回 JSON 示例：
{{
  "xiaohongshu": {{"title": "...", "content": "...", "format": "text"}},
  "zhihu": {{"title": "...", "content": "...", "format": "markdown"}},
  "official_account": {{"title": "...", "content": "...", "format": "html"}}
}}"""


def parse_llm_json(raw_text: str, platforms: list[str]) -> dict[str, ArticleDraft]:
    text = raw_text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced_match:
        text = fenced_match.group(1).strip()

    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("大模型返回内容不是 JSON 对象")

    drafts: dict[str, ArticleDraft] = {}
    for platform in platforms:
        item = parsed.get(platform)
        if not isinstance(item, dict):
            raise ValueError(f"大模型返回缺少 {platform}")
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        content_format = str(item.get("format") or "text").strip()
        if not title or not content:
            raise ValueError(f"大模型返回的 {platform} 内容不完整")
        drafts[platform] = ArticleDraft(platform, title, content, content_format)
    return drafts


async def generate_with_llm(material: MaterialInput, config: AppConfig) -> dict[str, ArticleDraft]:
    client = AsyncOpenAI(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        timeout=LLM_TIMEOUT_SECONDS,
    )
    response = await client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(material)},
        ],
        response_format={"type": "json_object"},
        temperature=0.75,
    )
    raw_text = response.choices[0].message.content or ""
    return parse_llm_json(raw_text, material.target_platforms)


def generate_drafts(material: MaterialInput, config: AppConfig) -> tuple[str, dict[str, ArticleDraft]]:
    if config.has_llm:
        try:
            return "llm", asyncio.run(generate_with_llm(material, config))
        except Exception:
            LOGGER.exception("LLM generation failed; using fallback templates")

    return (
        "fallback_template",
        {platform: fallback_draft(material, platform) for platform in material.target_platforms},
    )

