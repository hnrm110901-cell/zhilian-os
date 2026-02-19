"""
智能消息路由服务
Intelligent Message Router Service

将用户消息路由到相应的Agent进行处理
"""
from typing import Dict, Any, Optional, Tuple
import structlog
import re

logger = structlog.get_logger()


class MessageRouter:
    """消息路由器 - 将用户消息路由到相应的Agent"""

    def __init__(self):
        """初始化消息路由器"""
        # Agent关键词映射
        self.agent_keywords = {
            "schedule": ["排班", "班次", "调班", "换班", "值班", "上班时间", "工作时间"],
            "order": ["订单", "点单", "下单", "预定", "预订", "订餐", "外卖"],
            "inventory": ["库存", "补货", "进货", "盘点", "原料", "食材", "缺货"],
            "service": ["服务", "投诉", "反馈", "评价", "满意度", "客户"],
            "training": ["培训", "学习", "课程", "考试", "技能", "教学"],
            "decision": ["分析", "报表", "数据", "统计", "KPI", "业绩", "经营"],
            "reservation": ["宴会", "包厢", "预定", "座位", "大厅"],
        }

        # Agent动作映射
        self.action_keywords = {
            "schedule": {
                "查询": "query_schedule",
                "生成": "generate_schedule",
                "调整": "adjust_schedule",
                "申请": "request_change",
            },
            "order": {
                "查询": "query_order",
                "创建": "create_order",
                "取消": "cancel_order",
                "修改": "update_order",
            },
            "inventory": {
                "查询": "query_inventory",
                "补货": "request_restock",
                "盘点": "inventory_check",
                "预警": "check_alerts",
            },
            "service": {
                "查询": "query_feedback",
                "提交": "submit_feedback",
                "分析": "analyze_quality",
            },
            "training": {
                "查询": "query_courses",
                "报名": "enroll_course",
                "进度": "check_progress",
            },
            "decision": {
                "分析": "analyze_kpi",
                "报表": "generate_report",
                "建议": "get_recommendations",
            },
            "reservation": {
                "查询": "query_reservation",
                "预定": "create_reservation",
                "取消": "cancel_reservation",
            },
        }

    def route_message(self, content: str, user_id: str) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """
        路由消息到相应的Agent

        Args:
            content: 消息内容
            user_id: 用户ID

        Returns:
            (agent_type, action, params) 元组
        """
        # 识别Agent类型
        agent_type = self._identify_agent(content)
        if not agent_type:
            return None, None, {}

        # 识别动作
        action = self._identify_action(agent_type, content)
        if not action:
            # 如果无法识别具体动作，返回默认查询动作
            action = self._get_default_action(agent_type)

        # 提取参数
        params = self._extract_params(agent_type, action, content, user_id)

        return agent_type, action, params

    def _identify_agent(self, content: str) -> Optional[str]:
        """
        识别消息应该路由到哪个Agent

        Args:
            content: 消息内容

        Returns:
            Agent类型，如果无法识别则返回None
        """
        # 计算每个Agent的匹配分数
        scores = {}
        for agent_type, keywords in self.agent_keywords.items():
            score = sum(1 for keyword in keywords if keyword in content)
            if score > 0:
                scores[agent_type] = score

        # 返回得分最高的Agent
        if scores:
            return max(scores, key=scores.get)

        return None

    def _identify_action(self, agent_type: str, content: str) -> Optional[str]:
        """
        识别用户想要执行的动作

        Args:
            agent_type: Agent类型
            content: 消息内容

        Returns:
            动作名称
        """
        if agent_type not in self.action_keywords:
            return None

        action_map = self.action_keywords[agent_type]
        for keyword, action in action_map.items():
            if keyword in content:
                return action

        return None

    def _get_default_action(self, agent_type: str) -> str:
        """
        获取Agent的默认动作

        Args:
            agent_type: Agent类型

        Returns:
            默认动作名称
        """
        default_actions = {
            "schedule": "query_schedule",
            "order": "query_order",
            "inventory": "query_inventory",
            "service": "query_feedback",
            "training": "query_courses",
            "decision": "analyze_kpi",
            "reservation": "query_reservation",
        }
        return default_actions.get(agent_type, "query")

    def _extract_params(
        self, agent_type: str, action: str, content: str, user_id: str
    ) -> Dict[str, Any]:
        """
        从消息中提取参数

        Args:
            agent_type: Agent类型
            action: 动作名称
            content: 消息内容
            user_id: 用户ID

        Returns:
            参数字典
        """
        params = {
            "user_id": user_id,
            "message": content,
        }

        # 提取日期
        date_pattern = r"(\d{4}[-年]\d{1,2}[-月]\d{1,2}[日]?)"
        dates = re.findall(date_pattern, content)
        if dates:
            params["date"] = dates[0].replace("年", "-").replace("月", "-").replace("日", "")

        # 提取数字
        number_pattern = r"(\d+)"
        numbers = re.findall(number_pattern, content)
        if numbers:
            params["quantity"] = int(numbers[0])

        # 根据Agent类型提取特定参数
        if agent_type == "schedule":
            if "今天" in content:
                params["date"] = "today"
            elif "明天" in content:
                params["date"] = "tomorrow"
            elif "本周" in content:
                params["period"] = "week"

        elif agent_type == "order":
            if "订单号" in content:
                # 提取订单号
                order_pattern = r"[A-Z0-9]{10,}"
                orders = re.findall(order_pattern, content)
                if orders:
                    params["order_id"] = orders[0]

        elif agent_type == "inventory":
            # 提取商品名称（简单实现）
            if "查询" in content:
                # 移除关键词后的内容可能是商品名
                item_content = content.replace("查询", "").replace("库存", "").strip()
                if item_content:
                    params["item_name"] = item_content

        return params

    def format_agent_response(
        self, agent_type: str, action: str, result: Dict[str, Any]
    ) -> str:
        """
        格式化Agent响应为用户友好的消息

        Args:
            agent_type: Agent类型
            action: 动作名称
            result: Agent执行结果

        Returns:
            格式化后的消息文本
        """
        if not result.get("success", False):
            error_msg = result.get("error", "处理失败")
            return f"❌ {error_msg}\n\n请重新描述您的需求，或联系管理员。"

        # 根据Agent类型格式化响应
        if agent_type == "schedule":
            return self._format_schedule_response(action, result)
        elif agent_type == "order":
            return self._format_order_response(action, result)
        elif agent_type == "inventory":
            return self._format_inventory_response(action, result)
        elif agent_type == "service":
            return self._format_service_response(action, result)
        elif agent_type == "training":
            return self._format_training_response(action, result)
        elif agent_type == "decision":
            return self._format_decision_response(action, result)
        elif agent_type == "reservation":
            return self._format_reservation_response(action, result)
        else:
            return "✅ 处理成功"

    def _format_schedule_response(self, action: str, result: Dict[str, Any]) -> str:
        """格式化排班响应"""
        data = result.get("data", {})

        if action == "query_schedule":
            shifts = data.get("shifts", [])
            if not shifts:
                return "📅 暂无排班信息"

            msg = "📅 排班信息：\n\n"
            for shift in shifts[:5]:  # 最多显示5条
                msg += f"• {shift.get('date')} {shift.get('time_range')}\n"
                msg += f"  岗位：{shift.get('position')}\n\n"

            if len(shifts) > 5:
                msg += f"... 还有 {len(shifts) - 5} 条排班\n"

            return msg
        else:
            return "✅ 排班操作已完成"

    def _format_order_response(self, action: str, result: Dict[str, Any]) -> str:
        """格式化订单响应"""
        data = result.get("data", {})

        if action == "query_order":
            orders = data.get("orders", [])
            if not orders:
                return "📦 暂无订单信息"

            msg = "📦 订单信息：\n\n"
            for order in orders[:5]:
                msg += f"• 订单号：{order.get('order_id')}\n"
                msg += f"  状态：{order.get('status')}\n"
                msg += f"  金额：¥{order.get('amount', 0):.2f}\n\n"

            return msg
        else:
            return "✅ 订单操作已完成"

    def _format_inventory_response(self, action: str, result: Dict[str, Any]) -> str:
        """格式化库存响应"""
        data = result.get("data", {})

        if action == "query_inventory":
            items = data.get("items", [])
            if not items:
                return "📦 暂无库存信息"

            msg = "📦 库存信息：\n\n"
            for item in items[:5]:
                msg += f"• {item.get('name')}\n"
                msg += f"  库存：{item.get('quantity')} {item.get('unit')}\n"
                status = item.get('status', 'normal')
                if status == 'low':
                    msg += f"  ⚠️ 库存不足\n"
                msg += "\n"

            return msg
        else:
            return "✅ 库存操作已完成"

    def _format_service_response(self, action: str, result: Dict[str, Any]) -> str:
        """格式化服务响应"""
        return "✅ 服务质量查询已完成"

    def _format_training_response(self, action: str, result: Dict[str, Any]) -> str:
        """格式化培训响应"""
        return "✅ 培训信息查询已完成"

    def _format_decision_response(self, action: str, result: Dict[str, Any]) -> str:
        """格式化决策响应"""
        return "✅ 数据分析已完成"

    def _format_reservation_response(self, action: str, result: Dict[str, Any]) -> str:
        """格式化预定响应"""
        return "✅ 预定操作已完成"


# 创建全局实例
message_router = MessageRouter()
