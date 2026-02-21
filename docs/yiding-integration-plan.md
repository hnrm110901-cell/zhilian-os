# 智链OS与易订系统集成方案

> 版本: v1.0
> 日期: 2026-02-15
> 定位: 智链OS作为AI智能中间层,连接企业微信与易订预订系统

---

## 一、集成架构概述

### 1.1 系统定位

```
┌─────────────────────────────────────────────────────────┐
│              企业微信 / 飞书                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ AI Bot   │  │ 卡片消息 │  │ 群聊推送 │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
└───────┼─────────────┼─────────────┼────────────────────┘
        │             │             │
┌───────┴─────────────┴─────────────┴────────────────────┐
│              智链OS - AI智能中间层                       │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │         预定协同Agent (新增)                    │    │
│  │  • AI意图识别                                   │    │
│  │  • 自然语言预订                                 │    │
│  │  • 智能推荐                                     │    │
│  │  • 冲突检测                                     │    │
│  └────────────────┬───────────────────────────────┘    │
│                   │                                     │
│  ┌────────────────▼───────────────────────────────┐    │
│  │         易订适配器 (YiDing Adapter)             │    │
│  │  • API认证与鉴权                                │    │
│  │  • 数据格式转换                                 │    │
│  │  • 错误处理与重试                               │    │
│  │  • 缓存优化                                     │    │
│  └────────────────┬───────────────────────────────┘    │
└───────────────────┼────────────────────────────────────┘
                    │
┌───────────────────▼────────────────────────────────────┐
│              易订预订系统                                │
│  • 预订管理                                             │
│  • 客户管理                                             │
│  • 桌台管理                                             │
│  • 会员体系                                             │
└─────────────────────────────────────────────────────────┘
```

### 1.2 核心价值

**智链OS不替代易订,而是增强易订:**

✅ **AI驱动**: 自然语言预订,无需手动填表
✅ **企微入口**: 所有操作在企业微信完成
✅ **智能推荐**: 基于客户画像推荐时段/桌型
✅ **数据聚合**: 跨系统汇总预订、订单、会员数据
✅ **主动服务**: 自动提醒、智能叫号、VIP识别

---

## 二、易订系统分析

### 2.1 易订核心功能

根据文档分析,易订系统提供:

1. **预订管理**
   - 电话预订/线上预订
   - 预订确认与修改
   - 预订提醒
   - 预订统计

2. **客户管理**
   - 客户档案
   - 消费记录
   - 偏好标签
   - 会员等级

3. **桌台管理**
   - 桌台状态
   - 桌台分配
   - 翻台率统计

4. **营销功能**
   - 会员营销
   - 优惠券
   - 积分体系
   - 生日提醒

### 2.2 易订API能力(推测)

基于行业标准,易订应提供以下API:

```typescript
// 预订相关
POST   /api/reservations          // 创建预订
GET    /api/reservations/:id      // 查询预订详情
PUT    /api/reservations/:id      // 修改预订
DELETE /api/reservations/:id      // 取消预订
GET    /api/reservations/list     // 预订列表

// 客户相关
GET    /api/customers/:phone      // 根据手机号查客户
GET    /api/customers/:id         // 客户详情
POST   /api/customers             // 创建客户
PUT    /api/customers/:id         // 更新客户

// 桌台相关
GET    /api/tables                // 桌台列表
GET    /api/tables/available      // 可用桌台
PUT    /api/tables/:id/status     // 更新桌台状态

// 统计相关
GET    /api/stats/reservations    // 预订统计
GET    /api/stats/customers       // 客户统计
```

---

## 三、集成架构设计

### 3.1 目录结构

```
zhilian-os/
├── packages/
│   ├── agents/
│   │   ├── reservation/          # 已完成的预定Agent
│   │   │   ├── src/
│   │   │   │   └── agent.py
│   │   │   ├── tests/
│   │   │   └── README.md
│   │   │
│   │   └── reservation-coordinator/  # 新增:预定协同Agent
│   │       ├── src/
│   │       │   ├── agent.py          # 协同逻辑
│   │       │   ├── intent.py         # 意图识别
│   │       │   └── recommender.py    # 智能推荐
│   │       ├── tests/
│   │       └── README.md
│   │
│   └── api-adapters/
│       ├── base/
│       │   ├── adapter.interface.ts  # 统一接口
│       │   └── adapter.base.ts       # 基础适配器
│       │
│       └── yiding/                   # 新增:易订适配器
│           ├── yiding.adapter.ts     # 主适配器
│           ├── yiding.client.ts      # HTTP客户端
│           ├── yiding.mapper.ts      # 数据映射
│           ├── yiding.types.ts       # 类型定义
│           ├── yiding.cache.ts       # 缓存策略
│           └── README.md
```

