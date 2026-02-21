/**
 * 库存数据服务
 * 提供库存的CRUD操作和持久化
 */

import { storageService } from './storage';

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

const STORAGE_KEY = 'inventory';

class InventoryDataService {
  /**
   * 获取所有库存
   */
  getAll(): InventoryItem[] {
    const inventory = storageService.get<InventoryItem[]>(STORAGE_KEY);
    return inventory || [];
  }

  /**
   * 根据ID获取库存
   */
  getById(itemId: string): InventoryItem | null {
    const inventory = this.getAll();
    return inventory.find((item) => item.item_id === itemId) || null;
  }

  /**
   * 创建库存项
   */
  create(item: Omit<InventoryItem, 'item_id' | 'last_updated' | 'status'>): InventoryItem {
    const inventory = this.getAll();
    const status = this.calculateStatus(item.current_stock, item.min_stock);
    const newItem: InventoryItem = {
      ...item,
      item_id: `INV_${Date.now()}`,
      status,
      last_updated: new Date().toISOString(),
    };
    inventory.push(newItem);
    storageService.set(STORAGE_KEY, inventory);
    return newItem;
  }

  /**
   * 更新库存
   */
  update(itemId: string, updates: Partial<InventoryItem>): InventoryItem | null {
    const inventory = this.getAll();
    const index = inventory.findIndex((item) => item.item_id === itemId);
    if (index === -1) return null;

    const updatedItem = {
      ...inventory[index],
      ...updates,
      last_updated: new Date().toISOString(),
    };

    // 重新计算状态
    if (updates.current_stock !== undefined || updates.min_stock !== undefined) {
      updatedItem.status = this.calculateStatus(
        updatedItem.current_stock,
        updatedItem.min_stock
      );
    }

    inventory[index] = updatedItem;
    storageService.set(STORAGE_KEY, inventory);
    return updatedItem;
  }

  /**
   * 删除库存项
   */
  delete(itemId: string): boolean {
    const inventory = this.getAll();
    const filteredInventory = inventory.filter((item) => item.item_id !== itemId);
    if (filteredInventory.length === inventory.length) return false;

    storageService.set(STORAGE_KEY, filteredInventory);
    return true;
  }

  /**
   * 更新库存数量
   */
  updateStock(itemId: string, newStock: number): InventoryItem | null {
    return this.update(itemId, { current_stock: newStock });
  }

  /**
   * 按状态筛选库存
   */
  getByStatus(status: InventoryItem['status']): InventoryItem[] {
    const inventory = this.getAll();
    return inventory.filter((item) => item.status === status);
  }

  /**
   * 按分类筛选库存
   */
  getByCategory(category: string): InventoryItem[] {
    const inventory = this.getAll();
    return inventory.filter((item) => item.category === category);
  }

  /**
   * 获取预警库存
   */
  getAlerts(): InventoryItem[] {
    const inventory = this.getAll();
    return inventory.filter((item) => item.status !== 'normal');
  }

  /**
   * 计算库存状态
   */
  private calculateStatus(
    currentStock: number,
    minStock: number
  ): InventoryItem['status'] {
    if (currentStock === 0) return 'out';
    if (currentStock < minStock * 0.5) return 'critical';
    if (currentStock < minStock) return 'low';
    return 'normal';
  }

  /**
   * 清空所有库存
   */
  clear(): void {
    storageService.remove(STORAGE_KEY);
  }

  /**
   * 初始化示例数据
   */
  initializeSampleData(): void {
    const existingInventory = this.getAll();
    if (existingInventory.length > 0) return;

    const sampleInventory: InventoryItem[] = [
      {
        item_id: 'INV_001',
        name: '大米',
        category: '主食',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
        status: 'normal',
        last_updated: new Date().toISOString(),
      },
      {
        item_id: 'INV_002',
        name: '食用油',
        category: '调料',
        current_stock: 15,
        min_stock: 20,
        max_stock: 50,
        unit: 'L',
        status: 'low',
        last_updated: new Date().toISOString(),
      },
      {
        item_id: 'INV_003',
        name: '鸡蛋',
        category: '食材',
        current_stock: 5,
        min_stock: 30,
        max_stock: 100,
        unit: '盒',
        status: 'critical',
        last_updated: new Date().toISOString(),
      },
      {
        item_id: 'INV_004',
        name: '酱油',
        category: '调料',
        current_stock: 25,
        min_stock: 10,
        max_stock: 40,
        unit: '瓶',
        status: 'normal',
        last_updated: new Date().toISOString(),
      },
      {
        item_id: 'INV_005',
        name: '面粉',
        category: '主食',
        current_stock: 0,
        min_stock: 30,
        max_stock: 80,
        unit: 'kg',
        status: 'out',
        last_updated: new Date().toISOString(),
      },
    ];

    storageService.set(STORAGE_KEY, sampleInventory);
  }
}

export const inventoryDataService = new InventoryDataService();
