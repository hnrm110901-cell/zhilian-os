"""
智能培训Agent - Intelligent Training Agent

核心功能 Core Features:
1. 培训需求评估 - Training needs assessment
2. 培训计划生成 - Training plan generation
3. 培训内容管理 - Training content management
4. 培训进度追踪 - Training progress tracking
5. 培训效果评估 - Training effectiveness evaluation
6. 技能差距分析 - Skill gap analysis
7. 证书管理 - Certification management
"""

import os
import asyncio
import structlog
from datetime import datetime, timedelta
from enum import Enum
from typing import TypedDict, List, Optional, Dict, Any
from statistics import mean
from collections import defaultdict
import sys
from pathlib import Path

# Add core module to path
core_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "core"
sys.path.insert(0, str(core_path))

from base_agent import BaseAgent, AgentResponse

logger = structlog.get_logger()

# 内置课程目录（无 DB 时的基础课程定义，与 training_type 枚举对齐）
# 可通过未来的 training_courses 表扩展
_BUILTIN_COURSE_CATALOG: dict = {
    "COURSE_SERVICE_001": {
        "course_id": "COURSE_SERVICE_001",
        "course_name": "优质服务培训",
        "training_type": "customer_service",
        "description": "提升服务质量和客户满意度",
        "duration_hours": 8.0,
        "target_skill_level": "intermediate",
        "prerequisites": [],
        "content_url": "https://training.zhilian-os.com/service-001",
        "instructor": "培训师A",
        "max_participants": 20,
        "passing_score": 70,
    },
    "COURSE_COOKING_001": {
        "course_id": "COURSE_COOKING_001",
        "course_name": "基础烹饪技能",
        "training_type": "skill_upgrade",
        "description": "学习基础烹饪技能和菜品制作",
        "duration_hours": 16.0,
        "target_skill_level": "intermediate",
        "prerequisites": [],
        "content_url": "https://training.zhilian-os.com/cooking-001",
        "instructor": "厨师长",
        "max_participants": 10,
        "passing_score": 75,
    },
    "COURSE_SAFETY_001": {
        "course_id": "COURSE_SAFETY_001",
        "course_name": "食品安全培训",
        "training_type": "safety",
        "description": "食品安全法规和操作规范",
        "duration_hours": 4.0,
        "target_skill_level": "beginner",
        "prerequisites": [],
        "content_url": "https://training.zhilian-os.com/safety-001",
        "instructor": "安全专员",
        "max_participants": 30,
        "passing_score": 80,
    },
    "COURSE_ONBOARDING_001": {
        "course_id": "COURSE_ONBOARDING_001",
        "course_name": "新员工入职培训",
        "training_type": "onboarding",
        "description": "企业文化、制度规范、基础操作流程",
        "duration_hours": 4.0,
        "target_skill_level": "beginner",
        "prerequisites": [],
        "content_url": "https://training.zhilian-os.com/onboarding-001",
        "instructor": "人力资源专员",
        "max_participants": 30,
        "passing_score": 60,
    },
    "COURSE_MANAGEMENT_001": {
        "course_id": "COURSE_MANAGEMENT_001",
        "course_name": "门店管理培训",
        "training_type": "management",
        "description": "门店日常运营管理与团队领导力",
        "duration_hours": 12.0,
        "target_skill_level": "advanced",
        "prerequisites": ["COURSE_SERVICE_001"],
        "content_url": "https://training.zhilian-os.com/management-001",
        "instructor": "运营总监",
        "max_participants": 15,
        "passing_score": 75,
    },
}

class TrainingType(str, Enum):
    """培训类型 Training Type"""
    ONBOARDING = "onboarding"  # 入职培训
    SKILL_UPGRADE = "skill_upgrade"  # 技能提升
    COMPLIANCE = "compliance"  # 合规培训
    SAFETY = "safety"  # 安全培训
    MANAGEMENT = "management"  # 管理培训
    PRODUCT_KNOWLEDGE = "product_knowledge"  # 产品知识
    CUSTOMER_SERVICE = "customer_service"  # 客户服务


class TrainingStatus(str, Enum):
    """培训状态 Training Status"""
    NOT_STARTED = "not_started"  # 未开始
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"  # 已完成
    EXPIRED = "expired"  # 已过期
    FAILED = "failed"  # 未通过


class SkillLevel(str, Enum):
    """技能水平 Skill Level"""
    BEGINNER = "beginner"  # 初级
    INTERMEDIATE = "intermediate"  # 中级
    ADVANCED = "advanced"  # 高级
    EXPERT = "expert"  # 专家


class AssessmentType(str, Enum):
    """评估类型 Assessment Type"""
    QUIZ = "quiz"  # 测验
    PRACTICAL = "practical"  # 实操
    OBSERVATION = "observation"  # 观察
    PROJECT = "project"  # 项目
    PEER_REVIEW = "peer_review"  # 同行评审


class TrainingPriority(str, Enum):
    """培训优先级 Training Priority"""
    LOW = "low"  # 低
    MEDIUM = "medium"  # 中
    HIGH = "high"  # 高
    URGENT = "urgent"  # 紧急


class TrainingCourse(TypedDict):
    """培训课程 Training Course"""
    course_id: str  # 课程ID
    course_name: str  # 课程名称
    training_type: TrainingType  # 培训类型
    description: str  # 描述
    duration_hours: float  # 时长(小时)
    target_skill_level: SkillLevel  # 目标技能水平
    prerequisites: List[str]  # 前置课程ID列表
    content_url: Optional[str]  # 内容链接
    instructor: Optional[str]  # 讲师
    max_participants: int  # 最大参与人数
    passing_score: int  # 及格分数
    created_at: str  # 创建时间


