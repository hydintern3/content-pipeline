from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from openai import AsyncOpenAI

from .config import AppConfig
from .formatters import fallback_draft
from .schemas import ArticleDraft, MaterialInput


LOGGER = logging.getLogger(__name__)
LLM_TIMEOUT_SECONDS = int(os.getenv("CONTENT_LLM_TIMEOUT_SECONDS", "120"))
LLM_MAX_RETRIES = int(os.getenv("CONTENT_LLM_MAX_RETRIES", "1"))

PLATFORM_FORMATS = {
    "xiaohongshu": "text",
    "zhihu": "markdown",
    "zhihu_qa": "markdown",
    "official_account": "html",
    "toutiao": "markdown",
    "shipinhao": "script",
}

PLATFORM_RULES = {
    "official_account": """
公众号：
- 账号：商引羚航，品牌官方发声端口；即使账号暂未注册，也按未来官方服务号口径生成。
- 运营方向：全域流量收口、官方服务承接、私域沉淀、小程序最终转化。
- 人设：官方一站式企业数字化供需服务平台，可信、稳重、服务导向，不写个人口吻。
- 内容范围：深度行业分析、平台功能解读、成功案例复盘、行业白皮书、行业报告。
- 文风：专业、沉稳、客观，有官方可信度；段落式表达为主，可少量分点，但不要列表堆砌。
- 篇幅：默认 800-1500 字；如果素材很短，可生成精简版，但逻辑必须完整。
- 标题：平实但有吸引力，拒绝标题党、夸大承诺和极限词。
- 正文：可自然承接商引小程序、供需服务、企业数字化能力，但必须像官方服务说明或行业分析，避免硬广、强制引导、二维码、联系方式和诱导性话术。
- 输出格式：基础 HTML，仅使用 h2、h3、p、ul、li、strong 等安全标签。
""",
    "xiaohongshu": """
小红书：
- 账号：Jade一城探访记。
- 运营方向：公域泛流量种草，抓取精准 B 端刚需客户；标题要带痛点，轻量化图文/短笔记，适合搜索流量。
- 人设：温柔专业的行业干货博主，接地气、好读易懂。
- 文风：第一人称、轻量化、场景化、痛点直击，拒绝官方腔、教科书口吻和长篇大论。
- 篇幅：默认 250-600 字，拒绝长篇大论。
- 标题：痛点直击、场景化种草、颜值排版，拒绝标题党、夸大承诺和极限词。
- 内容：使用较多 emoji ，但不要花哨；轻量化图文 / 短笔记、场景化种草、痛点直击、颜值排版、搜索流量极强。
- 合规：不写硬广、二维码、联系方式、夸张承诺和明显导流。
- 结尾：自然引导收藏、评论或私信领取资料。
- 输出：正文末尾生成 3-6 个垂直精准话题标签。
""",
    "zhihu": """
知乎：
- 账号：Jade一城探访。
- 运营方向：高知、专业问答、深度长文，建立行业权威背书，沉淀可长期搜索的长尾流量。
- 人设：理性客观、无营销感，输出底层逻辑和行业深度分析，全程不硬推产品。
- 内容范围：上海办公室租赁、写字楼招商、企业选址逻辑、行业数字化转型、园区招商痛点等专业问题。
- 定位：问答回答或专栏长文，默认以“回答一个具体问题”的方式输出。
- 文风：逻辑严谨、分点论述、无网红话术、纯专业干货，偏行业分析、问题解答和深度观点。
- 篇幅：问答默认 600-900 字；素材足够时可接近 1000 字。
- 逻辑：先界定问题，再给判断和依据，最后给可执行建议。
- 合规：弱营销，产品植入要隐藏在解决方案里，避免夸张话术和广告感。
- 输出格式：Markdown。
""",
    "zhihu_qa": """
知乎 Q&A：
- 账号：Jade一城探访。
- 运营方向：专业问答占位和长尾搜索沉淀，用一个具体问题建立专业可信度。
- 人设：理性客观、无营销感，像行业从业者在拆解底层逻辑。
- 内容范围：上海哪里租办公室比较好、不同规模企业怎么选址、写字楼招商数字化、园区招商痛点等。
- 定位：独立问答式内容，像在知乎回答一个真实业务问题，不写成专栏文章。
- 标题：必须是问题句，优先使用“如何看待 / 为什么 / 是否值得 / 应该怎么做”这类具体问法。
- 结构：正文必须按“问题 + 回答”组织；先用 1-2 句话直接回答，再解释原因，最后给可执行建议。
- 文风：理性、克制、有判断，避免营销腔、鸡汤腔和空泛概念。
- 篇幅：默认 500-900 字；素材不足时宁可短一点，也不要编造案例、数据或政策结论。
- 产品植入：只能作为解决问题的工具或场景入口自然出现，不能写成广告推荐。
- 输出格式：Markdown，可使用二级标题和编号列表，但不要堆砌。
""",
    "toutiao": """
今日头条：
- 账号：一城探访手记。
- 运营方向：抓取同城精准行业流量，承接高意向企业决策者；适合信息流被动阅读。
- 人设：客观行业观察员，不走精致风，侧重行业行情、市场分析和完整复盘。
- 内容范围：本地写字楼空置率、租金走势、园区政策解读、企业选址逻辑、招商痛点拆解、园区线下拓客和渠道合作。
- 定位：综合信息流内容，兼顾专业和可读性，适合中长图文、行业观点、同城流量和行情解读。
- 文风：通俗直白、段落清晰、干货密度高，不用花哨排版，开篇直接给重点。
- 篇幅：默认 500-1000 字。
- 标题：适度吸睛，但拒绝低俗、夸大、标题党。
- 正文：段落拆分合理，重点内容可用 Markdown 加粗，避免虚假宣传和广告违规词。
- 输出格式：Markdown。
""",
    "shipinhao": """
视频号：
- 定位：短视频口播脚本，适配 15-60 秒视频。
- 文风：短句、上口、可朗读，不写复杂长句。
- 结构：开头 3 秒给痛点或钩子；中段讲清价值；结尾自然引导了解或收藏。
- 字数：默认 30 秒脚本，约 120-180 字；如果素材复杂，最多控制在 250 字内。
- 合规：避免硬广台词、夸大承诺、诱导性话术和违规词。
- 输出格式：script，按“开场 / 主体 / 结尾”分段。
""",
}

