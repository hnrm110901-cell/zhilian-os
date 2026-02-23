"""
美团等位API集成服务
Meituan Queue API Integration Service
"""
from typing import Dict, Any, List, Optional
import httpx
import hashlib
import time
import json
from urllib.parse import urlencode
import structlog

from ..core.config import settings

logger = structlog.get_logger()


class MeituanQueueService:
    """美团等位API服务"""

    def __init__(self):
        self.base_url = "https://api-open-cater.meituan.com"
        self.business_id = "49"  # 到店餐饮排队业务ID
        self.developer_id = settings.MEITUAN_DEVELOPER_ID if hasattr(settings, 'MEITUAN_DEVELOPER_ID') else ""
        self.sign_key = settings.MEITUAN_SIGN_KEY if hasattr(settings, 'MEITUAN_SIGN_KEY') else ""

    def _generate_sign(self, params: Dict[str, Any]) -> str:
        """
        生成签名

        Args:
            params: 请求参数

        Returns:
            签名字符串
        """
        # 按key排序
        sorted_params = sorted(params.items())

        # 拼接字符串
        sign_str = "&".join([f"{k}={v}" for k, v in sorted_params])

        # 添加signKey
        sign_str = f"{sign_str}{self.sign_key}"

        # MD5加密
        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()

        return sign

    async def _make_request(
        self,
        endpoint: str,
        biz_data: Dict[str, Any],
        app_auth_token: str,
    ) -> Dict[str, Any]:
        """
        发起API请求

        Args:
            endpoint: API端点
            biz_data: 业务数据
            app_auth_token: 应用授权token

        Returns:
            响应数据
        """
        try:
            # 构建系统参数
            timestamp = int(time.time())
            params = {
                "appAuthToken": app_auth_token,
                "businessId": self.business_id,
                "charset": "utf-8",
                "developerId": self.developer_id,
                "timestamp": str(timestamp),
                "version": "2",
            }

            # 生成签名
            sign = self._generate_sign(params)
            params["sign"] = sign

            # 添加业务参数
            params["biz"] = json.dumps(biz_data, ensure_ascii=False)

            # 发起请求
            url = f"{self.base_url}{endpoint}"

            async with httpx.AsyncClient(timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))) as client:
                response = await client.post(
                    url,
                    data=urlencode(params),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"
                    },
                )

                result = response.json()

                logger.info(
                    "美团API请求",
                    endpoint=endpoint,
                    code=result.get("code"),
                    msg=result.get("msg"),
                )

                return result

        except Exception as e:
            logger.error(
                "美团API请求失败",
                endpoint=endpoint,
                error=str(e),
                exc_info=e,
            )
            raise

    async def sync_table_types(
        self,
        app_auth_token: str,
        table_types: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        同步全量桌型

        Args:
            app_auth_token: 应用授权token
            table_types: 桌型列表
                [
                    {
                        "tableTypeId": 1,
                        "tableTypeName": "小桌",
                        "displayName": "小桌(2-4人)",
                        "minCapacity": 2,
                        "maxCapacity": 4,
                        "numPrefix": "A",
                        "operateType": 1  # 1:新增/更新 2:删除
                    }
                ]

        Returns:
            同步结果
        """
        biz_data = {
            "operateTime": int(time.time() * 1000),
            "tableTypeList": table_types,
        }

        result = await self._make_request(
            "/dcpd/queue/shop/config/tableType/sync",
            biz_data,
            app_auth_token,
        )

        return result

    async def sync_offline_order(
        self,
        app_auth_token: str,
        order_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        同步线下新订单

        Args:
            app_auth_token: 应用授权token
            order_data: 订单数据
                {
                    "peopleCount": 4,
                    "orderId": "local_order_123",
                    "num": 24,  # 排队号码数字部分
                    "index": 5,  # 队列位置
                    "tableTypeId": 1,
                    "takeNumTime": 1708432307945,  # 毫秒时间戳
                    "mobile": "13800138000",  # 可选
                    "remark": "需要儿童座椅"  # 可选
                }

        Returns:
            同步结果，包含美团侧订单ID (orderViewId)
        """
        result = await self._make_request(
            "/dcpd/queue/order/create/sync",
            order_data,
            app_auth_token,
        )

        return result

    async def update_order_status(
        self,
        app_auth_token: str,
        order_view_id: str,
        order_id: str,
        status: int,
        index: int,
    ) -> Dict[str, Any]:
        """
        更新订单状态

        Args:
            app_auth_token: 应用授权token
            order_view_id: 美团侧订单ID
            order_id: 本地订单ID
            status: 订单状态
                1: 取号中
                2: 取号失败
                3: 排队中
                4: 叫号中
                5: 已就餐
                6: 已过号
                7: 取消中
                8: 已取消
            index: 队列位置

        Returns:
            更新结果
        """
        biz_data = {
            "orderViewId": order_view_id,
            "orderId": order_id,
            "status": status,
            "index": index,
            "operateTime": int(time.time() * 1000),
        }

        result = await self._make_request(
            "/dcpd/queue/order/status/update",
            biz_data,
            app_auth_token,
        )

        return result

    async def sync_waiting_info(
        self,
        app_auth_token: str,
        order_wait_list: List[Dict[str, Any]],
        table_type_wait_list: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        同步等位信息

        Args:
            app_auth_token: 应用授权token
            order_wait_list: 分订单等位详情
                [
                    {
                        "orderViewId": "meituan_order_123",
                        "orderId": "local_order_123",
                        "index": 5
                    }
                ]
            table_type_wait_list: 桌位等位详情
                [
                    {
                        "tableTypeId": 1,
                        "waitCount": 10  # 等待桌数
                    }
                ]

        Returns:
            同步结果
        """
        biz_data = {
            "orderWaitList": order_wait_list,
            "tableTypeWaitList": table_type_wait_list,
            "operateTime": int(time.time() * 1000),
        }

        result = await self._make_request(
            "/dcpd/queue/order/index/sync",
            biz_data,
            app_auth_token,
        )

        return result

    async def callback_queue_number_result(
        self,
        app_auth_token: str,
        order_view_id: str,
        success: bool,
        order_data: Optional[Dict[str, Any]] = None,
        error_msg: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        取号结果回调

        当美团/大众点评用户线上取号时，需要回调此接口告知取号结果

        Args:
            app_auth_token: 应用授权token
            order_view_id: 美团侧订单ID
            success: 是否成功
            order_data: 成功时的订单数据
                {
                    "tableTypeId": 1,
                    "orderId": "local_order_123",
                    "index": 5,
                    "num": 24,
                    "takeNumTime": 1708432307945
                }
            error_msg: 失败时的错误信息

        Returns:
            回调结果
        """
        if success and order_data:
            biz_data = {
                "orderViewId": order_view_id,
                "tableTypeId": order_data["tableTypeId"],
                "orderId": order_data["orderId"],
                "index": order_data["index"],
                "num": order_data["num"],
                "takeNumTime": order_data["takeNumTime"],
                "status": 3,  # 3表示取号成功
            }
        else:
            biz_data = {
                "orderViewId": order_view_id,
                "status": 2,  # 2表示取号失败
                "msg": error_msg or "取号失败",
            }

        result = await self._make_request(
            "/dcpd/queue/order/create/callback",
            biz_data,
            app_auth_token,
        )

        return result

    def map_local_status_to_meituan(self, local_status: str) -> int:
        """
        将本地排队状态映射到美团状态

        Args:
            local_status: 本地状态 (waiting, called, seated, cancelled, no_show)

        Returns:
            美团状态码
        """
        status_mapping = {
            "waiting": 3,  # 排队中
            "called": 4,  # 叫号中
            "seated": 5,  # 已就餐
            "cancelled": 8,  # 已取消
            "no_show": 6,  # 已过号
        }

        return status_mapping.get(local_status, 3)


# 全局服务实例
meituan_queue_service = MeituanQueueService()