### 3.2 数据流设计

#### 场景1: 客户通过企微预订

```
1. 客户发消息: "明天晚上6点,4个人,要包间"
   ↓
2. 企微回调 → 智链OS接收消息
   ↓
3. AI意图识别:
   {
     intent: "CREATE_RESERVATION",
     params: {
       date: "2026-02-16",
       time: "18:00",
       partySize: 4,
       tableType: "private_room"
     }
   }
   ↓
4. 预定协同Agent处理:
   - 调用易订适配器查询可用性
   - 智能推荐最佳桌台
   - 检测冲突
   ↓
5. 易订适配器:
   - 调用易订API: GET /api/tables/available
   - 数据格式转换
   - 返回统一格式
   ↓
6. 创建预订:
   - 调用易订API: POST /api/reservations
   - 同步到智链OS数据库(聚合)
   ↓
7. 回复客户:
   "✅ 预订成功!
    日期: 2026-02-16 18:00
    人数: 4人
    桌台: 8号包间
    预订号: RES20260216001"
   ↓
8. 自动触发:
   - 发送确认短信(易订)
   - 推送到店长群(企微)
   - 记录到聚合数据库
   - 设置提醒任务
```

#### 场景2: 前台接电话预订

```
1. 前台李姐接到电话: 138****8888
   ↓
2. 李姐在企微发: "查一下138****8888"
   ↓
3. 智链OS识别意图 → 查询客户
   ↓
4. 易订适配器:
   - 调用: GET /api/customers/138****8888
   - 返回客户档案
   ↓
5. 智链OS聚合数据:
   - 易订的预订历史
   - 订单系统的消费记录
   - 会员系统的积分信息
   ↓
6. 推送卡片消息给李姐:
   ┌─────────────────────────────┐
   │ 👤 李先生 (VIP)              │
   │ 📞 138****8888              │
   │ 💰 累计消费: ¥48,600        │
   │ 📅 上次到店: 2周前          │
   │ ⭐ 满意度: 95分             │
   │                             │
   │ 🍽️ 偏好:                    │
   │ • 爱点: 清蒸鲈鱼、手撕包菜  │
   │ • 桌型: 8号包间             │
   │ • 时段: 晚上6-7点           │
   │                             │
   │ [快速预订] [查看详情]       │
   └─────────────────────────────┘
   ↓
7. 李姐点击[快速预订] → 一键创建
```

---

## 四、易订适配器实现

### 4.1 统一接口定义

