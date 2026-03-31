## 储值卡+积分路由注册

在 `apps/api-gateway/src/main.py` 中添加以下两行 import 和两行 include_router：

```python
from src.api.stored_value import router as stored_value_router
from src.api.loyalty_points import router as loyalty_points_router

app.include_router(stored_value_router)
app.include_router(loyalty_points_router)
```

### 路由汇总

#### 储值卡（stored_value_router）
| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/v1/stored-value/recharge` | 充值 |
| POST | `/api/v1/stored-value/consume` | 消费扣款 |
| GET  | `/api/v1/stored-value/{member_id}/balance` | 余额查询 |
| GET  | `/api/v1/stored-value/{member_id}/transactions` | 流水列表 |
| POST | `/api/v1/stored-value/promotions` | 创建充值活动 |
| GET  | `/api/v1/stored-value/promotions` | 活动列表 |

#### 积分与等级（loyalty_points_router）
| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/v1/points/earn` | 消费得积分 |
| POST | `/api/v1/points/redeem` | 积分兑换抵扣 |
| GET  | `/api/v1/points/{member_id}` | 积分账户+等级 |
| GET  | `/api/v1/points/{member_id}/history` | 积分历史 |
| GET  | `/api/v1/points/level-config` | 等级配置 |
| PUT  | `/api/v1/points/level-config/{level}` | 更新等级配置 |

### 数据库迁移

迁移链路：z69 → z70（储值卡）→ z71（积分等级）

```bash
cd apps/api-gateway
alembic upgrade z71
```
