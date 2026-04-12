"""
菜品SOP服务
管理菜品标准操作流程（步骤/时间/温度/图片），用于KDS展示和新员工培训
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class SOPStep:
    """SOP步骤"""
    step_no: int = 0
    description: str = ""
    duration_seconds: int = 0    # 预计耗时（秒）
    temperature: Optional[int] = None  # 温度要求（℃）
    image_url: str = ""
    tips: str = ""               # 注意事项
    tools: List[str] = field(default_factory=list)  # 所需工具


@dataclass
class DishSOP:
    """菜品SOP"""
    sop_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dish_id: str = ""
    dish_name: str = ""
    version: int = 1
    steps: List[SOPStep] = field(default_factory=list)
    total_time_seconds: int = 0  # 总耗时
    difficulty: str = ""         # "简单"/"中等"/"复杂"
    serving_size: str = ""       # 份量说明
    store_id: str = ""           # 空=全局
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def total_time_minutes(self) -> float:
        return round(self.total_time_seconds / 60, 1)


class DishSOPService:
    """菜品SOP服务"""

    def __init__(self):
        # dish_id -> DishSOP（最新版）
        self._sops: Dict[str, DishSOP] = {}
        # sop_id -> DishSOP
        self._by_sop_id: Dict[str, DishSOP] = {}

    def create_sop(
        self,
        dish_id: str,
        dish_name: str,
        steps: List[SOPStep],
        difficulty: str = "中等",
        serving_size: str = "",
        store_id: str = "",
    ) -> DishSOP:
        """创建菜品SOP"""
        if not steps:
            raise ValueError("SOP步骤不能为空")
        # 自动计算总耗时
        total_time = sum(s.duration_seconds for s in steps)
        # 自动编号
        for i, step in enumerate(steps, 1):
            step.step_no = i

        sop = DishSOP(
            dish_id=dish_id,
            dish_name=dish_name,
            steps=steps,
            total_time_seconds=total_time,
            difficulty=difficulty,
            serving_size=serving_size,
            store_id=store_id,
        )
        self._sops[dish_id] = sop
        self._by_sop_id[sop.sop_id] = sop
        logger.info("创建菜品SOP", dish=dish_name, steps=len(steps),
                     time_min=sop.total_time_minutes)
        return sop

    def get_sop(self, dish_id: str) -> Optional[DishSOP]:
        """获取菜品SOP（最新版）"""
        return self._sops.get(dish_id)

    def get_sop_by_id(self, sop_id: str) -> Optional[DishSOP]:
        """按SOP ID获取"""
        return self._by_sop_id.get(sop_id)

    def display_on_kds(self, dish_id: str) -> Dict:
        """
        生成KDS（厨显）展示数据
        简化步骤信息，适合屏幕展示
        """
        sop = self._sops.get(dish_id)
        if sop is None:
            return {"dish_id": dish_id, "has_sop": False, "steps": []}

        kds_steps = []
        for step in sop.steps:
            kds_step = {
                "step_no": step.step_no,
                "text": step.description,
                "time": f"{step.duration_seconds}秒" if step.duration_seconds < 120 else f"{step.duration_seconds // 60}分钟",
            }
            if step.temperature is not None:
                kds_step["temp"] = f"{step.temperature}℃"
            if step.tips:
                kds_step["tips"] = step.tips
            kds_steps.append(kds_step)

        return {
            "dish_id": dish_id,
            "dish_name": sop.dish_name,
            "has_sop": True,
            "total_time": f"{sop.total_time_minutes}分钟",
            "difficulty": sop.difficulty,
            "steps": kds_steps,
        }

    def update_step(
        self,
        dish_id: str,
        step_no: int,
        description: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        temperature: Optional[int] = None,
        image_url: Optional[str] = None,
        tips: Optional[str] = None,
    ) -> DishSOP:
        """更新SOP中的某个步骤"""
        sop = self._sops.get(dish_id)
        if sop is None:
            raise ValueError(f"菜品SOP不存在: {dish_id}")

        target = None
        for step in sop.steps:
            if step.step_no == step_no:
                target = step
                break
        if target is None:
            raise ValueError(f"步骤不存在: {step_no}")

        if description is not None:
            target.description = description
        if duration_seconds is not None:
            target.duration_seconds = duration_seconds
        if temperature is not None:
            target.temperature = temperature
        if image_url is not None:
            target.image_url = image_url
        if tips is not None:
            target.tips = tips

        # 重新计算总耗时
        sop.total_time_seconds = sum(s.duration_seconds for s in sop.steps)
        sop.updated_at = datetime.now(timezone.utc)
        sop.version += 1
        logger.info("更新SOP步骤", dish=sop.dish_name, step_no=step_no)
        return sop

    def add_step(self, dish_id: str, step: SOPStep) -> DishSOP:
        """在SOP末尾添加步骤"""
        sop = self._sops.get(dish_id)
        if sop is None:
            raise ValueError(f"菜品SOP不存在: {dish_id}")
        step.step_no = len(sop.steps) + 1
        sop.steps.append(step)
        sop.total_time_seconds = sum(s.duration_seconds for s in sop.steps)
        sop.updated_at = datetime.now(timezone.utc)
        sop.version += 1
        return sop

    def list_all(self, store_id: str = "") -> List[Dict]:
        """列出所有SOP摘要"""
        result = []
        for sop in self._sops.values():
            if store_id and sop.store_id != store_id and sop.store_id != "":
                continue
            result.append({
                "sop_id": sop.sop_id,
                "dish_id": sop.dish_id,
                "dish_name": sop.dish_name,
                "steps_count": len(sop.steps),
                "total_time_minutes": sop.total_time_minutes,
                "difficulty": sop.difficulty,
                "version": sop.version,
            })
        return result
