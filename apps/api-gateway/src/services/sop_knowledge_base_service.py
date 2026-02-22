"""
SOP知识库服务
SOP (Standard Operating Procedure) Knowledge Base Service

核心价值：
- 沉淀顶级门店运营知识
- RAG检索增强生成
- 打造"虚拟店长"产品

知识类型：
- 客诉应对话术
- 爆单指挥逻辑
- 设备维护规范
- 食品安全检查清单
- 员工培训最佳实践
- 异常处理决策树
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SOPCategory(str, Enum):
    """SOP类别"""
    CUSTOMER_SERVICE = "customer_service"      # 客户服务
    OPERATIONS = "operations"                  # 运营管理
    FOOD_SAFETY = "food_safety"                # 食品安全
    EQUIPMENT = "equipment"                    # 设备维护
    TRAINING = "training"                      # 员工培训
    EMERGENCY = "emergency"                    # 应急处理
    QUALITY_CONTROL = "quality_control"        # 质量控制


class SOPDifficulty(str, Enum):
    """SOP难度"""
    BEGINNER = "beginner"      # 新手
    INTERMEDIATE = "intermediate"  # 中级
    ADVANCED = "advanced"      # 高级
    EXPERT = "expert"          # 专家


class SOPDocument(BaseModel):
    """SOP文档"""
    sop_id: str
    title: str
    category: SOPCategory
    difficulty: SOPDifficulty
    content: str
    keywords: List[str]
    scenarios: List[str]          # 适用场景
    best_practices: List[str]     # 最佳实践
    common_mistakes: List[str]    # 常见错误
    source_store: Optional[str]   # 来源门店
    rating: float                 # 评分（0-5）
    usage_count: int              # 使用次数
    created_at: datetime
    updated_at: datetime


class QueryContext(BaseModel):
    """查询上下文"""
    user_role: str                # 用户角色（店长/服务员/厨师）
    user_experience_years: int    # 工作年限
    current_situation: str        # 当前情况描述
    urgency: str                  # 紧急程度（low/medium/high/critical）
    store_type: str               # 门店类型（火锅/烧烤/快餐）


class SOPRecommendation(BaseModel):
    """SOP推荐"""
    sop_id: str
    title: str
    relevance_score: float        # 相关性分数
    confidence: float             # 置信度
    summary: str                  # 摘要
    key_steps: List[str]          # 关键步骤
    estimated_time_minutes: int   # 预计耗时
    success_rate: float           # 成功率


class SOPKnowledgeBaseService:
    """SOP知识库服务"""

    def __init__(self):
        self.sop_database = {}        # SOP数据库
        self.vector_index = {}        # 向量索引（简化版）
        self._initialize_knowledge_base()

    def _initialize_knowledge_base(self):
        """初始化知识库（预置顶级门店SOP）"""
        # 客诉应对话术
        self._add_sop(SOPDocument(
            sop_id="SOP_CS_001",
            title="顾客投诉菜品口味不佳的应对话术",
            category=SOPCategory.CUSTOMER_SERVICE,
            difficulty=SOPDifficulty.BEGINNER,
            content="""
            1. 立即道歉，表达理解
               "非常抱歉给您带来不好的用餐体验，我完全理解您的感受"

            2. 询问具体问题
               "能否请您详细说明一下哪里不符合您的口味？"

            3. 提供解决方案
               - 重新制作（免费）
               - 更换其他菜品
               - 退款或折扣

            4. 记录反馈
               将问题记录到系统，供后厨改进

            5. 跟进确认
               "新菜品是否符合您的口味？"
            """,
            keywords=["客诉", "口味", "投诉", "应对"],
            scenarios=["顾客不满意", "菜品质量问题", "口味争议"],
            best_practices=[
                "保持微笑和耐心",
                "不要争辩或推卸责任",
                "快速响应，不超过2分钟",
                "给予实质性补偿"
            ],
            common_mistakes=[
                "推卸责任给后厨",
                "质疑顾客的口味",
                "拖延处理时间",
                "补偿不够诚意"
            ],
            source_store="海底捞北京王府井店",
            rating=4.8,
            usage_count=1523,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ))

        # 爆单指挥逻辑
        self._add_sop(SOPDocument(
            sop_id="SOP_OPS_001",
            title="高峰期爆单应急指挥流程",
            category=SOPCategory.OPERATIONS,
            difficulty=SOPDifficulty.ADVANCED,
            content="""
            1. 立即启动应急预案
               - 通知所有员工进入高峰模式
               - 暂停非紧急任务

            2. 优化出餐顺序
               - 优先处理等待时间最长的订单
               - 合并相同菜品批量制作
               - 简化摆盘流程

            3. 动态调配人力
               - 前厅服务员支援后厨
               - 店长亲自上阵传菜
               - 呼叫备班员工

            4. 客户沟通
               - 主动告知预计等待时间
               - 提供免费小吃或饮料
               - 对超时订单给予折扣

            5. 后续复盘
               - 记录爆单原因
               - 分析应对效果
               - 优化排班和备货
            """,
            keywords=["爆单", "高峰期", "应急", "指挥"],
            scenarios=["订单激增", "人手不足", "后厨压力大"],
            best_practices=[
                "提前15分钟预判高峰",
                "保持冷静，有序指挥",
                "优先保证食品安全",
                "事后给员工加餐或奖励"
            ],
            common_mistakes=[
                "慌乱无序",
                "忽视食品安全",
                "对顾客态度不佳",
                "事后不复盘"
            ],
            source_store="西贝莜面村上海南京西路店",
            rating=4.9,
            usage_count=892,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ))

        # 食品安全检查
        self._add_sop(SOPDocument(
            sop_id="SOP_SAFE_001",
            title="每日食品安全检查清单",
            category=SOPCategory.FOOD_SAFETY,
            difficulty=SOPDifficulty.INTERMEDIATE,
            content="""
            开店前检查（7:00-8:00）：
            1. 冷藏冷冻设备温度
               - 冷藏：0-4°C
               - 冷冻：-18°C以下

            2. 食材保质期
               - 检查所有食材标签
               - 临期食材优先使用
               - 过期食材立即销毁

            3. 厨房卫生
               - 操作台清洁消毒
               - 刀具砧板分类使用
               - 垃圾桶清空

            营业中检查（每2小时）：
            1. 食材温度
               - 热菜保温>60°C
               - 冷菜保冷<10°C

            2. 员工卫生
               - 佩戴口罩手套
               - 勤洗手消毒

            闭店后检查（22:00-23:00）：
            1. 食材封存
               - 生熟分开
               - 标注日期

            2. 设备关闭
               - 燃气阀门
               - 电源开关
            """,
            keywords=["食品安全", "检查", "清单", "卫生"],
            scenarios=["日常检查", "开店准备", "闭店收尾"],
            best_practices=[
                "使用检查表，逐项打勾",
                "拍照留存证据",
                "发现问题立即整改",
                "定期培训员工"
            ],
            common_mistakes=[
                "走过场，不认真检查",
                "发现问题不上报",
                "检查记录造假",
                "忽视小问题"
            ],
            source_store="麦当劳中国培训中心",
            rating=5.0,
            usage_count=3421,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ))

        # 设备维护
        self._add_sop(SOPDocument(
            sop_id="SOP_EQUIP_001",
            title="油烟机清洗维护规范",
            category=SOPCategory.EQUIPMENT,
            difficulty=SOPDifficulty.INTERMEDIATE,
            content="""
            清洗频率：
            - 日常清洁：每天营业结束后
            - 深度清洗：每周一次
            - 专业维护：每月一次

            日常清洁步骤：
            1. 关闭电源，等待冷却
            2. 拆卸油网，浸泡热碱水
            3. 擦拭外壳和风扇叶片
            4. 清理油杯，倒掉废油
            5. 安装复位，测试运行

            深度清洗步骤：
            1. 拆卸所有可拆部件
            2. 使用专业清洗剂浸泡
            3. 高压水枪冲洗
            4. 检查风机轴承润滑
            5. 检查电机运转声音

            注意事项：
            - 必须断电操作
            - 佩戴防护手套
            - 清洗剂不可入眼
            - 安装后测试吸力
            """,
            keywords=["设备", "维护", "油烟机", "清洗"],
            scenarios=["设备保养", "日常维护", "故障预防"],
            best_practices=[
                "建立维护台账",
                "使用专业工具",
                "定期更换易损件",
                "培训专人负责"
            ],
            common_mistakes=[
                "清洗不彻底",
                "忘记断电",
                "使用腐蚀性清洗剂",
                "安装不到位"
            ],
            source_store="海底捞设备维护部",
            rating=4.7,
            usage_count=756,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ))

        logger.info(f"Initialized knowledge base with {len(self.sop_database)} SOPs")

    def _add_sop(self, sop: SOPDocument):
        """添加SOP到数据库"""
        self.sop_database[sop.sop_id] = sop

        # 构建向量索引（简化版：基于关键词）
        for keyword in sop.keywords:
            if keyword not in self.vector_index:
                self.vector_index[keyword] = []
            self.vector_index[keyword].append(sop.sop_id)

    async def query_best_practice(
        self,
        query: str,
        context: QueryContext
    ) -> List[SOPRecommendation]:
        """
        查询最佳实践

        Args:
            query: 查询问题
            context: 查询上下文

        Returns:
            SOP推荐列表
        """
        logger.info(f"Querying best practice: {query}")

        # 简化的关键词匹配（生产环境应使用向量检索）
        relevant_sops = self._search_by_keywords(query)

        # 根据上下文过滤和排序
        recommendations = []

        for sop in relevant_sops:
            # 计算相关性分数
            relevance_score = self._calculate_relevance(sop, query, context)

            # 计算置信度
            confidence = self._calculate_confidence(sop, context)

            # 生成摘要
            summary = self._generate_summary(sop)

            # 提取关键步骤
            key_steps = self._extract_key_steps(sop)

            recommendations.append(SOPRecommendation(
                sop_id=sop.sop_id,
                title=sop.title,
                relevance_score=relevance_score,
                confidence=confidence,
                summary=summary,
                key_steps=key_steps,
                estimated_time_minutes=self._estimate_time(sop),
                success_rate=sop.rating / 5.0
            ))

        # 按相关性排序
        recommendations.sort(key=lambda x: x.relevance_score, reverse=True)

        return recommendations[:5]  # 返回Top 5

    def _search_by_keywords(self, query: str) -> List[SOPDocument]:
        """基于关键词搜索"""
        query_lower = query.lower()
        matched_sop_ids = set()

        # 匹配关键词
        for keyword, sop_ids in self.vector_index.items():
            if keyword in query_lower:
                matched_sop_ids.update(sop_ids)

        # 返回匹配的SOP
        return [
            self.sop_database[sop_id]
            for sop_id in matched_sop_ids
        ]

    def _calculate_relevance(
        self,
        sop: SOPDocument,
        query: str,
        context: QueryContext
    ) -> float:
        """计算相关性分数"""
        score = 0.0

        # 关键词匹配
        query_lower = query.lower()
        for keyword in sop.keywords:
            if keyword in query_lower:
                score += 0.2

        # 场景匹配
        for scenario in sop.scenarios:
            if scenario in context.current_situation:
                score += 0.3

        # 难度匹配
        if context.user_experience_years < 1:
            if sop.difficulty == SOPDifficulty.BEGINNER:
                score += 0.2
        elif context.user_experience_years < 3:
            if sop.difficulty in [SOPDifficulty.BEGINNER, SOPDifficulty.INTERMEDIATE]:
                score += 0.2
        else:
            score += 0.1  # 经验丰富的员工适用所有难度

        # 评分加权
        score += (sop.rating / 5.0) * 0.2

        # 使用次数加权
        score += min(sop.usage_count / 1000, 0.2)

        return min(score, 1.0)

    def _calculate_confidence(
        self,
        sop: SOPDocument,
        context: QueryContext
    ) -> float:
        """计算置信度"""
        confidence = 0.5  # 基础置信度

        # 来源门店加权
        if sop.source_store:
            confidence += 0.2

        # 评分加权
        confidence += (sop.rating / 5.0) * 0.2

        # 使用次数加权
        if sop.usage_count > 1000:
            confidence += 0.1

        return min(confidence, 1.0)

    def _generate_summary(self, sop: SOPDocument) -> str:
        """生成摘要"""
        # 简化版：取前100个字符
        return sop.content[:100] + "..."

    def _extract_key_steps(self, sop: SOPDocument) -> List[str]:
        """提取关键步骤"""
        # 简化版：提取数字开头的行
        lines = sop.content.split("\n")
        key_steps = []

        for line in lines:
            line = line.strip()
            if line and line[0].isdigit():
                key_steps.append(line)

        return key_steps[:5]  # 最多5个关键步骤

    def _estimate_time(self, sop: SOPDocument) -> int:
        """估算耗时（分钟）"""
        # 简化版：根据难度估算
        time_map = {
            SOPDifficulty.BEGINNER: 5,
            SOPDifficulty.INTERMEDIATE: 15,
            SOPDifficulty.ADVANCED: 30,
            SOPDifficulty.EXPERT: 60
        }
        return time_map.get(sop.difficulty, 15)

    async def add_custom_sop(
        self,
        store_id: str,
        sop: SOPDocument
    ) -> Dict[str, Any]:
        """
        添加自定义SOP

        Args:
            store_id: 门店ID
            sop: SOP文档

        Returns:
            添加结果
        """
        # 设置来源门店
        sop.source_store = store_id

        # 添加到数据库
        self._add_sop(sop)

        logger.info(f"Added custom SOP {sop.sop_id} from store {store_id}")

        return {
            "sop_id": sop.sop_id,
            "status": "success",
            "message": "SOP已添加到知识库"
        }

    async def rate_sop(
        self,
        sop_id: str,
        rating: float,
        feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        评价SOP

        Args:
            sop_id: SOP ID
            rating: 评分（0-5）
            feedback: 反馈意见

        Returns:
            评价结果
        """
        sop = self.sop_database.get(sop_id)

        if not sop:
            return {
                "status": "error",
                "message": "SOP不存在"
            }

        # 更新评分（加权平均）
        total_ratings = sop.usage_count
        new_rating = (
            (sop.rating * total_ratings + rating) /
            (total_ratings + 1)
        )

        sop.rating = new_rating
        sop.usage_count += 1
        sop.updated_at = datetime.now()

        logger.info(f"SOP {sop_id} rated: {rating}, new average: {new_rating:.2f}")

        return {
            "sop_id": sop_id,
            "new_rating": new_rating,
            "total_ratings": sop.usage_count,
            "status": "success"
        }

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_sops": len(self.sop_database),
            "by_category": self._count_by_category(),
            "by_difficulty": self._count_by_difficulty(),
            "top_rated": self._get_top_rated(5),
            "most_used": self._get_most_used(5)
        }

    def _count_by_category(self) -> Dict[str, int]:
        """按类别统计"""
        counts = {}
        for sop in self.sop_database.values():
            category = sop.category
            counts[category] = counts.get(category, 0) + 1
        return counts

    def _count_by_difficulty(self) -> Dict[str, int]:
        """按难度统计"""
        counts = {}
        for sop in self.sop_database.values():
            difficulty = sop.difficulty
            counts[difficulty] = counts.get(difficulty, 0) + 1
        return counts

    def _get_top_rated(self, limit: int) -> List[Dict]:
        """获取评分最高的SOP"""
        sorted_sops = sorted(
            self.sop_database.values(),
            key=lambda x: x.rating,
            reverse=True
        )
        return [
            {
                "sop_id": sop.sop_id,
                "title": sop.title,
                "rating": sop.rating
            }
            for sop in sorted_sops[:limit]
        ]

    def _get_most_used(self, limit: int) -> List[Dict]:
        """获取使用最多的SOP"""
        sorted_sops = sorted(
            self.sop_database.values(),
            key=lambda x: x.usage_count,
            reverse=True
        )
        return [
            {
                "sop_id": sop.sop_id,
                "title": sop.title,
                "usage_count": sop.usage_count
            }
            for sop in sorted_sops[:limit]
        ]


# 全局实例
sop_knowledge_base = SOPKnowledgeBaseService()
