# DeepSeek API 集成指南

## 概述

智链OS现已支持DeepSeek API作为LLM提供商。DeepSeek提供高性价比的大语言模型服务，特别适合中文场景和代码生成任务。

## 配置步骤

### 1. 获取DeepSeek API密钥

1. 访问 [DeepSeek官网](https://platform.deepseek.com/)
2. 注册账号并登录
3. 在控制台创建API密钥
4. 复制API密钥备用

### 2. 配置环境变量

编辑 `apps/api-gateway/.env` 文件，添加以下配置：

```bash
# 启用LLM功能
LLM_ENABLED=true

# 选择DeepSeek作为提供商
LLM_PROVIDER=deepseek

# 配置DeepSeek模型
LLM_MODEL=deepseek-chat  # 或 deepseek-coder（代码专用）

# 设置API密钥
LLM_API_KEY=your_deepseek_api_key_here

# DeepSeek API端点
LLM_BASE_URL=https://api.deepseek.com

# 可选参数
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
```

### 3. 安装依赖

DeepSeek使用OpenAI兼容API，需要安装openai包：

```bash
cd apps/api-gateway
pip install openai
```

### 4. 重启服务

```bash
# 重启API网关服务
python src/main.py
```

## 支持的模型

### deepseek-chat
- 通用对话模型
- 适合客服、决策支持、文本生成等场景
- 支持中英文
- 上下文长度: 32K tokens

### deepseek-coder
- 代码专用模型
- 适合代码生成、代码审查、技术文档等场景
- 支持多种编程语言
- 上下文长度: 16K tokens

## 使用示例

### 通过API测试连接

```bash
curl -X POST http://localhost:8000/api/v1/llm/test \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "你好，请介绍一下智链OS系统"
  }'
```

### 在代码中使用

```python
from src.core.llm import get_llm_client

# 获取LLM客户端
llm_client = get_llm_client()

# 生成文本
response = await llm_client.generate(
    prompt="分析这个订单的异常情况",
    system_prompt="你是智链OS的智能分析助手",
    temperature=0.7,
    max_tokens=1000
)

print(response)
```

### 在Agent中使用

```python
from src.agents.llm_agent import LLMAgent

class MyAgent(LLMAgent):
    async def process(self, input_data):
        # 使用LLM增强的处理
        result = await self.execute_with_llm(
            prompt=f"处理以下数据: {input_data}",
            fallback_data={"status": "mock"}
        )
        return result
```

## 成本优化建议

1. **合理设置max_tokens**: 根据实际需求设置，避免浪费
2. **使用缓存**: 对相同的prompt使用缓存机制
3. **批量处理**: 将多个小请求合并为一个大请求
4. **选择合适的模型**:
   - 简单任务使用deepseek-chat
   - 代码相关任务使用deepseek-coder
5. **设置合理的temperature**:
   - 确定性任务使用0.1-0.3
   - 创造性任务使用0.7-0.9

## 切换到其他LLM提供商

如需切换到OpenAI或Anthropic，只需修改环境变量：

### 切换到OpenAI
```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo-preview
LLM_API_KEY=your_openai_api_key
LLM_BASE_URL=  # 留空使用默认
```

### 切换到Anthropic Claude
```bash
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-sonnet-20240229
LLM_API_KEY=your_anthropic_api_key
```

## 故障排查

### 问题1: ImportError: No module named 'openai'
**解决方案**: 安装openai包
```bash
pip install openai
```

### 问题2: API密钥无效
**解决方案**:
1. 检查API密钥是否正确复制
2. 确认API密钥在DeepSeek控制台中是否激活
3. 检查账户余额是否充足

### 问题3: 连接超时
**解决方案**:
1. 检查网络连接
2. 确认DeepSeek API服务状态
3. 尝试增加超时时间

### 问题4: LLM_ENABLED=false
**解决方案**:
1. 确认.env文件中LLM_ENABLED=true
2. 重启服务使配置生效

## 监控和日志

系统会自动记录LLM调用日志：

```json
{
  "event": "OpenAI generation completed",
  "provider": "deepseek",
  "model": "deepseek-chat",
  "tokens_used": 150,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

可以通过日志监控：
- API调用次数
- Token使用量
- 响应时间
- 错误率

## 相关文档

- [LLM集成指南](./llm-integration-guide.md)
- [Agent开发指南](./agent-development.md)
- [API文档](./api-documentation.md)