```typescript
// packages/api-adapters/base/adapter.interface.ts

export interface IReservationAdapter {
  // 系统信息
  getSystemName(): string;
  healthCheck(): Promise<boolean>;

  // 预订管理
  createReservation(data: CreateReservationDTO): Promise<UnifiedReservation>;
  getReservation(id: string): Promise<UnifiedReservation>;
  updateReservation(id: string, data: UpdateReservationDTO): Promise<UnifiedReservation>;
  cancelReservation(id: string, reason?: string): Promise<void>;
  getReservations(storeId: string, date: string): Promise<UnifiedReservation[]>;

  // 客户管理
  getCustomerByPhone(phone: string): Promise<UnifiedCustomer | null>;
  getCustomerById(id: string): Promise<UnifiedCustomer>;
  createCustomer(data: CreateCustomerDTO): Promise<UnifiedCustomer>;
  updateCustomer(id: string, data: UpdateCustomerDTO): Promise<UnifiedCustomer>;

  // 桌台管理
  getAvailableTables(storeId: string, date: string, time: string, partySize: number): Promise<UnifiedTable[]>;
  getTableStatus(storeId: string): Promise<UnifiedTableStatus[]>;

  // 统计分析
  getReservationStats(storeId: string, startDate: string, endDate: string): Promise<ReservationStats>;
}

// 统一数据格式
export interface UnifiedReservation {
  id: string;                    // 智链OS内部ID
  externalId: string;            // 易订系统ID
  source: 'yiding';              // 来源系统
  storeId: string;               // 门店ID

  // 客户信息
  customerId: string;
  customerName: string;
  customerPhone: string;

  // 预订信息
  reservationDate: string;       // YYYY-MM-DD
  reservationTime: string;       // HH:mm
  partySize: number;
  tableType: string;
  tableNumber?: string;

  // 状态
  status: 'pending' | 'confirmed' | 'seated' | 'completed' | 'cancelled' | 'no_show';

  // 金额
  depositAmount: number;         // 定金(分)
  estimatedAmount: number;       // 预估消费(分)

  // 备注
  specialRequests?: string;
  note?: string;

  // 时间戳
  createdAt: string;
  updatedAt: string;
  confirmedAt?: string;
  seatedAt?: string;
  completedAt?: string;
}

export interface UnifiedCustomer {
  id: string;
  externalId: string;
  source: 'yiding';

  phone: string;
  name: string;
  gender?: 'male' | 'female';
  birthday?: string;

  // 会员信息
  memberLevel?: string;
  memberPoints?: number;
  balance?: number;

  // 统计
  totalVisits: number;
  totalSpent: number;
  lastVisit?: string;

  // 偏好
  preferences?: {
    favoriteDishes?: string[];
    tablePreference?: string;
    timePreference?: string;
    dietaryRestrictions?: string[];
  };

  tags?: string[];
  createdAt: string;
  updatedAt: string;
}

export interface UnifiedTable {
  id: string;
  tableNumber: string;
  tableType: 'small' | 'medium' | 'large' | 'round' | 'private_room';
  capacity: number;
  minCapacity: number;
  status: 'available' | 'occupied' | 'reserved' | 'maintenance';
  location?: string;
  features?: string[];
}
```

### 4.2 易订适配器实现

```typescript
// packages/api-adapters/yiding/yiding.adapter.ts

import { IReservationAdapter } from '../base/adapter.interface';
import { YiDingClient } from './yiding.client';
import { YiDingMapper } from './yiding.mapper';
import { YiDingCache } from './yiding.cache';
import structlog from 'structlog';

const logger = structlog.get_logger();

export class YiDingAdapter implements IReservationAdapter {
  private client: YiDingClient;
  private mapper: YiDingMapper;
  private cache: YiDingCache;

  constructor(config: YiDingConfig) {
    this.client = new YiDingClient(config);
    this.mapper = new YiDingMapper();
    this.cache = new YiDingCache();
  }

  getSystemName(): string {
    return 'yiding';
  }

  async healthCheck(): Promise<boolean> {
    try {
      await this.client.ping();
      return true;
    } catch (error) {
      logger.error('yiding_health_check_failed', { error });
      return false;
    }
  }

  // 创建预订
  async createReservation(data: CreateReservationDTO): Promise<UnifiedReservation> {
    logger.info('creating_reservation_in_yiding', { data });

    try {
      // 1. 转换为易订格式
      const yidingData = this.mapper.toYiDingReservation(data);

      // 2. 调用易订API
      const response = await this.client.post('/api/reservations', yidingData);

      // 3. 转换为统一格式
      const unified = this.mapper.toUnifiedReservation(response.data);

      // 4. 清除相关缓存
      await this.cache.invalidateReservations(data.storeId, data.reservationDate);

      logger.info('reservation_created_in_yiding', {
        reservationId: unified.id,
        externalId: unified.externalId
      });

      return unified;
    } catch (error) {
      logger.error('create_reservation_failed', { error, data });
      throw new AdapterError('创建预订失败', error);
    }
  }

  // 查询预订
  async getReservation(id: string): Promise<UnifiedReservation> {
    // 1. 尝试从缓存读取
    const cached = await this.cache.getReservation(id);
    if (cached) {
      return cached;
    }

    // 2. 调用易订API
    const response = await this.client.get(`/api/reservations/${id}`);

    // 3. 转换并缓存
    const unified = this.mapper.toUnifiedReservation(response.data);
    await this.cache.setReservation(id, unified);

    return unified;
  }

  // 更新预订
  async updateReservation(
    id: string,
    data: UpdateReservationDTO
  ): Promise<UnifiedReservation> {
    const yidingData = this.mapper.toYiDingReservationUpdate(data);
    const response = await this.client.put(`/api/reservations/${id}`, yidingData);

    const unified = this.mapper.toUnifiedReservation(response.data);

    // 清除缓存
    await this.cache.invalidateReservation(id);

    return unified;
  }

  // 取消预订
  async cancelReservation(id: string, reason?: string): Promise<void> {
    await this.client.delete(`/api/reservations/${id}`, {
      data: { reason }
    });

    await this.cache.invalidateReservation(id);
  }

  // 获取预订列表
  async getReservations(
    storeId: string,
    date: string
  ): Promise<UnifiedReservation[]> {
    // 尝试从缓存读取
    const cached = await this.cache.getReservations(storeId, date);
    if (cached) {
      return cached;
    }

    // 调用易订API
    const response = await this.client.get('/api/reservations/list', {
      params: {
        storeId,
        date,
        pageSize: 1000
      }
    });

    // 转换并缓存
    const unified = response.data.items.map(item =>
      this.mapper.toUnifiedReservation(item)
    );

    await this.cache.setReservations(storeId, date, unified, 300); // 5分钟缓存

    return unified;
  }

  // 根据手机号查询客户
  async getCustomerByPhone(phone: string): Promise<UnifiedCustomer | null> {
    try {
      const response = await this.client.get(`/api/customers/phone/${phone}`);

      if (!response.data) {
        return null;
      }

      return this.mapper.toUnifiedCustomer(response.data);
    } catch (error) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }

  // 查询可用桌台
  async getAvailableTables(
    storeId: string,
    date: string,
    time: string,
    partySize: number
  ): Promise<UnifiedTable[]> {
    const response = await this.client.get('/api/tables/available', {
      params: {
        storeId,
        date,
        time,
        partySize
      }
    });

    return response.data.map(item => this.mapper.toUnifiedTable(item));
  }

  // 获取预订统计
  async getReservationStats(
    storeId: string,
    startDate: string,
    endDate: string
  ): Promise<ReservationStats> {
    const response = await this.client.get('/api/stats/reservations', {
      params: {
        storeId,
        startDate,
        endDate
      }
    });

    return this.mapper.toReservationStats(response.data);
  }
}
```

