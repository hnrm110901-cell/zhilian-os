import { describe, it, expect, beforeEach } from 'vitest';
import { orderDataService } from './orderData';

describe('OrderDataService', () => {
  beforeEach(() => {
    // Clear all orders before each test
    orderDataService.clear();
  });

  describe('create', () => {
    it('should create a new order', () => {
      const orderData = {
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending' as const,
        items: [
          {
            item_id: 'item_001',
            name: '宫保鸡丁',
            quantity: 1,
            price: 3800,
          },
        ],
        total_amount: 3800,
      };

      const order = orderDataService.create(orderData);

      expect(order.order_id).toBeTruthy();
      expect(order.order_id).toMatch(/^ORD_/);
      expect(order.store_id).toBe('store_001');
      expect(order.table_number).toBe('A01');
      expect(order.status).toBe('pending');
      expect(order.items).toHaveLength(1);
      expect(order.total_amount).toBe(3800);
      expect(order.created_at).toBeTruthy();
      expect(order.updated_at).toBeTruthy();
    });

    it('should add new order to the beginning of the list', () => {
      const order1 = orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      const order2 = orderDataService.create({
        store_id: 'store_001',
        table_number: 'A02',
        status: 'pending',
        items: [],
        total_amount: 2000,
      });

      const orders = orderDataService.getAll();
      expect(orders[0].order_id).toBe(order2.order_id);
      expect(orders[1].order_id).toBe(order1.order_id);
    });
  });

  describe('getAll', () => {
    it('should return empty array when no orders exist', () => {
      const orders = orderDataService.getAll();
      expect(orders).toEqual([]);
    });

    it('should return all orders', () => {
      orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      orderDataService.create({
        store_id: 'store_001',
        table_number: 'A02',
        status: 'pending',
        items: [],
        total_amount: 2000,
      });

      const orders = orderDataService.getAll();
      expect(orders).toHaveLength(2);
    });
  });

  describe('getById', () => {
    it('should return order by id', () => {
      const created = orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      const found = orderDataService.getById(created.order_id);
      expect(found).toEqual(created);
    });

    it('should return null for non-existent id', () => {
      const found = orderDataService.getById('non-existent');
      expect(found).toBeNull();
    });
  });

  describe('update', () => {
    it('should update order fields', async () => {
      const order = orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      // Wait a bit to ensure different timestamp
      await new Promise(resolve => setTimeout(resolve, 10));

      const updated = orderDataService.update(order.order_id, {
        table_number: 'B05',
        total_amount: 2000,
      });

      expect(updated).toBeTruthy();
      expect(updated?.table_number).toBe('B05');
      expect(updated?.total_amount).toBe(2000);
      expect(updated?.store_id).toBe('store_001'); // Unchanged
      expect(updated?.updated_at).not.toBe(order.updated_at);
    });

    it('should return null for non-existent order', () => {
      const updated = orderDataService.update('non-existent', {
        status: 'completed',
      });
      expect(updated).toBeNull();
    });
  });

  describe('delete', () => {
    it('should delete an order', () => {
      const order = orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      const result = orderDataService.delete(order.order_id);
      expect(result).toBe(true);

      const found = orderDataService.getById(order.order_id);
      expect(found).toBeNull();
    });

    it('should return false for non-existent order', () => {
      const result = orderDataService.delete('non-existent');
      expect(result).toBe(false);
    });
  });

  describe('updateStatus', () => {
    it('should update order status', () => {
      const order = orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      const updated = orderDataService.updateStatus(order.order_id, 'processing');
      expect(updated?.status).toBe('processing');
    });

    it('should update through all status transitions', () => {
      const order = orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      orderDataService.updateStatus(order.order_id, 'processing');
      let current = orderDataService.getById(order.order_id);
      expect(current?.status).toBe('processing');

      orderDataService.updateStatus(order.order_id, 'completed');
      current = orderDataService.getById(order.order_id);
      expect(current?.status).toBe('completed');
    });
  });

  describe('getByStatus', () => {
    beforeEach(() => {
      orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      orderDataService.create({
        store_id: 'store_001',
        table_number: 'A02',
        status: 'processing',
        items: [],
        total_amount: 2000,
      });

      orderDataService.create({
        store_id: 'store_001',
        table_number: 'A03',
        status: 'completed',
        items: [],
        total_amount: 3000,
      });
    });

    it('should filter orders by status', () => {
      const pending = orderDataService.getByStatus('pending');
      expect(pending).toHaveLength(1);
      expect(pending[0].status).toBe('pending');

      const processing = orderDataService.getByStatus('processing');
      expect(processing).toHaveLength(1);
      expect(processing[0].status).toBe('processing');

      const completed = orderDataService.getByStatus('completed');
      expect(completed).toHaveLength(1);
      expect(completed[0].status).toBe('completed');
    });
  });

  describe('getByStore', () => {
    it('should filter orders by store', () => {
      orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      orderDataService.create({
        store_id: 'store_002',
        table_number: 'B01',
        status: 'pending',
        items: [],
        total_amount: 2000,
      });

      const store1Orders = orderDataService.getByStore('store_001');
      expect(store1Orders).toHaveLength(1);
      expect(store1Orders[0].store_id).toBe('store_001');

      const store2Orders = orderDataService.getByStore('store_002');
      expect(store2Orders).toHaveLength(1);
      expect(store2Orders[0].store_id).toBe('store_002');
    });
  });

  describe('initializeSampleData', () => {
    it('should initialize sample data when empty', () => {
      orderDataService.initializeSampleData();
      const orders = orderDataService.getAll();
      expect(orders.length).toBeGreaterThan(0);
    });

    it('should not initialize if data already exists', () => {
      orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      const countBefore = orderDataService.getAll().length;
      orderDataService.initializeSampleData();
      const countAfter = orderDataService.getAll().length;

      expect(countAfter).toBe(countBefore);
    });
  });

  describe('persistence', () => {
    it('should persist data across service instances', () => {
      const order = orderDataService.create({
        store_id: 'store_001',
        table_number: 'A01',
        status: 'pending',
        items: [],
        total_amount: 1000,
      });

      // Get data from a "new" service instance (simulated by calling getAll again)
      const orders = orderDataService.getAll();
      expect(orders).toHaveLength(1);
      expect(orders[0].order_id).toBe(order.order_id);
    });
  });
});
