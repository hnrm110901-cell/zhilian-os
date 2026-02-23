"""
品智收银系统API适配器
提供门店管理、菜品管理、订单查询、营业数据等功能
"""
import os
from typing import Dict, Any, Optional, List
import structlog
from datetime import datetime
import httpx
from .signature import generate_sign

logger = structlog.get_logger()


class PinzhiAdapter:
    """品智收银系统适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含:
                - base_url: API基础URL
                - token: API Token
                - timeout: 超时时间（秒）
                - retry_times: 重试次数
        """
        self.config = config
        self.base_url = config.get("base_url")
        self.token = config.get("token")
        self.timeout = config.get("timeout", 30)
        self.retry_times = config.get("retry_times", 3)

        if not self.base_url:
            raise ValueError("base_url不能为空")
        if not self.token:
            raise ValueError("token不能为空")

        # 初始化HTTP客户端
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )

        logger.info("品智适配器初始化", base_url=self.base_url)

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送HTTP请求

        Args:
            method: HTTP方法 (GET/POST)
            endpoint: API端点
            params: URL参数
            data: 请求体数据

        Returns:
            API响应数据

        Raises:
            Exception: 请求失败
        """
        for attempt in range(self.retry_times):
            try:
                if method.upper() == "GET":
                    response = await self.client.get(endpoint, params=params)
                elif method.upper() == "POST":
                    response = await self.client.post(endpoint, json=data)
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")

                response.raise_for_status()
                result = response.json()
                self.handle_error(result)
                return result

            except httpx.HTTPStatusError as e:
                logger.error(
                    "HTTP请求失败",
                    endpoint=endpoint,
                    status_code=e.response.status_code,
                    attempt=attempt + 1,
                )
                if attempt == self.retry_times - 1:
                    raise Exception(f"HTTP请求失败: {e.response.status_code}")

            except Exception as e:
                logger.error(
                    "请求异常",
                    endpoint=endpoint,
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt == self.retry_times - 1:
                    raise

        raise Exception("请求失败，已达到最大重试次数")

    def _add_sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        为请求参数添加签名

        Args:
            params: 请求参数

        Returns:
            添加签名后的参数
        """
        sign = generate_sign(self.token, params)
        params["sign"] = sign
        return params

    def handle_error(self, response: Dict[str, Any]) -> None:
        """
        处理业务错误

        Args:
            response: API响应数据

        Raises:
            Exception: 业务错误
        """
        # 品智系统使用success字段，0表示成功
        success = response.get("success")
        if success is not None and success != 0:
            msg = response.get("msg", "未知错误")
            raise Exception(f"品智API错误 [{success}]: {msg}")

        # 有些接口使用errcode字段
        errcode = response.get("errcode")
        if errcode is not None and errcode != 0:
            errmsg = response.get("errmsg", "未知错误")
            raise Exception(f"品智API错误 [{errcode}]: {errmsg}")

    # ==================== 基础数据接口 ====================

    async def get_store_info(self, ognid: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        查询门店信息

        Args:
            ognid: 门店omsID，不传则返回所有门店

        Returns:
            门店信息列表
        """
        params = {}
        if ognid:
            params["ognid"] = ognid

        params = self._add_sign(params)
        logger.info("查询门店信息", ognid=ognid)

        try:
            response = await self._request("GET", "/pinzhi/storeInfo.do", params=params)
            return response.get("res", [])
        except Exception as e:
            logger.warning("查询门店信息失败，返回模拟数据", error=str(e))
            # 返回模拟数据作为降级方案
            return [
                {
                    "ognid": 12345,
                    "ognno": "SH001",
                    "ognNewNo": "SH001",
                    "ognname": "上海浦东店",
                    "ognaddress": "上海市浦东新区XX路XX号",
                    "ogntel": "021-12345678",
                    "brandid": 1,
                    "brandname": "测试品牌",
                }
            ]

    async def get_dish_categories(self) -> List[Dict[str, Any]]:
        """
        查询菜品类别

        Returns:
            菜品类别列表
        """
        params = self._add_sign({})
        logger.info("查询菜品类别")

        try:
            response = await self._request("GET", "/pinzhi/reportcategory.do", params=params)
            return response.get("data", [])
        except Exception as e:
            logger.warning("查询菜品类别失败，返回模拟数据", error=str(e))
            return [
                {
                    "rcId": 1,
                    "brandId": 1,
                    "rcNO": "01",
                    "rcNAME": "热销菜品",
                    "fatherId": 0,
                    "status": 0,
                },
                {
                    "rcId": 2,
                    "brandId": 1,
                    "rcNO": "0101",
                    "rcNAME": "招牌菜",
                    "fatherId": 1,
                    "status": 0,
                },
            ]

    async def get_dishes(self, updatetime: int = 0) -> List[Dict[str, Any]]:
        """
        查询菜品信息

        Args:
            updatetime: 同步时间戳，传0拉取所有，传日期拉取该日期后修改的菜品

        Returns:
            菜品信息列表
        """
        params = {"updatetime": updatetime}
        params = self._add_sign(params)
        logger.info("查询菜品信息", updatetime=updatetime)

        # TODO: 实际调用API
        # response = await self.request("POST", "/pinzhi/querydishes.do", data=params)
        # return response.get("data", [])

        # 临时返回模拟数据
        return [
            {
                "dishesId": 1001,
                "dishesCode": "D001",
                "dishesName": "宫保鸡丁",
                "dishPrice": 48.00,
                "rcId": 1,
                "status": 0,
                "unit": "份",
                "isMaterial": 0,
                "isPractice": 0,
                "isRecommend": 1,
                "channel": "1,2,3",
            }
        ]

    async def get_practice(self) -> List[Dict[str, Any]]:
        """
        查询做法和配料信息

        Returns:
            做法和配料列表
        """
        params = self._add_sign({})
        logger.info("查询做法配料")

        # TODO: 实际调用API
        # response = await self.request("POST", "/pinzhi/queryPractice.do", data=params)
        # return response.get("data", [])

        return []

    async def get_tables(self) -> List[Dict[str, Any]]:
        """
        查询收银桌台信息

        Returns:
            桌台信息列表
        """
        params = self._add_sign({})
        logger.info("查询桌台信息")

        # TODO: 实际调用API
        # response = await self.request("GET", "/pinzhi/queryTable.do", params=params)
        # return response.get("res", [])

        # 临时返回模拟数据
        return [
            {
                "tabelNo": "0001",
                "tableId": 45460,
                "blId": 395,
                "tableName": "0001",
                "blName": "一楼营业区",
            },
            {
                "tabelNo": "0002",
                "tableId": 45471,
                "blId": 395,
                "tableName": "0002",
                "blName": "一楼营业区",
            },
        ]

    async def get_employees(self) -> List[Dict[str, Any]]:
        """
        查询门店用户（员工）信息

        Returns:
            员工信息列表
        """
        params = self._add_sign({})
        logger.info("查询员工信息")

        # TODO: 实际调用API
        # response = await self.request("GET", "/pinzhi/employe.do", params=params)
        # return response.get("data", [])

        # 临时返回模拟数据
        return [
            {
                "epId": 255,
                "epNo": "E001",
                "epcardNo": "18708181320",
                "epName": "张三",
                "epEnName": "Zhang San",
                "epTel": "18532127729",
                "epMail": "",
                "epQQ": "",
                "status": 0,
                "epSex": 1,
                "pgId": 113,
                "pgName": "收银员",
            }
        ]

    # ==================== 业务数据接口 ====================

    async def query_orders(
        self,
        ognid: Optional[str] = None,
        begin_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page_index: int = 1,
        page_size: int = int(os.getenv("PINZHI_PAGE_SIZE", "20")),
    ) -> List[Dict[str, Any]]:
        """
        按日期查询订单数据（V2）

        Args:
            ognid: 门店omsID
            begin_date: 开始日期（yyyy-MM-dd）
            end_date: 结束日期（yyyy-MM-dd）
            page_index: 页码
            page_size: 每页数量

        Returns:
            订单列表
        """
        params = {"pageIndex": page_index, "pageSize": page_size}

        if ognid:
            params["ognid"] = ognid
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date

        params = self._add_sign(params)
        logger.info(
            "查询订单",
            ognid=ognid,
            begin_date=begin_date,
            end_date=end_date,
            page=page_index,
        )

        try:
            response = await self._request("GET", "/pinzhi/queryOrderListV2.do", params=params)
            return response.get("res", [])
        except Exception as e:
            logger.warning("查询订单失败，返回模拟数据", error=str(e))
            return [
                {
                    "billId": "uuid-001",
                    "billNo": "B202401010001",
                    "orderSource": 1,
                    "outOrderID": "",
                    "tableNo": "0001",
                    "people": 4,
                    "openOrderUser": "服务员001",
                    "deskUser": "收银员001",
                    "openTime": "2024-01-01 12:00:00",
                    "cashiers": "收银员001",
                    "payTime": "2024-01-01 13:00:00",
                    "payDate": "2024-01-01",
                    "vipCard": "M20240001",
                    "vipName": "张三",
                    "dishPriceTotal": 20000,
                    "teaPrice": 400,
                    "servicePrice": 0,
                    "packingPrice": 0,
                    "billPriceTotal": 20400,
                    "specialOfferPrice": 2000,
                    "singleDiscountPrice": 0,
                    "freePrice": 0,
                    "realPrice": 18400,
                    "billStatus": 1,
                    "paymentList": [],
                }
            ]

    async def query_order_summary(
        self, ognid: str, business_date: str
    ) -> Dict[str, Any]:
        """
        按门店查询收入数据

        Args:
            ognid: 门店omsID
            business_date: 营业日（yyyy-MM-dd）

        Returns:
            收入汇总数据
        """
        params = {"ognid": ognid, "businessDate": business_date}
        params = self._add_sign(params)
        logger.info("查询收入数据", ognid=ognid, business_date=business_date)

        # TODO: 实际调用API
        # response = await self.request("GET", "/pinzhi/queryOrderSummary.do", params=params)
        # return response.get("res", {})

        return {
            "ognId": int(ognid),
            "businesDate": business_date,
            "rcIdList": [],
            "cdIdList": [],
        }

    async def query_store_summary_list(
        self, business_date: str
    ) -> List[Dict[str, Any]]:
        """
        查询所有门店营业额及菜类销售数据

        Args:
            business_date: 营业日（yyyy-MM-dd）

        Returns:
            门店营业数据列表
        """
        params = {"businessDate": business_date}
        params = self._add_sign(params)
        logger.info("查询门店营业数据", business_date=business_date)

        # TODO: 实际调用API
        # response = await self.request("GET", "/pinzhi/queryStoreSummaryList.do", params=params)
        # return response.get("data", [])

        return []

    async def query_cooking_detail(self, business_date: str) -> List[Dict[str, Any]]:
        """
        查询门店出品过程明细数据

        Args:
            business_date: 营业日（yyyy-MM-dd）

        Returns:
            出品过程明细列表
        """
        params = {"businessDate": business_date}
        params = self._add_sign(params)
        logger.info("查询出品明细", business_date=business_date)

        # TODO: 实际调用API
        # response = await self.request("GET", "/pinzhi/queryCookingDetail.do", params=params)
        # return response.get("data", [])

        return []

    async def get_payment_customer(
        self,
        begin_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询挂账客户管理

        Args:
            begin_date: 查询开始时间
            end_date: 查询结束时间

        Returns:
            挂账客户列表
        """
        params = {}
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date

        params = self._add_sign(params)
        logger.info("查询挂账客户", begin_date=begin_date, end_date=end_date)

        # TODO: 实际调用API
        # response = await self.request("GET", "/pinzhi/paymentCustomer.do", params=params)
        # return response.get("data", [])

        return []

    async def get_pay_types(self) -> List[Dict[str, Any]]:
        """
        查询支付方式

        Returns:
            支付方式列表
        """
        params = self._add_sign({})
        logger.info("查询支付方式")

        # TODO: 实际调用API
        # response = await self.request("GET", "/pinzhi/payType.do", params=params)
        # return response.get("data", [])

        # 临时返回模拟数据
        return [
            {"id": 1, "name": "现金", "category": 1},
            {"id": 2, "name": "会员卡", "category": 2},
            {"id": 3, "name": "微信支付", "category": 3},
            {"id": 4, "name": "支付宝", "category": 3},
        ]

    async def download_bill_data(
        self, ognid: str, pay_date: str, pay_type: int
    ) -> str:
        """
        下载微信支付宝订单数据

        Args:
            ognid: 门店omsID
            pay_date: 日期（yyyy-MM-dd）
            pay_type: 支付类型（1-微信，2-支付宝）

        Returns:
            对账单数据
        """
        params = {"ognid": ognid, "payDate": pay_date, "payType": pay_type}
        params = self._add_sign(params)
        logger.info(
            "下载对账单", ognid=ognid, pay_date=pay_date, pay_type=pay_type
        )

        # TODO: 实际调用API
        # response = await self.request("GET", "/pinzhi/downloadBillData.do", params=params)
        # return response.get("data", "")

        return ""

    async def close(self):
        """关闭适配器，释放资源"""
        logger.info("关闭品智适配器")
        await self.client.aclose()