ANTI_AI_RULES = """
去 AI 化和防模板化硬性要求：
- 禁止使用“总之、综上所述、在这个快节奏的时代、赋能、打造闭环、降本增效新范式、开启新篇章”等明显 AI 套话。
- 禁止统一开头、统一结尾、句式重复、机械分点、排比堆砌。
- 不要把每个平台都写成同一套“开头-过渡-正文-结尾”模板。
- 同一素材在不同平台必须换切入角度，可从痛点、场景、案例、经验、避坑、教程中选择。
- 优先自然段落行文，只有平台适合时才使用编号列表。
- 用词正式但不晦涩，避免空泛抒情，多写具体业务判断、实操建议和读者能采取的下一步。
"""

B2B_CONTEXT_RULES = """
B 端业务语境：
- 内容面向物业、企业主、行政、HR、招商负责人、园区/楼宇运营人员。
- 适用内容包括招商、企业选址、办公租赁、企业招聘、职场干货、小程序功能教程、行业解读、避坑指南、客户案例。
- 专业度要贴近商业地产、物业管理、办公租赁、企业服务和招聘场景。
- 可以使用“招商线索、楼宇空置、企业选址、办公租赁、企业服务、物业管理、供需信息、转化链路、运营素材”等行业表达。
- 不要编造具体数据、客户名称、政策结论或平台规则；素材没有的信息只能保守表达。
"""

COMPLIANCE_RULES = """
合规和风控要求：
- 规避广告法极限词、夸大承诺、虚假宣传、诱导转发、强制导流、联系方式和二维码描述。
- 不写“第一、唯一、保证、必然、稳赚、官方指定”等高风险表达。
- 如果素材中出现联系方式、二维码、强导流内容，要改写为“可在对应入口了解”这类温和表达。
- 输出应是可进入人工小幅润色的初稿，不要在正文外额外解释风险。
"""