### 4.3 HTTP客户端实现

```typescript
// packages/api-adapters/yiding/yiding.client.ts

import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import axiosRetry from 'axios-retry';
import crypto from 'crypto';

export interface YiDingConfig {
  baseURL: string;
  appId: string;
  appSecret: string;
  timeout?: number;
}

export class YiDingClient {
  private client: AxiosInstance;
  private config: YiDingConfig;

  constructor(config: YiDingConfig) {
    this.config = config;

    // 创建axios实例
    this.client = axios.create({
      baseURL: config.baseURL,
      timeout: config.timeout || 10000,
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'ZhilianOS/1.0'
      }
    });

    // 配置重试策略
    axiosRetry(this.client, {
      retries: 3,
      retryDelay: axiosRetry.exponentialDelay,
      retryCondition: (error) => {
        return axiosRetry.isNetworkOrIdempotentRequestError(error) ||
               error.response?.status === 429;
      }
    });

    // 请求拦截器 - 添加签名
    this.client.interceptors.request.use(
      (config) => {
        const timestamp = Date.now().toString();
        const nonce = this.generateNonce();
        const signature = this.generateSignature(timestamp, nonce);

        config.headers['X-YiDing-AppId'] = this.config.appId;
        config.headers['X-YiDing-Timestamp'] = timestamp;
        config.headers['X-YiDing-Nonce'] = nonce;
        config.headers['X-YiDing-Signature'] = signature;

        return config;
      },
      (error) => Promise.reject(error)
    );

    // 响应拦截器 - 统一错误处理
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response) {
          const { status, data } = error.response;

          // 统一错误格式
          throw new YiDingAPIError(
            data.message || '易订API调用失败',
            status,
            data.code,
            data
          );
        }

        throw error;
      }
    );
  }

  // 生成签名
  private generateSignature(timestamp: string, nonce: string): string {
    const signString = `${this.config.appId}${timestamp}${nonce}${this.config.appSecret}`;
    return crypto.createHash('sha256').update(signString).digest('hex');
  }

  // 生成随机字符串
  private generateNonce(): string {
    return crypto.randomBytes(16).toString('hex');
  }

  // HTTP方法封装
  async get(url: string, config?: AxiosRequestConfig) {
    return this.client.get(url, config);
  }

  async post(url: string, data?: any, config?: AxiosRequestConfig) {
    return this.client.post(url, data, config);
  }

  async put(url: string, data?: any, config?: AxiosRequestConfig) {
    return this.client.put(url, data, config);
  }

  async delete(url: string, config?: AxiosRequestConfig) {
    return this.client.delete(url, config);
  }

  async ping(): Promise<void> {
    await this.get('/api/health');
  }
}

export class YiDingAPIError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public code?: string,
    public data?: any
  ) {
    super(message);
    this.name = 'YiDingAPIError';
  }
}
```

