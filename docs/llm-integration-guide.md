# LLM集成指南

## 概述

智链OS现已支持集成大语言模型(LLM)，可以使用OpenAI GPT-4、Anthropic Claude等先进的AI模型来增强Agent系统的智能化水平。

## 支持的LLM提供商

### 1. OpenAI
- **模型**: GPT-4, GPT-4 Turbo, GPT-3.5 Turbo
- **优势**: 强大的通用能力，广泛的应用场景
- **配置**: 需要OpenAI API密钥

### 2. Anthropic Claude
- **模型**: Claude 3 Opus, Claude 3 Sonnet, Claude 3 Haiku
- **优势**: 更长的上下文窗口，更好的指令遵循
- **配置**: 需要Anthropic API密钥

### 3. Azure OpenAI
- **模型**: 与OpenAI相同的模型
- **优势**: 企业级支持，数据隐私保护
- **配置**: 需要Azure订阅和部署端点

## 快速开始

### 1. 配置环境变量

在 `.env` 文件中添加以下配置：

```bash
# 启用LLM
LLM_ENABLED=true

# 选择提供商 (openai, anthropic, azure_openai)
LLM_PROVIDER=openai

# 模型名称
LLM_MODEL=gpt-4-turbo-preview

# API密钥
LLM_API_KEY=sk-...

# 可选：自定义端点（用于Azure OpenAI）
LLM_BASE_URL=

# 生成参数
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
```

### 2. OpenAI配置示例

```bash
LLM_ENABLED=true
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo-preview
LLM_API_KEY=sk-proj-...
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
```

### 3. Anthropic Claude配置示例

```bash
LLM_ENABLED=true
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-sonnet-20240229
LLM_API_KEY=sk-ant-...
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
```

### 4. Azure OpenAI配置示例

```bash
LLM_ENABLED=true
LLM_PROVIDER=azure_openai
LLM_MODEL=gpt-4-turbo
LLM_API_KEY=your-azure-key
LLM_BASE_URL=https://your-resource.openai.azure.com/
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
```

## 安装依赖

### OpenAI

```bash
pip install openai
```

### Anthropic

```bash
pip install anthropic
```

## API使用

### 获取LLM配置

```bash
curl -X GET "http://localhost/api/v1/llm/config" \
  -H "Authorization: Bearer <access_token>"
```

### 更新LLM配置

```bash
curl -X PUT "http://localhost/api/v1/llm/config" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "provider": "openai",
    "model": "gpt-4-turbo-preview",
    "api_key": "sk-...",
    "temperature": 0.7,
    "max_tokens": 2000
  }'
```

### 测试LLM连接

```bash
curl -X POST "http://localhost/api/v1/llm/test" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "你好，请介绍一下你自己",
    "system_prompt": "你是一个友好的AI助手"
  }'
```

## Agent集成

### 工作模式

系统支持两种工作模式：

1. **模拟模式** (`LLM_ENABLED=false`)
   - 使用预定义的模拟数据
   - 快速响应，无需API调用
   - 适合开发和测试

2. **LLM模式** (`LLM_ENABLED=true`)
   - 使用真实的LLM生成响应
   - 智能化程度更高
   - 需要API密钥和网络连接

### Agent提示词

每个Agent都有专门设计的系统提示词：

- **ScheduleAgent**: 排班管理专家
- **OrderAgent**: 订单管理助手
- **InventoryAgent**: 库存管理专家
- **ServiceAgent**: 服务质量管理专家
- **TrainingAgent**: 员工培训专家
- **DecisionAgent**: 运营决策分析专家
- **ReservationAgent**: 预订管理专家

### 自动回退机制

系统具有智能回退机制：
- LLM调用失败时自动切换到模拟模式
- 确保系统稳定性和可用性
- 错误会被记录到监控系统

## 成本优化

### 1. 选择合适的模型