def build_system_prompt() -> str:
    return f"""你是资深 B 端新媒体内容运营专家，熟悉商业地产、物业管理、办公租赁、企业服务、招聘和小程序运营。

你的任务是把同一份业务素材，改写为多个平台可直接进入人工微调的文案初稿。

{ANTI_AI_RULES}

{B2B_CONTEXT_RULES}

{COMPLIANCE_RULES}

严格输出 JSON 对象，不要 Markdown 代码块，不要解释，不要输出请求的平台之外的内容。
每个平台对象必须包含 title、content、format 三个字段。"""


def build_user_prompt(material: MaterialInput) -> str:
    platforms = material.target_platforms
    keywords = ", ".join(material.keywords) or "无"
    platform_rules = "\n".join(
        f"## {platform}\n{PLATFORM_RULES.get(platform, '按该平台常见内容生态生成。').strip()}"
        for platform in platforms
    )
    example_items = ",\n  ".join(
        f'"{platform}": {{"title": "...", "content": "...", "format": "{PLATFORM_FORMATS.get(platform, "text")}"}}'
        for platform in platforms
    )

    return f"""请基于以下素材生成平台文案。

目标平台：{", ".join(platforms)}
标题/选题提示：{material.title_hint}
关键词：{keywords}
素材正文：
{material.raw_content}

平台专属规则：
{platform_rules}

生成要求：
- 每个平台必须独立构思标题、开头、结构和表达方式，不要简单复用同一段内容。
- 标题和正文都要贴合对应平台的阅读习惯、排版习惯和流量逻辑。
- 如果素材偏产品或工具介绍，必须自然植入，不能写成硬广。
- 如果素材信息不足，保持克制，不要编造案例、数据、政策或用户反馈。
- 输出字段 format 必须使用示例中的格式值。

返回 JSON 示例：
{{
  {example_items}
}}"""


def material_for_platform(material: MaterialInput, platform: str) -> MaterialInput:
    return MaterialInput(
        title_hint=material.title_hint,
        raw_content=material.raw_content,
        keywords=material.keywords,
        target_platforms=[platform],
        image_paths=material.image_paths,
        source_type=material.source_type,
        source_ref=material.source_ref,
    )


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
        content_format = str(item.get("format") or PLATFORM_FORMATS.get(platform, "text")).strip()
        if not title or not content:
            raise ValueError(f"大模型返回的 {platform} 内容不完整")
        drafts[platform] = ArticleDraft(platform, title, content, content_format)
    return drafts


async def generate_with_llm(material: MaterialInput, config: AppConfig) -> dict[str, ArticleDraft]:
    client = AsyncOpenAI(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )
    response = await client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(material)},
        ],
        response_format={"type": "json_object"},
        temperature=0.82,
    )
    raw_text = response.choices[0].message.content or ""
    return parse_llm_json(raw_text, material.target_platforms)


async def generate_platform_with_llm(
    client: AsyncOpenAI,
    material: MaterialInput,
    config: AppConfig,
    platform: str,
) -> ArticleDraft:
    platform_material = material_for_platform(material, platform)
    response = await client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(platform_material)},
        ],
        response_format={"type": "json_object"},
        temperature=0.82,
    )
    raw_text = response.choices[0].message.content or ""
    return parse_llm_json(raw_text, [platform])[platform]


async def generate_each_platform_with_llm(material: MaterialInput, config: AppConfig) -> dict[str, ArticleDraft]:
    client = AsyncOpenAI(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )

    async def _generate_one(platform: str) -> tuple[str, ArticleDraft]:
        try:
            return platform, await generate_platform_with_llm(client, material, config, platform)
        except Exception as exc:
            LOGGER.exception("LLM generation failed for %s; using fallback template: %s", platform, exc)
            return platform, fallback_draft(material, platform)

    results = await asyncio.gather(*(_generate_one(p) for p in material.target_platforms))
    return dict(results)


def generate_drafts(material: MaterialInput, config: AppConfig) -> tuple[str, dict[str, ArticleDraft]]:
    if config.has_llm:
        try:
            return "llm", asyncio.run(generate_each_platform_with_llm(material, config))
        except Exception as exc:
            LOGGER.exception("LLM generation failed after retries; using fallback templates: %s", exc)

    return (
        "fallback_template",
        {platform: fallback_draft(material, platform) for platform in material.target_platforms},
    )
