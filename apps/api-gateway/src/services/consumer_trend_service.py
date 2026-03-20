"""
消费趋势知识库服务（Consumer Trend Knowledge Service）

将 SMEI 2025 用户词典 + 全球消费热词内化为屯象OS的动态知识库。

核心能力：
  1. 27个消费趋势词结构化管理（6维度分类）
  2. 与餐饮场景的关联映射（趋势词→菜品/营销/服务策略）
  3. 热度追踪 + 趋势演变（支持每日更新）
  4. 供各Agent调用（私域Agent用趋势做营销、菜品Agent用趋势做研发）
  5. 自动识别与当前品牌最相关的趋势

数据来源：
  - SMEI 2025 中国用户词典（27词，6维度）
  - 全网热度指数追踪（可接入社媒API）
  - POS数据反向验证（趋势是否在本品牌客群中体现）
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List

import structlog

logger = structlog.get_logger()


@dataclass
class TrendWord:
    """消费趋势词条"""
    word_id: str
    category: str            # 新观念/新行为/新生活方式/新审美/新表达/新族群
    rank: int                # 热度排名（类内）
    word: str                # 趋势词
    heat_index: int          # SMEI热度指数
    synonyms: List[str]      # 近似词
    definition: str          # 含义
    background: str          # 诞生背景
    peak_date: str           # 热度顶峰日期
    user_voice: str          # 用户心声
    trend_2025: str          # 2025趋势预测
    # 餐饮关联
    restaurant_relevance: str    # 与餐饮的关联度 high/medium/low
    restaurant_application: str  # 餐饮应用场景
    menu_keywords: List[str]     # 可触发的菜单/营销关键词
    target_segments: List[str]   # 目标客群标签
    # 动态更新
    current_heat: int = 0        # 当前热度（可每日更新）
    heat_trend: str = "stable"   # rising/stable/declining
    last_updated: str = ""


@dataclass
class TrendInsight:
    """趋势洞察（面向具体品牌/门店）"""
    word: str
    relevance_score: float       # 0-100 与该品牌的相关度
    opportunity: str             # 机会描述
    suggested_actions: List[str] # 建议动作
    target_agent: str            # 建议由哪个Agent执行


# ── 2025用户词典完整数据（SMEI原文结构化） ────────────────────────────────────

TREND_DATABASE: List[Dict] = [
    # === 新观念 ===
    {"word_id": "T001", "category": "新观念", "rank": 1, "word": "反向消费", "heat_index": 2954,
     "synonyms": ["平替消费"], "definition": "用户不再盲目追求品牌与奢侈品，更注重性价比、体验和实用性",
     "background": "全球经济增速放缓，Z世代断舍离、极简主义流行",
     "peak_date": "2024-06-01", "user_voice": "想买一件能穿20年的大衣，不是大牌买不起，而是平替更有性价比",
     "trend_2025": "平替和优替将更为流行，渗透到更多消费品类",
     "restaurant_relevance": "high",
     "restaurant_application": "高性价比套餐、穷鬼套餐策略、品质不降价格降",
     "menu_keywords": ["超值套餐", "性价比之王", "平替菜品", "工作日特惠"],
     "target_segments": ["年轻白领", "学生", "价格敏感型"]},

    {"word_id": "T002", "category": "新观念", "rank": 2, "word": "情绪疗愈", "heat_index": 1932,
     "synonyms": ["情感治愈", "情绪消费", "精神悦己"],
     "definition": "通过购买产品或服务缓解负面情绪、带来情感慰藉",
     "background": "后疫情时代心理健康重视度提升，冥想、情感支持机器人进入市场",
     "peak_date": "2024-11-10", "user_voice": "上次心情不好就去买了一直舍不得买的手办，打开包装盒看到它的那一刻所有坏情绪都没了",
     "trend_2025": "情绪疗愈将继续升温，消费场景从线下扩展到线上虚拟空间",
     "restaurant_relevance": "high",
     "restaurant_application": "治愈系菜品命名、温馨用餐环境、一人食友好、甜品疗愈专区",
     "menu_keywords": ["治愈系", "暖心", "一人食", "甜蜜时光", "解压"],
     "target_segments": ["独居青年", "职场压力人群", "女性消费者"]},

    {"word_id": "T003", "category": "新观念", "rank": 3, "word": "便捷悦享", "heat_index": 1725,
     "synonyms": ["即刻享受", "即时满足", "即时消费"],
     "definition": "用户注重当下时刻的快速、便捷、愉悦满足",
     "background": "外卖即时达、数字支付、快速结算推动即时消费观念",
     "peak_date": "2024-01-14", "user_voice": "我要的我现在就要",
     "trend_2025": "线上线下融合更紧密，本地经营及外卖等业态将持续增长",
     "restaurant_relevance": "high",
     "restaurant_application": "快速出品承诺、扫码即点、外卖优化、即食小食",
     "menu_keywords": ["即点即出", "快手菜", "15分钟上桌", "便捷午餐"],
     "target_segments": ["上班族", "外卖用户", "效率追求者"]},

    # === 新行为 ===
    {"word_id": "T004", "category": "新行为", "rank": 1, "word": "以旧换新", "heat_index": 955395,
     "synonyms": [], "definition": "通过回收或置换旧产品实现资源循环利用",
     "background": "2024年中国政府以旧换新补贴政策",
     "peak_date": "2024-11-27", "user_voice": "以旧换新的优惠力度真的大",
     "trend_2025": "补贴政策扩展，循环消费生态更完善",
     "restaurant_relevance": "low",
     "restaurant_application": "旧餐具回收换优惠、环保包装策略",
     "menu_keywords": ["环保", "绿色餐饮"],
     "target_segments": ["环保意识消费者"]},

    {"word_id": "T005", "category": "新行为", "rank": 2, "word": "穷鬼套餐", "heat_index": 5524,
     "synonyms": [], "definition": "超高性价比的低价套餐，非贬义，指极致性价比吸引用户",
     "background": "2022年麦当劳1+1随心配不涨价被调侃为穷鬼套餐，餐饮品牌纷纷跟进",
     "peak_date": "2024-09-02", "user_voice": "打工人的穷鬼套餐自助火锅又涨价1块钱",
     "trend_2025": "将扩展到茶饮、咖啡、旅游、日用等品类",
     "restaurant_relevance": "high",
     "restaurant_application": "限定低价套餐、工作日特供、引流菜品组合",
     "menu_keywords": ["穷鬼套餐", "超值", "工作日限定", "9.9特惠"],
     "target_segments": ["学生", "年轻白领", "价格敏感型"]},

    {"word_id": "T006", "category": "新行为", "rank": 3, "word": "小城文旅", "heat_index": 1278,
     "synonyms": [], "definition": "前往小众三四线城市品尝特色美食、体验慢生活的旅游消费",
     "background": "天水麻辣烫等小城美食爆红，高铁便利化推动",
     "peak_date": "2024-10-19", "user_voice": "打卡了天水，那麻辣烫太绝了",
     "trend_2025": "带动更多中小城市挖掘美食文旅资源",
     "restaurant_relevance": "high",
     "restaurant_application": "地方特色菜品推广、产地溯源故事、文旅联名",
     "menu_keywords": ["地道风味", "产地直供", "小城味道", "在地食材"],
     "target_segments": ["美食爱好者", "旅游消费者", "文化体验者"]},

    {"word_id": "T007", "category": "新行为", "rank": 4, "word": "智能化消费", "heat_index": 975,
     "synonyms": [], "definition": "在智能化场景中消费或追求智能化产品",
     "background": "AI产品、智能家居、智能点餐普及",
     "peak_date": "2024-03-15", "user_voice": "我们的家正在越变越聪明",
     "trend_2025": "AI加持的智能化产品将进入日常生活",
     "restaurant_relevance": "medium",
     "restaurant_application": "AI点餐推荐、智能厨房设备、个性化菜单",
     "menu_keywords": ["AI推荐", "智能点餐", "个性化"],
     "target_segments": ["科技爱好者", "年轻消费者"]},

    {"word_id": "T008", "category": "新行为", "rank": 5, "word": "攻略先行", "heat_index": 550,
     "synonyms": [], "definition": "消费决策前精心研究攻略，追求最优方案",
     "background": "小红书、携程等平台的攻略文化",
     "peak_date": "2024-10-31", "user_voice": "无论是购物还是旅行，攻略先行已经成为我的必修课",
     "trend_2025": "AI个性化推荐让攻略更精细",
     "restaurant_relevance": "high",
     "restaurant_application": "小红书种草、探店攻略配合、必点清单营销",
     "menu_keywords": ["必点", "探店推荐", "隐藏菜单", "攻略"],
     "target_segments": ["小红书用户", "年轻女性", "社交分享型"]},

    # === 新生活方式 ===
    {"word_id": "T009", "category": "新生活方式", "rank": 1, "word": "City Walk", "heat_index": 190000,
     "synonyms": [], "definition": "城市漫步，徒步或骑行深度体验城市的人文、历史与美食",
     "background": "社交媒体推动，低成本深度体验城市的方式",
     "peak_date": "2024-10-17", "user_voice": "沉浸式来一场古代运河市镇的city walk",
     "trend_2025": "将与AR技术融合，City Walk专门社区兴起",
     "restaurant_relevance": "high",
     "restaurant_application": "City Walk路线合作、街边小食推荐、打卡营销",
     "menu_keywords": ["City Walk", "打卡", "街头美食", "漫步"],
     "target_segments": ["年轻人", "社交达人", "本地生活爱好者"]},

    {"word_id": "T010", "category": "新生活方式", "rank": 2, "word": "松弛感", "heat_index": 133124,
     "synonyms": ["公园20分钟效应"], "definition": "低紧张、低压力的放松状态，追求淡然平和",
     "background": "巴黎奥运会中国00后表现出的松弛感引发热议",
     "peak_date": "2024-09-14", "user_voice": "成都人的松弛感不像是演的",
     "trend_2025": "松弛感将成为普遍的生活理念",
     "restaurant_relevance": "high",
     "restaurant_application": "慢餐文化、不催促服务、舒适用餐环境、下午茶时光",
     "menu_keywords": ["慢享", "不赶时间", "下午茶", "悠闲", "松弛"],
     "target_segments": ["都市白领", "压力人群", "追求品质者"]},

    {"word_id": "T011", "category": "新生活方式", "rank": 4, "word": "朋克养生", "heat_index": 2920,
     "synonyms": [], "definition": "一边放纵享受辛辣食物，一边补救式养生的矛盾生活方式",
     "background": "年轻人吃火锅配养生茶、熬夜后泡枸杞",
     "peak_date": "2024-08-16", "user_voice": "吃火锅配降火茶，喝奶茶加益生菌",
     "trend_2025": "将融入年轻人日常，成为更包容性的生活方式",
     "restaurant_relevance": "high",
     "restaurant_application": "养生火锅、药膳系列、配餐养生饮品、功能性食材",
     "menu_keywords": ["养生", "药膳", "滋补", "枸杞", "降火", "功能性"],
     "target_segments": ["年轻养生族", "火锅爱好者", "健康意识消费者"]},

    # === 新审美 ===
    {"word_id": "T012", "category": "新审美", "rank": 5, "word": "新中式", "heat_index": 631,
     "synonyms": [], "definition": "融合传统文化元素与现代设计，既保留中式美学又满足现代实用性",
     "background": "传统文化复兴，年轻人对本土文化认同感增强",
     "peak_date": "2024-06-01", "user_voice": "杨幂说自己穿新中式被看到是宋牟",
     "trend_2025": "将扩展到家居、婚礼、饮食等领域",
     "restaurant_relevance": "high",
     "restaurant_application": "新中式装修风格、国潮菜品命名、传统食器、节气菜单",
     "menu_keywords": ["新中式", "国潮", "节气", "非遗", "传统手艺"],
     "target_segments": ["文化自信青年", "国潮爱好者", "中高端消费者"]},

    # === 新表达 ===
    {"word_id": "T013", "category": "新表达", "rank": 2, "word": "偷感", "heat_index": 147036,
     "synonyms": [], "definition": "特定情境下偷偷摸摸的隐秘情绪体验",
     "background": "年轻人在高竞争社会环境中的矛盾心理",
     "peak_date": "2024-08-31", "user_voice": "减肥期是偷感最重的时候",
     "trend_2025": "将继续作为年轻人表达自我的方式",
     "restaurant_relevance": "medium",
     "restaurant_application": "隐藏菜单、限定款、小确幸甜品、秘密菜单营销",
     "menu_keywords": ["隐藏款", "限定", "小确幸", "偷偷吃"],
     "target_segments": ["年轻人", "社交媒体用户"]},

    {"word_id": "T014", "category": "新表达", "rank": 5, "word": "班味", "heat_index": 31224,
     "synonyms": [], "definition": "上班族因工作压力显现出的疲惫和缺乏活力状态",
     "background": "年轻人自嘲上班状态的流行语",
     "peak_date": "2024-10-19", "user_voice": "去散散你的班味",
     "trend_2025": "将成为职场文化符号",
     "restaurant_relevance": "medium",
     "restaurant_application": "去班味套餐、打工人专属、周五犒劳自己",
     "menu_keywords": ["打工人", "犒劳", "周五", "去班味", "续命"],
     "target_segments": ["上班族", "年轻白领"]},

    # === 新族群 ===
    {"word_id": "T015", "category": "新族群", "rank": 1, "word": "谷子", "heat_index": 154620,
     "synonyms": ["谷子文化"], "definition": "Goods（商品）音译，动漫/游戏/偶像等版权衍生周边产品",
     "background": "谷子经济2024年爆发式增长，撬动超千亿元市场",
     "peak_date": "2024-01-21", "user_voice": "这次漫展的谷子摊位太火爆了",
     "trend_2025": "将与时尚、餐饮、文旅跨界联合",
     "restaurant_relevance": "medium",
     "restaurant_application": "IP联名套餐、限定谷子赠品、动漫主题活动",
     "menu_keywords": ["联名", "限定", "IP", "周边", "打卡"],
     "target_segments": ["Z世代", "二次元爱好者", "收藏控"]},

    {"word_id": "T016", "category": "新族群", "rank": 2, "word": "银发力量", "heat_index": 8861,
     "synonyms": ["银发数字游民", "富裕银发族"], "definition": "老年群体在消费、文化、服务方面不可忽视的力量",
     "background": "2024年银发经济受到政策高度重视，国务院印发相关意见",
     "peak_date": "2024-10-11", "user_voice": "以前总觉得网购是年轻人的事，后来闺女教我用了几次，好方便",
     "trend_2025": "银发群体消费需求将更加多样化",
     "restaurant_relevance": "high",
     "restaurant_application": "老年友好菜单（大字体、低盐低油选项）、寿宴套餐、银发会员",
     "menu_keywords": ["养生", "低盐", "软烂", "寿宴", "银发优惠"],
     "target_segments": ["50+消费者", "子女代付群体", "银发数字用户"]},

    {"word_id": "T017", "category": "新族群", "rank": 3, "word": "淡人", "heat_index": 8001,
     "synonyms": ["淡学人生"], "definition": "对生活淡淡情绪、淡泊态度的年轻人",
     "background": "快节奏社会中年轻人选择平和、淡泊的生活态度",
     "peak_date": "2024-05-09", "user_voice": "我确诊为淡人",
     "trend_2025": "淡人消费领域简约、实用、情绪价值产品受青睐",
     "restaurant_relevance": "medium",
     "restaurant_application": "简约菜单设计、不打扰服务、安静用餐区",
     "menu_keywords": ["简约", "自在", "不打扰", "静享"],
     "target_segments": ["内向消费者", "独处爱好者", "极简主义者"]},

    {"word_id": "T018", "category": "新族群", "rank": 5, "word": "县漂", "heat_index": 1500,
     "synonyms": [], "definition": "倾向于在小县城安家、寻求平衡生活节奏的年轻群体",
     "background": "大城市生活成本攀升，县域经济发展机会增加",
     "peak_date": "2024-12-23", "user_voice": "在大城市卷不动了，回县城考了个事业编",
     "trend_2025": "县城文学、县城旅游等概念兴起",
     "restaurant_relevance": "high",
     "restaurant_application": "县城门店扩张策略、本地化菜单、社区餐饮",
     "menu_keywords": ["家的味道", "本地特色", "社区食堂", "亲民价格"],
     "target_segments": ["下沉市场消费者", "返乡青年", "县城居民"]},
]


# ── 餐饮场景关联度计算 ────────────────────────────────────────────────────────

RESTAURANT_KEYWORDS = {
    "high": ["套餐", "菜品", "美食", "餐饮", "火锅", "外卖", "打卡", "味道",
             "养生", "性价比", "食材", "探店", "环境", "服务", "慢餐"],
    "medium": ["消费", "体验", "文化", "健康", "生活方式", "社交"],
}


def calc_restaurant_relevance(word_data: Dict) -> str:
    """计算趋势词与餐饮的关联度"""
    text = f"{word_data.get('definition', '')} {word_data.get('restaurant_application', '')} {word_data.get('trend_2025', '')}"
    high_hits = sum(1 for kw in RESTAURANT_KEYWORDS["high"] if kw in text)
    med_hits = sum(1 for kw in RESTAURANT_KEYWORDS["medium"] if kw in text)
    if high_hits >= 2:
        return "high"
    elif high_hits >= 1 or med_hits >= 2:
        return "medium"
    return "low"


def match_trends_to_brand(
    trends: List[TrendWord],
    brand_tags: List[str],
    customer_segments: List[str],
) -> List[TrendInsight]:
    """
    匹配趋势词与品牌特征，生成洞察建议。

    Args:
        trends: 趋势词列表
        brand_tags: 品牌标签（如 ["湘菜", "中端", "连锁", "年轻化"]）
        customer_segments: 主要客群（如 ["年轻白领", "家庭聚餐"]）
    """
    insights = []
    for t in trends:
        if t.restaurant_relevance == "low":
            continue

        # 计算相关度
        score = 0.0
        if t.restaurant_relevance == "high":
            score += 40
        elif t.restaurant_relevance == "medium":
            score += 20

        # 客群匹配
        segment_overlap = len(set(t.target_segments) & set(customer_segments))
        score += segment_overlap * 15

        # 热度加分
        if t.heat_index > 100000:
            score += 20
        elif t.heat_index > 10000:
            score += 10
        elif t.heat_index > 1000:
            score += 5

        score = min(100, score)
        if score < 30:
            continue

        # 决定由哪个Agent执行
        if any(kw in t.restaurant_application for kw in ["菜品", "菜单", "套餐", "食材"]):
            agent = "dish_rd_agent"
        elif any(kw in t.restaurant_application for kw in ["营销", "种草", "打卡", "联名"]):
            agent = "private_domain_agent"
        elif any(kw in t.restaurant_application for kw in ["环境", "服务", "装修"]):
            agent = "ops_agent"
        else:
            agent = "decision_agent"

        insights.append(TrendInsight(
            word=t.word,
            relevance_score=round(score, 1),
            opportunity=f"「{t.word}」趋势（热度{t.heat_index}）与您的品牌高度相关。{t.restaurant_application}",
            suggested_actions=t.menu_keywords[:3],
            target_agent=agent,
        ))

    insights.sort(key=lambda x: x.relevance_score, reverse=True)
    return insights


# ── 服务类 ────────────────────────────────────────────────────────────────────

class ConsumerTrendService:
    """
    消费趋势知识库服务。

    各Agent调用方式：
    - 私域Agent: get_marketing_trends() → 获取营销相关趋势词+话术
    - 菜品Agent: get_menu_trends() → 获取菜品研发灵感
    - 决策Agent: match_to_brand() → 匹配品牌最相关趋势
    """

    def __init__(self):
        self._trends: Dict[str, TrendWord] = {}
        self._load_builtin()

    def _load_builtin(self):
        for d in TREND_DATABASE:
            tw = TrendWord(
                word_id=d["word_id"], category=d["category"], rank=d["rank"],
                word=d["word"], heat_index=d["heat_index"],
                synonyms=d.get("synonyms", []), definition=d["definition"],
                background=d["background"], peak_date=d["peak_date"],
                user_voice=d["user_voice"], trend_2025=d["trend_2025"],
                restaurant_relevance=d.get("restaurant_relevance", "low"),
                restaurant_application=d.get("restaurant_application", ""),
                menu_keywords=d.get("menu_keywords", []),
                target_segments=d.get("target_segments", []),
                current_heat=d["heat_index"],
                last_updated=datetime.utcnow().isoformat(),
            )
            self._trends[tw.word_id] = tw

    def get_all_trends(self) -> List[TrendWord]:
        return sorted(self._trends.values(), key=lambda t: t.heat_index, reverse=True)

    def get_by_category(self, category: str) -> List[TrendWord]:
        return sorted(
            [t for t in self._trends.values() if t.category == category],
            key=lambda t: t.rank,
        )

    def get_high_relevance(self) -> List[TrendWord]:
        """获取与餐饮高度相关的趋势"""
        return [t for t in self._trends.values() if t.restaurant_relevance == "high"]

    def get_marketing_trends(self, limit: int = 5) -> List[Dict]:
        """供私域Agent调用：获取营销相关趋势词+话术关键词"""
        trends = self.get_high_relevance()
        return [
            {"word": t.word, "heat": t.heat_index,
             "keywords": t.menu_keywords, "segments": t.target_segments,
             "application": t.restaurant_application}
            for t in sorted(trends, key=lambda x: x.heat_index, reverse=True)[:limit]
        ]

    def get_menu_trends(self, limit: int = 5) -> List[Dict]:
        """供菜品Agent调用：获取菜品研发灵感"""
        trends = [t for t in self._trends.values()
                  if any(kw in t.restaurant_application for kw in ["菜品", "菜单", "套餐", "食材", "养生"])]
        return [
            {"word": t.word, "menu_keywords": t.menu_keywords,
             "application": t.restaurant_application, "trend": t.trend_2025}
            for t in sorted(trends, key=lambda x: x.heat_index, reverse=True)[:limit]
        ]

    def match_to_brand(
        self, brand_tags: List[str], customer_segments: List[str],
    ) -> List[TrendInsight]:
        """供决策Agent调用：匹配品牌最相关趋势"""
        return match_trends_to_brand(
            list(self._trends.values()), brand_tags, customer_segments,
        )

    def update_heat(self, word_id: str, new_heat: int, trend: str = "stable"):
        """每日更新热度（接入社媒API后自动调用）"""
        tw = self._trends.get(word_id)
        if tw:
            tw.current_heat = new_heat
            tw.heat_trend = trend
            tw.last_updated = datetime.utcnow().isoformat()

    def add_trend(self, data: Dict) -> TrendWord:
        """新增趋势词（发现新热词时调用）"""
        tw = TrendWord(
            word_id=data.get("word_id", f"T{len(self._trends)+100}"),
            category=data.get("category", "新观念"),
            rank=data.get("rank", 99),
            word=data["word"],
            heat_index=data.get("heat_index", 0),
            synonyms=data.get("synonyms", []),
            definition=data.get("definition", ""),
            background=data.get("background", ""),
            peak_date=data.get("peak_date", ""),
            user_voice=data.get("user_voice", ""),
            trend_2025=data.get("trend_2025", ""),
            restaurant_relevance=calc_restaurant_relevance(data),
            restaurant_application=data.get("restaurant_application", ""),
            menu_keywords=data.get("menu_keywords", []),
            target_segments=data.get("target_segments", []),
            current_heat=data.get("heat_index", 0),
            last_updated=datetime.utcnow().isoformat(),
        )
        self._trends[tw.word_id] = tw
        logger.info("新增趋势词", word=tw.word, relevance=tw.restaurant_relevance)
        return tw

    def get_categories(self) -> List[Dict]:
        """获取分类统计"""
        cats: Dict[str, int] = {}
        for t in self._trends.values():
            cats[t.category] = cats.get(t.category, 0) + 1
        return [{"category": k, "count": v} for k, v in sorted(cats.items())]
