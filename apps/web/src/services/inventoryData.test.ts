import { describe, it, expect, vi, beforeEach } from 'vitest';
import { inventoryDataService, type InventoryItem } from './inventoryData';
import apiClient from './api';

vi.mock('./api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const makeItem = (overrides: Partial<InventoryItem> = {}): InventoryItem => ({
  item_id: 'INV_001',
  name: '大米',
  category: '主食',
  current_stock: 50,
  min_stock: 20,
  max_stock: 100,
  unit: 'kg',
  status: 'normal',
  last_updated: '2024-01-01T00:00:00Z',
  ...overrides,
});

describe('InventoryDataService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getAll', () => {
    it('should return items from the API', async () => {
      const items = [makeItem(), makeItem({ item_id: 'INV_002', name: 'Item 2' })];
      vi.mocked(apiClient.get).mockResolvedValue({ data: items });

      const result = await inventoryDataService.getAll();
      expect(result).toEqual(items);
      expect(apiClient.get).toHaveBeenCalledWith('/api/v1/inventory');
    });

    it('should pass storeId as query param', async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ data: [] });

      await inventoryDataService.getAll('store_1');
      expect(apiClient.get).toHaveBeenCalledWith('/api/v1/inventory?store_id=store_1');
    });

    it('should return empty array when data is null', async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ data: null });

      const result = await inventoryDataService.getAll();
      expect(result).toEqual([]);
    });
  });

  describe('getById', () => {
    it('should return item by id', async () => {
      const item = makeItem();
      vi.mocked(apiClient.get).mockResolvedValue({ data: item });

      const result = await inventoryDataService.getById('INV_001');
      expect(result).toEqual(item);
      expect(apiClient.get).toHaveBeenCalledWith('/api/v1/inventory/INV_001');
    });

    it('should return null on error', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('Not found'));

      const result = await inventoryDataService.getById('non-existent');
      expect(result).toBeNull();
    });
  });

  describe('create', () => {
    it('should post to the API and return the created item', async () => {
      const newItem = makeItem();
      vi.mocked(apiClient.post).mockResolvedValue({ data: newItem });

      const payload = {
        name: '大米',
        category: '主食',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      };
      const result = await inventoryDataService.create(payload);
      expect(result).toEqual(newItem);
      expect(apiClient.post).toHaveBeenCalledWith('/api/v1/inventory', payload);
    });
  });

  describe('update', () => {
    it('should put to the API and return the updated item', async () => {
      const updated = makeItem({ current_stock: 75 });
      vi.mocked(apiClient.put).mockResolvedValue({ data: updated });

      const result = await inventoryDataService.update('INV_001', { current_stock: 75 });
      expect(result).toEqual(updated);
      expect(apiClient.put).toHaveBeenCalledWith('/api/v1/inventory/INV_001', { current_stock: 75 });
    });

    it('should return null on error', async () => {
      vi.mocked(apiClient.put).mockRejectedValue(new Error('Not found'));

      const result = await inventoryDataService.update('non-existent', { current_stock: 100 });
      expect(result).toBeNull();
    });
  });

  describe('delete', () => {
    it('should call delete API and return true', async () => {
      vi.mocked(apiClient.delete).mockResolvedValue(undefined);

      const result = await inventoryDataService.delete('INV_001');
      expect(result).toBe(true);
      expect(apiClient.delete).toHaveBeenCalledWith('/api/v1/inventory/INV_001');
    });

    it('should return false on error', async () => {
      vi.mocked(apiClient.delete).mockRejectedValue(new Error('Not found'));

      const result = await inventoryDataService.delete('non-existent');
      expect(result).toBe(false);
    });
  });

  describe('updateStock', () => {
    it('should delegate to update with current_stock', async () => {
      const updated = makeItem({ current_stock: 0, status: 'out' });
      vi.mocked(apiClient.put).mockResolvedValue({ data: updated });

      const result = await inventoryDataService.updateStock('INV_001', 0);
      expect(result).toEqual(updated);
      expect(apiClient.put).toHaveBeenCalledWith('/api/v1/inventory/INV_001', { current_stock: 0 });
    });
  });

  describe('getByStatus', () => {
    it('should filter by status via query param', async () => {
      const items = [makeItem({ status: 'low' })];
      vi.mocked(apiClient.get).mockResolvedValue({ data: items });

      const result = await inventoryDataService.getByStatus('low');
      expect(result).toEqual(items);
      expect(apiClient.get).toHaveBeenCalledWith('/api/v1/inventory?status=low');
    });
  });

  describe('getByCategory', () => {
    it('should filter by category via URL-encoded query param', async () => {
      const items = [makeItem({ category: '主食' })];
      vi.mocked(apiClient.get).mockResolvedValue({ data: items });

      const result = await inventoryDataService.getByCategory('主食');
      expect(result).toEqual(items);
      expect(apiClient.get).toHaveBeenCalledWith(
        `/api/v1/inventory?category=${encodeURIComponent('主食')}`
      );
    });
  });

  describe('getAlerts', () => {
    it('should fetch the alerts endpoint', async () => {
      const alerts = [
        makeItem({ status: 'low' }),
        makeItem({ item_id: 'INV_002', status: 'critical' }),
      ];
      vi.mocked(apiClient.get).mockResolvedValue({ data: alerts });

      const result = await inventoryDataService.getAlerts();
      expect(result).toEqual(alerts);
      expect(apiClient.get).toHaveBeenCalledWith('/api/v1/inventory/alerts');
    });
  });
});
