"""
奥琦玮供应链开放平台适配器
Base URL: http://openapi.acescm.cn
认证方式: AppKey + AppSecret + MD5签名
"""
import hashlib
import os
import time
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger()


class AoqiweiAdapter:
    """奥琦玮供应链开放平台适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含:
                - base_url: API基础URL
                - app_key: AppKey
                - app_secret: AppSecret
                - timeout: 超时时间（秒）
                - retry_times: 重试次数
        """
        self.base_url = config.get("base_url", os.getenv("AOQIWEI_BASE_URL", "http://openapi.acescm.cn"))
        self.app_key = config.get("app_key", os.getenv("AOQIWEI_APP_KEY", ""))
        self.app_secret = config.get("app_secret", os.getenv("AOQIWEI_APP_SECRET", ""))
        self.timeout = config.get("timeout", int(os.getenv("AOQIWEI_TIMEOUT", "30")))
        self.retry_times = config.get("retry_times", int(os.getenv("AOQIWEI_RETRY_TIMES", "3")))

        if not self.app_key or not self.app_secret:
            logger.warning("奥琦玮AppKey或AppSecret未配置，将使用降级模式")

        logger.info("奥琦玮供应链适配器初始化", base_url=self.base_url)

    def _sign(self, params: Dict[str, Any]) -> str:
        """
        生成请求签名

        算法：将所有参数按key字母序排列，拼接为 key=value&...，
        末尾追加 AppSecret，对整体做 MD5（小写）。

        Args:
            params: 请求参数（不含 sign 字段）

        Returns:
            签名字符串（32位小写MD5）
        """
        sorted_keys = sorted(params.keys())
        parts = [f"{k}={params[k]}" for k in sorted_keys if params[k] is not None and params[k] != ""]
        raw = "&".join(parts) + self.app_secret
        return hashlib.md5(raw.encode("utf-8")).hexdigest().lower()

    def _build_params(self, biz_params: Dict[str, Any]) -> Dict[str, Any]:
        """构建带公共参数和签名的完整请求体"""
        params: Dict[str, Any] = {
            "appKey": self.app_key,
            "timestamp": str(int(time.time() * 1000)),
        }
        params.update(biz_params)
        params["sign"] = self._sign(params)
        return params

    async def _request(
        self,
        endpoint: str,
        biz_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送 POST 请求

        Args:
            endpoint: API端点路径（如 /api/stock_v1/remain.html）
            biz_params: 业务参数

        Returns:
            API响应数据

        Raises:
            Exception: 请求失败或业务错误
        """
        params = self._build_params(biz_params or {})
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.retry_times):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=params)
                    response.raise_for_status()
                    result = response.json()

                # 奥琦玮通用响应格式：{"code": 0, "msg": "success", "data": {...}}
                code = result.get("code", result.get("errcode", 0))
                if code != 0:
                    msg = result.get("msg", result.get("errmsg", "未知错误"))
                    raise Exception(f"奥琦玮API错误 [{code}]: {msg}")

                return result.get("data", result)

            except httpx.HTTPStatusError as e:
                logger.error("HTTP请求失败", endpoint=endpoint, status=e.response.status_code, attempt=attempt + 1)
                if attempt == self.retry_times - 1:
                    raise Exception(f"HTTP请求失败: {e.response.status_code}")

            except Exception as e:
                if "奥琦玮API错误" in str(e):
                    raise
                logger.error("请求异常", endpoint=endpoint, error=str(e), attempt=attempt + 1)
                if attempt == self.retry_times - 1:
                    raise

        raise Exception("请求失败，已达到最大重试次数")

    # ==================== POS订单接口 ====================

    async def pos_upload_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        POS订单上传

        Args:
            order_data: 订单数据，包含门店编码、订单号、菜品明细等

        Returns:
            上传结果
        """
        logger.info("POS订单上传", order_no=order_data.get("orderNo"))
        try:
            return await self._request("/api/pos/order.html", order_data)
        except Exception as e:
            logger.warning("POS订单上传失败，返回降级数据", error=str(e))
            return {"success": False, "message": str(e)}

    async def pos_check_order(self, shop_code: str, date: str) -> Dict[str, Any]:
        """
        POS订单校验

        Args:
            shop_code: 门店编码
            date: 日期（YYYY-MM-DD）

        Returns:
            校验结果
        """
        logger.info("POS订单校验", shop_code=shop_code, date=date)
        try:
            return await self._request("/api/pos/ordercheck.html", {"shopCode": shop_code, "date": date})
        except Exception as e:
            logger.warning("POS订单校验失败", error=str(e))
            return {"checked": False, "message": str(e)}

    async def pos_day_done(self, shop_code: str, date: str) -> Dict[str, Any]:
        """
        POS日结

        Args:
            shop_code: 门店编码
            date: 日结日期（YYYY-MM-DD）

        Returns:
            日结结果
        """
        logger.info("POS日结", shop_code=shop_code, date=date)
        try:
            return await self._request("/api/pos/daydone.html", {"shopCode": shop_code, "date": date})
        except Exception as e:
            logger.warning("POS日结失败", error=str(e))
            return {"success": False, "message": str(e)}

    # ==================== 库存接口 ====================

    async def query_stock(
        self,
        depot_code: Optional[str] = None,
        shop_code: Optional[str] = None,
        good_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询库存

        Args:
            depot_code: 仓库编码
            shop_code: 门店编码
            good_code: 货品编码

        Returns:
            库存列表
        """
        params: Dict[str, Any] = {}
        if depot_code:
            params["depotCode"] = depot_code
        if shop_code:
            params["shopCode"] = shop_code
        if good_code:
            params["goodCode"] = good_code

        logger.info("查询库存", params=params)
        try:
            result = await self._request("/api/stock_v1/remain.html", params)
            return result if isinstance(result, list) else result.get("list", [])
        except Exception as e:
            logger.warning("查询库存失败，返回空列表", error=str(e))
            return []

    async def query_stock_estimate(
        self,
        shop_code: str,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        库存预估

        Args:
            shop_code: 门店编码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            预估数据
        """
        logger.info("库存预估", shop_code=shop_code)
        try:
            return await self._request(
                "/api/stock_v1/estimate.html",
                {"shopCode": shop_code, "startDate": start_date, "endDate": end_date},
            )
        except Exception as e:
            logger.warning("库存预估失败", error=str(e))
            return {}

    # ==================== 货品接口 ====================

    async def query_goods(
        self,
        good_code: Optional[str] = None,
        good_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        查询货品信息

        Args:
            good_code: 货品编码
            good_name: 货品名称（模糊查询）
            page: 页码
            page_size: 每页数量

        Returns:
            货品列表及分页信息
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if good_code:
            params["goodCode"] = good_code
        if good_name:
            params["goodName"] = good_name

        logger.info("查询货品", params=params)
        try:
            return await self._request("/api/basic/good.html", params)
        except Exception as e:
            logger.warning("查询货品失败", error=str(e))
            return {"list": [], "total": 0}

    async def query_suppliers(
        self,
        supplier_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        查询供应商信息

        Args:
            supplier_code: 供应商编码
            page: 页码
            page_size: 每页数量

        Returns:
            供应商列表
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if supplier_code:
            params["supplierCode"] = supplier_code

        logger.info("查询供应商", params=params)
        try:
            return await self._request("/api/basic/supplier.html", params)
        except Exception as e:
            logger.warning("查询供应商失败", error=str(e))
            return {"list": [], "total": 0}

    # ==================== 配送业务接口 ====================

    async def create_delivery_apply(self, apply_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建配送申请单

        Args:
            apply_data: 申请数据，包含门店编码、货品列表、期望配送时间等

        Returns:
            申请结果，含申请单号
        """
        logger.info("创建配送申请", shop_code=apply_data.get("shopCode"))
        try:
            return await self._request("/api/delivery_v1/applygood.html", apply_data)
        except Exception as e:
            logger.warning("创建配送申请失败", error=str(e))
            return {"success": False, "message": str(e)}

    async def query_delivery_dispatch_out(
        self,
        start_date: str,
        end_date: str,
        shop_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询配送出库单

        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            shop_code: 门店编码

        Returns:
            配送出库单列表
        """
        params: Dict[str, Any] = {"startDate": start_date, "endDate": end_date}
        if shop_code:
            params["shopCode"] = shop_code

        logger.info("查询配送出库单", params=params)
        try:
            result = await self._request("/api/delivery_v1/dispatchout.html", params)
            return result if isinstance(result, list) else result.get("list", [])
        except Exception as e:
            logger.warning("查询配送出库单失败", error=str(e))
            return []

    async def confirm_delivery_in(self, dispatch_in_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        配送入库确认（门店收货）

        Args:
            dispatch_in_data: 入库数据，包含出库单号、实收数量等

        Returns:
            确认结果
        """
        logger.info("配送入库确认", order_no=dispatch_in_data.get("orderNo"))
        try:
            return await self._request("/api/delivery_v1/dispatchin.html", dispatch_in_data)
        except Exception as e:
            logger.warning("配送入库确认失败", error=str(e))
            return {"success": False, "message": str(e)}

    # ==================== 采购业务接口 ====================

    async def query_purchase_orders(
        self,
        start_date: str,
        end_date: str,
        depot_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        查询采购入库单

        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            depot_code: 仓库编码
            page: 页码
            page_size: 每页数量

        Returns:
            采购入库单列表及分页信息
        """
        params: Dict[str, Any] = {
            "startDate": start_date,
            "endDate": end_date,
            "page": page,
            "pageSize": page_size,
        }
        if depot_code:
            params["depotCode"] = depot_code

        logger.info("查询采购入库单", params=params)
        try:
            return await self._request("/api/purchase/pur_order.html", params)
        except Exception as e:
            logger.warning("查询采购入库单失败", error=str(e))
            return {"list": [], "total": 0}

    async def create_reserve_order(self, reserve_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建采购订货单

        Args:
            reserve_data: 订货数据，包含仓库编码、货品列表、期望到货时间等

        Returns:
            创建结果，含订货单号
        """
        logger.info("创建采购订货单", depot_code=reserve_data.get("depotCode"))
        try:
            return await self._request("/api/purchase/reserve_order.html", reserve_data)
        except Exception as e:
            logger.warning("创建采购订货单失败", error=str(e))
            return {"success": False, "message": str(e)}

    # ==================== 数据报表接口 ====================

    async def query_inventory_report(
        self,
        start_date: str,
        end_date: str,
        shop_code: Optional[str] = None,
        good_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询进销存报表

        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            shop_code: 门店编码
            good_code: 货品编码

        Returns:
            进销存报表数据
        """
        params: Dict[str, Any] = {"startDate": start_date, "endDate": end_date}
        if shop_code:
            params["shopCode"] = shop_code
        if good_code:
            params["goodCode"] = good_code

        logger.info("查询进销存报表", params=params)
        try:
            return await self._request("/api/report/invocingcost.html", params)
        except Exception as e:
            logger.warning("查询进销存报表失败", error=str(e))
            return {"list": [], "total": 0}

    async def query_good_diff_analysis(
        self,
        start_date: str,
        end_date: str,
        shop_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        货品差异分析

        Args:
            start_date: 开始日期
            end_date: 结束日期
            shop_code: 门店编码

        Returns:
            差异分析数据
        """
        params: Dict[str, Any] = {"startDate": start_date, "endDate": end_date}
        if shop_code:
            params["shopCode"] = shop_code

        logger.info("货品差异分析", params=params)
        try:
            return await self._request("/api/report/goodDiffAnalyse.html", params)
        except Exception as e:
            logger.warning("货品差异分析失败", error=str(e))
            return {"list": []}
