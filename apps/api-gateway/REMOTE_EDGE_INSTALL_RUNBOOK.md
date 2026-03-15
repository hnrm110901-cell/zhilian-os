# 树莓派 5 远程安装运行手册

本文档面向现场部署，目标是用最少步骤把树莓派 5 安装为智链OS边缘节点。

## 已识别到的树莓派网络地址

根据现场截图，这台树莓派当前可用地址为：

- 有线 `eth0`: `192.168.110.96`
- 无线 `wlan0`: `192.168.110.95`
- Docker 网桥 `docker0`: `172.17.0.1`，这个地址不要用于远程安装

推荐优先使用：

1. `192.168.110.96`（有线）
2. `192.168.110.95`（无线）

## 安装前提

需要准备：

- 树莓派 SSH 已开启
- 已知树莓派登录用户，默认通常是 `pi`
- API Gateway 对树莓派可达
- 服务端已配置 `EDGE_BOOTSTRAP_TOKEN`
- 你手里有对应的 `EDGE_API_TOKEN`

## 推荐安装方式

在开发机或运维机上，进入仓库：

```bash
cd apps/api-gateway
```

然后优先尝试有线 IP：

```bash
REMOTE_HOST=192.168.110.96 \
REMOTE_USER=pi \
EDGE_API_BASE_URL=http://<API_GATEWAY_IP>:8000 \
EDGE_API_TOKEN=<EDGE_BOOTSTRAP_TOKEN_VALUE> \
EDGE_STORE_ID=STORE001 \
EDGE_DEVICE_NAME=store001-rpi5 \
EDGE_SHOKZ_CALLBACK_SECRET=<EDGE_SHOKZ_CALLBACK_SECRET_VALUE> \
bash scripts/install_raspberry_pi_edge_remote.sh
```

如果有线不通，再试无线 IP：

```bash
REMOTE_HOST=192.168.110.95 \
REMOTE_USER=pi \
EDGE_API_BASE_URL=http://<API_GATEWAY_IP>:8000 \
EDGE_API_TOKEN=<EDGE_BOOTSTRAP_TOKEN_VALUE> \
EDGE_STORE_ID=STORE001 \
EDGE_DEVICE_NAME=store001-rpi5 \
EDGE_SHOKZ_CALLBACK_SECRET=<EDGE_SHOKZ_CALLBACK_SECRET_VALUE> \
bash scripts/install_raspberry_pi_edge_remote.sh
```

## 同时启用开机自动安装 / 自动注册

如果希望这台树莓派后续重装系统后也能继续沿用首启自动安装机制，加上：

```bash
ENABLE_AUTOPROVISION=1
```

完整示例：

```bash
REMOTE_HOST=192.168.110.96 \
REMOTE_USER=pi \
ENABLE_AUTOPROVISION=1 \
EDGE_API_BASE_URL=http://<API_GATEWAY_IP>:8000 \
EDGE_API_TOKEN=<EDGE_BOOTSTRAP_TOKEN_VALUE> \
EDGE_STORE_ID=STORE001 \
EDGE_DEVICE_NAME=store001-rpi5 \
EDGE_SHOKZ_CALLBACK_SECRET=<EDGE_SHOKZ_CALLBACK_SECRET_VALUE> \
bash scripts/install_raspberry_pi_edge_remote.sh
```

## 安装后检查

远程登录树莓派后检查：

```bash
systemctl status zhilian-edge-node.service
systemctl status zhilian-edge-shokz.service
cat /var/lib/zhilian-edge/node_state.json
cat /var/lib/zhilian-edge/shokz_state.json
```

或者直接在开发机执行统一验收：

```bash
cd apps/api-gateway
REMOTE_HOST=192.168.110.96 \
REMOTE_USER=pi \
bash scripts/check_raspberry_pi_edge_delivery.sh
```

如果启用了自动安装，再检查：

```bash
systemctl status zhilian-edge-bootstrap.service
ls -la /var/lib/zhilian-edge/.bootstrap-complete
```

## 常见问题

### 1. SSH 不通

先确认树莓派 SSH 已启用，并从现场网络测试：

```bash
ssh pi@192.168.110.96
```

### 2. API Gateway 不通

在树莓派上测试：

```bash
curl http://<API_GATEWAY_IP>:8000/api/v1/health
```

### 3. 注册成功但状态不上报

检查：

```bash
journalctl -u zhilian-edge-node.service -f
sqlite3 /var/lib/zhilian-edge/status_queue.db 'select count(*) from pending_status_updates;'
```

### 4. Shokz 回调不生效

检查：

```bash
systemctl status zhilian-edge-shokz.service
curl http://127.0.0.1:9781/health
cat /var/lib/zhilian-edge/shokz_state.json
```