### 4.4 数据映射器

```typescript
// packages/api-adapters/yiding/yiding.mapper.ts

export class YiDingMapper {
  // 易订预订 → 统一格式
  toUnifiedReservation(yidingData: any): UnifiedReservation {
    return {
      id: `yiding_${yidingData.id}`,
      externalId: yidingData.id,
      source: 'yiding',
      storeId: yidingData.storeId,

      customerId: yidingData.customerId,
      customerName: yidingData.customerName,
      customerPhone: yidingData.customerPhone,

      reservationDate: yidingData.reservationDate,
      reservationTime: yidingData.reservationTime,
      partySize: yidingData.partySize,
      tableType: this.mapTableType(yidingData.tableType),
      tableNumber: yidingData.tableNumber,

      status: this.mapStatus(yidingData.status),

      depositAmount: yidingData.depositAmount || 0,
      estimatedAmount: yidingData.estimatedAmount || 0,

      specialRequests: yidingData.specialRequests,
      note: yidingData.note,

      createdAt: yidingData.createdAt,
      updatedAt: yidingData.updatedAt,
      confirmedAt: yidingData.confirmedAt,
      seatedAt: yidingData.seatedAt,
      completedAt: yidingData.completedAt
    };
  }

  // 统一格式 → 易订预订
  toYiDingReservation(data: CreateReservationDTO): any {
    return {
      storeId: data.storeId,
      customerId: data.customerId,
      customerName: data.customerName,
      customerPhone: data.customerPhone,
      reservationDate: data.reservationDate,
      reservationTime: data.reservationTime,
      partySize: data.partySize,
      tableType: this.reverseMapTableType(data.tableType),
      specialRequests: data.specialRequests,
      source: 'zhilianos' // 标记来源
    };
  }

  // 易订客户 → 统一格式
  toUnifiedCustomer(yidingData: any): UnifiedCustomer {
    return {
      id: `yiding_${yidingData.id}`,
      externalId: yidingData.id,
      source: 'yiding',

      phone: yidingData.phone,
      name: yidingData.name,
      gender: yidingData.gender,
      birthday: yidingData.birthday,

      memberLevel: yidingData.memberLevel,
      memberPoints: yidingData.points,
      balance: yidingData.balance,

      totalVisits: yidingData.visitCount || 0,
      totalSpent: yidingData.totalSpent || 0,
      lastVisit: yidingData.lastVisitDate,

      preferences: {
        favoriteDishes: yidingData.favoriteDishes || [],
        tablePreference: yidingData.preferredTable,
        timePreference: yidingData.preferredTime,
        dietaryRestrictions: yidingData.dietaryRestrictions || []
      },

      tags: yidingData.tags || [],
      createdAt: yidingData.createdAt,
      updatedAt: yidingData.updatedAt
    };
  }

  // 状态映射
  private mapStatus(yidingStatus: string): string {
    const statusMap: Record<string, string> = {
      'pending': 'pending',
      'confirmed': 'confirmed',
      'arrived': 'seated',
      'finished': 'completed',
      'cancelled': 'cancelled',
      'noshow': 'no_show'
    };

    return statusMap[yidingStatus] || 'pending';
  }

  // 桌型映射
  private mapTableType(yidingType: string): string {
    const typeMap: Record<string, string> = {
      'small': 'small',
      'medium': 'medium',
      'large': 'large',
      'round': 'round',
      'private': 'private_room'
    };

    return typeMap[yidingType] || 'medium';
  }

  private reverseMapTableType(unifiedType: string): string {
    const typeMap: Record<string, string> = {
      'small': 'small',
      'medium': 'medium',
      'large': 'large',
      'round': 'round',
      'private_room': 'private'
    };

    return typeMap[unifiedType] || 'medium';
  }
}
```

