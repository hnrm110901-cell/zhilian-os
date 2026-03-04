# 品智餐饮 API 接口参数汇总文档

> 汇总品智收银系统所有 API 接口及其请求/响应参数，便于对接与查阅。  
> 数据来源：`品智餐饮API接口补充.md`、`packages/api-adapters/pinzhi` 适配器代码。  
> 更新：2026-03-02

---

## 一、通用约定

### 1.1 鉴权与签名

- **Token 来源**：须在 **商户管理 → 商户管理** 下申请（填写回调地址），非门店管理下生成的门店 Token。
- **签名算法**（推荐）：请求参数（排除 `sign`、`pageIndex`、`pageSize`、`token`）按参数名 ASCII 升序排列，拼接为 `key1=value1&key2=value2&...`，**末尾**追加 `&token={token}`，对整串做 **MD5** 得到 sign（部分环境要求**大写**，部分为小写，以实际网关为准）。
- **Token 传参**：Query 参数 / 请求头 `X-Token` / 两者兼有，由配置 `token_in_header` 等决定。

### 1.2 公共请求参数（所有接口）

| 参数名 | 类型   | 是否必须 | 说明 |
|--------|--------|----------|------|
| sign   | string | 是       | 签名值（32 位 MD5，大小写以环境为准） |

除上述外，各接口另有业务参数，见下表。**签名时**：通常不参与排序的为 `sign`、`pageIndex`、`pageSize`、`token`（若配置为末尾追加则 token 不参与排序）。

### 1.3 配置项（pinzhi_api_config）

| 配置项 | 必填/可选 | 说明 |
|--------|-----------|------|
| pinzhi.base_url | 必填 | 网关基础地址，如 `http://ip:port/pzcatering-gateway/pinzhi` |
| pinzhi.token | 必填 | 商户 API 令牌（商户管理下申请） |
| pinzhi.timeout | 可选 | 请求超时秒数，默认 30 |
| pinzhi.token_in_header | 可选 | 是否通过请求头 X-Token 传 token |
| pinzhi.token_in_sort | 可选 | 签名时 token 是否参与排序 |
| pinzhi.sign_upper | 可选 | 签名 MD5 大写(true)/小写(false)，默认 true |
| pinzhi.weix_base_url | 可选 | weix 网关地址，不填则从 base_url 推导 |
| pinzhi.store_ognids | 可选 | 门店名称 → ognid |
| pinzhi.store_tokens | 可选 | 门店名称 → 该门店 Token |
| pinzhi.store_ids | 可选 | 门店名称 → 门店 id（部分接口要传门店 id 而非 ognid） |
| pinzhi.store_codes | 可选 | 门店名称 → 门店简码 |
| pinzhi.brand_codes | 可选 | 门店名称 → 品牌编码 |

---

## 二、基础数据接口

### 2.1 门店信息 storeInfo.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/storeInfo.do` |
| 请求方式 | GET |

**请求参数**

| 参数名 | 类型   | 是否必须 | 说明 |
|--------|--------|----------|------|
| sign   | string | 是       | 签名值 |
| ognid  | string | 否       | 门店 omsID，不传则返回所有门店 |

**响应**：`res` 为门店信息列表。

---

### 2.2 组织/机构列表 organizations.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/organizations.do` |
| 请求方式 | GET |

**请求参数**

| 参数名 | 类型   | 是否必须 | 说明 |
|--------|--------|----------|------|
| sign   | string | 是       | 签名值 |

**说明**：无业务参数，返回组织/机构列表，用于与门店、品牌等基础数据关联。  
**响应**：`data` 或 `res` 为列表。

---

### 2.3 菜品类别 reportcategory.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/reportcategory.do` |
| 请求方式 | GET |

**请求参数**

| 参数名 | 类型   | 是否必须 | 说明 |
|--------|--------|----------|------|
| sign   | string | 是       | 签名值 |

**响应**：`data` 为菜品类别列表。

---

### 2.4 菜品信息 querydishes.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/querydishes.do` |
| 请求方式 | POST（适配器中使用 JSON body） |

**请求参数**

| 参数名    | 类型   | 是否必须 | 说明 |
|-----------|--------|----------|------|
| sign      | string | 是       | 签名值 |
| updatetime| int    | 否       | 0=全部，或按时间戳/日期拉取该时间后修改的菜品 |

