# SSL 证书目录

Nginx 从此目录读取 TLS 证书。生产部署前必须将证书文件放置于此目录。

## 期望的文件

| 文件名 | 说明 |
|--------|------|
| `fullchain.pem` | 完整证书链（含中间证书） |
| `privkey.pem` | 私钥（权限应为 600，仅 root 可读） |

## 获取证书

### 方式 1：Let's Encrypt（推荐）

```bash
# 安装 certbot
apt-get install certbot

# 申请证书（将 your-domain.com 替换为实际域名）
certbot certonly --standalone -d your-domain.com

# 将证书复制到此目录
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ./ssl/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem  ./ssl/

# 设置权限
chmod 644 ./ssl/fullchain.pem
chmod 600 ./ssl/privkey.pem
```

### 方式 2：自签名证书（仅用于内网/测试）

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ./ssl/privkey.pem \
  -out    ./ssl/fullchain.pem \
  -subj   "/C=CN/ST=Beijing/L=Beijing/O=ZhilianOS/CN=localhost"
chmod 600 ./ssl/privkey.pem
```

## 证书自动续签（Let's Encrypt）

在宿主机 crontab 中添加：

```cron
0 3 * * * certbot renew --quiet && \
  cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /path/to/ssl/ && \
  cp /etc/letsencrypt/live/your-domain.com/privkey.pem  /path/to/ssl/ && \
  docker exec zhilian-nginx nginx -s reload
```

## 注意事项

- `.gitignore` 已排除 `ssl/*.pem`，**证书文件不会被提交到版本库**
- 生产环境私钥权限应为 `600`，确保仅 root 可读