---

## 五、预定协同Agent

### 5.1 Agent架构

```python
# packages/agents/reservation-coordinator/src/agent.py

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

logger = structlog.get_logger()

class ReservationIntent(str, Enum):
    """预订意图"""
    CREATE = "create"              # 创建预订
    QUERY = "query"                # 查询预订
    MODIFY = "modify"              # 修改预订
    CANCEL = "cancel"              # 取消预订
    CHECK_AVAILABILITY = "check"   # 查询可用性

class ReservationCoordinatorAgent:
    """
    预定协同Agent

    职责:
    1. 接收企微消息,识别预订意图
    2. 调用易订适配器完成预订操作
    3. 智能推荐最佳时段/桌型
    4. 冲突检测和自动调整
    5. 主动提醒和通知
    """

    def __init__(
        self,
        yiding_adapter,
        order_agent=None,
        member_agent=None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.yiding_adapter = yiding_adapter
        self.order_agent = order_agent
        self.member_agent = member_agent
        self.config = config or {}
        self.logger = logger.bind(agent="reservation_coordinator")

    async def handle_message(
        self,
        message: str,
        user_id: str,
        store_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        处理企微消息

        Args:
            message: 用户消息
            user_id: 用户ID
            store_id: 门店ID
            context: 上下文信息

        Returns:
            回复消息
        """
        self.logger.info("handling_message", message=message, user_id=user_id)

        try:
            # 1. 识别意图
            intent_result = await self._recognize_intent(message, context)

            # 2. 根据意图路由
            if intent_result['intent'] == ReservationIntent.CREATE:
                return await self._handle_create(intent_result['params'], store_id, user_id)

            elif intent_result['intent'] == ReservationIntent.QUERY:
                return await self._handle_query(intent_result['params'], store_id, user_id)

            elif intent_result['intent'] == ReservationIntent.MODIFY:
                return await self._handle_modify(intent_result['params'], store_id, user_id)

            elif intent_result['intent'] == ReservationIntent.CANCEL:
                return await self._handle_cancel(intent_result['params'], store_id, user_id)

            elif intent_result['intent'] == ReservationIntent.CHECK_AVAILABILITY:
                return await self._handle_check_availability(intent_result['params'], store_id)

            else:
                return self._get_help_message()

        except Exception as e:
            self.logger.error("handle_message_failed", error=str(e))
            return f"抱歉,处理您的请求时出现错误: {str(e)}"

    async def _recognize_intent(
        self,
        message: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        识别预订意图

        使用规则+AI混合方式:
        1. 先用关键词快速匹配
        2. 复杂情况调用AI
        """
        # 关键词匹配
        if any(kw in message for kw in ['预订', '预定', '订位', '订桌']):
            params = self._extract_reservation_params(message)
            return {
                'intent': ReservationIntent.CREATE,
                'params': params,
                'confidence': 0.9
            }

        if any(kw in message for kw in ['查', '看', '有没有']):
            if any(kw in message for kw in ['预订', '预定']):
                params = self._extract_query_params(message)
                return {
                    'intent': ReservationIntent.QUERY,
                    'params': params,
                    'confidence': 0.85
                }

        if any(kw in message for kw in ['取消', '不来了']):
            params = self._extract_cancel_params(message)
            return {
                'intent': ReservationIntent.CANCEL,
                'params': params,
                'confidence': 0.9
            }

        # 默认返回帮助
        return {
            'intent': 'help',
            'params': {},
            'confidence': 0.1
        }

    async def _handle_create(
        self,
        params: Dict[str, Any],
        store_id: str,
        user_id: str
    ) -> str:
        """处理创建预订"""
        self.logger.info("creating_reservation", params=params)

        # 1. 参数验证
        if not all(k in params for k in ['date', 'time', 'party_size']):
            return "请提供完整的预订信息:\n日期、时间、人数"

        # 2. 查询可用桌台
        available_tables = await self.yiding_adapter.getAvailableTables(
            store_id,
            params['date'],
            params['time'],
            params['party_size']
        )

        if not available_tables:
            # 推荐其他时段
            alternatives = await self._recommend_alternatives(
                store_id,
                params['date'],
                params['party_size']
            )
            return f"抱歉,{params['time']}暂无合适桌位\n\n推荐时段:\n{alternatives}"

        # 3. 智能推荐最佳桌台
        best_table = self._select_best_table(available_tables, params)

        # 4. 创建预订
        reservation = await self.yiding_adapter.createReservation({
            'storeId': store_id,
            'customerName': params.get('name', ''),
            'customerPhone': params.get('phone', ''),
            'reservationDate': params['date'],
            'reservationTime': params['time'],
            'partySize': params['party_size'],
            'tableType': best_table['tableType'],
            'tableNumber': best_table['tableNumber'],
            'specialRequests': params.get('requests', '')
        })

        # 5. 格式化回复
        return self._format_reservation_success(reservation)

    def _format_reservation_success(self, reservation: Dict[str, Any]) -> str:
        """格式化预订成功消息"""
        return f"""✅ 预订成功!

📅 日期: {reservation['reservationDate']}
⏰ 时间: {reservation['reservationTime']}
👥 人数: {reservation['partySize']}人
🪑 桌台: {reservation['tableNumber']}
📝 预订号: {reservation['externalId']}

💡 温馨提示:
• 请提前10分钟到店
• 如需取消请提前2小时通知
• 超时15分钟将自动取消

期待您的光临!"""

    def _get_help_message(self) -> str:
        """获取帮助消息"""
        return """我可以帮您:

📝 预订: "明天晚上6点,4个人"
🔍 查询: "查一下我的预订"
✏️ 修改: "改到7点"
❌ 取消: "取消预订"

有什么可以帮您?"""
```