**说明**：与 `queryDishesInfo.do` 可能为不同路径或同一能力不同协议；若为 multipart/form-data，签名规则需与品智确认。  
**响应**：`data` 为菜品列表。

---

### 2.5 菜品信息 queryDishesInfo.do（POST multipart）

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/queryDishesInfo.do` |
| 请求方式 | POST（multipart/form-data） |

**请求参数**

| 参数名     | 类型   | 是否必须 | 说明 |
|------------|--------|----------|------|
| sign       | string | 是       | 签名值 |
| updatetime | 见文档 | 否       | 0=全部，或按日期拉取该日期后修改的菜品 |

**说明**：multipart 下参与签名的字段与顺序以品智文档为准，若出现 sign error 需向品智确认。

---

### 2.6 做法和配料 queryPractice.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/queryPractice.do` |
| 请求方式 | POST |

**请求参数**

| 参数名 | 类型   | 是否必须 | 说明 |
|--------|--------|----------|------|
| sign   | string | 是       | 签名值 |

**响应**：`data` 为做法和配料列表。

---

### 2.7 收银桌台 queryTable.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/queryTable.do` |
| 请求方式 | GET |

**请求参数**

| 参数名 | 类型   | 是否必须 | 说明 |
|--------|--------|----------|------|
| sign   | string | 是       | 签名值 |

**响应**：`res` 为桌台列表。

---

### 2.8 收银桌台（weix 网关）getTableInfoById.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{weix_base_url}/getTableInfoById.do` |
| 请求方式 | GET |

**请求参数**

| 参数名   | 类型   | 是否必须 | 说明 |
|----------|--------|----------|------|
| sign     | string | 是       | 签名值 |
| 门店 id  | string | 是       | 部分网关报「门店id为空」时需确认参数名与 token 权限 |

**说明**：桌台信息可能走 weix 网关，需门店级 token 或门店 id。

---

### 2.9 门店用户/员工 employe.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/employe.do` |
| 请求方式 | GET |

**请求参数**

| 参数名 | 类型   | 是否必须 | 说明 |
|--------|--------|----------|------|
| sign   | string | 是       | 签名值 |

**响应**：`data` 为员工列表。

---

### 2.10 门店用户信息 queryUserInfo.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/queryUserInfo.do` |
| 请求方式 | GET |

**请求参数**

| 参数名   | 类型   | 是否必须 | 说明 |
|----------|--------|----------|------|
| sign     | string | 是       | 签名值 |
| 门店 id  | string | 是       | 需传门店 id（非 ognid），参数名以实际环境为准 |

**说明**：部分网关与 `employe.do` 并存；若报「门店id不能为空」，需确认参数名及是否使用门店级 Token。

---

## 三、业务数据接口

### 3.1 门店每日经营数据（报表核心）queryOgnDailyBizData.do ★

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/queryOgnDailyBizData.do` |
| 请求方式 | GET |

**请求参数**

| 参数名       | 类型   | 是否必须 | 说明 |
|--------------|--------|----------|------|
| sign         | string | 是       | 签名值 |
| businessDate | string | 是       | 营业日，格式 yyyy-MM-dd |
| ognid        | string | 否       | 门店 omsID，不传则全部门店 |

**响应结构**：`res` 或 `data`，含 **sum**（汇总，如 `consumeAmount_{餐段}_{类型}`、`dishList` 等）、**list**（明细）。  
**餐段**：0-全天，1-早市，2-午市，3-下午茶，4-晚市，5-夜宵。  
**类型**：0-全部，1-堂食，2-外卖，3-外带。  
**说明**：报表与数据同步的核心接口；若返回「操作失败-商户token为空」，请检查 token 来源与 base_url 是否同一环境。

---

### 3.2 按门店收入数据 queryOrderSummary.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/queryOrderSummary.do` |
| 请求方式 | GET |

**请求参数**

| 参数名       | 类型   | 是否必须 | 说明 |
|--------------|--------|----------|------|
| sign         | string | 是       | 签名值 |
| ognid        | string | 是       | 门店 omsID |
| businessDate | string | 是       | 营业日，格式 yyyy-MM-dd |

**响应**：`res` 为收入汇总数据。

---

### 3.3 所有门店营业额及菜类销售 queryStoreSummaryList.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/queryStoreSummaryList.do` |
| 请求方式 | GET |