| 模型 | 成本 | 性能 | 适用场景 |
|------|------|------|----------|
| GPT-4 Turbo | 高 | 最强 | 复杂决策分析 |
| GPT-3.5 Turbo | 低 | 良好 | 日常操作 |
| Claude 3 Opus | 高 | 最强 | 长文本处理 |
| Claude 3 Sonnet | 中 | 优秀 | 平衡性能和成本 |
| Claude 3 Haiku | 低 | 快速 | 简单任务 |

### 2. 调整参数

- **temperature**: 降低温度(0.3-0.5)可以获得更确定的输出
- **max_tokens**: 根据实际需求设置，避免浪费
- **缓存**: 对于重复查询，考虑实现缓存机制

### 3. 监控使用量

- 使用监控系统追踪LLM调用次数
- 设置使用量告警
- 定期审查成本报告

## 安全建议

### 1. API密钥管理

- ✅ 使用环境变量存储API密钥
- ✅ 不要将密钥提交到版本控制
- ✅ 定期轮换API密钥
- ✅ 使用密钥管理服务（如AWS Secrets Manager）

### 2. 访问控制

- ✅ LLM配置API需要 `system:config` 权限
- ✅ 限制可以修改LLM配置的用户
- ✅ 记录所有配置变更

### 3. 内容过滤

- ✅ 验证用户输入
- ✅ 过滤敏感信息
- ✅ 实现内容审核机制

## 故障排查

### 问题1: LLM调用失败

**症状**: API返回错误或超时

**解决方案**:
1. 检查API密钥是否正确
2. 验证网络连接
3. 检查API配额是否用尽
4. 查看监控系统的错误日志

### 问题2: 响应质量不佳

**症状**: LLM生成的内容不符合预期

**解决方案**:
1. 调整temperature参数
2. 优化提示词
3. 尝试不同的模型
4. 增加上下文信息

### 问题3: 响应速度慢

**症状**: API响应时间过长

**解决方案**:
1. 使用更快的模型（如GPT-3.5或Claude Haiku）
2. 减少max_tokens
3. 实现响应缓存
4. 考虑异步处理

## 最佳实践

### 1. 提示词工程

- 明确指定输出格式（JSON）
- 提供具体的示例
- 使用结构化的提示词模板
- 包含必要的上下文信息

### 2. 错误处理

- 实现重试机制
- 设置合理的超时时间
- 提供回退方案
- 记录详细的错误信息

### 3. 性能优化

- 批量处理请求
- 实现请求缓存
- 使用流式响应（适用场景）
- 监控响应时间

### 4. 测试

- 在开发环境使用模拟模式
- 在测试环境验证LLM集成
- 进行负载测试
- 监控生产环境表现

## 示例代码

### Python客户端

```python
import requests

# 配置LLM
response = requests.put(
    "http://localhost/api/v1/llm/config",
    headers={"Authorization": f"Bearer {access_token}"},
    json={
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4-turbo-preview",
        "api_key": "sk-...",
        "temperature": 0.7,
        "max_tokens": 2000
    }
)

# 测试LLM
response = requests.post(
    "http://localhost/api/v1/llm/test",
    headers={"Authorization": f"Bearer {access_token}"},
    json={
        "prompt": "分析这个月的销售数据",
        "system_prompt": "你是一个数据分析专家"
    }
)

print(response.json())
```

### JavaScript客户端

```javascript
// 配置LLM
const configResponse = await fetch('http://localhost/api/v1/llm/config', {
  method: 'PUT',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    enabled: true,
    provider: 'openai',
    model: 'gpt-4-turbo-preview',
    api_key: 'sk-...',
    temperature: 0.7,
    max_tokens: 2000,
  }),
});

// 测试LLM
const testResponse = await fetch('http://localhost/api/v1/llm/test', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    prompt: '分析这个月的销售数据',
    system_prompt: '你是一个数据分析专家',
  }),
});

const result = await testResponse.json();
console.log(result);
```

## 支持

如有问题或建议，请联系：
- **邮箱**: support@zhilian-os.com
- **文档**: http://localhost/docs
- **GitHub**: https://github.com/zhilian-os/api-gateway/issues
