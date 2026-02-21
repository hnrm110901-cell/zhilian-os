# 安全指南

## 安全扫描

### Bandit扫描
```bash
bandit -r src/ -f json -o bandit-report.json
```

### 依赖检查
```bash
safety check --json
```

## 安全最佳实践

1. **密钥管理**
   - 使用环境变量
   - 定期轮换密钥
   - 不提交到版本控制

2. **输入验证**
   - 使用Pydantic验证
   - SQL注入防护
   - XSS防护

3. **认证授权**
   - JWT token
   - RBAC权限控制
   - 会话管理

4. **数据加密**
   - HTTPS传输
   - 密码哈希
   - 敏感数据加密

5. **日志审计**
   - 记录关键操作
   - 不记录敏感信息
   - 定期审查日志

## 漏洞报告

发现安全漏洞请发送邮件至: security@example.com
