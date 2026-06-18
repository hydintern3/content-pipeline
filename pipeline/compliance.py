from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ComplianceRule:
    term: str
    category: str
    level: str
    suggestion: str
    platforms: set[str] | None = None

# 暂时使用以下规则
RULES = [
    ComplianceRule("最", "广告法极限词", "high", "避免绝对化表达，可改为“较为”“更适合”等相对表述。"),
    ComplianceRule("第一", "广告法极限词", "high", "如无权威依据，不要使用排名承诺。"),
    ComplianceRule("唯一", "广告法极限词", "high", "改为“一个选择”“可选方案”。"),
    ComplianceRule("保证", "承诺风险", "high", "避免结果承诺，改为“有助于”“可辅助”。"),
    ComplianceRule("稳赚", "金融/收益风险", "high", "删除收益承诺。"),
    ComplianceRule("必然", "夸大承诺", "medium", "改为“可能”“通常”“在部分场景下”。"),
    ComplianceRule("立即扫码", "导流风险", "medium", "改为“可在对应入口了解”。"),
    ComplianceRule("加微信", "导流风险", "medium", "平台内容中避免直接联系方式。"),
    ComplianceRule("私信领取", "导流风险", "low", "小红书可温和使用，其他平台建议弱化。", {"official_account", "zhihu", "toutiao"}),
    ComplianceRule("二维码", "导流风险", "medium", "避免直接出现二维码导流描述。"),
    ComplianceRule("官方指定", "虚假背书", "high", "无正式授权时删除。"),
]

AI_PHRASES = [
    "总之",
    "综上所述",
    "在这个快节奏的时代",
    "赋能",
    "打造闭环",
    "降本增效新范式",
    "开启新篇章",
]


def check_text(text: str, platform: str = "") -> dict[str, Any]:
    value = text or ""
    risks: list[dict[str, Any]] = []

    for rule in RULES:
        if rule.platforms and platform and platform not in rule.platforms:
            continue
        for match in re.finditer(re.escape(rule.term), value, re.IGNORECASE):
            risks.append(
                {
                    "term": match.group(0),
                    "category": rule.category,
                    "level": rule.level,
                    "suggestion": rule.suggestion,
                    "start": match.start(),
                    "end": match.end(),
                    "platform": platform,
                }
            )

    for phrase in AI_PHRASES:
        for match in re.finditer(re.escape(phrase), value, re.IGNORECASE):
            risks.append(
                {
                    "term": match.group(0),
                    "category": "AI 痕迹",
                    "level": "medium",
                    "suggestion": "删除套话，改成具体场景、判断或动作建议。",
                    "start": match.start(),
                    "end": match.end(),
                    "platform": platform,
                }
            )

    status = "pass"
    if any(item["level"] == "high" for item in risks):
        status = "high_risk"
    elif risks:
        status = "review"

    return {
        "status": status,
        "risk_count": len(risks),
        "risks": risks,
    }


def check_articles(articles: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for article in articles:
        platform = str(article.get("platform") or "")
        title = str(article.get("title") or "")
        content = str(article.get("content") or "")
        result = check_text(f"{title}\n{content}", platform)
        result["article_id"] = article.get("id")
        result["platform"] = platform
        results.append(result)

    return {
        "status": "pass" if all(item["status"] == "pass" for item in results) else "review",
        "results": results,
    }
