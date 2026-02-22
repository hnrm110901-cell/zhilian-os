# 联邦学习服务文档

## 概述

联邦学习（Federated Learning）是一种分布式机器学习技术，允许多个门店协同训练模型，同时保护各自的数据隐私。

## 核心概念

### 工作原理

```
1. 服务器创建训练轮次
   ↓
2. 各门店下载初始模型
   ↓
3. 各门店使用本地数据训练模型
   ↓
4. 各门店上传模型参数（不上传原始数据）
   ↓
5. 服务器聚合所有门店的模型参数
   ↓
6. 生成全局模型
   ↓
7. 各门店下载全局模型
   ↓
8. 重复步骤3-7，直到收敛
```

### 隐私保护

- **数据不出门店**：原始数据永远不离开门店
- **差分隐私**：向模型参数添加噪声，防止反向推断
- **安全聚合**：服务器只能看到聚合后的参数，无法识别单个门店

## 支持的模型类型

1. **销售预测** (`sales_forecast`)
   - 预测未来销售额
   - 基于历史销售数据

2. **需求预测** (`demand_prediction`)
   - 预测菜品需求量
   - 优化库存管理

3. **客户细分** (`customer_segmentation`)
   - 识别客户群体
   - 个性化营销

4. **流失预测** (`churn_prediction`)
   - 预测客户流失风险
   - 提前干预

## 聚合算法

### FedAvg（联邦平均）

最常用的聚合算法，计算所有门店模型参数的简单平均值。

**优点**：
- 简单高效
- 收敛速度快
- 适用于数据分布相似的场景

**公式**：
```
w_global = (1/n) * Σ w_i
```

### 加权平均

根据门店的数据量或模型性能加权。

**优点**：
- 考虑门店差异
- 数据量大的门店权重更高
- 提升整体模型质量

**公式**：
```
w_global = Σ (weight_i * w_i) / Σ weight_i
```

## 差分隐私

### 原理

向模型参数添加拉普拉斯噪声，使得攻击者无法从模型参数反推原始数据。

### 隐私预算（Epsilon）

- **ε = 0.1**：极高隐私保护，但准确性较低
- **ε = 1.0**：平衡隐私和准确性（推荐）
- **ε = 10.0**：较低隐私保护，但准确性高

### 噪声添加

```python
noise_scale = sensitivity / epsilon
noise = np.random.laplace(0, noise_scale, shape)
noisy_parameter = parameter + noise
```

## API使用指南

### 1. 创建训练轮次（管理员）

```bash
POST /api/v1/federated-learning/rounds
```

**请求体**：
```json
{
  "model_type": "sales_forecast",
  "target_stores": ["STORE001", "STORE002", "STORE003"],
  "config": {
    "epochs": 10,
    "batch_size": 32,
    "learning_rate": 0.001
  }
}
```

**响应**：
```json
{
  "round_id": "round_abc123",
  "status": "created",
  "message": "Training round created successfully"
}
```

### 2. 门店加入训练

```bash
POST /api/v1/federated-learning/rounds/{round_id}/join
```

**响应**：
```json
{
  "round_id": "round_abc123",
  "store_id": "STORE001",
  "status": "joined",
  "training_config": {
    "epochs": 10,
    "batch_size": 32,
    "learning_rate": 0.001
  }
}
```

### 3. 本地训练并上传模型

```bash
POST /api/v1/federated-learning/rounds/{round_id}/upload
```

**请求体**：
```json
{
  "round_id": "round_abc123",
  "model_parameters": {
    "layer1": [[0.1, 0.2], [0.3, 0.4]],
    "layer2": [[0.5], [0.6]]
  },
  "training_metrics": {
    "loss": 0.25,
    "accuracy": 0.85,
    "training_samples": 1000
  }
}
```

### 4. 聚合模型（管理员）

```bash
POST /api/v1/federated-learning/rounds/{round_id}/aggregate
```

**请求体**：
```json
{
  "round_id": "round_abc123",
  "method": "fedavg"
}
```

**响应**：
```json
{
  "round_id": "round_abc123",
  "global_model": {
    "parameters": {...},
    "aggregation_method": "fedavg"
  },
  "num_participating_stores": 3,
  "aggregated_at": "2026-02-22T15:30:00"
}
```

### 5. 下载全局模型

```bash
GET /api/v1/federated-learning/rounds/{round_id}/download
```

**响应**：
```json
{
  "round_id": "round_abc123",
  "model_version": "v1.0",
  "parameters": {...},
  "download_time": "2026-02-22T15:35:00"
}
```

### 6. 查询训练状态

```bash
GET /api/v1/federated-learning/rounds/{round_id}/status
```