**请求参数**

| 参数名       | 类型   | 是否必须 | 说明 |
|--------------|--------|----------|------|
| sign         | string | 是       | 签名值 |
| businessDate | string | 是       | 营业日，格式 yyyy-MM-dd |

**响应**：`data` 为门店营业数据列表。

---

### 3.4 订单列表 V2 queryOrderListV2.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/queryOrderListV2.do` |
| 请求方式 | GET |

**请求参数**

| 参数名     | 类型   | 是否必须 | 说明 |
|------------|--------|----------|------|
| sign       | string | 是       | 签名值 |
| beginDate  | string | 否       | 开始日期 yyyy-MM-dd |
| endDate    | string | 否       | 结束日期 yyyy-MM-dd |
| ognid      | string | 否       | 门店 omsID |
| pageIndex  | int    | 否       | 页码，默认 1 |
| pageSize   | int    | 否       | 每页数量，默认 20 |

**说明**：签名时通常排除 `pageIndex`、`pageSize`。  
**响应**：`res` 为订单列表；订单字段可含 billId、billNo、orderSource、tableNo、openTime、payTime、dishPriceTotal、specialOfferPrice、realPrice、billStatus、dishList 等。

---

### 3.5 订单列表 V1 order.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/order.do` |
| 请求方式 | GET |

**请求参数**

| 参数名     | 类型   | 是否必须 | 说明 |
|------------|--------|----------|------|
| sign       | string | 是       | 签名值 |
| beginDate  | string | 否       | 开始日期 yyyy-MM-dd |
| endDate    | string | 否       | 结束日期 yyyy-MM-dd |
| ognid      | string | 否       | 门店 omsID |
| pageIndex  | int    | 否       | 页码 |
| pageSize   | int    | 否       | 每页数量 |

**说明**：V1 与 V2 并存；若返回「服务器错误」，需向品智确认参数名（如 startDate/endDate 等）。

---

### 3.6 出品过程明细 queryCookingDetail.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/queryCookingDetail.do` |
| 请求方式 | GET |

**请求参数**

| 参数名       | 类型   | 是否必须 | 说明 |
|--------------|--------|----------|------|
| sign         | string | 是       | 签名值 |
| businessDate | string | 是       | 营业日，格式 yyyy-MM-dd |

**响应**：`data` 为出品过程明细列表。

---

### 3.7 挂账客户 paymentCustomer.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/paymentCustomer.do` |
| 请求方式 | GET |

**请求参数**

| 参数名     | 类型   | 是否必须 | 说明 |
|------------|--------|----------|------|
| sign       | string | 是       | 签名值 |
| beginDate  | string | 否       | 查询开始时间 |
| endDate    | string | 否       | 查询结束时间 |

**响应**：`data` 为挂账客户列表。

---

### 3.8 下载微信/支付宝对账单 downloadBillData.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/downloadBillData.do` |
| 请求方式 | GET |

**请求参数**

| 参数名   | 类型   | 是否必须 | 说明 |
|----------|--------|----------|------|
| sign     | string | 是       | 签名值 |
| ognid    | string | 是       | 门店 omsID |
| payDate  | string | 是       | 日期 yyyy-MM-dd |
| payType  | int    | 是       | 支付类型：1-微信，2-支付宝 |

**响应**：`data` 为对账单数据。

---

## 四、支付方式接口

### 4.1 支付方式 payType.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/payType.do` |
| 请求方式 | GET |

**请求参数**

| 参数名 | 类型   | 是否必须 | 说明 |
|--------|--------|----------|------|
| sign   | string | 是       | 签名值 |

**响应**：`data` 或 `res` 为支付方式列表（id、name、category 等）。

---

### 4.2 支付方式 payment.do

| 项目 | 说明 |
|------|------|
| 接口地址 | `{base_url}/pinzhi/payment.do` |
| 请求方式 | GET |

**请求参数**

| 参数名 | 类型   | 是否必须 | 说明 |
|--------|--------|----------|------|
| sign   | string | 是       | 签名值 |

**说明**：部分环境使用 `payment.do` 作为支付方式列表，与 `payType.do` 可能为同一能力不同路径。

---

## 五、接口与参数速查表

