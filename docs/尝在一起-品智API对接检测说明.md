# 尝在一起 · 品智 API 对接检测说明

**目的**：确认「对接品智 API、拉取尝在一起数据」在工程中是否已实现，以及如何自检。

---

## 一、实现情况总览

| 层级 | 内容 | 状态 | 说明 |
|------|------|------|------|
| **适配器** | 品智收银 API 封装（.do 接口） | ✅ 已实现 | `packages/api-adapters/pinzhi/`：门店、经营数据、订单、支付方式等 |
| **脚本 · 对接检测** | 接口连通性 | ✅ 已实现 | `scripts/check_pinzhi_api.py`：检测各 .do 接口是否可调通 |
| **脚本 · 数据验证** | 完整性 + 稳定性 | ✅ 已实现 | `scripts/verify_pinzhi_data.py`：拉取核心数据并做二次拉取对比 |
| **脚本 · 月度拉取** | 指定月份实收/订单 | ✅ 已实现 | `scripts/fetch_pinzhi_monthly_data.py`：按月拉取总营业实收、订单笔数、客单价 |
| **API 网关 · 注册** | 通过接口注册品智适配器 | ✅ 已实现 | `POST /api/adapters/register`，adapter_name=pinzhi + config |
| **API 网关 · POS 服务** | 门店/菜品/订单/收入等 | ✅ 已实现 | `pos_service` 使用 PinzhiAdapter（需配置 PINZHI_*） |
| **API 网关 · 健康检查** | 品智状态 | ⚠ 部分 | `pinzhi_service.health_check()` 请求 `{base_url}/api/health`，非品智 .do；与脚本用的 .do 非同一套 |
| **订单同步** | 从品智同步订单到智链OS | ✅ 已实现 | `POST /api/adapters/sync/order` 已支持 `source_system=pinzhi`（按门店+日期范围匹配 `billId/billNo`） |

**尝在一起**：品智按 **Token 区分主体**。配置尝在一起对应的 `PINZHI_BASE_URL` 与 `PINZHI_TOKEN` 后，上述适配器与脚本拉取到的即为尝在一起数据，无需在代码里再按品牌名过滤。

---

## 二、如何检测「对接是否成功、能否拉取尝在一起数据」

在**已配置尝在一起品智环境**（PINZHI_BASE_URL、PINZHI_TOKEN）的机器上依次执行下列命令，通过即视为对接成功、可拉取尝在一起数据。

### 2.1 第一步：接口连通性检测

```bash
cd zhilian-os
export PINZHI_BASE_URL="http://<品智网关>/pzcatering-gateway"
export PINZHI_TOKEN="<尝在一起对应的商户 token>"

python3 scripts/check_pinzhi_api.py --date 2026-01-31
```

- **通过**：输出中核心接口（门店信息、门店每日经营数据、订单列表V2、菜品类别、支付方式）均为「成功」。
- **未通过**：按提示检查网络、Token、base_url 与品智后台是否一致。

### 2.2 第二步：数据完整性与稳定性（可选）

```bash
python3 scripts/verify_pinzhi_data.py --date 2026-01-31
```

- 会先跑接口连通性，再拉取核心数据做结构校验，并对关键接口做两次拉取对比。
- 结论为「数据拉取完整且稳定」即可用于报表。

### 2.3 第三步：实际拉取月度数据（验证能拿到尝在一起数据）

```bash
# 拉取 2026 年 1 月
python3 scripts/fetch_pinzhi_monthly_data.py --month 2026-01

# 拉取 2025 年 12 月
python3 scripts/fetch_pinzhi_monthly_data.py --month 2025-12
```

- 若输出**总营业实收(元)**、**订单笔数**、**客单价**且无数值异常，则说明**从品智 API 拉取尝在一起数据已实现**，可将该结果与品智后台报表比对口径。

---

## 三、API 网关内使用品智（POS 服务）

若智链OS 通过 API 网关对外提供「门店/订单/收入」等能力，由 `pos_service` 调用品智适配器：

- **配置**：在 api-gateway 环境变量或配置中设置 `PINZHI_BASE_URL`、`PINZHI_TOKEN`（尝在一起 token）。
- **注意**：`pos_service` 的 import 为 `from api_adapters.pinzhi.src.adapter import PinzhiAdapter`，而仓库目录为 `packages/api-adapters/`（带连字符）。若运行时报 `PinzhiAdapter not available`，需在工程中保证能以 `api_adapters` 包名引用到 `api-adapters`（例如通过 sys.path 或包别名），否则 POS 相关接口会不可用。
- **健康检查**：`GET /api/health/pinzhi` 使用 `pinzhi_service`，请求的是 `{base_url}/api/health`，与品智 .do 接口不是同一套；要验证「.do 对接」是否正常，应以 **2.1 脚本** 为准。

---

## 四、结论速查

| 问题 | 答案 |
|------|------|
| 对接品智 API 是否实现？ | **是**。适配器在 `packages/api-adapters/pinzhi`，脚本与 POS 服务均基于该适配器。 |
| 拉取尝在一起数据是否实现？ | **是**。配置尝在一起的 PINZHI_TOKEN 后，`check_pinzhi_api.py`、`verify_pinzhi_data.py`、`fetch_pinzhi_monthly_data.py` 拉取到的即为尝在一起数据；POS 服务在配置正确且 import 成功时也可拉取。 |
| 如何自检？ | 按 **二** 执行：先 `check_pinzhi_api.py`，再（可选）`verify_pinzhi_data.py`，最后 `fetch_pinzhi_monthly_data.py --month yyyy-mm` 看实际月度数据。 |

---

*文档路径：`zhilian-os/docs/尝在一起-品智API对接检测说明.md`*
