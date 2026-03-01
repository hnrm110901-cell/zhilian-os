"""
根因 → 培训映射配置

将 WasteReasoningEngine 输出的根因维度映射到具体培训技能、课程和紧迫度。
被 dispatch_training_recommendation Celery 任务引用。

根因维度来源（waste_reasoning_service._step5_root_cause_score）：
  - inventory_variance  库存盘点差异
  - bom_deviation       BOM 配方偏差
  - time_window_staff   时间窗口当班员工
  - supplier_batch      供应商批次质量

额外通用根因类型（供外部调用方传入）：
  - staff_error / process_deviation / food_quality / equipment_fault / supply_chain
"""

from typing import Any, Dict

# key: 根因维度/类型（与 waste_reasoning_service step5 的 dimension 字段一致）
# value: 对应培训配置
ROOT_CAUSE_TO_TRAINING: Dict[str, Dict[str, Any]] = {
    # ── 来自损耗推理引擎的维度 ──────────────────────────────────────
    "inventory_variance": {
        "skill_gap": "inventory_management",
        "course_ids": ["inv_count_accuracy", "stock_recording_sop"],
        "urgency": "high",
        "urgency_days": 3,
        "description": "库存盘点不准确，需培训库存管理操作规范与盘点方法",
    },
    "bom_deviation": {
        "skill_gap": "food_prep_standards",
        "course_ids": ["bom_compliance", "portion_control"],
        "urgency": "high",
        "urgency_days": 3,
        "description": "食材消耗偏离BOM标准，需培训食材操作规范与份量控制",
    },
    "time_window_staff": {
        "skill_gap": "waste_prevention",
        "course_ids": ["waste_awareness", "food_handling_basics"],
        "urgency": "medium",
        "urgency_days": 7,
        "description": "当班时段出现异常损耗，需培训废料预防意识与食材处理",
    },
    "supplier_batch": {
        "skill_gap": "receiving_inspection",
        "course_ids": ["supplier_quality_sop", "receiving_checklist"],
        "urgency": "medium",
        "urgency_days": 7,
        "description": "供应商批次质量异常，需培训收货验收操作规范",
    },
    # ── 通用根因类型（供外部调用方使用）──────────────────────────────
    "staff_error": {
        "skill_gap": "general_operations",
        "course_ids": ["ops_standards", "error_prevention"],
        "urgency": "medium",
        "urgency_days": 7,
        "description": "操作失误导致损耗，需加强操作规范培训",
    },
    "process_deviation": {
        "skill_gap": "sop_compliance",
        "course_ids": ["sop_training", "process_adherence"],
        "urgency": "medium",
        "urgency_days": 7,
        "description": "流程偏差，需重新培训标准操作程序",
    },
    "food_quality": {
        "skill_gap": "food_safety",
        "course_ids": ["food_safety_basics", "quality_control_101"],
        "urgency": "high",
        "urgency_days": 2,
        "description": "食材质量问题导致损耗，需培训食品安全与质量管控",
    },
    "equipment_fault": {
        "skill_gap": "equipment_maintenance",
        "course_ids": ["equipment_ops", "preventive_maintenance"],
        "urgency": "low",
        "urgency_days": 14,
        "description": "设备故障导致损耗，需培训设备操作规范与日常保养",
    },
    "supply_chain": {
        "skill_gap": "supply_management",
        "course_ids": ["supply_chain_basics", "vendor_management"],
        "urgency": "low",
        "urgency_days": 14,
        "description": "供应链问题导致损耗，需加强供应管理培训",
    },
}

# 紧迫度 → 优先级标签映射
URGENCY_TO_PRIORITY: Dict[str, str] = {
    "high": "P1",
    "medium": "P2",
    "low": "P3",
}
