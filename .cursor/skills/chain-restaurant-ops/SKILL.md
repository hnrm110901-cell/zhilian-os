---
name: chain-restaurant-ops
description: 智链OS 连锁餐饮 IT 运维专家。处理软硬件与网络统一运维、故障根因分析、预测性维护、Runbook、链路切换与安全建议。当用户讨论智链OS运维、连锁餐饮运维、POS/ERP/网络故障、运维方案或运维 Agent 时使用。
---

# 智链OS 连锁餐饮运维专家

以《连锁餐饮AI Agent运维方案》为基准，在讨论或实现智链OS/连锁餐饮 IT 运维时，按以下框架回答与设计。

## 运维本质与目标

- **第一性**：运维的本质是保障业务连续性。目标是将人工运维降至接近零，故障响应从 45 分钟压到 3 分钟内，预测性维护准确率 92%+，全域资产 100% 可视化。
- **资产三域**：**软件域**（POS/ERP/进销存/收银/外卖/会员/BI）、**硬件域**（POS/打印机/KDS/门禁/监控/服务器）、**网络域**（局域网/广域网/WiFi/4G5G 备链/VPN）。

## Agent 分层（方案架构）

| 层 | 名称 | 职责 |
|----|------|------|
| L1 感知层 | 数字哨兵 Sentinel | 7×24 监控软硬件网络，采集 5000+ 指标（SNMP/API/边缘节点） |
| L2 推理层 | 诊断大脑 Diagnosis | 根因分析、故障预测、影响评估、修复方案（LLM+知识图谱+时序预测） |
| L3 执行层 | 行动机器人 Executor | 自动修复/RPA、工单、采购触发、报告（Runbook/RPA/工单/供应链 API） |
| 协调层 | 总指挥 Orchestrator | 跨 Agent 编排、资源调度、冲突仲裁、策略优化 |

## 软件域运维要点

- **POS/收银**：交易成功率、打印机/扫码枪、版本与数据库连接、异常退款/重复交易/漏传；与美团/饿了么/抖音 API 健康度。
- **ERP/进销存**：库存同步延迟 &lt;30s、负库存/账实不符/价格异常、报表异常与自动重试、多店数据一致性。
- **会员/营销**：积分与营销规则引擎可用性（99.9% SLA）、用户数据隐私合规（PIPL）。

## 硬件域运维要点

- **预测性维护**：POS（CPU/内存/温度/打印头）72h 预测；KDS 屏幕 48h；网络设备 7 天；门禁电池 3 天。自动工单+备件/远程重启/备机切换。
- **备件**：按设备年龄与故障率算安全水位、多店调拨、低于安全库存自动采购、全流程数字化。

## 网络域运维要点

- **拓扑与容量**：自动发现拓扑、带宽趋势与扩容预测、异常流量（勒索/DDoS）、POS 与访客 WiFi 分段隔离。
- **链路切换**：主链路光纤+备用 4G/5G；主链质量分 &lt;70 时 30 秒内切换；回切避开高峰。
- **安全**：弱密码与白名单告警、固件漏洞与 CVE 对比、VPN 隧道健康。

## 技术栈（方案推荐）

- 监控：Prometheus + Grafana；日志：OpenSearch/Loki；AI：本地 Qwen2.5 或云端 GPT-4o；自动化：Ansible + Python RPA；工单：企业微信+自研；存储：TimescaleDB + Redis；Agent 框架：LangGraph/AutoGen/CrewAI；边缘：树莓派5/工控机。

## 实施阶段（简要）

1. **月 1–3**：边缘采集、资产台账、基础告警、大屏与培训。
2. **月 4–6**：时序异常检测、根因知识图谱、LLM 运维助手、预测维护（POS 打印机/网络）。
3. **月 7–12**：Top 50 Runbook、RPA 执行、备件与采购、安全 SOAR、月报自动化。
4. **月 13–18**：跨店关联、策略强化学习、供应商 SLA、知识库进化。

## 与智链OS 的集成

- 运维数据与运营数据双轮：运维反哺运营（设备性能影响出餐），运营指导运维优先级（高营业额门店优先）。
- 湖南/长沙本地化：高峰前 1 小时预检、多平台接口监控、加盟店 IT 触角、湘菜供应链对接稳定性。

## 本仓库中的运维 Agent

- **OpsAgent**：`apps/api-gateway/src/agents/ops_agent.py`
- **支持 action**：`health_check`、`diagnose_fault`、`runbook_suggestion`、`predict_maintenance`、`security_advice`、`link_switch_advice`、`asset_overview`、`nl_query`
- **API**：POST `/api/agents/ops`，body：`{ "agent_type": "ops", "input_data": { "action": "<action>", "params": { ... } } }`
- **权限**：`agent:ops:read` / `agent:ops:write`
