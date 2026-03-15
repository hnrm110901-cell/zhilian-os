"""诺诺开放平台 — 电子发票适配器"""
import hashlib
import hmac
import json
import time
import uuid
from typing import Dict, Any, Optional
import httpx
import structlog

logger = structlog.get_logger()


class NuonuoAdapter:
    """诺诺开放平台发票适配器

    文档: https://open.nuonuo.com
    认证: App Token + HMAC-SHA256签名
    """

    def __init__(self, config: Dict[str, Any]):
        self.app_key = config["app_key"]
        self.app_secret = config["app_secret"]
        self.tax_number = config["tax_number"]  # 销方税号
        self.base_url = config.get("base_url", "https://sdk.nuonuo.com/open/v1/services")
        self.sandbox = config.get("sandbox", False)
        if self.sandbox:
            self.base_url = "https://sandbox.nuonuocs.cn/open/v1/services"
        self._client = httpx.AsyncClient(timeout=30)
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    async def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 300:
            return self._access_token
        url = (
            "https://sandbox.nuonuocs.cn/accessToken"
            if self.sandbox
            else "https://open.nuonuo.com/accessToken"
        )
        resp = await self._client.post(url, json={
            "client_id": self.app_key,
            "client_secret": self.app_secret,
            "grant_type": "client_credentials",
        })
        data = resp.json()
        self._access_token = data.get("access_token", "")
        self._token_expires_at = time.time() + data.get("expires_in", 7200)
        return self._access_token

    def _generate_sign(self, params: str, timestamp: str, nonce: str) -> str:
        sign_str = f"{self.app_secret}{timestamp}{nonce}{params}"
        return hmac.new(
            self.app_secret.encode(), sign_str.encode(), hashlib.sha256
        ).hexdigest().upper()

    async def _request(self, method: str, content: Dict[str, Any]) -> Dict[str, Any]:
        token = await self._get_access_token()
        timestamp = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex[:8]
        content_str = json.dumps(content, ensure_ascii=False)

        headers = {
            "X-Nuonuo-Sign": self._generate_sign(content_str, timestamp, nonce),
            "accessToken": token,
            "userTax": self.tax_number,
            "method": method,
            "timestamp": timestamp,
            "nonce": nonce,
            "Content-Type": "application/json",
        }
        resp = await self._client.post(self.base_url, headers=headers, content=content_str)
        result = resp.json()
        if result.get("code") != "E0000":
            logger.error("nuonuo.api_error", method=method, code=result.get("code"), msg=result.get("describe"))
            raise Exception(f"诺诺API错误: {result.get('describe', '未知错误')}")
        return result.get("result", {})

    async def issue_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """开具发票（异步，通过回调返回结果）"""
        return await self._request("nuonuo.ElectronInvoice.requestBillingNew", invoice_data)

    async def query_invoice(self, serial_nos: list) -> Dict[str, Any]:
        """查询发票开票结果"""
        return await self._request("nuonuo.ElectronInvoice.queryInvoiceResult", {
            "serialNos": serial_nos,
        })

    async def void_invoice(self, invoice_id: str, invoice_code: str, invoice_number: str) -> Dict[str, Any]:
        """作废发票"""
        return await self._request("nuonuo.ElectronInvoice.invoiceCancellation", {
            "invoiceId": invoice_id,
            "invoiceCode": invoice_code,
            "invoiceNo": invoice_number,
        })

    async def issue_red_invoice(self, original_invoice_code: str, original_invoice_number: str,
                                 reason: str, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """开具红字发票（红冲）"""
        invoice_data["invoiceCode"] = original_invoice_code
        invoice_data["invoiceNo"] = original_invoice_number
        invoice_data["reason"] = reason
        return await self._request("nuonuo.ElectronInvoice.requestBillingNew", invoice_data)

    async def download_pdf(self, invoice_code: str, invoice_number: str) -> str:
        """获取发票PDF下载链接"""
        result = await self._request("nuonuo.ElectronInvoice.getInvoicePDFUrl", {
            "invoiceCode": invoice_code,
            "invoiceNo": invoice_number,
        })
        return result.get("pdfUrl", "")

    async def close(self):
        await self._client.aclose()
