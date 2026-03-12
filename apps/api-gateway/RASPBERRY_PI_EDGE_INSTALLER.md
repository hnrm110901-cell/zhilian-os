# Raspberry Pi 5 边缘安装器

## 适用范围

这是智链OS第一版树莓派 5 边缘节点安装器，目标是尽快把 PoC / 测试店的边缘节点跑起来，而不是一次性做到完整生产化。

当前安装器会完成：

- 安装最小运行依赖
- 安装边缘 agent
- 写入本地配置
- 注册 systemd 服务
- 首次向云端注册节点
- 获取并落盘 `device_secret`
- 按周期上报节点状态
- 在本地 SQLite 队列里缓存失败的状态上报，并在恢复联网后自动重放
- 安装本地 Shokz 回调守护进程，接住云端蓝牙/播报命令
- 提供 SSH 远程安装脚本
- 提供开机自动安装 / 自动注册 bootstrap 服务

当前服务端还提供恢复指引接口：

- `GET /api/v1/hardware/edge-node/{node_id}/recovery-guide`

硬件管理页里的“恢复指引”按钮，展示的就是这套服务端返回内容。

## 当前限制

- 首次注册仍依赖 `EDGE_API_TOKEN` 作为 bootstrap token
- 注册成功后会下发 `device_secret`，后续状态上报优先走设备密钥
- 还没有独立设备证书或设备 secret
- 还没有本地模型下载和离线任务队列

## 安装前准备

需要提前准备：

- Raspberry Pi 5，推荐 Raspberry Pi OS 64-bit
- 能访问智链OS API Gateway 的网络
- 服务端已配置 `EDGE_BOOTSTRAP_TOKEN`
- 一个与 `EDGE_BOOTSTRAP_TOKEN` 对应的 `EDGE_API_TOKEN`
- 对应门店的 `EDGE_STORE_ID`

## 一键安装

在仓库根目录执行：

```bash
cd apps/api-gateway
sudo EDGE_API_BASE_URL=http://your-api-host:8000 \
     EDGE_API_TOKEN=replace-with-token \
     EDGE_STORE_ID=STORE001 \
     EDGE_DEVICE_NAME=store001-rpi5 \
     EDGE_SHOKZ_CALLBACK_SECRET=replace-with-callback-secret \
     bash scripts/install_raspberry_pi_edge.sh
```

## 通过 SSH 远程安装

如果你在开发机上远程给树莓派下发安装，直接执行：

```bash
cd apps/api-gateway
REMOTE_HOST=192.168.110.96 \
REMOTE_USER=pi \
EDGE_API_BASE_URL=http://your-api-host:8000 \
EDGE_API_TOKEN=replace-with-token \
EDGE_STORE_ID=STORE001 \
EDGE_DEVICE_NAME=store001-rpi5 \
EDGE_SHOKZ_CALLBACK_SECRET=replace-with-callback-secret \
bash scripts/install_raspberry_pi_edge_remote.sh
```

如果希望同时把“下次开机自动安装 / 自动注册”也准备好，增加：

```bash
ENABLE_AUTOPROVISION=1
```

## 安装后检查

```bash
systemctl status zhilian-edge-node.service
systemctl status zhilian-edge-shokz.service
journalctl -u zhilian-edge-node.service -f
journalctl -u zhilian-edge-shokz.service -f
cat /var/lib/zhilian-edge/node_state.json
sqlite3 /var/lib/zhilian-edge/status_queue.db 'select count(*) from pending_status_updates;'
cat /var/lib/zhilian-edge/shokz_state.json
```

如果注册成功，`node_state.json` 里会出现 `node_id`。
如果出现短时断网，待发送的状态上报会进入 `status_queue.db`，恢复联网后 agent 会自动按顺序补发。

## 重注册 / 恢复

如果硬件管理页显示：

- `需重注册`
- 最近凭证操作是 `最近吊销`
- 或节点状态接口里 `device_secret_active=false`

优先按下面顺序处理。

### 1. 检查服务端前提

- API Gateway 已配置 `EDGE_BOOTSTRAP_TOKEN`
- 树莓派仍能访问 `EDGE_API_BASE_URL`
- 门店 `EDGE_STORE_ID` 没填错

### 2. 检查本地关键文件

```bash
cat /etc/zhilian-edge/edge-node.env
cat /var/lib/zhilian-edge/node_state.json
systemctl status zhilian-edge-node.service
```

重点确认：

