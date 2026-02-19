# 智链OS神经系统实现报告

## 概述

智链OS神经系统是餐饮门店的中枢神经网络，通过事件驱动架构、语义搜索和联邦学习，实现门店运营的智能化协调和持续优化。

## 核心架构

### 1. 五大核心维度

神经系统基于餐饮业务的五个核心维度构建标准Schema：

#### 订单维度 (OrderSchema)
- 订单基本信息（订单号、类型、状态）
- 订单项目（菜品、数量、价格）
- 金额信息（小计、折扣、税费、总额）
- 时间信息（创建、确认、完成时间）
- 人员关联（服务员、收银员、厨师）

#### 菜品维度 (DishSchema)
- 菜品基本信息（名称、分类、描述）
- 配料信息（主料、辅料、调料）
- 营养信息（卡路里、蛋白质、脂肪、碳水化合物）
- 价格信息（成本、售价、利润率）
- 制作信息（准备时间、烹饪时间、难度等级）

#### 人员维度 (StaffSchema)
- 员工基本信息（姓名、角色、联系方式）
- 班次信息（工作时间、休息时间）
- 绩效信息（订单数、评分、投诉数）
- 技能信息（技能列表、认证、培训记录）

#### 时间维度 (TimeSlotSchema, BusinessHoursSchema)
- 时间段定义（开始、结束、类型）
- 营业时间配置（工作日、周末、节假日）
- 高峰时段标识

#### 金额维度 (TransactionSchema, FinancialSummarySchema)
- 交易信息（交易号、类型、金额、支付方式）
- 财务汇总（总收入、总支出、净利润、交易数）

### 2. 三大核心服务

#### 向量数据库服务 (VectorDatabaseService)
- **技术栈**: Qdrant + Sentence-Transformers
- **向量维度**: 384维（paraphrase-multilingual-MiniLM-L12-v2）
- **集合**: orders, dishes, staff, events
- **功能**:
  - 索引订单、菜品、事件数据
  - 语义搜索（支持自然语言查询）
  - 数据隔离（基于store_id过滤）

#### 联邦学习服务 (FederatedLearningService)
- **算法**: FedAvg (Federated Averaging)
- **架构**: 中心化协调 + 分布式训练
- **数据隔离**: 原始数据永不离开本地门店
- **功能**:
  - 全局模型初始化
  - 门店注册和本地更新上传
  - 加权模型聚合（基于训练样本数）
  - 全局模型分发

#### 神经系统编排器 (NeuralSystemOrchestrator)
- **角色**: 中枢协调器
- **功能**:
  - 事件发射和处理
  - 语义搜索接口
  - 联邦学习参与
  - Agent系统集成

### 3. 事件驱动架构

#### 事件类型
- **order**: 订单事件（创建、更新、完成、取消）
- **dish**: 菜品事件（添加、修改、缺货、补货）
- **staff**: 人员事件（打卡、请假、绩效更新）
- **payment**: 支付事件（支付成功、退款）
- **inventory**: 库存事件（库存预警、补货请求）

#### 事件处理流程
1. 事件发射 → 2. 事件处理器 → 3. 向量索引 → 4. Agent通知

## API接口

### 1. 事件发射
```http
POST /api/v1/neural/events/emit
Content-Type: application/json

{
  "event_type": "order",
  "store_id": "store_001",
  "data": {
    "order_id": "ORD20260218001",
    "total_amount": 158.50,
    "status": "completed"
  },
  "metadata": {
    "source": "pos_system"
  }
}
```

### 2. 语义搜索订单
```http
POST /api/v1/neural/search/orders
Content-Type: application/json

{
  "query": "今天下午的大额订单",
  "store_id": "store_001",
  "top_k": 10
}
```

### 3. 语义搜索菜品
```http
POST /api/v1/neural/search/dishes
Content-Type: application/json

{
  "query": "低卡路里的素食菜品",
  "store_id": "store_001",
  "top_k": 5
}
```

### 4. 语义搜索事件
```http
POST /api/v1/neural/search/events
Content-Type: application/json

{
  "query": "库存预警相关的事件",
  "store_id": "store_001",
  "top_k": 20
}
```

### 5. 参与联邦学习
```http
POST /api/v1/neural/federated-learning/participate
Content-Type: application/json

{
  "store_id": "store_001",
  "local_model_path": "/models/local_model.pkl",
  "training_samples": 1000,
  "metrics": {
    "accuracy": 0.95,
    "loss": 0.05
  }
}
```