class TrainingNeed(TypedDict):
    """培训需求 Training Need"""
    need_id: str  # 需求ID
    staff_id: str  # 员工ID
    staff_name: str  # 员工姓名
    position: str  # 岗位
    skill_gap: str  # 技能差距
    current_level: SkillLevel  # 当前水平
    target_level: SkillLevel  # 目标水平
    priority: TrainingPriority  # 优先级
    recommended_courses: List[str]  # 推荐课程ID列表
    reason: str  # 原因
    identified_at: str  # 识别时间


class TrainingPlan(TypedDict):
    """培训计划 Training Plan"""
    plan_id: str  # 计划ID
    staff_id: str  # 员工ID
    staff_name: str  # 员工姓名
    courses: List[str]  # 课程ID列表
    start_date: str  # 开始日期
    end_date: str  # 结束日期
    total_hours: float  # 总时长
    priority: TrainingPriority  # 优先级
    status: TrainingStatus  # 状态
    progress_percentage: float  # 进度百分比
    created_at: str  # 创建时间
    updated_at: str  # 更新时间


class TrainingRecord(TypedDict):
    """培训记录 Training Record"""
    record_id: str  # 记录ID
    staff_id: str  # 员工ID
    course_id: str  # 课程ID
    plan_id: Optional[str]  # 计划ID
    start_date: str  # 开始日期
    completion_date: Optional[str]  # 完成日期
    status: TrainingStatus  # 状态
    attendance_hours: float  # 出勤时长
    score: Optional[int]  # 分数
    passed: Optional[bool]  # 是否通过
    feedback: Optional[str]  # 反馈
    created_at: str  # 创建时间


class Assessment(TypedDict):
    """评估 Assessment"""
    assessment_id: str  # 评估ID
    staff_id: str  # 员工ID
    course_id: str  # 课程ID
    assessment_type: AssessmentType  # 评估类型
    score: int  # 分数
    max_score: int  # 满分
    passed: bool  # 是否通过
    assessor: str  # 评估人
    feedback: str  # 反馈
    assessed_at: str  # 评估时间


class Certificate(TypedDict):
    """证书 Certificate"""
    certificate_id: str  # 证书ID
    staff_id: str  # 员工ID
    staff_name: str  # 员工姓名
    course_id: str  # 课程ID
    course_name: str  # 课程名称
    issue_date: str  # 颁发日期
    expiry_date: Optional[str]  # 过期日期
    certificate_url: Optional[str]  # 证书链接
    status: str  # 状态(valid/expired)


class SkillGap(TypedDict):
    """技能差距 Skill Gap"""
    staff_id: str  # 员工ID
    staff_name: str  # 员工姓名
    position: str  # 岗位
    skill_name: str  # 技能名称
    current_level: SkillLevel  # 当前水平
    required_level: SkillLevel  # 要求水平
    gap_score: int  # 差距分数(0-100)
    priority: TrainingPriority  # 优先级


