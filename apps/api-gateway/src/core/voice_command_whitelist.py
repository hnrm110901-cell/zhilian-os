"""
语音指令白名单
Voice Command Whitelist

高危操作（财务/批量删除/系统权限）必须回到手机端二次确认；
低风险查询/通知类操作可直接通过语音执行。

设计原则：
- 高危先检查（优先拒绝）
- 未匹配指令保守降级为 CONFIRM（需语音二次确认）
- 所有函数为纯函数，无 I/O、无 DB 依赖
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class RiskLevel(str, Enum):
    SAFE = "safe"  # 查询/通知类，直接执行，无需确认
    CONFIRM = "confirm"  # 普通写操作，需语音二次确认
    HIGH_RISK = "high_risk"  # 财务/批量删除/权限，必须手机端确认后才执行


@dataclass(frozen=True)
class VoiceValidationResult:
    allowed: bool  # 是否允许发起（高危也 True，但需确认）
    risk_level: RiskLevel
    category: str  # 指令类别，如 "query" / "financial"
    require_mobile_confirm: bool  # True → 推送到手机端等待点按确认
    reason: str  # 人类可读的说明


# ── 关键词字典（中文关键词匹配）────────────────────────────────────────────────

_SAFE_PATTERNS: dict[str, list[str]] = {
    "query": [
        "查询",
        "查看",
        "今天",
        "昨天",
        "营收",
        "库存",
        "订单",
        "多少",
        "报告",
        "状态",
        "营业额",
        "收入",
        "库存量",
        "剩余",
    ],
    "notify": [
        "催菜",
        "呼叫服务员",
        "通知后厨",
        "提醒备料",
        "叫一下",
        "通知",
    ],
    "simple_confirm": [
        "确认收货",
        "标记完成",
        "确认入库",
        "签收",
    ],
}

_HIGH_RISK_PATTERNS: dict[str, list[str]] = {
    "financial": [
        "退款",
        "打款",
        "转账",
        "提现",
        "划账",
        "付款",
        "汇款",
    ],
    "bulk_inventory": [
        "调拨大宗",
        "批量删除",
        "清空库存",
        "全部清除",
        "批量清除",
    ],
    "system": [
        "修改权限",
        "删除数据",
        "重置系统",
        "删除账号",
        "撤销权限",
    ],
}

_CONFIRM_PATTERNS: dict[str, list[str]] = {
    "purchase": ["采购", "下单", "订货", "进货", "补货"],
    "adjust": ["调整", "修改", "更新", "变更", "修正"],
    "schedule": ["排班", "换班", "调休", "请假"],
}


# ── 纯函数 ────────────────────────────────────────────────────────────────────


def classify_risk_level(command: str) -> Tuple[RiskLevel, str]:
    """
    对语音指令进行风险分级。

    高危先检查：即使指令同时包含安全和高危关键词，
    也优先返回 HIGH_RISK（保守原则）。

    Returns:
        (RiskLevel, category_name)
    """
    # 1. 高危先检查
    for category, keywords in _HIGH_RISK_PATTERNS.items():
        if any(kw in command for kw in keywords):
            return RiskLevel.HIGH_RISK, category

    # 2. 安全类（查询/通知/简单确认）
    for category, keywords in _SAFE_PATTERNS.items():
        if any(kw in command for kw in keywords):
            return RiskLevel.SAFE, category

    # 3. 普通写操作（需语音二次确认）
    for category, keywords in _CONFIRM_PATTERNS.items():
        if any(kw in command for kw in keywords):
            return RiskLevel.CONFIRM, category

    # 4. 未匹配 → 保守降级为 CONFIRM
    return RiskLevel.CONFIRM, "unknown"


def is_high_risk_operation(command: str) -> bool:
    """判断指令是否属于高危操作（需手机端二次确认）。"""
    level, _ = classify_risk_level(command)
    return level == RiskLevel.HIGH_RISK


def get_confirmation_type(command: str) -> str:
    """
    返回该指令需要的确认方式。

    Returns:
        "none"   — 无需确认，直接执行
        "voice"  — 语音二次确认（再说一次"确认"）
        "mobile" — 手机端点按确认（高危操作）
    """
    level, _ = classify_risk_level(command)
    if level == RiskLevel.SAFE:
        return "none"
    if level == RiskLevel.CONFIRM:
        return "voice"
    return "mobile"


# ── 类接口 ────────────────────────────────────────────────────────────────────


class VoiceCommandWhitelist:
    """语音指令白名单验证器（无状态，可共享实例）。"""

    def validate(self, command: str) -> VoiceValidationResult:
        """
        验证语音指令，返回风险等级与是否需要手机确认。

        Args:
            command: 已识别的语音文本（中文）

        Returns:
            VoiceValidationResult
        """
        if not command or not command.strip():
            return VoiceValidationResult(
                allowed=False,
                risk_level=RiskLevel.CONFIRM,
                category="empty",
                require_mobile_confirm=False,
                reason="指令为空，无法执行",
            )

        level, category = classify_risk_level(command)

        if level == RiskLevel.HIGH_RISK:
            return VoiceValidationResult(
                allowed=True,  # 允许发起流程，但必须经手机端确认后才执行
                risk_level=level,
                category=category,
                require_mobile_confirm=True,
                reason=f"高危操作（{category}）—— 已推送到手机端，请点按确认后执行",
            )

        if level == RiskLevel.CONFIRM:
            return VoiceValidationResult(
                allowed=True,
                risk_level=level,
                category=category,
                require_mobile_confirm=False,
                reason="请再次说「确认」以执行该操作",
            )

        # SAFE
        return VoiceValidationResult(
            allowed=True,
            risk_level=level,
            category=category,
            require_mobile_confirm=False,
            reason="指令通过审查，直接执行",
        )
