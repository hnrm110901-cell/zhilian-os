# 测试说明

## 测试环境要求

本项目的单元测试需要PostgreSQL数据库支持，因为模型使用了PostgreSQL特定的UUID类型。

### 设置测试数据库

1. 安装PostgreSQL（如果尚未安装）
2. 创建测试数据库：
```bash
createdb zhilian_test
```

3. 设置环境变量（可选）：
```bash
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/zhilian_test"
```

### 运行测试

运行所有测试：
```bash
pytest
```

运行特定测试文件：
```bash
pytest tests/test_task_service.py
```

运行特定测试：
```bash
pytest tests/test_task_service.py::TestTaskService::test_create_task
```

### 测试覆盖率

查看测试覆盖率：
```bash
pytest --cov=src --cov-report=html
```

然后打开 `htmlcov/index.html` 查看详细报告。

## 新增测试

本次新增了以下测试文件：

1. `test_task_service.py` - 任务管理服务测试
   - 创建任务
   - 获取任务
   - 更新任务状态
   - 完成任务
   - 列出任务（按分配人、状态、优先级）
   - 删除任务
   - 更新任务详情

2. `test_daily_report_service.py` - 日报服务测试
   - 生成日报
   - 获取日报
   - 列出日报
   - 格式化报告消息
   - 无订单时生成日报
   - 数据聚合

3. `test_reconcile_service.py` - 对账服务测试
   - 对账匹配
   - 对账不匹配
   - 对账阈值
   - 超过对账阈值
   - 获取对账记录
   - 列出对账记录
   - 按状态列出对账记录
   - 计算系统金额
   - 无订单时对账

## 注意事项

- 测试使用独立的测试数据库，不会影响开发或生产数据
- 每个测试函数都会创建和清理自己的数据
- 测试使用了mock来模拟Neural System事件发送，避免实际发送消息
