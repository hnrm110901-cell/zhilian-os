"""动态标签推断服务（纯函数，无DB依赖）"""
from typing import Dict, Any, List


def infer_tags(customer: Dict[str, Any]) -> List[str]:
    """根据客户数据推断动态标签"""
    tags = []
    monetary = customer.get("monetary", 0)
    frequency = customer.get("frequency", 0)
    recency = customer.get("recency_days", 999)

    # 基础标签
    if monetary >= 5000:
        tags.append("高消费")
    if frequency >= 4:
        tags.append("高频")
    if recency <= 7:
        tags.append("近期活跃")

    # 时段偏好
    avg_time = customer.get("avg_order_time")
    if avg_time is not None:
        if 11 <= avg_time < 14:
            tags.append("午餐偏好")
        elif 17 <= avg_time < 21:
            tags.append("晚餐偏好")

    # 消费类型
    avg_party = customer.get("avg_party_size", 0)
    if avg_party >= 4:
        tags.append("家庭聚餐")

    # 消费趋势（需要至少3个月数据）
    amounts = customer.get("monthly_amounts", [])
    if len(amounts) >= 3:
        recent = amounts[-2:]
        earlier = amounts[:-2]
        if recent and earlier:
            avg_recent = sum(recent) / len(recent)
            avg_earlier = sum(earlier) / len(earlier)
            if avg_earlier > 0:
                ratio = avg_recent / avg_earlier
                if ratio >= 1.3:
                    tags.append("消费上升")
                elif ratio <= 0.5:
                    tags.append("消费下降")

    # 跨店活跃
    if customer.get("store_count", 1) >= 2:
        tags.append("跨店活跃")

    return tags or ["普通用户"]
