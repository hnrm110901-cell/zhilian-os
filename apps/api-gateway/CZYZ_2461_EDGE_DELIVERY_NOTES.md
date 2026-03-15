# CZYZ-2461 树莓派 5 交付参数

适用设备：

- 主机名：`tunxiangOS`
- SSH 地址：`tunxiangos@192.168.110.96`
- 门店：`CZYZ-2461`
- 设备名：`czyz-wenhuacheng-rpi5`

服务端参数：

- `EDGE_API_BASE_URL=https://admin.zlsjos.cn`
- `EDGE_STORE_ID=CZYZ-2461`
- `EDGE_DEVICE_NAME=czyz-wenhuacheng-rpi5`
- `EDGE_SHOKZ_CALLBACK_SECRET` 与 `SHOKZ_CALLBACK_SECRET`：已在树莓派 `/etc/zhilian-edge/*.env` 中配置

敏感参数来源：

- bootstrap token：`/etc/zhilian-edge/edge-bootstrap.env`
- 运行时 token：`/etc/zhilian-edge/edge-node.env`
- 当前 `device_secret`：`/var/lib/zhilian-edge/node_state.json`

远程安装命令模板：

```bash
cd apps/api-gateway

REMOTE_HOST=192.168.110.96 \
REMOTE_USER=tunxiangos \
EDGE_API_BASE_URL=https://admin.zlsjos.cn \
EDGE_API_TOKEN='<从 /etc/zhilian-edge/edge-bootstrap.env 读取>' \
EDGE_STORE_ID=CZYZ-2461 \
EDGE_DEVICE_NAME=czyz-wenhuacheng-rpi5 \
EDGE_SHOKZ_CALLBACK_SECRET='<从 /etc/zhilian-edge/edge-bootstrap.env 读取>' \
bash scripts/install_raspberry_pi_edge_remote.sh
```

远程验收命令：

```bash
cd apps/api-gateway

REMOTE_HOST=192.168.110.96 \
REMOTE_USER=tunxiangos \
bash scripts/check_raspberry_pi_edge_delivery.sh
```

当前已确认状态：

- `zhilian-edge-node.service` 运行中
- `zhilian-edge-shokz.service` 运行中
- 节点持续成功上报心跳
- 树莓派对 `https://admin.zlsjos.cn/api/v1/health` 连通正常

注意：

- 后台管理用 access token 当前已失效，直接调用硬件管理查询接口会返回 `无效的认证凭证`
- 这不影响边缘节点继续用本地 `device_secret` 上报状态
