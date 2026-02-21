# TODO清理计划
## 智链OS - Week 1任务

**总数**: 16个TODO
**分类策略**: 本周必做 / 下个月 / 永远删除

---

## 分类结果

### 📌 本周必做（Week 1-2）- 0个
无

### 📅 下个月（Week 2-6）- 10个

#### Week 2: 业务调度任务
- `src/services/scheduler.py:57` - TODO Week 2: 实现业务驱动的调度任务
  - **优先级**: P0
  - **计划**: Week 2实现营收异常检测、日报生成、库存预警

#### Week 4: 语音集成
- `src/services/voice_service.py:56` - TODO: 集成实际的STT服务
- `src/services/voice_service.py:109` - TODO: 集成实际的TTS服务
- `src/services/voice_service.py:150` - TODO: 实现Azure Speech Services集成
- `src/services/voice_service.py:162` - TODO: 实现Azure Speech Services集成
- `src/services/shokz_service.py:128` - TODO: 实际的蓝牙连接逻辑
- `src/services/shokz_service.py:167` - TODO: 实际的蓝牙断开逻辑
- `src/services/shokz_service.py:218` - TODO: 实际的音频发送逻辑
- `src/services/shokz_service.py:270` - TODO: 实际的音频接收逻辑
  - **优先级**: P0
  - **计划**: Week 4实现讯飞STT/TTS和Shokz设备集成

#### Week 5-6: 增强功能
- `src/services/vector_db_service.py:44` - TODO: 可以替换为其他嵌入模型
  - **优先级**: P1
  - **计划**: Week 5-6实现分域向量索引

### ❌ 永远删除（低优先级/不会做）- 6个

#### 非核心功能
- `src/api/wechat_triggers.py:163` - TODO: 实现触发统计功能
  - **原因**: 非MVP核心功能，优先级低
  - **行动**: 删除TODO注释，标记为"Future Enhancement"

- `src/api/customer360.py:154` - TODO: 实现客户搜索功能
  - **原因**: 可以使用现有的查询接口
  - **行动**: 删除TODO注释

- `src/api/enterprise.py:192` - TODO: 根据消息类型进行不同的处理
  - **原因**: 当前的通用处理已足够
  - **行动**: 删除TODO注释

#### 第三方集成（非必需）
- `src/services/multi_channel_notification.py:498` - TODO: 实际集成企业微信API
- `src/services/multi_channel_notification.py:530` - TODO: 实际集成微信公众号API
- `src/services/multi_channel_notification.py:590` - TODO: 集成推送服务
  - **原因**: 企业微信已有集成，其他渠道非必需
  - **行动**: 删除TODO注释，保留代码框架

---

## 执行计划

### 立即执行（今天）
1. 删除6个"永远删除"类别的TODO注释
2. 将10个"下个月"的TODO转换为明确的Week标记

### 转换规则
```python
# 旧格式
# TODO: 实现XXX功能

# 新格式（保留）
# Week 2: 实现XXX功能
# Week 4: 实现XXX功能

# 新格式（删除）
# Future Enhancement: XXX功能（低优先级）
```

---

## 清理后的TODO统计

- **删除**: 6个
- **保留**: 10个（明确标记Week）
- **总计**: 从16个减少到10个

---

**下一步**: 执行清理脚本
