"""Build compliance-check prompts using condensed platform rule checklists.

Instead of loading full raw doc files into every LLM request, we maintain
concise checklists extracted from the documents — only covering rules that
can be detected from article text analysis.
"""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)

PLATFORM_NAMES: dict[str, str] = {
    "official_account": "微信公众号",
    "xiaohongshu": "小红书",
    "zhihu": "知乎",
    "zhihu_qa": "知乎",
    "toutiao": "今日头条",
    "shipinhao": "微信视频号",
}
SUPPORTED_COMPLIANCE_PLATFORMS = tuple(PLATFORM_NAMES.keys())
CORE_RULE_CATEGORIES = (
    "广告法极限词",
    "导流风险",
    "低俗色情",
    "虚假宣传",
    "未成年保护",
    "AI痕迹",
)

# ── Condensed rule checklists (extracted from doc/ files) ──────────
# Only includes rules detectable from text. Each rule is one line in
# "类别 | 严重度 | 具体规则描述" format.

_BASE_RULES = """广告法极限词 | high | 禁止使用"最""第一""唯一""国家级""最高级""最佳""顶级""首选""独家""绝对"等极限词
广告法极限词 | high | 禁止无权威依据的排名承诺，如"中国第一""行业第一"
虚假宣传 | high | 禁止夸大产品/服务效果，禁止不符合常理的效果承诺
虚假宣传 | high | 禁止编造案例、数据、用户反馈或政策结论
虚假宣传 | high | 禁止假借政府/学术机构/专家名义做推荐证明（品牌代言人除外）
虚假宣传 | high | 非医疗用品不得明示或暗示医疗功效
导流风险 | high | 禁止出现手机号、微信号、QQ号、邮箱等个人联系方式
导流风险 | medium | 禁止出现二维码或扫码引导（公众号/服务号除外）
导流风险 | medium | 禁止出现引导至第三方平台的链接或口令
导流风险 | medium | 禁止诱导用户关注、转发、点赞以获取奖励
低俗色情 | high | 禁止性行为描写、性暗示、性挑逗语言
低俗色情 | high | 禁止低俗配图描述、以低俗标题诱导点击
低俗色情 | high | 禁止传播色情网站、色情交易信息
暴力恐怖 | high | 禁止暴力血腥描写，禁止宣扬以暴制暴
暴力恐怖 | high | 禁止描述恐怖活动或教唆犯罪方法
赌博违法 | high | 禁止赌博平台、赌博技巧、博彩推荐信息
赌博违法 | high | 禁止组织聚众赌博、传授赌博方法
封建迷信 | medium | 禁止算命、占卜、看相、风水转运等迷信服务宣传
封建迷信 | medium | 禁止以迷信方式宣称治病消灾
医疗风险 | high | 禁止推广非正规医疗场所或未经验证的药品/保健品
医疗风险 | high | 禁止宣传违法违规医疗行为（代孕、胎儿性别鉴定等）
医疗风险 | high | 禁止夸大疗效，使用"根治""包治百病""神药"等表述
投资诱导 | high | 禁止荐股荐彩、推荐具体股票或博彩产品
投资诱导 | high | 禁止诱导投资话术（P2P、区块链、各种网赚等）
投资诱导 | high | 禁止使用"稳赚""保收益""预计涨幅"等收益承诺表述
标题党 | medium | 禁止标题使用夸张描述、制造耸人听闻效果
标题党 | medium | 禁止标题故意隐藏关键信息、扭曲原意
标题党 | medium | 禁止标题采用挑衅恐吓、强迫建议方式诱导点击
标题党 | medium | 禁止标题与正文内容严重不符
AI痕迹 | medium | 禁止出现"总之""综上所述""在这个快节奏的时代"等AI套话
AI痕迹 | medium | 禁止机械分点堆砌、句式重复、模板化表达
AI痕迹 | medium | 禁止多个平台共用同一套开头-过渡-正文-结尾模板
不友善内容 | medium | 禁止侮辱性词汇、歧视性言论（性别/地域/种族）
不友善内容 | medium | 禁止恶意贴标签、阴阳怪气挖苦讥讽
不友善内容 | medium | 禁止煽动群体对立、拉踩引战
谣言不实 | high | 禁止编造名人明星相关谣言
谣言不实 | high | 禁止传播已被官方辟谣的信息
谣言不实 | medium | 禁止使用"网传""据网友表示"等模糊来源表述
谣言不实 | high | 禁止编造食品安全、健康养生等生活领域不实信息
违规物品 | high | 禁止枪支弹药、毒品、违禁药品、管制刀具等违规物品信息
违规物品 | high | 禁止假币、伪造证件、走私物品等非法交易信息
抄袭侵权 | medium | 疑似洗稿：与他人作品主题/观点/结构高度相似
抄袭侵权 | medium | 未经授权大量引用他人原创内容
版权标识 | medium | 发布时事/政策类信息未标注权威信息来源
未成年保护 | high | 禁止涉及未成年人色情、暴力、欺凌内容
未成年保护 | high | 禁止披露未成年人隐私信息
未成年保护 | medium | 禁止诱导未成年人应援消费、非理性追星
网络水军 | medium | 疑似虚假测评、虚假体验软文
网络水军 | medium | 疑似组织刷评、刷分控评"""

