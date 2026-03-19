"""会员等级变更后的自动化行动服务 — 状态转移触发企微推送或旅程"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

TRANSITION_ACTIONS: Dict[tuple, Dict[str, Any]] = {
    ("FIRST_ORDER_PENDING", "REPEAT"): {
        "type": "wechat_push", "template": "repeat_celebration", "priority": "medium",
        "message": "欢迎再次光临！您已成为我们的回头客 ✨",
    },
    ("REPEAT", "HIGH_FREQUENCY"): {
        "type": "wechat_push", "template": "high_frequency_recognition", "priority": "medium",
        "message": "感谢您的频繁光顾！已为您标记高频贵客身份 🎉",
    },
    ("HIGH_FREQUENCY", "VIP"): {
        "type": "wechat_push", "template": "vip_welcome", "priority": "high",
        "message": "恭喜您成为 VIP 会员！专属特权已开通 👑",
    },
    ("VIP", "AT_RISK"): {
        "type": "journey_trigger", "journey": "vip_retention", "priority": "urgent",
    },
    ("HIGH_FREQUENCY", "AT_RISK"): {
        "type": "journey_trigger", "journey": "high_freq_win_back", "priority": "high",
    },
    ("REPEAT", "AT_RISK"): {
        "type": "journey_trigger", "journey": "repeat_win_back", "priority": "medium",
    },
    ("AT_RISK", "DORMANT"): {
        "type": "journey_trigger", "journey": "dormant_reactivation", "priority": "high",
    },
}


class LifecycleActionService:
    def get_action(self, from_state: str, to_state: str,
                   store_id: str, customer_id: str) -> Optional[Dict[str, Any]]:
        if from_state == to_state:
            return None
        action = TRANSITION_ACTIONS.get((from_state, to_state))
        if action:
            return {**action, "store_id": store_id, "customer_id": customer_id}
        return None