### 6. 系统状态
```http
GET /api/v1/neural/status
```

响应示例：
```json
{
  "status": "operational",
  "total_events": 15234,
  "total_stores": 50,
  "federated_learning_round": 12,
  "vector_db_collections": {
    "orders": 45678,
    "dishes": 234,
    "staff": 156,
    "events": 15234
  },
  "uptime_seconds": 86400.0
}
```

### 7. 健康检查
```http
GET /api/v1/neural/health
```

## 数据隔离架构

### 三层隔离机制

#### 1. 向量数据库层
- 所有查询强制添加 `store_id` 过滤条件
- 门店A无法访问门店B的数据

#### 2. 联邦学习层
- 原始数据永不上传
- 仅上传模型参数（梯度/权重）
- DataIsolationManager强制执行隔离策略

#### 3. API层
- 所有请求必须包含 `store_id`
- 中间件验证用户权限
- 跨门店访问被拒绝

## 部署配置

### 依赖安装
```bash
# 向量数据库
pip install qdrant-client sentence-transformers

# 机器学习
pip install torch numpy scikit-learn

# 已有依赖
# fastapi, pydantic, structlog
```

### Qdrant配置
```yaml
# docker-compose.yml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage
```

### 环境变量
```bash
# .env
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=your_api_key_here

# 向量模型
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DIMENSION=384

# 联邦学习
FL_MIN_STORES=3
FL_AGGREGATION_THRESHOLD=0.8
```

## 使用场景

### 场景1: 智能订单推荐
```python
# 1. 客户询问："有什么低卡路里的菜品？"
response = await neural_system.semantic_search_dishes(
    query="低卡路里的菜品",
    store_id="store_001",
    top_k=5
)

# 2. 返回相关菜品（按相似度排序）
# - 清蒸鲈鱼 (score: 0.92)
# - 蔬菜沙拉 (score: 0.89)
# - 白灼虾 (score: 0.85)
```

### 场景2: 异常检测
```python
# 1. 发射支付事件
await neural_system.emit_event(NeuralEventSchema(
    event_type="payment",
    store_id="store_001",
    data={"amount": 5000, "payment_method": "cash"}
))

# 2. 搜索类似的大额现金支付
results = await neural_system.semantic_search_events(
    query="大额现金支付",
    store_id="store_001",
    top_k=10
)

# 3. 分析是否异常
if len(results) < 3:  # 历史上很少有大额现金支付
    alert_manager.send_alert("异常大额现金支付")
```

### 场景3: 跨门店学习
```python
# 门店A训练本地模型
local_model = train_demand_prediction_model(store_a_data)

# 参与联邦学习
await neural_system.participate_in_federated_learning(
    store_id="store_001",
    local_model=local_model,
    training_samples=len(store_a_data)
)

# 获取全局模型（融合了所有门店的知识）
global_model = neural_system.fl_service.get_global_model()

# 门店A现在可以利用其他门店的经验
predictions = global_model.predict(new_data)
```

## 技术优势

### 1. 语义理解
- 自然语言查询，无需精确匹配
- 多语言支持（中文、英文）
- 上下文理解能力

### 2. 隐私保护
- 联邦学习确保数据不出门店
- 三层隔离机制
- 符合数据保护法规

### 3. 持续学习
- 全局模型不断优化
- 新门店快速获得经验
- 异常检测能力提升

### 4. 可扩展性
- 事件驱动架构易于扩展
- 向量数据库支持海量数据
- 联邦学习支持无限门店

## 下一步计划

1. **实现实际模型训练逻辑**
   - 需求预测模型
   - 菜品推荐模型
   - 异常检测模型

2. **集成更多事件源**
   - POS系统事件
   - 会员系统事件
   - 供应链系统事件

3. **增强语义搜索**
   - 多模态搜索（文本+图片）
   - 时间序列分析
   - 关联规则挖掘

4. **优化联邦学习**
   - 差分隐私保护
   - 安全聚合协议
   - 拜占庭容错

## 总结

智链OS神经系统通过标准Schema、向量数据库、联邦学习和事件驱动架构，构建了餐饮门店的智能中枢。它不仅实现了数据的语义理解和智能搜索，还通过联邦学习在保护隐私的前提下实现了跨门店的知识共享和持续优化。

神经系统是智链OS的核心基础设施，为上层的Agent系统、语音交互、企业集成等功能提供了强大的数据和智能支持。