# Platform-specific additions on top of base rules.
_PLATFORM_EXTRA: dict[str, str] = {
    "official_account": """胁迫分享 | high | 禁止"不转不是中国人""不点赞死全家"等胁迫性语言
商业广告 | medium | 商业推广内容须依法标明"广告"字样
商业广告 | medium | 禁止以介绍健康养生知识形式变相发布医疗广告
地图规范 | medium | 涉及中国地图须完整准确，不得使用未经审核的地图
诱骗点击 | medium | 禁止仿冒系统消息/红包到账等欺骗用户点击
信息溯源 | medium | 时事/政策类信息须在正文开头或结尾标注"来源：官方账号全称"
AI标识 | medium | 生成式AI内容须进行显著标识，禁止规避平台显式/隐式标识
恶意编辑 | medium | 禁止将正文内容隐藏在极小窗口内等非常规手段
群体对立 | medium | 禁止借热点话题挑起群体对立，煽动互撕谩骂""",

    "xiaohongshu": """交易导流 | high | 严格禁止发布个人联系方式（手机号/微信号/邮箱/地址）
交易导流 | high | 严格禁止发布其他平台链接、二维码、水印引导
交易导流 | medium | 禁止代购、转卖、拼单等营销倾向内容
真实体验 | medium | 产品分享须有真实体验经历，禁止纯官方宣传口吻
真实体验 | medium | 禁止编造公众人物社会谣言
科学常识 | medium | 禁止发布已被科学界或权威机构辟谣的错误信息
危险行为 | medium | 禁止易引人模仿的危险行为描述（危险驾驶等）
作弊行为 | high | 禁止批量发布、机器发布等非正常模式
未成年保护 | high | 未成年模式下严格限制相关敏感内容
违规物品 | high | 禁止翻墙软件、外挂程序等违法工具信息""",

    "zhihu": """AI创作 | medium | 使用AI辅助创作须主动添加"包含AI辅助创作"声明
AI创作 | medium | 须说明AI使用目的（文献调研/数据分析/文字润色等）
AI创作 | high | 禁止滥用AI大量发布生成、拼凑内容
AI创作 | high | 禁止利用AI生成文不对题、事实错误、虚假谣言信息
无来源信息 | medium | 禁止发布无可信来源的新闻资讯或社会事件信息
无来源信息 | medium | 禁止发布未经权威学术机构认可的学术突破/科学发现爆料
编造经历 | medium | 禁止胡编乱造虚假或引人误解的背景、情节
答非所问 | medium | 知乎问答模式禁止发布与问题无关的内容
低质内容 | medium | 禁止发布语言逻辑混乱、表意不明的内容
不良价值观 | medium | 禁止宣扬炫富、拜金主义等扭曲价值观
不良价值观 | medium | 禁止宣扬丧文化、过度渲染夸大社会问题贩卖焦虑
不良价值观 | medium | 禁止支持破坏他人家庭、鼓励一夜情/PUA等不良两性观念
饭圈乱象 | medium | 禁止诱导未成年人应援集资、非理性追星
饭圈乱象 | medium | 禁止粉丝互撕谩骂、拉踩引战、造谣攻击
冒充身份 | high | 禁止伪造身份、冒充他人或特定机构""",

    "toutiao": """旧闻新发 | medium | 禁止将已过时事件重新包装为新近发生
旧闻新发 | medium | 禁止刻意隐藏时间或用"今天""本月"等误导性时间词
无资质发布 | high | 未取得互联网新闻信息服务许可不得发布时政新闻
无资质发布 | high | 未取得健康类专业资质不得发布疾病治疗/用药指导
无资质发布 | high | 未取得财经类专业资质不得发布股票投资指导
标题夸张 | medium | 禁止夸张式/悬念式/强迫式标题
标题夸张 | medium | 禁止标题捏造不存在的人、物、情节、言论
封面低质 | medium | 封面/配图须与文章主体相关
内容低质 | medium | 禁止排版混乱、语意不明、逻辑混乱的低质内容
商业广告 | medium | 文章内引导消费须标明广告性质
流量作弊 | high | 禁止批量发布重复/无意义内容，禁止刷粉刷赞
引人不适 | medium | 禁止血腥暴力画面、密集恐惧、猎奇恶心恐怖内容
不良价值观 | medium | 禁止宣扬拜金主义、丧文化、自杀游戏
恶意营销 | high | 禁止推广微信时的变体写法（薇欣、微^信等）
恶意营销 | high | 禁止多个账号重复推荐同一产品或联系方式""",

    "shipinhao": """胁迫分享 | high | 禁止"不点赞死光光""不点赞不是中国人"等胁迫用语
胁迫分享 | medium | 禁止用夸张诅咒性质言语胁迫用户分享
诱导行为 | medium | 禁止利诱用户分享/关注/点赞/评论
诱导行为 | medium | 禁止诱导未成年人应援消费
虚假信息 | high | 禁止编造夸张猎奇故事冲击用户价值观
虚假信息 | medium | 禁止"卖惨式"推广商品、利用残障人士骗取同情
低俗内容 | high | 禁止衣着暴露/疑似裸体/性暗示行为
低俗内容 | medium | 禁止宣扬非主流婚恋观（婚外恋等）
不良内容 | medium | 禁止宣扬风水运势、伪科学、违背自然规律内容
不良内容 | medium | 禁止展示落后恶俗风俗习惯（婚闹、童养媳等）
刷量刷粉 | high | 禁止非正常手段获取虚假粉丝/点赞/评论数据
假冒身份 | high | 禁止冒用身份、使用虚假信息注册
不当营销 | high | 禁止荐股/推荐金融产品等投资咨询活动
不当营销 | high | 禁止利用视频号实施诈骗传销等违法犯罪
未成年保护 | high | 禁止未成年人吸烟/饮酒/吸毒行为内容
未成年保护 | high | 禁止利用未成年人进行恶俗表演
不规范医疗 | high | 禁止不符合诊疗规范的医疗科普内容
不规范医疗 | medium | 禁止医疗科普中片面/夸大描述疗效
不规范医疗 | medium | 禁止通过医疗内容进行营销引流""",
}

