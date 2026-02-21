/**
 * 订单数据服务
 * 提供订单的CRUD操作和持久化
 */

import { storageService } from './storage';

export interface OrderItem {
  item_id: string;
  name: string;
  quantity: number;
  price: number;
}

export interface Order {
  order_id: string;
  store_id: string;
  table_number: string;
  status: 'pending' | 'processing' | 'completed' | 'cancelled';
  items: OrderItem[];
  total_amount: number;
  created_at: string;
  updated_at: string;
}

const STORAGE_KEY = 'orders';

class OrderDataService {
  /**
   * 获取所有订单
   */
  getAll(): Order[] {
    const orders = storageService.get<Order[]>(STORAGE_KEY);
    return orders || [];
  }

  /**
   * 根据ID获取订单
   */
  getById(orderId: string): Order | null {
    const orders = this.getAll();
    return orders.find((order) => order.order_id === orderId) || null;
  }

  /**
   * 创建订单
   */
  create(order: Omit<Order, 'order_id' | 'created_at' | 'updated_at'>): Order {
    const orders = this.getAll();
    const newOrder: Order = {
      ...order,
      order_id: `ORD_${Date.now()}`,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    orders.unshift(newOrder);
    storageService.set(STORAGE_KEY, orders);
    return newOrder;
  }

  /**
   * 更新订单
   */
  update(orderId: string, updates: Partial<Order>): Order | null {
    const orders = this.getAll();
    const index = orders.findIndex((order) => order.order_id === orderId);
    if (index === -1) return null;

    orders[index] = {
      ...orders[index],
      ...updates,
      updated_at: new Date().toISOString(),
    };
    storageService.set(STORAGE_KEY, orders);
    return orders[index];
  }

  /**
   * 删除订单
   */
  delete(orderId: string): boolean {
    const orders = this.getAll();
    const filteredOrders = orders.filter((order) => order.order_id !== orderId);
    if (filteredOrders.length === orders.length) return false;

    storageService.set(STORAGE_KEY, filteredOrders);
    return true;
  }

  /**
   * 更新订单状态
   */
  updateStatus(
    orderId: string,
    status: Order['status']
  ): Order | null {
    return this.update(orderId, { status });
  }

  /**
   * 按状态筛选订单
   */
  getByStatus(status: Order['status']): Order[] {
    const orders = this.getAll();
    return orders.filter((order) => order.status === status);
  }

  /**
   * 按门店筛选订单
   */
  getByStore(storeId: string): Order[] {
    const orders = this.getAll();
    return orders.filter((order) => order.store_id === storeId);
  }

  /**
   * 清空所有订单
   */
  clear(): void {
    storageService.remove(STORAGE_KEY);
  }

  /**
   * 初始化示例数据
   */
  initializeSampleData(): void {
    const existingOrders = this.getAll();
    if (existingOrders.length > 0) return;

    const sampleOrders: Order[] = [
      {
        order_id: 'ORD_001',
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [
          {
            item_id: 'item_001',
            name: '宫保鸡丁',
            quantity: 1,
            price: 3800,
          },
          {
            item_id: 'item_002',
            name: '米饭',
            quantity: 2,
            price: 200,
          },
        ],
        total_amount: 4200,
        created_at: new Date(Date.now() - 3600000).toISOString(),
        updated_at: new Date(Date.now() - 3600000).toISOString(),
      },
      {
        order_id: 'ORD_002',
        store_id: 'store_001',
        table_number: 'B05',
        status: 'processing',
        items: [
          {
            item_id: 'item_003',
            name: '麻婆豆腐',
            quantity: 1,
            price: 2800,
          },
        ],
        total_amount: 2800,
        created_at: new Date(Date.now() - 1800000).toISOString(),
        updated_at: new Date(Date.now() - 900000).toISOString(),
      },
      {
        order_id: 'ORD_003',
        store_id: 'store_001',
        table_number: 'C03',
        status: 'completed',
        items: [
          {
            item_id: 'item_004',
            name: '红烧肉',
            quantity: 1,
            price: 4500,
          },
          {
            item_id: 'item_005',
            name: '青菜',
            quantity: 1,
            price: 1500,
          },
        ],
        total_amount: 6000,
        created_at: new Date(Date.now() - 7200000).toISOString(),
        updated_at: new Date(Date.now() - 3600000).toISOString(),
      },
    ];

    storageService.set(STORAGE_KEY, sampleOrders);
  }
}

export const orderDataService = new OrderDataService();