| 接口名称           | 路径 | 方法 | 业务参数 |
|--------------------|------|------|----------|
| 门店信息           | /pinzhi/storeInfo.do | GET | ognid(选) |
| 组织/机构          | /pinzhi/organizations.do | GET | — |
| 菜品类别           | /pinzhi/reportcategory.do | GET | — |
| 菜品信息           | /pinzhi/querydishes.do | POST | updatetime(选) |
| 菜品信息(multipart)| /pinzhi/queryDishesInfo.do | POST | updatetime(选) |
| 做法配料           | /pinzhi/queryPractice.do | POST | — |
| 桌台信息           | /pinzhi/queryTable.do | GET | — |
| 桌台(weix)         | getTableInfoById.do | GET | 门店id(必) |
| 员工               | /pinzhi/employe.do | GET | — |
| 门店用户           | /pinzhi/queryUserInfo.do | GET | 门店id(必) |
| 门店每日经营数据   | /pinzhi/queryOgnDailyBizData.do | GET | businessDate(必), ognid(选) |
| 按门店收入         | /pinzhi/queryOrderSummary.do | GET | ognid(必), businessDate(必) |
| 门店营业额汇总     | /pinzhi/queryStoreSummaryList.do | GET | businessDate(必) |
| 订单列表V2         | /pinzhi/queryOrderListV2.do | GET | beginDate(选), endDate(选), ognid(选), pageIndex(选), pageSize(选) |
| 订单列表V1         | /pinzhi/order.do | GET | beginDate(选), endDate(选), ognid(选), pageIndex(选), pageSize(选) |
| 出品明细           | /pinzhi/queryCookingDetail.do | GET | businessDate(必) |
| 挂账客户           | /pinzhi/paymentCustomer.do | GET | beginDate(选), endDate(选) |
| 下载对账单         | /pinzhi/downloadBillData.do | GET | ognid(必), payDate(必), payType(必) |
| 支付方式           | /pinzhi/payType.do | GET | — |
| 支付方式(备用)     | /pinzhi/payment.do | GET | — |

---

## 六、对接成功判定（参考）

- **核心接口**：storeInfo、queryOgnDailyBizData、queryOrderSummary、queryOrderListV2、reportcategory、payType（或 payment）。
- **必过项**：queryOgnDailyBizData、reportcategory、payment 全部通过；有门店时含 queryOrderSummary；storeInfo、queryOrderListV2 通过。
- **可选**：queryUserInfo、weix/getTableInfoById 等，不通过不影响「能同步数据和报表」结论。
- 当检测脚本输出「【报表 queryOgnDailyBizData.do】成功」且返回数据正常时，可认为**品智餐饮系统 API 对接成功**。

---

## 七、数据拉取完整性与稳定性验证

完成全部对接后（如在本机 openclaw 或任意环境），可定期验证**拉取数据是否完整、稳定**。

### 7.1 接口连通性检测

```bash
export PINZHI_BASE_URL="http://ip:port/pzcatering-gateway"
export PINZHI_TOKEN="your_merchant_token"
cd zhilian-os && python3 scripts/check_pinzhi_api.py --date 2026-02-28 --ognid <门店ognid>
```

通过即表示各接口可调通、返回格式正常。

### 7.2 数据完整性 + 稳定性验证

在连通性通过后，运行数据验证脚本，会依次执行：

1. **接口连通性**：复用 `run_all_checks`，确保核心接口可用。
2. **数据完整性**：对门店信息、每日经营数据、订单列表 V2、菜品类别、支付方式等拉取一次，校验返回结构（如 sum/list、条数、必选字段）。
3. **稳定性**：对每日经营数据、订单列表、门店信息进行两次拉取（间隔可配），对比是否均成功且数据量一致或差异在可接受范围。

```bash
# 完整验证（含稳定性二次拉取）
python3 scripts/verify_pinzhi_data.py --date 2026-02-28 --ognid <门店ognid>

# 仅完整性，不做稳定性
python3 scripts/verify_pinzhi_data.py --no-stability

# 稳定性两次拉取间隔 3 秒
python3 scripts/verify_pinzhi_data.py --stability-interval 3
```

脚本路径：`zhilian-os/scripts/verify_pinzhi_data.py`。结论为「数据拉取完整且稳定」时，可放心用于报表与经营分析。

---

*文档路径：`zhilian-os/docs/品智餐饮API接口参数汇总.md`*