class TrainingAgent(BaseAgent):
    """
    智能培训Agent

    工作流程 Workflow:
    1. assess_training_needs() - 评估培训需求
    2. generate_training_plan() - 生成培训计划
    3. track_training_progress() - 追踪培训进度
    4. evaluate_training_effectiveness() - 评估培训效果
    5. analyze_skill_gaps() - 分析技能差距
    6. manage_certificates() - 管理证书
    """

    def __init__(
        self,
        store_id: str,
        training_config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化培训Agent

        Args:
            store_id: 门店ID
            training_config: 培训配置
        """
        super().__init__()
        self.store_id = store_id
        self.training_config = training_config or {
            "min_passing_score": 70,  # 最低及格分数
            "max_training_hours_per_month": 40,  # 每月最大培训时长
            "certificate_validity_months": 12,  # 证书有效期(月)
            "mandatory_training_types": [
                TrainingType.SAFETY,
                TrainingType.COMPLIANCE
            ]
        }
        self.logger = logger.bind(agent="training", store_id=store_id)
        self._db_engine = None

    def _get_db_engine(self):
        """获取数据库引擎（懒加载）"""
        if self._db_engine is None:
            db_url = os.getenv("DATABASE_URL")
            if db_url:
                try:
                    from sqlalchemy import create_engine
                    self._db_engine = create_engine(db_url, pool_pre_ping=True)
                except Exception:
                    pass
        return self._db_engine

    def get_supported_actions(self) -> List[str]:
        """获取支持的操作列表"""
        return [
            "assess_training_needs", "generate_training_plan", "track_training_progress",
            "evaluate_training_effectiveness", "analyze_skill_gaps",
            "manage_certificates", "issue_certificate", "get_training_report"
        ]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """
        执行Agent操作

        Args:
            action: 操作名称
            params: 操作参数

        Returns:
            AgentResponse: 统一的响应格式
        """
        try:
            if action == "assess_training_needs":
                result = await self.assess_training_needs(
                    staff_id=params.get("staff_id"),
                    position=params.get("position")
                )
                return AgentResponse(success=True, data=result)
            elif action == "generate_training_plan":
                result = await self.generate_training_plan(
                    staff_id=params["staff_id"],
                    training_needs=params.get("training_needs"),
                    start_date=params.get("start_date")
                )
                return AgentResponse(success=True, data=result)
            elif action == "track_training_progress":
                result = await self.track_training_progress(
                    staff_id=params.get("staff_id"),
                    plan_id=params.get("plan_id")
                )
                return AgentResponse(success=True, data=result)
            elif action == "evaluate_training_effectiveness":
                result = await self.evaluate_training_effectiveness(
                    course_id=params.get("course_id"),
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            elif action == "analyze_skill_gaps":
                result = await self.analyze_skill_gaps(
                    staff_id=params["staff_id"]
                )
                return AgentResponse(success=True, data=result)
            elif action == "manage_certificates":
                result = await self.manage_certificates(
                    staff_id=params.get("staff_id"),
                    include_expired=params.get("include_expired", False)
                )
                return AgentResponse(success=True, data=result)
            elif action == "issue_certificate":
                result = await self.issue_certificate(
                    staff_id=params["staff_id"],
                    course_id=params["course_id"],
                    record_id=params["record_id"]
                )
                return AgentResponse(success=True, data=result)
            elif action == "get_training_report":
                result = await self.get_training_report(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            else:
                return AgentResponse(
                    success=False,
                    data=None,
                    error=f"Unsupported action: {action}"
                )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                error=str(e)
            )

    async def assess_training_needs(
        self,
        staff_id: Optional[str] = None,
        position: Optional[str] = None
    ) -> List[TrainingNeed]:
        """
        评估培训需求

        Args:
            staff_id: 员工ID(可选)
            position: 岗位(可选)

        Returns:
            培训需求列表
        """
        self.logger.info(
            "assessing_training_needs",
            staff_id=staff_id,
            position=position
        )

        try:
            # 获取员工数据
            staff_list = await self._get_staff_list(staff_id, position)

            needs = []
            for staff in staff_list:
                # 分析技能差距
                skill_gaps = await self.analyze_skill_gaps(staff["staff_id"])

                # 获取员工表现数据
                performance = await self._get_staff_performance(staff["staff_id"])

                # 识别培训需求
                staff_needs = self._identify_training_needs(
                    staff,
                    skill_gaps,
                    performance
                )

                needs.extend(staff_needs)

            # 按优先级排序
            needs.sort(
                key=lambda x: ["low", "medium", "high", "urgent"].index(x["priority"]),
                reverse=True
            )

            self.logger.info(
                "training_needs_assessed",
                total_needs=len(needs),
                urgent=sum(1 for n in needs if n["priority"] == TrainingPriority.URGENT)
            )

            return needs

        except Exception as e:
            self.logger.error("assess_training_needs_failed", error=str(e))
            raise

    def _identify_training_needs(
        self,
        staff: Dict[str, Any],
        skill_gaps: List[SkillGap],
        performance: Dict[str, Any]
    ) -> List[TrainingNeed]:
        """识别培训需求"""
        needs = []

        # 基于技能差距识别需求
        for gap in skill_gaps:
            if gap["gap_score"] >= int(os.getenv("TRAINING_NEED_GAP_THRESHOLD", "30")):  # 差距分数>=30需要培训
                # 推荐课程
                recommended_courses = self._recommend_courses_for_skill(
                    gap["skill_name"],
                    gap["current_level"],
                    gap["required_level"]
                )

                need: TrainingNeed = {
                    "need_id": f"NEED_{staff['staff_id']}_{gap['skill_name']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "staff_id": staff["staff_id"],
                    "staff_name": staff["staff_name"],
                    "position": staff["position"],
                    "skill_gap": gap["skill_name"],
                    "current_level": gap["current_level"],
                    "target_level": gap["required_level"],
                    "priority": gap["priority"],
                    "recommended_courses": recommended_courses,
                    "reason": f"技能差距分数: {gap['gap_score']}, 需要从{gap['current_level']}提升到{gap['required_level']}",
                    "identified_at": datetime.now().isoformat()
                }
                needs.append(need)

        # 基于表现识别需求
        if performance.get("service_score", 100) < 70:
            need: TrainingNeed = {
                "need_id": f"NEED_{staff['staff_id']}_performance_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "staff_id": staff["staff_id"],
                "staff_name": staff["staff_name"],
                "position": staff["position"],
                "skill_gap": "服务质量",
                "current_level": SkillLevel.BEGINNER,
                "target_level": SkillLevel.INTERMEDIATE,
                "priority": TrainingPriority.HIGH,
                "recommended_courses": ["COURSE_SERVICE_001"],
                "reason": f"服务得分偏低: {performance.get('service_score', 0)}",
                "identified_at": datetime.now().isoformat()
            }
            needs.append(need)

        return needs

    def _recommend_courses_for_skill(
        self,
        skill_name: str,
        current_level: SkillLevel,
        target_level: SkillLevel
    ) -> List[str]:
        """为技能推荐课程"""
        # 简化的课程推荐逻辑
        skill_course_map = {
            "菜品制作": ["COURSE_COOKING_001", "COURSE_COOKING_002"],
            "服务礼仪": ["COURSE_SERVICE_001"],
            "收银操作": ["COURSE_CASHIER_001"],
            "食品安全": ["COURSE_SAFETY_001"],
            "客户沟通": ["COURSE_COMMUNICATION_001"],
        }

        return skill_course_map.get(skill_name, ["COURSE_GENERAL_001"])

    async def generate_training_plan(
        self,
        staff_id: str,
        training_needs: Optional[List[TrainingNeed]] = None,
        start_date: Optional[str] = None
    ) -> TrainingPlan:
        """
        生成培训计划

        Args:
            staff_id: 员工ID
            training_needs: 培训需求列表(可选,不提供则自动评估)
            start_date: 开始日期(可选)

        Returns:
            培训计划
        """
        self.logger.info(
            "generating_training_plan",
            staff_id=staff_id,
            start_date=start_date
        )

        try:
            # 如果没有提供培训需求,自动评估
            if not training_needs:
                all_needs = await self.assess_training_needs(staff_id=staff_id)
                training_needs = all_needs

            if not training_needs:
                raise ValueError(f"No training needs found for staff {staff_id}")

            # 获取员工信息
            staff_list = await self._get_staff_list(staff_id=staff_id)
            staff = staff_list[0] if staff_list else {"staff_id": staff_id, "staff_name": f"员工{staff_id}"}

            # 收集所有推荐课程
            all_courses = []
            for need in training_needs:
                all_courses.extend(need["recommended_courses"])

            # 去重并排序
            unique_courses = list(set(all_courses))

            # 获取课程信息
            courses_info = await self._get_courses_info(unique_courses)

            # 计算总时长
            total_hours = sum(c["duration_hours"] for c in courses_info)

            # 确定日期范围
            if not start_date:
                start_date = datetime.now().isoformat()

            # 根据总时长计算结束日期(假设每天2小时)
            days_needed = int(total_hours / 2) + 1
            end_date = (datetime.fromisoformat(start_date) + timedelta(days=days_needed)).isoformat()

            # 确定优先级(取最高优先级)
            priorities = [n["priority"] for n in training_needs]
            priority = max(
                priorities,
                key=lambda p: ["low", "medium", "high", "urgent"].index(p)
            )

            plan: TrainingPlan = {
                "plan_id": f"PLAN_{staff_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "staff_id": staff_id,
                "staff_name": staff["staff_name"],
                "courses": unique_courses,
                "start_date": start_date,
                "end_date": end_date,
                "total_hours": total_hours,
                "priority": priority,
                "status": TrainingStatus.NOT_STARTED,
                "progress_percentage": 0.0,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            self.logger.info(
                "training_plan_generated",
                plan_id=plan["plan_id"],
                total_courses=len(unique_courses),
                total_hours=total_hours
            )

            return plan

        except Exception as e:
            self.logger.error("generate_training_plan_failed", error=str(e))
            raise

    async def track_training_progress(
        self,
        staff_id: Optional[str] = None,
        plan_id: Optional[str] = None
    ) -> List[TrainingRecord]:
        """
        追踪培训进度

        Args:
            staff_id: 员工ID(可选)
            plan_id: 计划ID(可选)

        Returns:
            培训记录列表
        """
        self.logger.info(
            "tracking_training_progress",
            staff_id=staff_id,
            plan_id=plan_id
        )

        try:
            # 获取培训记录
            records = await self._get_training_records(staff_id, plan_id)

            # 更新记录状态
            for record in records:
                record["status"] = self._update_record_status(record)

            self.logger.info(
                "training_progress_tracked",
                total_records=len(records),
                completed=sum(1 for r in records if r["status"] == TrainingStatus.COMPLETED)
            )

            return records

        except Exception as e:
            self.logger.error("track_training_progress_failed", error=str(e))
            raise

    def _update_record_status(self, record: TrainingRecord) -> TrainingStatus:
        """更新记录状态"""
        if record["status"] == TrainingStatus.COMPLETED:
            return TrainingStatus.COMPLETED

        if record["completion_date"]:
            if record.get("passed"):
                return TrainingStatus.COMPLETED
            else:
                return TrainingStatus.FAILED

        # 检查是否过期
        start_date = datetime.fromisoformat(record["start_date"])
        if datetime.now() - start_date > timedelta(days=int(os.getenv("TRAINING_RECORD_EXPIRY_DAYS", "90"))):
            return TrainingStatus.EXPIRED

        return TrainingStatus.IN_PROGRESS

    async def evaluate_training_effectiveness(
        self,
        course_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        评估培训效果

        Args:
            course_id: 课程ID(可选)
            start_date: 开始日期(可选)
            end_date: 结束日期(可选)

        Returns:
            培训效果评估结果
        """
        self.logger.info(
            "evaluating_training_effectiveness",
            course_id=course_id,
            start_date=start_date,
            end_date=end_date
        )

        try:
            # 获取培训记录
            records = await self._get_training_records(
                start_date=start_date,
                end_date=end_date
            )

            # 按课程筛选
            if course_id:
                records = [r for r in records if r["course_id"] == course_id]

            if not records:
                # 无记录时返回空评估结构，而非抛出异常
                return {
                    "course_id": course_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_participants": 0,
                    "completion_rate": 0.0,
                    "pass_rate": 0.0,
                    "average_score": 0.0,
                    "effectiveness_rating": "needs_improvement",
                    "improvement_suggestions": ["暂无培训记录，请先录入培训数据"],
                }

            # 计算指标
            total_participants = len(records)
            completed = [r for r in records if r["status"] == TrainingStatus.COMPLETED]
            completion_rate = len(completed) / total_participants

            # 计算通过率
            assessed_records = [r for r in records if r.get("passed") is not None]
            passed_records = [r for r in assessed_records if r["passed"]]
            pass_rate = len(passed_records) / len(assessed_records) if assessed_records else 0

            # 计算平均分数
            scored_records = [r for r in records if r.get("score") is not None]
            average_score = mean([r["score"] for r in scored_records]) if scored_records else 0

            # 计算平均出勤时长
            average_attendance = mean([r["attendance_hours"] for r in records])

            # 按课程分组统计
            course_stats = defaultdict(lambda: {
                "participants": 0,
                "completed": 0,
                "average_score": 0,
                "scores": []
            })

            for record in records:
                cid = record["course_id"]
                course_stats[cid]["participants"] += 1
                if record["status"] == TrainingStatus.COMPLETED:
                    course_stats[cid]["completed"] += 1
                if record.get("score") is not None:
                    course_stats[cid]["scores"].append(record["score"])

            # 计算每个课程的平均分
            for cid, stats in course_stats.items():
                if stats["scores"]:
                    stats["average_score"] = mean(stats["scores"])

            evaluation = {
                "period_start": start_date or (datetime.now() - timedelta(days=int(os.getenv("TRAINING_STATS_DAYS", "30")))).isoformat(),
                "period_end": end_date or datetime.now().isoformat(),
                "course_id": course_id,
                "total_participants": total_participants,
                "completion_rate": round(completion_rate, 2),
                "pass_rate": round(pass_rate, 2),
                "average_score": round(average_score, 2),
                "average_attendance_hours": round(average_attendance, 2),
                "course_statistics": dict(course_stats),
                "effectiveness_rating": self._calculate_effectiveness_rating(
                    completion_rate,
                    pass_rate,
                    average_score
                ),
                "evaluated_at": datetime.now().isoformat()
            }

            self.logger.info(
                "training_effectiveness_evaluated",
                completion_rate=evaluation["completion_rate"],
                pass_rate=evaluation["pass_rate"],
                effectiveness_rating=evaluation["effectiveness_rating"]
            )

            return evaluation

        except Exception as e:
            self.logger.error("evaluate_training_effectiveness_failed", error=str(e))
            raise

    def _calculate_effectiveness_rating(
        self,
        completion_rate: float,
        pass_rate: float,
        average_score: float
    ) -> str:
        """计算培训效果评级"""
        # 综合评分 = 完成率*权重 + 通过率*权重 + 平均分/100*权重
        _w_completion = float(os.getenv("TRAINING_COMPLETION_WEIGHT", "0.3"))
        _w_pass = float(os.getenv("TRAINING_PASS_WEIGHT", "0.4"))
        _w_score = float(os.getenv("TRAINING_SCORE_WEIGHT", "0.3"))
        score = (completion_rate * _w_completion + pass_rate * _w_pass + (average_score / 100) * _w_score) * 100

        if score >= float(os.getenv("TRAINING_SCORE_EXCELLENT", "90")):
            return "excellent"
        elif score >= float(os.getenv("TRAINING_SCORE_GOOD", "80")):
            return "good"
        elif score >= float(os.getenv("TRAINING_SCORE_SATISFACTORY", "70")):
            return "satisfactory"
        elif score >= float(os.getenv("TRAINING_SCORE_NEEDS_IMPROVEMENT", "60")):
            return "needs_improvement"
        else:
            return "poor"

    async def analyze_skill_gaps(
        self,
        staff_id: str
    ) -> List[SkillGap]:
        """
        分析技能差距

        Args:
            staff_id: 员工ID

        Returns:
            技能差距列表
        """
        self.logger.info("analyzing_skill_gaps", staff_id=staff_id)

        try:
            # 获取员工信息
            staff_list = await self._get_staff_list(staff_id=staff_id)
            if not staff_list:
                raise ValueError(f"Staff {staff_id} not found")

            staff = staff_list[0]

            # 获取岗位要求的技能
            required_skills = self._get_position_required_skills(staff["position"])

            # 获取员工当前技能水平
            current_skills = await self._get_staff_skills(staff_id)

            # 分析差距
            gaps = []
            for skill_name, required_level in required_skills.items():
                current_level = current_skills.get(skill_name, SkillLevel.BEGINNER)

                # 计算差距分数
                gap_score = self._calculate_gap_score(current_level, required_level)

                if gap_score > 0:
                    # 确定优先级
                    priority = self._determine_gap_priority(gap_score, skill_name)

                    gap: SkillGap = {
                        "staff_id": staff_id,
                        "staff_name": staff["staff_name"],
                        "position": staff["position"],
                        "skill_name": skill_name,
                        "current_level": current_level,
                        "required_level": required_level,
                        "gap_score": gap_score,
                        "priority": priority
                    }
                    gaps.append(gap)

            # 按差距分数排序
            gaps.sort(key=lambda x: x["gap_score"], reverse=True)

            self.logger.info(
                "skill_gaps_analyzed",
                staff_id=staff_id,
                total_gaps=len(gaps),
                high_priority=sum(1 for g in gaps if g["priority"] in [TrainingPriority.HIGH, TrainingPriority.URGENT])
            )

            return gaps

        except Exception as e:
            self.logger.error("analyze_skill_gaps_failed", error=str(e))
            raise

    def _get_position_required_skills(self, position: str) -> Dict[str, SkillLevel]:
        """获取岗位要求的技能"""
        position_skills = {
            "服务员": {
                "服务礼仪": SkillLevel.INTERMEDIATE,
                "客户沟通": SkillLevel.INTERMEDIATE,
                "菜品知识": SkillLevel.BEGINNER,
                "食品安全": SkillLevel.BEGINNER,
            },
            "厨师": {
                "菜品制作": SkillLevel.ADVANCED,
                "食品安全": SkillLevel.INTERMEDIATE,
                "厨房管理": SkillLevel.INTERMEDIATE,
            },
            "收银员": {
                "收银操作": SkillLevel.INTERMEDIATE,
                "客户沟通": SkillLevel.BEGINNER,
                "系统操作": SkillLevel.INTERMEDIATE,
            },
            "店长": {
                "团队管理": SkillLevel.ADVANCED,
                "运营管理": SkillLevel.ADVANCED,
                "客户服务": SkillLevel.INTERMEDIATE,
                "财务管理": SkillLevel.INTERMEDIATE,
            }
        }

        return position_skills.get(position, {
            "基础技能": SkillLevel.BEGINNER
        })

    def _calculate_gap_score(
        self,
        current_level: SkillLevel,
        required_level: SkillLevel
    ) -> int:
        """计算差距分数(0-100)"""
        level_scores = {
            SkillLevel.BEGINNER: 0,
            SkillLevel.INTERMEDIATE: 33,
            SkillLevel.ADVANCED: 66,
            SkillLevel.EXPERT: 100
        }

        current_score = level_scores[current_level]
        required_score = level_scores[required_level]

        gap = required_score - current_score
        return max(0, gap)

    def _determine_gap_priority(self, gap_score: int, skill_name: str) -> TrainingPriority:
        """确定差距优先级"""
        # 关键技能优先级更高
        critical_skills = ["食品安全", "服务礼仪", "菜品制作"]

        if skill_name in critical_skills:
            if gap_score >= int(os.getenv("TRAINING_PRIORITY_CRITICAL_URGENT", "50")):
                return TrainingPriority.URGENT
            elif gap_score >= int(os.getenv("TRAINING_PRIORITY_CRITICAL_HIGH", "30")):
                return TrainingPriority.HIGH
            else:
                return TrainingPriority.MEDIUM
        else:
            if gap_score >= int(os.getenv("TRAINING_PRIORITY_NORMAL_HIGH", "66")):
                return TrainingPriority.HIGH
            elif gap_score >= int(os.getenv("TRAINING_PRIORITY_NORMAL_MEDIUM", "33")):
                return TrainingPriority.MEDIUM
            else:
                return TrainingPriority.LOW

    async def manage_certificates(
        self,
        staff_id: Optional[str] = None,
        include_expired: bool = False
    ) -> List[Certificate]:
        """
        管理证书

        Args:
            staff_id: 员工ID(可选)
            include_expired: 是否包含过期证书

        Returns:
            证书列表
        """
        self.logger.info(
            "managing_certificates",
            staff_id=staff_id,
            include_expired=include_expired
        )

        try:
            # 获取证书列表
            certificates = await self._get_certificates(staff_id)

            # 更新证书状态
            for cert in certificates:
                cert["status"] = self._check_certificate_status(cert)

            # 筛选有效证书
            if not include_expired:
                certificates = [c for c in certificates if c["status"] == "valid"]

            # 识别即将过期的证书
            expiring_soon = [
                c for c in certificates
                if c.get("expiry_date") and
                datetime.fromisoformat(c["expiry_date"]) - datetime.now() < timedelta(days=int(os.getenv("TRAINING_CERT_EXPIRY_WARNING_DAYS", "30")))
            ]

            if expiring_soon:
                self.logger.warning(
                    "certificates_expiring_soon",
                    count=len(expiring_soon)
                )

            self.logger.info(
                "certificates_managed",
                total_certificates=len(certificates),
                valid=sum(1 for c in certificates if c["status"] == "valid"),
                expiring_soon=len(expiring_soon)
            )

            return certificates

        except Exception as e:
            self.logger.error("manage_certificates_failed", error=str(e))
            raise

    def _check_certificate_status(self, certificate: Certificate) -> str:
        """检查证书状态"""
        if not certificate.get("expiry_date"):
            return "valid"

        expiry_date = datetime.fromisoformat(certificate["expiry_date"])
        if datetime.now() > expiry_date:
            return "expired"

        return "valid"

    async def issue_certificate(
        self,
        staff_id: str,
        course_id: str,
        record_id: str
    ) -> Certificate:
        """
        颁发证书

        Args:
            staff_id: 员工ID
            course_id: 课程ID
            record_id: 培训记录ID

        Returns:
            证书
        """
        self.logger.info(
            "issuing_certificate",
            staff_id=staff_id,
            course_id=course_id
        )

        try:
            # 验证培训记录
            records = await self._get_training_records(staff_id=staff_id)
            record = next((r for r in records if r["record_id"] == record_id), None)

            if not record:
                raise ValueError(f"Training record {record_id} not found")

            if not record.get("passed"):
                raise ValueError("Cannot issue certificate for failed training")

            # 获取课程信息
            courses = await self._get_courses_info([course_id])
            course = courses[0] if courses else {"course_name": f"课程{course_id}"}

            # 获取员工信息
            staff_list = await self._get_staff_list(staff_id=staff_id)
            staff = staff_list[0] if staff_list else {"staff_name": f"员工{staff_id}"}

            # 计算过期日期
            validity_months = self.training_config["certificate_validity_months"]
            expiry_date = (datetime.now() + timedelta(days=validity_months * 30)).isoformat()

            certificate: Certificate = {
                "certificate_id": f"CERT_{staff_id}_{course_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "staff_id": staff_id,
                "staff_name": staff["staff_name"],
                "course_id": course_id,
                "course_name": course["course_name"],
                "issue_date": datetime.now().isoformat(),
                "expiry_date": expiry_date,
                "certificate_url": f"https://certificates.zhilian-os.com/{staff_id}/{course_id}",
                "status": "valid"
            }

            self.logger.info(
                "certificate_issued",
                certificate_id=certificate["certificate_id"],
                staff_id=staff_id,
                course_id=course_id
            )

            return certificate

        except Exception as e:
            self.logger.error("issue_certificate_failed", error=str(e))
            raise

    async def get_training_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取培训综合报告

        Args:
            start_date: 开始日期(可选)
            end_date: 结束日期(可选)

        Returns:
            培训报告
        """
        self.logger.info(
            "generating_training_report",
            start_date=start_date,
            end_date=end_date
        )

        try:
            # 并发执行多个任务
            needs_task = self.assess_training_needs()
            records_task = self.track_training_progress()
            effectiveness_task = self.evaluate_training_effectiveness(
                start_date=start_date,
                end_date=end_date
            )
            certificates_task = self.manage_certificates()

            needs, records, effectiveness, certificates = await asyncio.gather(
                needs_task,
                records_task,
                effectiveness_task,
                certificates_task
            )

            # 统计培训状态
            status_counts = defaultdict(int)
            for record in records:
                status_counts[record["status"]] += 1

            # 统计培训类型
            type_counts = defaultdict(int)
            courses = await self._get_courses_info([r["course_id"] for r in records])
            for course in courses:
                type_counts[course["training_type"]] += 1

            report = {
                "store_id": self.store_id,
                "report_date": datetime.now().isoformat(),
                "period_start": start_date or (datetime.now() - timedelta(days=int(os.getenv("TRAINING_STATS_DAYS", "30")))).isoformat(),
                "period_end": end_date or datetime.now().isoformat(),
                "training_needs": {
                    "total": len(needs),
                    "urgent": sum(1 for n in needs if n["priority"] == TrainingPriority.URGENT),
                    "high": sum(1 for n in needs if n["priority"] == TrainingPriority.HIGH),
                    "needs_list": needs[:10]  # 前10个需求
                },
                "training_progress": {
                    "total_records": len(records),
                    "status_distribution": dict(status_counts),
                    "completion_rate": status_counts[TrainingStatus.COMPLETED] / len(records) if records else 0
                },
                "training_effectiveness": effectiveness,
                "certificates": {
                    "total": len(certificates),
                    "valid": sum(1 for c in certificates if c["status"] == "valid"),
                    "expiring_soon": sum(
                        1 for c in certificates
                        if c.get("expiry_date") and
                        datetime.fromisoformat(c["expiry_date"]) - datetime.now() < timedelta(days=int(os.getenv("TRAINING_CERT_EXPIRY_WARNING_DAYS", "30")))
                    )
                },
                "training_type_distribution": dict(type_counts)
            }

            self.logger.info(
                "training_report_generated",
                total_needs=len(needs),
                total_records=len(records),
                effectiveness_rating=effectiveness["effectiveness_rating"]
            )

            return report

        except Exception as e:
            self.logger.error("get_training_report_failed", error=str(e))
            raise

    # Helper methods for mock data

    async def _get_staff_list(
        self,
        staff_id: Optional[str] = None,
        position: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取员工列表（优先从 DB 查询，无 DB 时使用内置样本数据）"""
        engine = self._get_db_engine()
        if engine:
            try:
                from sqlalchemy import text
                query = "SELECT id, name, position FROM employees WHERE store_id = :store_id AND is_active = true"
                params: Dict[str, Any] = {"store_id": self.store_id}
                if staff_id:
                    query += " AND id = :staff_id"
                    params["staff_id"] = staff_id
                if position:
                    query += " AND position = :position"
                    params["position"] = position
                with engine.connect() as conn:
                    rows = conn.execute(text(query), params).fetchall()
                if rows:
                    return [{"staff_id": str(r[0]), "staff_name": r[1], "position": r[2]} for r in rows]
            except Exception as e:
                self.logger.warning("get_staff_list_db_failed", error=str(e))

        # Fallback: 内置样本数据
        sample_staff = [
            {"staff_id": "STAFF001", "staff_name": "张三", "position": "服务员"},
            {"staff_id": "STAFF002", "staff_name": "李四", "position": "厨师"},
            {"staff_id": "STAFF003", "staff_name": "王五", "position": "收银员"},
            {"staff_id": "STAFF004", "staff_name": "赵六", "position": "店长"},
        ]
        if staff_id:
            return [s for s in sample_staff if s["staff_id"] == staff_id]
        if position:
            return [s for s in sample_staff if s["position"] == position]
        return sample_staff

    async def _get_staff_performance(self, staff_id: str) -> Dict[str, Any]:
        """获取员工表现"""
        engine = self._get_db_engine()
        if engine:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    row = conn.execute(text(
                        "SELECT performance_score FROM employees WHERE id=:id AND store_id=:s"
                    ), {"id": staff_id, "s": self.store_id}).fetchone()
                if row and row[0]:
                    score = float(row[0])
                    return {
                        "staff_id": staff_id,
                        "service_score": int(score),
                        "customer_rating": round(score / 20, 1),  # 100分制→5分制
                    }
            except Exception as e:
                self.logger.warning("get_staff_performance_db_failed", error=str(e))
        return {"staff_id": staff_id, "service_score": 0, "customer_rating": 0.0}

    async def _get_staff_skills(self, staff_id: str) -> Dict[str, "SkillLevel"]:
        """获取员工技能"""
        engine = self._get_db_engine()
        if engine:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    row = conn.execute(text(
                        "SELECT skills FROM employees WHERE id=:id AND store_id=:s"
                    ), {"id": staff_id, "s": self.store_id}).fetchone()
                if row and row[0]:
                    skill_list = row[0] if isinstance(row[0], list) else []
                    result = {}
                    for skill in skill_list:
                        result[skill] = SkillLevel.INTERMEDIATE
                    if result:
                        return result
            except Exception as e:
                self.logger.warning("get_staff_skills_db_failed", error=str(e))
        return {}

    async def _get_courses_info(self, course_ids: List[str]) -> List[TrainingCourse]:
        """获取课程信息 - 优先从 DB 查询，无 DB 时使用内置课程目录"""
        if not course_ids:
            return []

        # 尝试从 DB 的 training_courses 表查询（表存在时使用）
        engine = self._get_db_engine()
        if engine:
            try:
                from sqlalchemy import text
                placeholders = ", ".join(f":id_{i}" for i in range(len(course_ids)))
                params = {f"id_{i}": cid for i, cid in enumerate(course_ids)}
                with engine.connect() as conn:
                    rows = conn.execute(text(f"""
                        SELECT course_id, course_name, training_type, description,
                               duration_hours, target_skill_level, prerequisites,
                               content_url, instructor, max_participants, passing_score,
                               created_at
                        FROM training_courses
                        WHERE course_id IN ({placeholders})
                    """), params).fetchall()
                if rows:
                    return [
                        {
                            "course_id": str(r[0]),
                            "course_name": str(r[1]),
                            "training_type": r[2],
                            "description": str(r[3] or ""),
                            "duration_hours": float(r[4]) if r[4] else 8.0,
                            "target_skill_level": r[5],
                            "prerequisites": r[6] if isinstance(r[6], list) else [],
                            "content_url": str(r[7]) if r[7] else None,
                            "instructor": str(r[8]) if r[8] else None,
                            "max_participants": int(r[9]) if r[9] else 20,
                            "passing_score": int(r[10]) if r[10] else 70,
                            "created_at": str(r[11]) if r[11] else datetime.now().isoformat(),
                        }
                        for r in rows
                    ]
            except Exception as e:
                # training_courses 表不存在时静默降级到内置目录
                self.logger.debug("get_courses_db_fallback", error=str(e))

        # 降级：使用内置课程目录
        now = datetime.now().isoformat()
        return [
            {**_BUILTIN_COURSE_CATALOG[cid], "created_at": now}
            if cid in _BUILTIN_COURSE_CATALOG
            else {
                "course_id": cid,
                "course_name": f"课程 {cid}",
                "training_type": "skill_upgrade",
                "description": "待完善课程",
                "duration_hours": 8.0,
                "target_skill_level": "intermediate",
                "prerequisites": [],
                "content_url": None,
                "instructor": None,
                "max_participants": 20,
                "passing_score": 70,
                "created_at": now,
            }
            for cid in course_ids
        ]

    async def _get_training_records(
        self,
        staff_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[TrainingRecord]:
        """获取培训记录"""
        engine = self._get_db_engine()
        if engine:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    query = "SELECT id, name, training_completed, hire_date FROM employees WHERE store_id = :store_id AND is_active = true"
                    params: Dict[str, Any] = {"store_id": self.store_id}
                    if staff_id:
                        query += " AND id = :staff_id"
                        params["staff_id"] = staff_id
                    rows = conn.execute(text(query), params).fetchall()

                records: List[TrainingRecord] = []
                for row in rows:
                    emp_id, emp_name, completed_courses, hire_date = row[0], row[1], row[2] or [], row[3]
                    for idx, course_id in enumerate(completed_courses):
                        record: TrainingRecord = {
                            "record_id": f"REC_{emp_id}_{idx:04d}",
                            "staff_id": emp_id,
                            "course_id": course_id,
                            "plan_id": None,
                            "start_date": hire_date.isoformat() if hire_date else datetime.now().isoformat(),
                            "completion_date": datetime.now().isoformat(),
                            "status": TrainingStatus.COMPLETED,
                            "attendance_hours": 8.0,
                            "score": 80,
                            "passed": True,
                            "feedback": "培训完成",
                            "created_at": hire_date.isoformat() if hire_date else datetime.now().isoformat(),
                        }
                        if plan_id and record.get("plan_id") != plan_id:
                            continue
                        records.append(record)
                return records
            except Exception as e:
                self.logger.warning("get_training_records_db_failed", error=str(e))

        # Fallback: empty list (no mock random data)
        return []

    async def _get_certificates(self, staff_id: Optional[str] = None) -> List[Certificate]:
        """获取证书列表"""
        engine = self._get_db_engine()
        if engine:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    query = "SELECT id, name, training_completed FROM employees WHERE store_id = :store_id AND is_active = true"
                    params: Dict[str, Any] = {"store_id": self.store_id}
                    if staff_id:
                        query += " AND id = :staff_id"
                        params["staff_id"] = staff_id
                    rows = conn.execute(text(query), params).fetchall()

                validity_days = int(os.getenv("TRAINING_CERT_VALIDITY_DAYS", "365"))
                certs: List[Certificate] = []
                for row in rows:
                    emp_id, emp_name, completed_courses = row[0], row[1], row[2] or []
                    for idx, course_id in enumerate(completed_courses):
                        issue_date = datetime.now() - timedelta(days=validity_days // 2)
                        expiry_date = issue_date + timedelta(days=validity_days)
                        cert: Certificate = {
                            "certificate_id": f"CERT_{emp_id}_{idx:04d}",
                            "staff_id": emp_id,
                            "staff_name": emp_name,
                            "course_id": course_id,
                            "course_name": course_id,
                            "issue_date": issue_date.isoformat(),
                            "expiry_date": expiry_date.isoformat(),
                            "certificate_url": f"https://certificates.zhilian-os.com/{emp_id}/{course_id}",
                            "status": "valid",
                        }
                        certs.append(cert)
                return certs
            except Exception as e:
                self.logger.warning("get_certificates_db_failed", error=str(e))

        return []