"""Regex patterns for structural compliance violations.

These patterns catch obvious structural violations that regex handles
faster and more reliably than an LLM: phone numbers, WeChat IDs, URLs,
email addresses, and other contact/redirect patterns.
"""

from __future__ import annotations

from .models import RegexRule

REGEX_RULES: list[RegexRule] = [
    # ── 导流 / 联系方式 ──────────────────────────────────────────
    RegexRule(
        id="contact_phone",
        pattern=r"1[3-9]\d{9}",
        category="导流风险",
        level="medium",
        suggestion="平台内容中避免出现手机号，改为'可通过站内私信联系'等合规表达。",
        description="中国大陆手机号",
    ),
    RegexRule(
        id="contact_wechat_id",
        pattern=r"(?:微信[号]?|VX|vx|wx|WeChat)\s*[:：]\s*\w+",
        category="导流风险",
        level="medium",
        suggestion="平台内容中避免直接留微信号，改为引导用户关注官方账号或使用平台私信功能。",
        description="微信号引导",
        platforms=frozenset({"xiaohongshu", "toutiao", "zhihu", "zhihu_qa"}),  # 公众号/视频号是腾讯系，微信号可接受
    ),
    RegexRule(
        id="contact_qq",
        pattern=r"(?:QQ|qq|Qq)\s*[:：]?\s*\d{5,12}",
        category="导流风险",
        level="medium",
        suggestion="平台内容中避免直接留 QQ 号，改为引导用户使用官方联系方式。",
        description="QQ号",
        platforms=frozenset({"xiaohongshu", "toutiao", "zhihu", "zhihu_qa", "shipinhao"}),
    ),
    RegexRule(
        id="contact_email",
        pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        category="导流风险",
        level="medium",
        suggestion="平台内容中避免直接留邮箱，改为引导用户通过官方渠道联系。",
        description="邮箱地址",
    ),
    RegexRule(
        id="contact_url",
        pattern=r"https?://[^\s一-鿿。，！？；：、]+",
        category="导流风险",
        level="low",
        suggestion="外部链接可能被平台限流或屏蔽，建议改为'可在对应入口了解'等温和引导。",
        description="外部URL链接",
    ),
    RegexRule(
        id="contact_qrcode_keyword",
        pattern=r"扫码[添加加]|扫一扫|二维码",
        category="导流风险",
        level="medium",
        suggestion="避免直接出现二维码导流描述，改为引导用户通过平台内置功能获取信息。",
        description="二维码关键词",
        platforms=frozenset({"xiaohongshu", "zhihu", "zhihu_qa", "toutiao"}),  # 公众号可放二维码
    ),
    # ── 胁迫/诱导分享 ────────────────────────────────────────────
    RegexRule(
        id="forced_share",
        pattern=r"不[转转发送]不是|不点赞.{0,8}死|不.{0,5}不是中国人|转发.{0,5}保平安",
        category="胁迫分享",
        level="high",
        suggestion="禁止使用胁迫性语言诱导用户分享或点赞，应删除相关表述。",
        description="胁迫分享话术",
        platforms=frozenset({"official_account", "shipinhao"}),  # 微信生态特有禁止
    ),
]
