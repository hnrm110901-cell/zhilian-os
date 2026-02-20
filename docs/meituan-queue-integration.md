# 美团等位系统集成

## 概述

智链OS已集成美团等位API，实现线上线下排队统一管理，支持美团/大众点评双端展示。

## 核心功能

### 1. 双向同步
- **线下到线上**: 本地POS取号自动同步到美团
- **线上到线下**: 美团/大众点评取号自动创建本地排队

### 2. 状态实时同步
- 排队中 → 叫号中 → 已就餐
- 取消排队、过号自动同步

### 3. 桌型配置
- 支持多种桌型（小桌、中桌、大桌）
- 自动同步桌型配置到美团

## API端点

### 1. 处理美团用户取号推送
```http
POST /api/v1/meituan/queue/webhook/user-queue
```

### 2. 同步桌型配置
```http
POST /api/v1/meituan/queue/sync/table-types
```

### 3. 同步排队状态
```http
POST /api/v1/meituan/queue/sync/queue-status
```

### 4. 同步等位信息
```http
POST /api/v1/meituan/queue/sync/waiting-info
```

## 配置

### 环境变量
```bash
# 美团等位配置
MEITUAN_DEVELOPER_ID=your_developer_id
MEITUAN_SIGN_KEY=your_sign_key
MEITUAN_BUSINESS_ID=49
```

### OAuth 2.0授权
1. 商家在美团开店宝授权
2. 获取appAuthToken
3. 使用token调用API

## 业务流程

### 线下取号流程
1. 客户在POS机取号
2. 本地创建排队记录
3. 自动同步到美团
4. 美团/大众点评显示排队信息

### 线上取号流程
1. 客户在美团/大众点评App取号
2. 美团推送到webhook
3. 本地创建排队记录
4. 回调美团取号结果

## 状态映射

| 本地状态 | 美团状态码 | 说明 |
|---------|-----------|------|
| waiting | 3 | 排队中 |
| called | 4 | 叫号中 |
| seated | 5 | 已就餐 |
| cancelled | 8 | 已取消 |
| no_show | 6 | 已过号 |

## 相关文档
- [排队系统](./queue-system.md)
- [美团等位API官方文档](https://developer.meituan.com/docs/biz/dcpd)
