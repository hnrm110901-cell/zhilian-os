# 品智餐饮 API 接口补充

> 本文档为《API接口知识库》中「二、品智收银系统」的补充内容，可与《品智餐饮系统API对接明细与问题汇总》对照使用。  
> 更新：2026-03-01

---

## 一、签名与 Token 补充

### 1.1 Token 来源

- Token 须在 **商户管理 → 商户管理** 下申请（填写回调地址），**非**门店管理下生成的门店 Token。
- 运维系统：https://oms.pinzhikeji.net/pzcatering-oms/login.do  
- 官方文档：品智收银开放 API（语雀）https://www.yuque.com/diandaobuzhi/gmgnz9

### 1.2 签名变体与配置

不同网关可能存在差异，对接时可按环境选用：

| 配置项 | 说明 | 默认 |
|--------|------|------|
| token 参与排序 | 若为 false，则**仅业务参数**按 key 升序拼接，**末尾**再追加 `&token={token}` 后做 MD5 | 推荐末尾追加 |
| MD5 大小写 | sign 取 32 位 MD5 的**大写**或小写 | 大写 |
| token 传参方式 | 仅 Query 参数 / 仅请求头 `X-Token` / 两者兼有 | Query |

**推荐算法**：请求参数（排除 sign、pageIndex、pageSize、**token**）按参数名 ASCII 升序排列，拼接为 `key1=value1&key2=value2&...`，**末尾**追加 `&token={token}`，对整串做 **MD5 后大写** 得到 sign。

---

## 二、基础数据接口补充

### 2.1 组织/机构列表

**接口地址**：`http://ip:port/pzcatering-gateway/pinzhi/organizations.do`

**请求方式**：GET

**请求参数**：
| 参数 | 类型 | 是否必须 | 说明 |
|------|------|----------|------|
| sign | string | 是 | 签名值 |

**说明**：无业务参数，返回组织/机构列表，用于与门店、品牌等基础数据关联。

---

### 2.2 门店用户信息（queryUserInfo.do）

**接口地址**：`http://ip:port/pzcatering-gateway/pinzhi/queryUserInfo.do`

**请求方式**：GET

**请求参数**：
| 参数 | 类型 | 是否必须 | 说明 |
|------|------|----------|------|
| sign | string | 是 | 签名值 |
| 门店 id | string | 是 | 需传门店 id（非 ognid），参数名以实际环境为准 |

**说明**：部分网关与 `employe.do` 并存；若报「门店id不能为空」，需向品智确认参数名及是否使用门店级 Token（如 `pinzhi.store_tokens`、`pinzhi.store_ids`）。

---

### 2.3 菜品信息（queryDishesInfo.do，POST multipart）

**接口地址**：`http://ip:port/pzcatering-gateway/pinzhi/queryDishesInfo.do`

**请求方式**：POST（multipart/form-data）

**请求参数**：
| 参数 | 类型 | 是否必须 | 说明 |
|------|------|----------|------|
| sign | string | 是 | 签名值 |
| updatetime | 见文档 | 否 | 0=全部，或按日期拉取该日期后修改的菜品 |

**说明**：与 `querydishes.do` 可能为不同路径或同一能力不同协议。POST multipart 下签名规则可能与 GET 不同，若出现 sign error 需向品智确认 multipart 下参与签名的字段与顺序。

---

### 2.4 收银桌台信息（weix 网关）

**接口地址**：`{weix_base_url}/getTableInfoById.do`  
（weix_base_url 不填时可由主 base_url 推导，或单独配置）

**请求方式**：GET

**请求参数**：
| 参数 | 类型 | 是否必须 | 说明 |
|------|------|----------|------|
| sign | string | 是 | 签名值 |
| 门店 id | string | 是 | 部分网关报「门店id为空」时需向品智确认参数名与 token 权限 |

**说明**：桌台信息可能走 weix 网关，需门店级 token 或门店 id。

---

## 三、业务数据接口补充

### 3.1 门店每日经营数据（报表核心）★

**接口地址**：`http://ip:port/pzcatering-gateway/pinzhi/queryOgnDailyBizData.do`

**请求方式**：GET

**请求参数**：
| 参数 | 类型 | 是否必须 | 说明 |
|------|------|----------|------|
| sign | string | 是 | 签名值 |
| businessDate | string | 是 | 营业日，格式 yyyy-MM-dd |
| ognid | string | 否 | 门店 omsID，不传则全部门店 |

**响应结构**：
- **sum**：汇总数据，包含 `consumeAmount_{餐段}_{类型}`、`dishList`（按菜类）等。
- **list**：明细列表。

