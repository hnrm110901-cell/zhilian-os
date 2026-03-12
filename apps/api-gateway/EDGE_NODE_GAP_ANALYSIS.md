# 树莓派 5 边缘节点差距清单

## 当前已具备

- 云端已规划树莓派 5 作为门店边缘节点，负责本地推理、离线模式和云边同步。
- API Gateway 已提供硬件管理接口：
  - `POST /api/v1/hardware/edge-node/register`
  - `POST /api/v1/hardware/edge-node/{node_id}/status`
  - `POST /api/v1/hardware/edge-node/{node_id}/network-mode`
  - `POST /api/v1/hardware/edge-node/{node_id}/sync`
- Web 管理后台已有硬件页，可查看边缘节点和 Shokz 设备。
- Shokz 边缘回调已具备云边闭环：
  - API Gateway 配置 `EDGE_SHOKZ_CALLBACK_URL` / `EDGE_SHOKZ_CALLBACK_SECRET` 后可把蓝牙/音频动作回推到边缘节点
  - 树莓派已新增本地守护进程 `edge/shokz_callback_daemon.py`
  - 本地执行状态会持久化到 `shokz_state.json`

## 当前缺口

### 1. 安装与首启

- 已有一键安装脚本
- 已有 SSH 远程安装脚本
- 已有首启自动安装 / 自动注册脚本和 systemd 服务
- 还没有 Raspberry Pi OS 镜像定制脚本
- 还没有 cloud-init / firstboot 镜像级预装方案

### 2. 设备认证

- 已增加 `EDGE_BOOTSTRAP_TOKEN`，用于首次注册
- 已增加 `device_secret`，注册成功后由节点侧持久化使用
- `device_secret` 已持久化到 `edge_hubs.device_secret_hash`
- 已有 `device_secret` 轮换与吊销接口
- 仍没有证书级轮换机制

说明：
当前方案已经从“长期复用人工 JWT”升级为“bootstrap token + device secret”两段式认证，已经适合 PoC、测试店和小规模试点；但还不算完整生产级设备身份体系。

### 3. 边缘节点本地能力

- 当前 `raspberry_pi_edge_service.py` 是云端内存态服务，不是运行在树莓派上的本地 agent
- 已有第一版树莓派端 Shokz 回调守护进程，但还不是直接操控蓝牙的生产版守护进程
- 还没有真实蓝牙适配层和本地音频采集 / 播放守护进程
- 没有边缘端模型下载、缓存和升级逻辑
- 没有断网重试、离线消息队列和本地持久化数据库

### 4. 运维与交付

- 没有边缘节点日志采集方案
- 没有节点升级脚本
- 没有节点健康检查 CLI
- 没有批量门店部署流程
- 没有针对 ARM64 的交付包说明

## 本轮新增

本轮已新增第一版最小可运行交付物：

- `edge/edge_node_agent.py`
- `edge/zhilian-edge-node.service`
- `edge/shokz_callback_daemon.py`
- `edge/zhilian-edge-shokz.service`
- `edge/.env.edge.example`
- `scripts/install_raspberry_pi_edge.sh`
- `scripts/install_raspberry_pi_edge_remote.sh`
- `scripts/enable_raspberry_pi_edge_autoprovision.sh`
- `RASPBERRY_PI_EDGE_INSTALLER.md`

这套交付物解决的是：

- 首次安装
- SSH 远程安装
- 开机自动安装 / 自动注册
- 本机配置落盘
- systemd 常驻
- 首次注册到云端
- 周期性状态上报
- Shokz 本地回调接收
- 本地 Shokz 连接 / 断开 / 语音播报状态持久化

还没有解决的是：

- 证书级轮换 / 吊销
- 真实蓝牙配对守护
- 本地模型与离线任务执行
- 远程升级与批量运维

## 建议下一阶段

### P0

- 将 bootstrap token 管理从环境变量推进到正式配置中心或后台
- 增加 device secret 审计日志
- 为边缘节点增加独立的凭证管理后台

### P1

- 将当前回调守护进程从状态桥接升级为真实蓝牙连接、断开、音频播放执行层
- 增加本地 SQLite 队列，支持断网重试
- 增加本地设备健康检查与日志采集

### P2

- 制作 Raspberry Pi OS 首启镜像
- 增加 `cloud-init` / `firstboot` 自动注册
- 增加远程升级和批量门店部署工具
