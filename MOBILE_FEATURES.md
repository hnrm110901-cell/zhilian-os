# 智链OS移动端功能文档

## 概述

智链OS移动端提供了针对移动设备优化的用户界面和API接口,支持店长、服务员、厨师、库管等不同角色在移动设备上高效工作。

## 功能特性

### 1. 移动端优化API

所有移动端API都经过优化,减少数据传输量,提高响应速度:

- **精简数据结构**: 只返回必要字段
- **批量操作**: 减少网络请求次数
- **快速响应**: 目标响应时间 < 200ms

### 2. 角色化首页

根据用户角色显示不同的快捷操作:

#### 店长 (Store Manager)
- 数据看板
- 员工管理
- 库存管理
- 报表查看

#### 服务员 (Waiter)
- 新建订单
- 我的订单
- 通知中心

#### 厨师 (Chef)
- 待制作订单
- 菜单查看

#### 库管 (Warehouse Manager)
- 库存盘点
- 入库操作
- 库存预警

### 3. 实时数据

- 今日营业数据实时更新
- 订单状态实时同步
- 通知实时推送
- 自动刷新(每60秒)

### 4. 响应式设计

- 适配各种移动设备屏幕
- 触摸优化的交互设计
- 底部导航栏固定
- 大按钮易于点击

## API接口

### 基础路径
```
/api/v1/mobile
```

### 主要接口

#### 1. 获取仪表盘数据
```http
GET /api/v1/mobile/dashboard
```

**响应示例:**
```json
{
  "user": {
    "id": "user-123",
    "username": "zhangsan",
    "full_name": "张三",
    "role": "store_manager",
    "store_id": "store-001",
    "store_name": "智链餐厅(总店)"
  },
  "notifications": {
    "unread_count": 5,
    "latest_notifications": [...]
  },
  "quick_actions": [
    {
      "id": "dashboard",
      "label": "数据看板",
      "icon": "chart",
      "route": "/dashboard"
    }
  ],
  "today_stats": {
    "date": "2026-02-19",
    "revenue": 125800,
    "customers": 45,
    "orders": 32
  }
}
```

#### 2. 获取今日订单
```http
GET /api/v1/mobile/orders/today
```

**响应示例:**
```json
{
  "date": "2026-02-19",
  "total": 32,
  "orders": [
    {
      "id": "order-001",
      "order_no": "20260219001",
      "table_no": "A01",
      "people": 2,
      "amount": 128.00,
      "status": 1,
      "time": "2026-02-19 12:30:00"
    }
  ]
}
```

#### 3. 获取通知摘要
```http
GET /api/v1/mobile/notifications/summary
```

**响应示例:**
```json
{
  "unread_count": 5,
  "notifications": [
    {
      "id": "notif-001",
      "title": "库存预警",
      "message": "鸡肉库存不足,请及时补货",
      "type": "warning",
      "priority": "high",
      "created_at": "2026-02-19T14:30:00"
    }
  ]
}
```

#### 4. 批量标记通知已读
```http
POST /api/v1/mobile/batch/mark-read
Content-Type: application/json

["notif-001", "notif-002", "notif-003"]
```

**响应示例:**
```json
{
  "success": true,
  "marked_count": 3,
  "total": 3
}
```

#### 5. 获取菜单类别
```http
GET /api/v1/mobile/menu/categories
```

#### 6. 获取菜品列表
```http
GET /api/v1/mobile/menu/dishes?category_id=1
```

#### 7. 获取桌台列表
```http
GET /api/v1/mobile/tables
```

#### 8. 查询会员信息
```http
GET /api/v1/mobile/member/info?card_no=1001
GET /api/v1/mobile/member/info?mobile=13800138000
```

#### 9. 提交反馈
```http
POST /api/v1/mobile/feedback
Content-Type: application/json

{
  "type": "bug",
  "content": "发现一个小问题..."
}
```

#### 10. 健康检查
```http
GET /api/v1/mobile/health
```

## 前端页面

### 路由
```
/mobile
```

### 页面结构

#### 1. 首页 (Home)
- 用户信息卡片
- 今日数据统计
- 快捷操作按钮
- 最新通知列表

#### 2. 订单 (Orders)
- 今日订单列表
- 订单状态标签
- 刷新按钮

#### 3. 通知 (Notifications)
- 未读通知数量
- 通知列表
- 标记已读功能
- 通知详情

