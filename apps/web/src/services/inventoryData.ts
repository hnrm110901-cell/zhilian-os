/**
 * 库存数据服务
 * 通过后端 REST API 进行 CRUD（原 localStorage 已移除）
 */

import apiClient from './api';

export interface InventoryItem {
  item_id: string;
  name: string;
  category: string;
  current_stock: number;
  min_stock: number;
  max_stock: number;
  unit: string;
  status: 'normal' | 'low' | 'critical' | 'out';
  last_updated: string;
}

class InventoryDataService {
  private readonly basePath = '/api/v1/inventory';

  async getAll(storeId?: string): Promise<InventoryItem[]> {
    const params = storeId ? `?store_id=${storeId}` : '';
    const res = await apiClient.get<{ data: InventoryItem[] }>(`${this.basePath}${params}`);
    return res.data ?? [];
  }

  async getById(itemId: string): Promise<InventoryItem | null> {
    try {
      const res = await apiClient.get<{ data: InventoryItem }>(`${this.basePath}/${itemId}`);
      return res.data ?? null;
    } catch {
      return null;
    }
  }

  async create(
    item: Omit<InventoryItem, 'item_id' | 'last_updated' | 'status'>
  ): Promise<InventoryItem> {
    const res = await apiClient.post<{ data: InventoryItem }>(this.basePath, item);
    return res.data;
  }

  async update(itemId: string, updates: Partial<InventoryItem>): Promise<InventoryItem | null> {
    try {
      const res = await apiClient.put<{ data: InventoryItem }>(
        `${this.basePath}/${itemId}`,
        updates
      );
      return res.data ?? null;
    } catch {
      return null;
    }
  }

  async delete(itemId: string): Promise<boolean> {
    try {
      await apiClient.delete(`${this.basePath}/${itemId}`);
      return true;
    } catch {
      return false;
    }
  }

  async updateStock(itemId: string, newStock: number): Promise<InventoryItem | null> {
    return this.update(itemId, { current_stock: newStock });
  }

  async getByStatus(status: InventoryItem['status']): Promise<InventoryItem[]> {
    const res = await apiClient.get<{ data: InventoryItem[] }>(
      `${this.basePath}?status=${status}`
    );
    return res.data ?? [];
  }

  async getByCategory(category: string): Promise<InventoryItem[]> {
    const res = await apiClient.get<{ data: InventoryItem[] }>(
      `${this.basePath}?category=${encodeURIComponent(category)}`
    );
    return res.data ?? [];
  }

  async getAlerts(): Promise<InventoryItem[]> {
    const res = await apiClient.get<{ data: InventoryItem[] }>(`${this.basePath}/alerts`);
    return res.data ?? [];
  }
}

export const inventoryDataService = new InventoryDataService();
