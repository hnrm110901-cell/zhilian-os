import { describe, it, expect, vi, beforeEach } from 'vitest';
import { orderDataService, type Order } from './orderData';
import apiClient from './api';

vi.mock('./api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockedClient = vi.mocked(apiClient);

const makeOrder = (overrides: Partial<Order> = {}): Order => ({
  order_id: 'ORD_001',
  store_id: 'store_001',
  table_number: 'A01',
  status: 'pending',
  items: [],
  total_amount: 1000,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  ...overrides,
});

describe('OrderDataService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getAll', () => {
    it('should call GET /api/v1/orders without params', async () => {
      const orders = [makeOrder()];
      mockedClient.get.mockResolvedValue({ data: orders });

      const result = await orderDataService.getAll();
      expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/orders');
      expect(result).toEqual(orders);
    });

    it('should include store_id query param when provided', async () => {
      mockedClient.get.mockResolvedValue({ data: [] });

      await orderDataService.getAll('store_001');
      expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/orders?store_id=store_001');
    });

    it('should return empty array when response has no data', async () => {
      mockedClient.get.mockResolvedValue({ data: undefined });

      const result = await orderDataService.getAll();
      expect(result).toEqual([]);
    });
  });

  describe('getById', () => {
    it('should call GET /api/v1/orders/:id and return order', async () => {
      const order = makeOrder();
      mockedClient.get.mockResolvedValue({ data: order });

      const result = await orderDataService.getById('ORD_001');
      expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/orders/ORD_001');
      expect(result).toEqual(order);
    });

    it('should return null when request fails', async () => {
      mockedClient.get.mockRejectedValue(new Error('Not found'));

      const result = await orderDataService.getById('non-existent');
      expect(result).toBeNull();
    });
  });

  describe('create', () => {
    it('should call POST /api/v1/orders and return created order', async () => {
      const order = makeOrder();
      mockedClient.post.mockResolvedValue({ data: order });

      const result = await orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });
      expect(mockedClient.post).toHaveBeenCalledWith('/api/v1/orders', expect.objectContaining({
        store_id: 'store_001',
        table_number: 'A01',
      }));
      expect(result).toEqual(order);
    });
  });

  describe('update', () => {
    it('should call PUT /api/v1/orders/:id and return updated order', async () => {
      const updated = makeOrder({ table_number: 'B05' });
      mockedClient.put.mockResolvedValue({ data: updated });

      const result = await orderDataService.update('ORD_001', { table_number: 'B05' });
      expect(mockedClient.put).toHaveBeenCalledWith('/api/v1/orders/ORD_001', { table_number: 'B05' });
      expect(result).toEqual(updated);
    });

    it('should return null when request fails', async () => {
      mockedClient.put.mockRejectedValue(new Error('Not found'));

      const result = await orderDataService.update('non-existent', { status: 'completed' });
      expect(result).toBeNull();
    });
  });

  describe('delete', () => {
    it('should call DELETE /api/v1/orders/:id and return true', async () => {
      mockedClient.delete.mockResolvedValue({});

      const result = await orderDataService.delete('ORD_001');
      expect(mockedClient.delete).toHaveBeenCalledWith('/api/v1/orders/ORD_001');
      expect(result).toBe(true);
    });

    it('should return false when request fails', async () => {
      mockedClient.delete.mockRejectedValue(new Error('Not found'));

      const result = await orderDataService.delete('non-existent');
      expect(result).toBe(false);
    });
  });

  describe('updateStatus', () => {
    it('should call PUT to update status field', async () => {
      const updated = makeOrder({ status: 'processing' });
      mockedClient.put.mockResolvedValue({ data: updated });

      const result = await orderDataService.updateStatus('ORD_001', 'processing');
      expect(mockedClient.put).toHaveBeenCalledWith('/api/v1/orders/ORD_001', { status: 'processing' });
      expect(result?.status).toBe('processing');
    });
  });

  describe('getByStatus', () => {
    it('should call GET with status query param', async () => {
      const orders = [makeOrder({ status: 'pending' })];
      mockedClient.get.mockResolvedValue({ data: orders });

      const result = await orderDataService.getByStatus('pending');
      expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/orders?status=pending');
      expect(result).toEqual(orders);
    });
  });

  describe('getByStore', () => {
    it('should call GET with store_id query param', async () => {
      const orders = [makeOrder()];
      mockedClient.get.mockResolvedValue({ data: orders });

      const result = await orderDataService.getByStore('store_001');
      expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/orders?store_id=store_001');
      expect(result).toEqual(orders);
    });
  });
});
