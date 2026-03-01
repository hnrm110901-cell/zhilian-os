/**
 * 订单数据服务
 * 通过后端 REST API 进行 CRUD（原 localStorage 已移除）
 */

import apiClient from './api';

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

class OrderDataService {
  private readonly basePath = '/api/v1/orders';

  async getAll(storeId?: string): Promise<Order[]> {
    const params = storeId ? `?store_id=${storeId}` : '';
    const res = await apiClient.get<{ data: Order[] }>(`${this.basePath}${params}`);
    return res.data ?? [];
  }

  async getById(orderId: string): Promise<Order | null> {
    try {
      const res = await apiClient.get<{ data: Order }>(`${this.basePath}/${orderId}`);
      return res.data ?? null;
    } catch {
      return null;
    }
  }

  async create(order: Omit<Order, 'order_id' | 'created_at' | 'updated_at'>): Promise<Order> {
    const res = await apiClient.post<{ data: Order }>(this.basePath, order);
    return res.data;
  }

  async update(orderId: string, updates: Partial<Order>): Promise<Order | null> {
    try {
      const res = await apiClient.put<{ data: Order }>(`${this.basePath}/${orderId}`, updates);
      return res.data ?? null;
    } catch {
      return null;
    }
  }

  async delete(orderId: string): Promise<boolean> {
    try {
      await apiClient.delete(`${this.basePath}/${orderId}`);
      return true;
    } catch {
      return false;
    }
  }

  async updateStatus(orderId: string, status: Order['status']): Promise<Order | null> {
    return this.update(orderId, { status });
  }

  async getByStatus(status: Order['status']): Promise<Order[]> {
    const res = await apiClient.get<{ data: Order[] }>(`${this.basePath}?status=${status}`);
    return res.data ?? [];
  }

  async getByStore(storeId: string): Promise<Order[]> {
    const res = await apiClient.get<{ data: Order[] }>(
      `${this.basePath}?store_id=${encodeURIComponent(storeId)}`
    );
    return res.data ?? [];
  }
}

export const orderDataService = new OrderDataService();
