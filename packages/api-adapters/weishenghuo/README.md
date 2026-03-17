# 微生活会员管理平台适配器

微生活（i200.cn）会员管理系统 API 适配器，用于会员数据同步、查询和交易记录拉取。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| WSH_BASE_URL | API 基础地址 | https://open.i200.cn |
| WSH_APPID | 应用ID | - |
| WSH_APP_SECRET | 应用密钥 | - |
| WSH_TIMEOUT | 请求超时（秒） | 30 |
| WSH_RETRY_TIMES | 重试次数 | 3 |

## 使用

```python
from src.adapter import WeishenghuoAdapter

adapter = WeishenghuoAdapter({
    "appid": "your_appid",
    "app_secret": "your_secret",
})

# 查询会员
member = await adapter.get_member_info(mobile="13800138000")

# 分页拉取会员列表（增量同步）
members = await adapter.list_members(page=1, page_size=100, updated_after="2026-03-01")

# 关闭连接
await adapter.aclose()
```

## 测试

```bash
pytest tests/ -v
```
