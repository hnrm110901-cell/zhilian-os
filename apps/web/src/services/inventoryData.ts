/**
 * 库存数据服务
 * 对齐 api-gateway /api/v1/inventory 真实接口
 */

import apiClient from './api';

export type InventoryStatus = 'normal' | 'low' | 'critical' | 'out_of_stock';

export interface InventoryItem {
  id: string;
  store_id: string;
  name: string;
  category: string | null;
  unit: string | null;
  current_quantity: number;
  min_quantity: number;
  max_quantity: number | null;
  unit_cost: number | null;
  status: InventoryStatus | null;
}

export interface CreateInventoryItemPayload {
  id: string;
  store_id: string;
  name: string;
  category?: string;
  unit?: string;
  current_quantity: number;
  min_quantity: number;
  max_quantity?: number;
  unit_cost?: number;
}

export interface UpdateInventoryItemPayload {
  name?: string;
  category?: string;
  unit?: string;
  current_quantity?: number;
  min_quantity?: number;
  max_quantity?: number;
  unit_cost?: number;
  status?: InventoryStatus;
}

export interface InventoryTransaction {
  id: string;
  transaction_type: 'purchase' | 'usage' | 'waste' | 'adjustment' | 'transfer';
  quantity: number;
  quantity_before: number;
  quantity_after: number;
  notes: string | null;
  performed_by: string | null;
  transaction_time: string | null;
}

export interface InventoryStats {
  total_items: number;
  total_value: number;
  category_distribution: Record<string, number>;
  status_distribution: Record<string, number>;
  alert_items: Array<{
    id: string;
    name: string;
    status: InventoryStatus;
    current_quantity: number;
    min_quantity: number;
    unit: string | null;
  }>;
}

export interface BatchRestockResult {
  restocked: number;
  items: Array<{
    id: string;
    name: string;
    restocked_qty: number;
    new_qty: number;
  }>;
}

class InventoryDataService {
  private readonly basePath = '/api/v1/inventory';

  private unwrap<T>(value: T | { data: T } | null | undefined): T | undefined {
    if (value && typeof value === 'object' && 'data' in value) {
      return (value as { data: T }).data;
    }
    return value ?? undefined;
  }

  async getAll(storeId?: string, lowStockOnly: boolean = false): Promise<InventoryItem[]> {
    const resolvedStoreId = storeId || localStorage.getItem('store_id') || 'STORE001';
    const params = new URLSearchParams({ store_id: resolvedStoreId });
    if (lowStockOnly) {
      params.append('low_stock_only', 'true');
    }
    const res = await apiClient.get<InventoryItem[] | { data: InventoryItem[] }>(
      `${this.basePath}?${params.toString()}`
    );
    return this.unwrap(res) ?? [];
  }

  async getById(itemId: string): Promise<InventoryItem | null> {
    try {
      const res = await apiClient.get<InventoryItem | { data: InventoryItem }>(
        `${this.basePath}/${itemId}`
      );
      return this.unwrap(res) ?? null;
    } catch {
      return null;
    }
  }

  async create(item: CreateInventoryItemPayload): Promise<InventoryItem> {
    const res = await apiClient.post<InventoryItem | { data: InventoryItem }>(this.basePath, item);
    return this.unwrap(res)!;
  }

  async update(itemId: string, updates: UpdateInventoryItemPayload): Promise<InventoryItem | null> {
    try {
      const res = await apiClient.patch<InventoryItem | { data: InventoryItem }>(
        `${this.basePath}/${itemId}`,
        updates
      );
      return this.unwrap(res) ?? null;
    } catch {
      return null;
    }
  }

  async recordTransaction(
    itemId: string,
    payload: { transaction_type: InventoryTransaction['transaction_type']; quantity: number; notes?: string }
  ): Promise<{ success: boolean; new_quantity: number }> {
    return apiClient.post<{ success: boolean; new_quantity: number }>(
      `${this.basePath}/${itemId}/transaction`,
      payload
    );
  }

  async getTransactions(itemId: string, limit: number = 50): Promise<InventoryTransaction[]> {
    const res = await apiClient.get<InventoryTransaction[] | { data: InventoryTransaction[] }>(
      `${this.basePath}/${itemId}/transactions?limit=${limit}`
    );
    return this.unwrap(res) ?? [];
  }

  async getStats(storeId: string): Promise<InventoryStats> {
    return apiClient.get<InventoryStats>(`/api/v1/inventory-stats?store_id=${encodeURIComponent(storeId)}`);
  }

  async batchRestock(storeId: string, itemIds?: string[] | null): Promise<BatchRestockResult> {
    return apiClient.post<BatchRestockResult>(
      `/api/v1/inventory/batch-restock?store_id=${encodeURIComponent(storeId)}`,
      { item_ids: itemIds ?? null }
    );
  }

  async getAlertsByStore(storeId: string): Promise<InventoryItem[]> {
    const items = await this.getAll(storeId);
    return items.filter((item) => item.status && item.status !== 'normal');
  }
}

export const inventoryDataService = new InventoryDataService();