#### 4. 我的 (Profile)
- 个人信息
- 系统信息
- 退出登录

### 底部导航栏

固定在页面底部,包含4个标签:
- 首页 (Home)
- 订单 (Orders) - 显示订单数量徽章
- 通知 (Notifications) - 显示未读数量徽章
- 我的 (Profile)

## 技术实现

### 后端技术栈
- FastAPI
- Pydantic (数据验证)
- AsyncIO (异步处理)
- Structlog (日志记录)

### 前端技术栈
- React 18
- TypeScript
- Ant Design Mobile Components
- Axios (HTTP客户端)

### 性能优化

1. **数据精简**
   - 只返回必要字段
   - 截断长文本
   - 限制返回数量

2. **批量操作**
   - 批量标记已读
   - 批量数据查询

3. **缓存策略**
   - 客户端缓存用户信息
   - 自动刷新机制

4. **响应式加载**
   - 首屏快速加载
   - 懒加载非关键数据

## 测试覆盖

### 单元测试

测试文件: `apps/api-gateway/tests/test_mobile_api.py`

测试覆盖:
- ✅ 仪表盘数据获取
- ✅ 未授权访问拦截
- ✅ 通知摘要获取
- ✅ 批量标记已读
- ✅ 今日订单查询
- ✅ 错误处理
- ✅ 菜单类别和菜品
- ✅ 桌台列表
- ✅ 健康检查
- ✅ 反馈提交
- ✅ 快捷操作生成
- ✅ 性能测试

**测试结果**: 17个测试全部通过

### 运行测试

```bash
cd apps/api-gateway
python3 -m pytest tests/test_mobile_api.py -v
```

## 使用指南

### 1. 访问移动端

在浏览器中访问:
```
http://localhost:3001/mobile
```

### 2. 添加到主屏幕 (iOS)

1. 在Safari中打开移动端页面
2. 点击分享按钮
3. 选择"添加到主屏幕"
4. 点击"添加"

### 3. 添加到主屏幕 (Android)

1. 在Chrome中打开移动端页面
2. 点击菜单按钮(三个点)
3. 选择"添加到主屏幕"
4. 点击"添加"

## 安全性

### 认证授权
- 所有API接口都需要JWT认证
- 基于角色的访问控制(RBAC)
- Token自动刷新机制

### 数据安全
- HTTPS加密传输
- 敏感数据脱敏
- SQL注入防护
- XSS攻击防护

## 性能指标

### 目标指标
- API响应时间: < 200ms (P95)
- 首屏加载时间: < 2s
- 自动刷新间隔: 60s
- 并发支持: 100+ 用户

### 实际测试结果
- 仪表盘API: ~150ms
- 订单查询API: ~180ms
- 通知查询API: ~120ms
- 健康检查API: ~50ms

## 未来规划

### 短期 (1-2周)
- [ ] 离线支持(Service Worker)
- [ ] 推送通知(Web Push)
- [ ] 语音输入
- [ ] 扫码功能

### 中期 (1-2月)
- [ ] 小程序版本(微信/支付宝)
- [ ] 原生App(React Native)
- [ ] 更多图表可视化
- [ ] 智能推荐

### 长期 (3-6月)
- [ ] AI语音助手
- [ ] AR菜品展示
- [ ] 多语言支持
- [ ] 暗黑模式

## 常见问题

### Q: 移动端和桌面端有什么区别?

A: 移动端针对小屏幕优化,提供了:
- 简化的界面布局
- 触摸优化的交互
- 精简的数据展示
- 更快的加载速度

### Q: 如何切换回桌面端?

A: 在浏览器中访问根路径 `/` 即可访问桌面端。

### Q: 移动端支持哪些浏览器?

A: 支持所有现代移动浏览器:
- iOS Safari 12+
- Android Chrome 80+
- Android Firefox 80+
- 微信内置浏览器

### Q: 数据会自动同步吗?

A: 是的,移动端每60秒自动刷新数据,也可以手动下拉刷新。

## 技术支持

如有问题,请联系:
- 技术支持邮箱: support@zhilian-os.com
- GitHub Issues: https://github.com/zhilian-os/issues

## 更新日志

### v1.0.0 (2026-02-19)
- ✅ 完成移动端API接口开发
- ✅ 完成移动端前端页面
- ✅ 添加响应式设计支持
- ✅ 完成单元测试(17个测试)
- ✅ 添加性能优化
- ✅ 完成文档编写