**餐段与类型约定**（与 queryStoreSummaryList 一致）：
- 餐段：0-全天，1-早市，2-午市，3-下午茶，4-晚市，5-夜宵。
- 类型：0-全部，1-堂食，2-外卖，3-外带。

**说明**：报表与数据同步的**核心接口**。若返回「操作失败-商户token为空」，优先检查 token 来源（商户管理下）、有效性及 base_url 与 token 是否同一环境；可尝试 `token_in_header: true`。

---

### 3.2 订单列表 V1（order.do）

**接口地址**：`http://ip:port/pzcatering-gateway/pinzhi/order.do`

**请求方式**：GET

**请求参数**：
| 参数 | 类型 | 是否必须 | 说明 |
|------|------|----------|------|
| sign | string | 是 | 签名值 |
| beginDate | string | 否 | 开始日期（yyyy-MM-dd） |
| endDate | string | 否 | 结束日期（yyyy-MM-dd） |
| ognid | string | 否 | 门店 omsID |
| pageIndex | int | 否 | 页码 |
| pageSize | int | 否 | 每页数量 |

**说明**：V1 与 V2（queryOrderListV2.do）并存；若返回「服务器错误」，需向品智确认参数名（如是否为 startDate/endDate 等）。

---

## 四、支付方式接口

- **payment.do**：部分环境使用 `payment.do` 作为支付方式列表接口。
- **payType.do**：知识库已收录，与 payment.do 可能为同一能力不同路径，以实际环境为准。  
请求方式均为 GET，需 sign；响应包含支付方式 id、name、category 等。

---

## 五、配置项说明（pinzhi_api_config）

| 配置项 | 必填/可选 | 说明 |
|--------|-----------|------|
| pinzhi.base_url | 必填 | 网关基础地址，如 `http://ip:port/pzcatering-gateway/pinzhi` |
| pinzhi.token | 必填 | 商户 API 令牌（商户管理下申请） |
| pinzhi.timeout | 可选 | 请求超时秒数，默认 30 |
| pinzhi.token_in_header | 可选 | 是否通过请求头 X-Token 传 token |
| pinzhi.token_in_sort | 可选 | 签名时 token 是否参与排序 |
| pinzhi.sign_upper | 可选 | 签名 MD5 大写(true)/小写(false)，默认 true |
| pinzhi.weix_base_url | 可选 | weix 网关地址，不填则从 base_url 推导 |
| pinzhi.store_ognids | 可选 | 门店名称 → ognid，按门店拉取与报告展示 |
| pinzhi.store_tokens | 可选 | 门店名称 → 该门店 Token（queryUserInfo、weix 等按门店鉴权） |
| pinzhi.store_ids | 可选 | 门店名称 → 门店 id（部分接口要传门店 id 而非 ognid） |
| pinzhi.store_codes | 可选 | 门店名称 → 门店简码（如 0001） |
| pinzhi.brand_codes | 可选 | 门店名称 → 品牌编码 |

配置文件路径示例：`pinzhi_api_config.yaml`（参考 `pinzhi_api_config.example.yaml`），勿将含真实 token 的配置提交到公共仓库。

---

## 六、对接成功判定

- **核心接口**：storeInfo、queryOgnDailyBizData、queryOrderSummary、queryOrderListV2、reportcategory、payment（或 payType）。
- **必过项**：queryOgnDailyBizData、reportcategory、payment 全部通过；有门店时含 queryOrderSummary；storeInfo、queryOrderListV2 通过。
- **可选**：queryUserInfo、weix/getTableInfoById 等，部分网关需门店参数/权限，不通过不影响「能同步数据和报表」结论。
- **结论**：当检测脚本输出「【报表 queryOgnDailyBizData.do】成功」且返回数据条数或结构正常时，可认为**品智餐饮系统 API 对接成功，可正常拉取报表数据**。

---

## 七、与《API接口知识库》的合并方式

将上述内容合并到《API接口知识库》时建议：

1. 在 **2.2 签名机制** 下增加「2.2.3 签名变体与配置」及 Token 来源说明。
2. 在 **2.3 基础数据接口** 中增加：2.3.7 组织/机构（organizations.do）、2.3.8 门店用户信息（queryUserInfo.do）、2.3.9 菜品信息（queryDishesInfo.do）、2.3.10 收银桌台（weix/getTableInfoById.do）。
3. 在 **2.4 业务数据接口** 最前增加「2.4.1 门店每日经营数据（queryOgnDailyBizData.do）」，原 2.4.1～2.4.5 序号顺延；并增加订单 V1（order.do）。
4. 在 **2.6 支付方式接口** 中注明 payment.do 与 payType.do 的对应关系。
5. 新增 **2.7 配置文件与对接判定**，将第五节、第六节内容纳入。

---

*文档路径：`zhilian-os/docs/品智餐饮API接口补充.md`*