# zhihu_qa uses the same rules as zhihu
_PLATFORM_EXTRA["zhihu_qa"] = _PLATFORM_EXTRA["zhihu"]


def get_platform_name(platform: str) -> str:
    return PLATFORM_NAMES.get(platform, platform)


def _build_checklist(platform: str) -> str:
    """Build a condensed checklist for the given platform."""
    extra = _PLATFORM_EXTRA.get(platform, "")
    if extra:
        return _BASE_RULES + "\n" + extra
    return _BASE_RULES


def get_compliance_checklist(platform: str) -> str:
    """Return the condensed compliance checklist for tests and diagnostics."""
    return _build_checklist(platform)


def build_compliance_system_prompt(platform: str) -> str:
    """Build the system prompt with condensed platform rules."""
    checklist = _build_checklist(platform)
    platform_name = get_platform_name(platform)

    return f"""你是 {platform_name} 平台的内容合规审核员。按以下规则清单逐条检查文章内容。

审查规则清单（格式: 类别 | 严重度 | 规则）：
---
{checklist}
---

审核要求：
1. 逐条对照上述清单，检查文章是否违规
2. 只报告你确信的违规项，不确定的不报
3. 违规输出 JSON 数组，每项必须包含：
   - term: 文章中违规的原文片段（一字不差地摘录）
   - category: 违规类别（使用清单中的类别名）
   - level: high / medium / low
   - suggestion: 具体、可操作的修改建议（用中文）
4. 如果文章没有违规，返回空数组 []
5. 只输出 JSON 数组，不要 Markdown 代码块，不要解释"""


def build_compliance_user_prompt(title: str, content: str) -> str:
    """Build the user prompt containing the article to check."""
    return f"""检查以下文章：

标题：{title}
正文：
{content}

直接输出 JSON 数组（无代码块包裹）："""
