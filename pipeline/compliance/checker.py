"""Compliance checking engine.

Orchestrates regex pre-checks and LLM semantic checks against platform
content guidelines. Falls back to regex-only mode when no LLM key is configured.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from openai import AsyncOpenAI

from .models import RegexRule
from .patterns import REGEX_RULES
from .prompts import build_compliance_system_prompt, build_compliance_user_prompt

LOGGER = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = int(os.getenv("CONTENT_LLM_TIMEOUT_SECONDS", "120"))
LLM_MAX_RETRIES = int(os.getenv("CONTENT_LLM_MAX_RETRIES", "1"))


def _build_llm_client() -> AsyncOpenAI | None:
    """Create an AsyncOpenAI client from environment / config, or None."""
    from pipeline.config import build_config

    cfg = build_config()
    if not cfg.has_llm:
        return None
    return AsyncOpenAI(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


# ── Regex pre-check ──────────────────────────────────────────────


def _regex_check(text: str, platform: str) -> list[dict[str, Any]]:
    """Run regex-based structural checks. Returns a list of risk dicts."""
    if not text:
        return []
    risks: list[dict[str, Any]] = []

    for rule in REGEX_RULES:
        # Platform filter: if rule.platforms is set and platform is not in it, skip
        if rule.platforms and platform and platform not in rule.platforms:
            continue
        for match in re.finditer(rule.pattern, text):
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

    return risks


# ── LLM semantic check ───────────────────────────────────────────


def _locate_term(text: str, term: str, offset: int = 0) -> tuple[int, int]:
    """Find the start/end position of `term` in `text`, searching from `offset`.

    Returns (start, end) or (-1, -1) if not found.
    """
    idx = text.find(term, offset)
    if idx == -1:
        return -1, -1
    return idx, idx + len(term)


def _locate_risks(text: str, llm_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate LLM-returned risk items with start/end positions in the original text."""
    annotated: list[dict[str, Any]] = []
    search_offset = 0

    for item in llm_items:
        term = str(item.get("term", "")).strip()
        if not term:
            continue
        start, end = _locate_term(text, term, search_offset)
        if start >= 0:
            search_offset = end  # prevent matching the same position for subsequent items
        annotated.append(
            {
                "term": term,
                "category": str(item.get("category", "违规内容")),
                "level": str(item.get("level", "medium")),
                "suggestion": str(item.get("suggestion", "")),
                "start": start,
                "end": end,
                "platform": item.get("platform", ""),
            }
        )

    return annotated


def _parse_llm_response(raw_text: str) -> list[dict[str, Any]]:
    """Parse the LLM JSON response into a list of risk dicts."""
    text = raw_text.strip()

    # Strip markdown code fences if present
    fenced_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced_match:
        text = fenced_match.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        LOGGER.warning("Failed to parse LLM compliance response as JSON: %s", text[:200])
        return []

    if not isinstance(parsed, list):
        # Some models might wrap in an object
        if isinstance(parsed, dict):
            for key in ("risks", "violations", "items", "results"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break
            else:
                return []
        else:
            return []

    results: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        if not term:
            continue
        level = str(item.get("level") or "medium").strip().lower()
        if level not in ("high", "medium", "low"):
            level = "medium"
        results.append(
            {
                "term": term,
                "category": str(item.get("category") or "违规内容").strip(),
                "level": level,
                "suggestion": str(item.get("suggestion") or "").strip(),
            }
        )

    return results


async def _llm_check_async(text: str, platform: str, client: AsyncOpenAI) -> list[dict[str, Any]]:
    """Run LLM-based semantic compliance check. Returns risk items (without positions)."""
    from pipeline.config import build_config

    cfg = build_config()

    system_prompt = build_compliance_system_prompt(platform)
    user_prompt = build_compliance_user_prompt(title="", content=text)

    response = await client.chat.completions.create(
        model=cfg.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,  # lower temperature for more consistent compliance checking
    )

    raw_text = response.choices[0].message.content or ""
    return _parse_llm_response(raw_text)


def _llm_check(text: str, platform: str) -> list[dict[str, Any]]:
    """Synchronous wrapper for LLM compliance check. Returns annotated risk items."""
    client = _build_llm_client()
    if client is None:
        return []

    try:
        llm_items = asyncio.run(_llm_check_async(text, platform, client))
        return _locate_risks(text, llm_items)
    except Exception:
        LOGGER.exception("LLM compliance check failed for platform=%s", platform)
        return []


# ── Merge & deduplicate ──────────────────────────────────────────


def _merge_risks(
    regex_risks: list[dict[str, Any]],
    llm_risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge regex and LLM risks, deduplicating by overlapping position.

    When both regex and LLM flag the same text span, keep the LLM result
    (which has richer category/suggestion) but preserve the regex position.
    """
    if not llm_risks:
        return regex_risks

    merged = list(regex_risks)

    for llm_risk in llm_risks:
        llm_start = llm_risk.get("start", -1)
        llm_end = llm_risk.get("end", -1)

        # Check for overlap with existing risks
        is_dup = False
        if llm_start >= 0 and llm_end >= 0:
            for existing in merged:
                ex_start = existing.get("start", -1)
                ex_end = existing.get("end", -1)
                # overlap if the intervals intersect
                if ex_start >= 0 and ex_end >= 0:
                    if llm_start < ex_end and llm_end > ex_start:
                        is_dup = True
                        break

        if not is_dup:
            merged.append(llm_risk)

    # Sort by position
    merged.sort(key=lambda r: (r.get("start", 0), r.get("end", 0)))
    return merged


def _compute_status(risks: list[dict[str, Any]], llm_available: bool) -> str:
    """Determine overall check status from risk list.

    - "high_risk": any high-level risk found
    - "review": any risk found, or LLM not available (uncertain)
    - "pass": no risks found and LLM available
    """
    has_high = any(r.get("level") == "high" for r in risks)
    if has_high:
        return "high_risk"

    if risks:
        return "review"

    if not llm_available:
        # Regex found nothing, but without LLM we can't be sure it's clean
        return "review"

    return "pass"


# ── Public API ───────────────────────────────────────────────────


def check_text(text: str, platform: str = "") -> dict[str, Any]:
    """Check a single text for platform compliance violations.

    Runs regex pre-checks synchronously, then attempts an LLM semantic
    check.  Falls back to regex-only when no LLM key is configured or
    the LLM call fails.

    Returns:
        dict with keys: status, risk_count, risks
    """
    value = text or ""

    # 1. Regex pre-check (always runs, no API call)
    regex_risks = _regex_check(value, platform)

    # 2. LLM semantic check (only if API key available)
    client = _build_llm_client()
    llm_available = client is not None
    llm_risks: list[dict[str, Any]] = []
    if llm_available:
        try:
            llm_items = asyncio.run(_llm_check_async(value, platform, client))
            llm_risks = _locate_risks(value, llm_items)
        except Exception:
            LOGGER.exception("LLM compliance check failed for platform=%s", platform)

    # 3. Merge and compute status
    risks = _merge_risks(regex_risks, llm_risks)

    return {
        "status": _compute_status(risks, llm_available),
        "risk_count": len(risks),
        "risks": risks,
    }


def check_articles(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Check multiple articles for compliance violations.

    Args:
        articles: list of dicts with keys: id, platform, title, content

    Returns:
        dict with keys: status, results
    """
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
        "status": "pass" if all(r["status"] == "pass" for r in results) else "review",
        "results": results,
    }
