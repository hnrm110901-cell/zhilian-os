"""
品智收银系统MD5签名工具
"""
import hashlib
from collections import OrderedDict
from typing import Dict, Any


def generate_sign(token: str, params: Dict[str, Any]) -> str:
    """
    生成品智API签名

    签名算法:
    1. 将所有请求参数（除sign外）按参数名ASCII码升序排列
    2. 排除pageIndex和pageSize参数
    3. 拼接成key1=value1&key2=value2&...&token=xxx格式
    4. 对拼接后的字符串进行MD5加密得到签名值

    Args:
        token: API Token
        params: 请求参数字典

        Returns:
        MD5签名字符串（32位小写）

    Example:
        >>> params = {"ognid": "12345", "beginDate": "2024-01-01"}
        >>> sign = generate_sign("your_token", params)
        >>> print(sign)
        'a1b2c3d4e5f6...'
    """
    # 1. 过滤掉sign、pageIndex、pageSize参数
    filtered_params = {
        k: v
        for k, v in params.items()
        if k not in ["sign", "pageIndex", "pageSize"] and v is not None
    }

    # 2. 按key排序
    ordered_params = OrderedDict(sorted(filtered_params.items()))

    # 3. 构建参数字符串
    param_list = [f"{k}={v}" for k, v in ordered_params.items()]
    param_str = "&".join(param_list)

    # 4. 添加token
    param_str += f"&token={token}"

    # 5. MD5加密（小写）
    sign = hashlib.md5(param_str.encode("utf-8")).hexdigest()

    return sign


def verify_sign(token: str, params: Dict[str, Any], expected_sign: str) -> bool:
    """
    验证品智API签名

    Args:
        token: API Token
        params: 请求参数字典
        expected_sign: 期望的签名值

    Returns:
        签名是否正确
    """
    calculated_sign = generate_sign(token, params)
    return calculated_sign == expected_sign