- `EDGE_API_BASE_URL`
- `EDGE_API_TOKEN`
- `EDGE_STORE_ID`
- `EDGE_DEVICE_NAME`
- `EDGE_QUEUE_FLUSH_BATCH_SIZE`
- `EDGE_SHOKZ_CALLBACK_SECRET`

### 3. 重新写入 bootstrap 配置并重启

如果当前 `device_secret` 已失效，直接重新执行安装命令即可覆盖本地配置并触发重新注册：

```bash
cd apps/api-gateway
sudo EDGE_API_BASE_URL=http://your-api-host:8000 \
     EDGE_API_TOKEN=replace-with-bootstrap-token \
     EDGE_STORE_ID=STORE001 \
     EDGE_DEVICE_NAME=store001-rpi5 \
     EDGE_SHOKZ_CALLBACK_SECRET=replace-with-callback-secret \
     bash scripts/install_raspberry_pi_edge.sh
```

随后查看日志：

```bash
journalctl -u zhilian-edge-node.service -f
```

## 首启自动安装 / 自动注册

当前已提供一套无人值守 bootstrap 方案：

- 启用脚本：`scripts/enable_raspberry_pi_edge_autoprovision.sh`
- 首启脚本：`edge/bootstrap_edge_firstboot.sh`
- 首启服务：`edge/zhilian-edge-bootstrap.service`
- 配置模板：`edge/.env.edge.bootstrap.example`

启用后，树莓派下次开机且网络可用时，会自动执行标准安装脚本，
完成：

- 写入 `/etc/zhilian-edge/edge-node.env`
- 注册边缘节点
- 获取 `device_secret`
- 启动 `zhilian-edge-node.service`
- 启动 `zhilian-edge-shokz.service`

成功后会写入标记文件：

- `/var/lib/zhilian-edge/.bootstrap-complete`

默认成功一次后自动禁用 `zhilian-edge-bootstrap.service`，避免重复执行。

### 4. 回到管理页确认恢复

恢复成功后，应看到：

- 凭证状态从 `需重注册` 变回 `正常`
- 节点重新出现心跳
- 审计记录里新增注册或轮换记录

## 关键文件

- 安装脚本：`scripts/install_raspberry_pi_edge.sh`
- 远程安装脚本：`scripts/install_raspberry_pi_edge_remote.sh`
- 自动安装启用脚本：`scripts/enable_raspberry_pi_edge_autoprovision.sh`
- 边缘 agent：`edge/edge_node_agent.py`
- 本地 Shokz 守护进程：`edge/shokz_callback_daemon.py`
- 首启 bootstrap 脚本：`edge/bootstrap_edge_firstboot.sh`
- systemd 模板：`edge/zhilian-edge-node.service`
- Shokz systemd 模板：`edge/zhilian-edge-shokz.service`
- 首启 bootstrap systemd 模板：`edge/zhilian-edge-bootstrap.service`
- 配置模板：`edge/.env.edge.example`
- 首启模板：`edge/.env.edge.bootstrap.example`
- 本地配置文件：`/etc/zhilian-edge/edge-node.env`
- 本地状态文件：`/var/lib/zhilian-edge/node_state.json`
- 本地离线队列：`/var/lib/zhilian-edge/status_queue.db`
- 本地 Shokz 状态文件：`/var/lib/zhilian-edge/shokz_state.json`
- 差距清单：`EDGE_NODE_GAP_ANALYSIS.md`

## 建议的下一步

### P0

- 将 bootstrap token 管理从环境变量推进到后台配置
- 增加 device secret 审计、轮换记录和吊销记录

## 本地 Shokz 回调守护进程

树莓派会额外启动 `zhilian-edge-shokz.service`，监听：

- `GET /health`
- `POST /shokz/callback`

API Gateway 在配置以下环境变量后，会把 `connect_device` / `disconnect_device` /
`voice_output` 直接回推到树莓派执行：

- `EDGE_SHOKZ_CALLBACK_URL=http://<树莓派IP>:9781/shokz/callback`
- `EDGE_SHOKZ_CALLBACK_SECRET=<shared-secret>`

第一版守护进程会把本地连接状态、最近一次播报文本和历史记录持久化到
`/var/lib/zhilian-edge/shokz_state.json`，作为蓝牙层接入前的可运行桥接。

### P1

- 增加本地蓝牙适配层，把 `shokz_state.json` 操作替换成真实蓝牙命令
- 增加本地 SQLite 队列和断网重试

### P2

- 制作 Raspberry Pi OS 首启镜像
- 实现批量门店自动化安装
