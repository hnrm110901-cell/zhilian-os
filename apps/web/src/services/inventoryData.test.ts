import { beforeEach, describe, expect, it, vi } from 'vitest';
import { inventoryDataService, type InventoryItem } from './inventoryData';
import apiClient from './api';

vi.mock('./api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

const makeItem = (overrides: Partial<InventoryItem> = {}): InventoryItem => ({
  id: 'INV_001',
  store_id: 'STORE001',
  name: '大米',
  category: '主食',
  unit: 'kg',
  current_quantity: 50,
  min_quantity: 20,
  max_quantity: 100,
  unit_cost: 1000,
  status: 'normal',
  ...overrides,
});

describe('InventoryDataService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getAll should query real inventory endpoint with store_id', async () => {
    const items = [makeItem()];
    vi.mocked(apiClient.get).mockResolvedValue(items);

    const result = await inventoryDataService.getAll('STORE001');
    expect(result).toEqual(items);
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/inventory?store_id=STORE001');
  });

  it('getAll should support wrapped data response', async () => {
    const items = [makeItem()];
    vi.mocked(apiClient.get).mockResolvedValue({ data: items });

    const result = await inventoryDataService.getAll('STORE001');
    expect(result).toEqual(items);
  });

  it('getById should return item and fallback null on error', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(makeItem());
    const found = await inventoryDataService.getById('INV_001');
    expect(found?.id).toBe('INV_001');

    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('not found'));
    const missing = await inventoryDataService.getById('INV_404');
    expect(missing).toBeNull();
  });

  it('create should post to inventory endpoint', async () => {
    const created = makeItem({ id: 'INV_002' });
    vi.mocked(apiClient.post).mockResolvedValue(created);

    const payload = {
      id: 'INV_002',
      store_id: 'STORE001',
      name: '牛肉',
      current_quantity: 30,
      min_quantity: 10,
      category: '肉类',
      unit: 'kg',
      max_quantity: 80,
      unit_cost: 3200,
    };
    const result = await inventoryDataService.create(payload);

    expect(result).toEqual(created);
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/inventory', payload);
  });

  it('update should patch inventory item', async () => {
    const updated = makeItem({ current_quantity: 60 });
    vi.mocked(apiClient.patch).mockResolvedValue(updated);

    const result = await inventoryDataService.update('INV_001', { current_quantity: 60 });
    expect(result?.current_quantity).toBe(60);
    expect(apiClient.patch).toHaveBeenCalledWith('/api/v1/inventory/INV_001', { current_quantity: 60 });
  });

  it('recordTransaction should call transaction endpoint', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ success: true, new_quantity: 35 });

    const result = await inventoryDataService.recordTransaction('INV_001', {
      transaction_type: 'usage',
      quantity: 15,
      notes: '日常消耗',
    });

    expect(result).toEqual({ success: true, new_quantity: 35 });
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/inventory/INV_001/transaction', {
      transaction_type: 'usage',
      quantity: 15,
      notes: '日常消耗',
    });
  });

  it('getTransactions should call transaction history endpoint', async () => {
    const history = [
      {
        id: '1',
        transaction_type: 'usage',
        quantity: 5,
        quantity_before: 50,
        quantity_after: 45,
        notes: null,
        performed_by: 'u1',
        transaction_time: '2026-03-08T07:00:00',
      },
    ];
    vi.mocked(apiClient.get).mockResolvedValue(history);

    const result = await inventoryDataService.getTransactions('INV_001', 20);
    expect(result).toEqual(history);
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/inventory/INV_001/transactions?limit=20');
  });

  it('getStats should call inventory-stats endpoint', async () => {
    const stats = {
      total_items: 8,
      total_value: 120000,
      category_distribution: { 主食: 3 },
      status_distribution: { normal: 6, low: 1, critical: 1, out_of_stock: 0 },
      alert_items: [],
    };
    vi.mocked(apiClient.get).mockResolvedValue(stats);

    const result = await inventoryDataService.getStats('STORE001');
    expect(result.total_items).toBe(8);
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/inventory-stats?store_id=STORE001');
  });

  it('batchRestock should post with nullable item_ids', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ restocked: 2, items: [] });

    const result = await inventoryDataService.batchRestock('STORE001', null);
    expect(result.restocked).toBe(2);
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/inventory/batch-restock?store_id=STORE001',
      { item_ids: null }
    );
  });

  it('getAlertsByStore should filter non-normal items', async () => {
    vi.mocked(apiClient.get).mockResolvedValue([
      makeItem({ id: 'INV_001', status: 'normal' }),
      makeItem({ id: 'INV_002', status: 'low' }),
      makeItem({ id: 'INV_003', status: 'critical' }),
    ]);

    const result = await inventoryDataService.getAlertsByStore('STORE001');
    expect(result.map((i) => i.id)).toEqual(['INV_002', 'INV_003']);
  });
});