**响应**：
```json
{
  "round_id": "round_abc123",
  "status": "in_progress",
  "participating_stores": 5,
  "completed_stores": 3,
  "progress": 0.6,
  "estimated_completion": "2026-02-23T10:00:00"
}
```

## 完整训练流程示例

### Python客户端代码

```python
import requests
import numpy as np

# 配置
API_BASE = "http://localhost/api/v1/federated-learning"
STORE_ID = "STORE001"
TOKEN = "your_auth_token"

headers = {"Authorization": f"Bearer {TOKEN}"}

# 1. 加入训练轮次
round_id = "round_abc123"
response = requests.post(
    f"{API_BASE}/rounds/{round_id}/join",
    headers=headers
)
config = response.json()["training_config"]

# 2. 本地训练模型
def train_local_model(config):
    # 加载本地数据
    X_train, y_train = load_local_data(STORE_ID)

    # 训练模型
    model = create_model()
    model.fit(
        X_train, y_train,
        epochs=config["epochs"],
        batch_size=config["batch_size"]
    )

    # 提取模型参数
    parameters = {
        f"layer{i}": layer.get_weights()
        for i, layer in enumerate(model.layers)
    }

    # 计算训练指标
    loss, accuracy = model.evaluate(X_train, y_train)
    metrics = {
        "loss": float(loss),
        "accuracy": float(accuracy),
        "training_samples": len(X_train)
    }

    return parameters, metrics

# 3. 上传模型参数
parameters, metrics = train_local_model(config)
response = requests.post(
    f"{API_BASE}/rounds/{round_id}/upload",
    headers=headers,
    json={
        "round_id": round_id,
        "model_parameters": parameters,
        "training_metrics": metrics
    }
)

# 4. 等待聚合完成
import time
while True:
    response = requests.get(
        f"{API_BASE}/rounds/{round_id}/status",
        headers=headers
    )
    status = response.json()["status"]

    if status == "completed":
        break

    time.sleep(10)

# 5. 下载全局模型
response = requests.get(
    f"{API_BASE}/rounds/{round_id}/download",
    headers=headers
)
global_model = response.json()

# 6. 更新本地模型
update_local_model(global_model["parameters"])
```

## 配置参数

### 环境变量

```bash
# 最少参与门店数
FL_MIN_STORES=3

# 聚合阈值
FL_AGGREGATION_THRESHOLD=0.8

# 隐私预算
FL_PRIVACY_EPSILON=1.0

# 学习率
FL_LEARNING_RATE=0.001
```

### 训练配置

```python
config = {
    "epochs": 10,              # 训练轮数
    "batch_size": 32,          # 批次大小
    "learning_rate": 0.001,    # 学习率
    "privacy_epsilon": 1.0,    # 隐私预算
    "aggregation_method": "fedavg",  # 聚合方法
}
```

## 监控指标

### 训练指标

- **Loss**：训练损失
- **Accuracy**：准确率
- **Training Samples**：训练样本数

### 聚合指标

- **Participating Stores**：参与门店数
- **Aggregation Time**：聚合耗时
- **Model Size**：模型大小

### 隐私指标

- **Privacy Budget Used**：已使用的隐私预算
- **Noise Level**：噪声水平

## 最佳实践

### 1. 数据准备

- 确保各门店数据格式一致
- 数据预处理标准化
- 处理缺失值和异常值

### 2. 模型设计

- 使用简单模型（避免过拟合）
- 参数量适中（减少通信开销）
- 支持增量学习

### 3. 隐私保护

- 合理设置隐私预算（推荐ε=1.0）
- 定期审计隐私泄露风险
- 限制训练轮次（避免过度暴露）

### 4. 性能优化

- 使用模型压缩技术
- 异步聚合（不等待所有门店）
- 缓存中间结果

## 故障排查

### 问题：聚合失败

**原因**：参与门店数不足

**解决**：
- 检查最少门店数配置
- 确认门店已成功上传模型
- 延长等待时间

### 问题：模型准确率低

**原因**：隐私预算过小

**解决**：
- 增加隐私预算（ε值）
- 增加训练轮次
- 使用更多训练数据

### 问题：训练时间过长

**原因**：模型过大或数据量过多

**解决**：
- 减少模型参数
- 使用数据采样
- 增加batch_size

## 安全考虑

1. **认证授权**：所有API需要认证
2. **传输加密**：使用HTTPS传输
3. **参数验证**：验证模型参数有效性
4. **审计日志**：记录所有训练活动
5. **访问控制**：限制管理员权限

## 相关文件

- `src/services/federated_learning_service.py` - 核心服务
- `src/api/federated_learning.py` - API端点
- `tests/test_federated_learning.py` - 单元测试