---

## 六、实施计划

### 6.1 开发阶段(2周)

**Week 1: 适配器开发**
- Day 1-2: 易订API对接调研,获取API文档和测试账号
- Day 3-4: 实现YiDingAdapter核心功能
- Day 5: 实现数据映射和缓存策略
- Day 6-7: 单元测试和集成测试

**Week 2: Agent开发**
- Day 1-2: 实现ReservationCoordinatorAgent
- Day 3: 意图识别和智能推荐
- Day 4: 企微消息处理集成
- Day 5: 端到端测试
- Day 6-7: Bug修复和优化

### 6.2 测试阶段(1周)

- 功能测试: 所有预订场景覆盖
- 性能测试: 并发预订压力测试
- 容错测试: 易订API异常处理
- 用户测试: 内部员工试用

### 6.3 上线阶段(1周)

- 灰度发布: 先在1个门店试点
- 监控观察: 收集日志和反馈
- 全量上线: 推广到所有门店
- 培训支持: 员工使用培训

---

## 七、监控指标

### 7.1 技术指标

- API调用成功率 > 99.5%
- 平均响应时间 < 500ms
- 缓存命中率 > 80%
- 错误率 < 0.5%

### 7.2 业务指标

- 预订创建成功率
- 预订确认率
- 预订取消率
- 用户满意度

---

## 八、风险与应对

### 8.1 技术风险

**风险1: 易订API不稳定**
- 应对: 实现重试机制和降级策略
- 应对: 本地缓存关键数据

**风险2: 数据同步延迟**
- 应对: 使用Webhook实时推送
- 应对: 定时轮询兜底

**风险3: 并发冲突**
- 应对: 乐观锁+分布式锁
- 应对: 预订确认二次校验

### 8.2 业务风险

**风险1: 用户不习惯AI预订**
- 应对: 保留传统预订方式
- 应对: 提供详细使用指引

**风险2: 预订信息不准确**
- 应对: 多轮对话确认
- 应对: 关键信息人工复核

---

## 九、总结

本方案通过智链OS作为AI智能中间层,连接企业微信与易订预订系统,实现:

✅ **无缝集成**: 不改变易订现有功能,只是增强
✅ **AI驱动**: 自然语言预订,降低操作门槛
✅ **数据聚合**: 跨系统整合预订、订单、会员数据
✅ **智能推荐**: 基于历史数据推荐最佳方案
✅ **主动服务**: 自动提醒、智能叫号、VIP识别

预计开发周期4周,可快速上线验证效果。