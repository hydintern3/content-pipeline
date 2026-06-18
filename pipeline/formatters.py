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
    tags = " ".join(f"#{tag}" for tag in keyword_tags(material, ["选址避坑", "招商运营", "企业服务"])[:6])
    title = f"{material.title_hint}，这个细节建议先看"
    content = "\n".join(
        [
            f"最近整理素材时，我发现一个挺适合运营、招商和办公选址场景的信息：{material.title_hint}。",
            "",
            compact_text(material.raw_content, 260),
            "",
            "我的判断是，先别急着把它当成一条普通消息发出去。更好的处理方式，是把里面真正能帮用户省时间、少踩坑的点拎出来。",
            "",
            "如果你平时要做企业服务、楼宇招商、办公租赁或招聘相关内容，这类素材可以重点看三个地方：信息是否真实、适合谁看、看完之后能做什么。",
            "",
            "发布前建议再补一张清晰配图，语气保持像经验分享，不要写成硬广。",
            "",
            tags,
        ]
    )
    return ArticleDraft("xiaohongshu", title, content, "text")


def zhihu_fallback(material: MaterialInput) -> ArticleDraft:
    title = f"如何看待「{material.title_hint}」这类信息对 B 端运营的价值？"
    content = "\n".join(
        [
            f"# {title}",
            "",
            "这个问题不能只看信息本身，要看它能不能帮助业务人员更快做判断。",
            "",
            "从素材来看，核心信息是：",
            "",
            compact_text(material.raw_content, 420),
            "",
            "对招商、物业、企业服务或招聘运营来说，这类内容的价值通常有三点。",
            "",
            "第一，它可以降低用户理解成本。B 端用户不太需要情绪化表达，更关心信息是否清楚、是否可信、是否能辅助决策。",
            "",
            "第二，它可以沉淀成可复用的内容资产。同一份素材可以拆成公众号长文、小红书笔记、头条干货和短视频脚本。",
            "",
            "第三，它适合和真实业务入口结合，但表达上要克制。不要急着导流，先把问题讲清楚，再给出温和的下一步建议。",
        ]
    )
    return ArticleDraft("zhihu", title, content, "markdown")


def zhihu_qa_fallback(material: MaterialInput) -> ArticleDraft:
    title = f"{material.title_hint}是否值得 B 端运营重点关注？"
    content = "\n".join(
        [
            f"# {title}",
            "",
            f"**问题：{title}**",
            "",
            "**回答：值得关注，但不建议直接当成宣传稿发布。**",
            "",
            "这类素材的价值不在于把信息原样搬运出去，而在于帮助读者更快判断：它和自己的业务、选址、招商、招聘或企业服务场景有没有关系。",
            "",
            "从现有素材看，核心信息可以先概括为：",
            "",
            compact_text(material.raw_content, 380),
            "",
            "为什么要这样处理？原因有三点。",
            "",
            "1. B 端读者更看重确定性。标题可以提问题，但正文要尽快给判断，不要绕太久。",
            "2. 业务素材需要转译。运营人员要把原始信息拆成适用人群、使用场景和下一步动作。",
            "3. 产品或工具可以出现，但最好放在解决方案里，而不是一上来就推荐。",
            "",
            "实际发布前，建议再补充一两个真实场景：比如谁会用到、什么时候用、能减少哪类沟通成本。这样内容会更像一条有判断的问答，而不是一篇泛泛的介绍。",
        ]
    )
    return ArticleDraft("zhihu_qa", title, content, "markdown")


def official_account_fallback(material: MaterialInput) -> ArticleDraft:
    title = material.title_hint
    escaped_title = html.escape(material.title_hint)
    escaped_body = html.escape(material.raw_content)
    paragraphs = [
        f"<h2>{escaped_title}</h2>",
        "<p>这是一条值得运营团队进一步整理的业务素材。它适合从信息价值、适用人群和后续动作三个角度展开，而不是简单转述。</p>",
        f"<p>{escaped_body}</p>",
        "<h3>为什么值得关注</h3>",
        "<p>B 端内容的重点不在于热闹，而在于帮助读者更快判断：这条信息和我的业务有没有关系，是否值得进一步了解。</p>",
        "<h3>可以怎么使用</h3>",
        "<p>发布前建议补充真实场景、配图和明确但克制的行动入口，让内容既能提供信息，也能自然承接后续咨询。</p>",
    ]
    return ArticleDraft("official_account", title, "\n".join(paragraphs), "html")


def toutiao_fallback(material: MaterialInput) -> ArticleDraft:
    title = f"{material.title_hint}：这几个信息点值得运营人员关注"
    content = "\n".join(
        [
            f"# {title}",
            "",
            "对 B 端运营来说，一条素材能不能发，关键不在于标题是否热闹，而在于信息是否清楚、读者是否看得懂、看完是否知道下一步。",
            "",
            "**核心信息：**",
            "",
            compact_text(material.raw_content, 360),
            "",
            "**可以提炼的价值：**",
            "",
            "1. 帮助招商、物业或企业服务人员快速判断线索价值。",
            "2. 适合改写成不同平台内容，覆盖图文、问答和短视频脚本。",
            "3. 如果补充真实案例或使用场景，内容可信度会更高。",
            "",
            "发布前建议再检查一遍敏感词和夸张表达，避免把业务介绍写成硬广。",
        ]
    )
    return ArticleDraft("toutiao", title, content, "markdown")


def shipinhao_fallback(material: MaterialInput) -> ArticleDraft:
    title = f"{material.title_hint}口播脚本"
    content = "\n".join(
        [
            "开场：",
            f"如果你平时要做招商、办公租赁或企业服务内容，{material.title_hint} 这类素材不要只当消息转发。",
            "",
            "主体：",
            compact_text(material.raw_content, 180),
            "",
            "它真正有用的地方，是能帮用户更快判断：这条信息和我的业务有没有关系，值不值得继续了解。",
            "",
            "结尾：",
            "发布前把重点、适用人群和下一步入口讲清楚，比堆一堆宣传词更有效。",
        ]
    )
    return ArticleDraft("shipinhao", title, content, "script")


def fallback_draft(material: MaterialInput, platform: str) -> ArticleDraft:
    if platform == "xiaohongshu":
        return xiaohongshu_fallback(material)
    if platform == "zhihu":
        return zhihu_fallback(material)
    if platform == "zhihu_qa":
        return zhihu_qa_fallback(material)
    if platform == "official_account":
        return official_account_fallback(material)
    if platform == "toutiao":
        return toutiao_fallback(material)
    if platform == "shipinhao":
        return shipinhao_fallback(material)
    raise ValueError(f"不支持的平台：{platform}")


def sanitize_filename(value: str, max_chars: int = 40) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    return (cleaned or "draft")[:max_chars]
