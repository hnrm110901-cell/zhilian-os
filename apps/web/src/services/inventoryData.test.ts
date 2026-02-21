import { describe, it, expect, beforeEach } from 'vitest';
import { inventoryDataService } from './inventoryData';

describe('InventoryDataService', () => {
  beforeEach(() => {
    // Clear all inventory before each test
    inventoryDataService.clear();
  });

  describe('create', () => {
    it('should create a new inventory item', () => {
      const itemData = {
        name: '大米',
        category: '主食',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      };

      const item = inventoryDataService.create(itemData);

      expect(item.item_id).toBeTruthy();
      expect(item.item_id).toMatch(/^INV_/);
      expect(item.name).toBe('大米');
      expect(item.category).toBe('主食');
      expect(item.current_stock).toBe(50);
      expect(item.status).toBe('normal');
      expect(item.last_updated).toBeTruthy();
    });

    it('should calculate status correctly on creation', () => {
      // Normal status
      const normal = inventoryDataService.create({
        name: 'Item 1',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });
      expect(normal.status).toBe('normal');

      // Low status
      const low = inventoryDataService.create({
        name: 'Item 2',
        category: 'Test',
        current_stock: 15,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });
      expect(low.status).toBe('low');

      // Critical status
      const critical = inventoryDataService.create({
        name: 'Item 3',
        category: 'Test',
        current_stock: 5,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });
      expect(critical.status).toBe('critical');

      // Out status
      const out = inventoryDataService.create({
        name: 'Item 4',
        category: 'Test',
        current_stock: 0,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });
      expect(out.status).toBe('out');
    });
  });

  describe('getAll', () => {
    it('should return empty array when no items exist', () => {
      const items = inventoryDataService.getAll();
      expect(items).toEqual([]);
    });

    it('should return all inventory items', () => {
      inventoryDataService.create({
        name: 'Item 1',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      inventoryDataService.create({
        name: 'Item 2',
        category: 'Test',
        current_stock: 30,
        min_stock: 10,
        max_stock: 50,
        unit: 'L',
      });

      const items = inventoryDataService.getAll();
      expect(items).toHaveLength(2);
    });
  });

  describe('getById', () => {
    it('should return item by id', () => {
      const created = inventoryDataService.create({
        name: 'Test Item',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      const found = inventoryDataService.getById(created.item_id);
      expect(found).toEqual(created);
    });

    it('should return null for non-existent id', () => {
      const found = inventoryDataService.getById('non-existent');
      expect(found).toBeNull();
    });
  });

  describe('update', () => {
    it('should update item fields', async () => {
      const item = inventoryDataService.create({
        name: 'Test Item',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      // Wait a bit to ensure different timestamp
      await new Promise(resolve => setTimeout(resolve, 10));

      const updated = inventoryDataService.update(item.item_id, {
        name: 'Updated Item',
        current_stock: 75,
      });

      expect(updated).toBeTruthy();
      expect(updated?.name).toBe('Updated Item');
      expect(updated?.current_stock).toBe(75);
      expect(updated?.category).toBe('Test'); // Unchanged
      expect(updated?.last_updated).not.toBe(item.last_updated);
    });

    it('should recalculate status when stock changes', () => {
      const item = inventoryDataService.create({
        name: 'Test Item',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      expect(item.status).toBe('normal');

      // Update to low stock
      const updated1 = inventoryDataService.update(item.item_id, {
        current_stock: 15,
      });
      expect(updated1?.status).toBe('low');

      // Update to critical stock
      const updated2 = inventoryDataService.update(item.item_id, {
        current_stock: 5,
      });
      expect(updated2?.status).toBe('critical');

      // Update to out of stock
      const updated3 = inventoryDataService.update(item.item_id, {
        current_stock: 0,
      });
      expect(updated3?.status).toBe('out');
    });

    it('should return null for non-existent item', () => {
      const updated = inventoryDataService.update('non-existent', {
        current_stock: 100,
      });
      expect(updated).toBeNull();
    });
  });

  describe('delete', () => {
    it('should delete an item', () => {
      const item = inventoryDataService.create({
        name: 'Test Item',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      const result = inventoryDataService.delete(item.item_id);
      expect(result).toBe(true);

      const found = inventoryDataService.getById(item.item_id);
      expect(found).toBeNull();
    });

    it('should return false for non-existent item', () => {
      const result = inventoryDataService.delete('non-existent');
      expect(result).toBe(false);
    });
  });

  describe('updateStock', () => {
    it('should update stock quantity', () => {
      const item = inventoryDataService.create({
        name: 'Test Item',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      const updated = inventoryDataService.updateStock(item.item_id, 75);
      expect(updated?.current_stock).toBe(75);
    });

    it('should recalculate status when updating stock', () => {
      const item = inventoryDataService.create({
        name: 'Test Item',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      const updated = inventoryDataService.updateStock(item.item_id, 0);
      expect(updated?.status).toBe('out');
    });
  });

  describe('getByStatus', () => {
    beforeEach(() => {
      inventoryDataService.create({
        name: 'Normal Item',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      inventoryDataService.create({
        name: 'Low Item',
        category: 'Test',
        current_stock: 15,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      inventoryDataService.create({
        name: 'Critical Item',
        category: 'Test',
        current_stock: 5,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      inventoryDataService.create({
        name: 'Out Item',
        category: 'Test',
        current_stock: 0,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });
    });

    it('should filter items by status', () => {
      const normal = inventoryDataService.getByStatus('normal');
      expect(normal).toHaveLength(1);
      expect(normal[0].status).toBe('normal');

      const low = inventoryDataService.getByStatus('low');
      expect(low).toHaveLength(1);
      expect(low[0].status).toBe('low');

      const critical = inventoryDataService.getByStatus('critical');
      expect(critical).toHaveLength(1);
      expect(critical[0].status).toBe('critical');

      const out = inventoryDataService.getByStatus('out');
      expect(out).toHaveLength(1);
      expect(out[0].status).toBe('out');
    });
  });

  describe('getByCategory', () => {
    it('should filter items by category', () => {
      inventoryDataService.create({
        name: 'Rice',
        category: '主食',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      inventoryDataService.create({
        name: 'Oil',
        category: '调料',
        current_stock: 30,
        min_stock: 10,
        max_stock: 50,
        unit: 'L',
      });

      const mainFood = inventoryDataService.getByCategory('主食');
      expect(mainFood).toHaveLength(1);
      expect(mainFood[0].category).toBe('主食');

      const seasoning = inventoryDataService.getByCategory('调料');
      expect(seasoning).toHaveLength(1);
      expect(seasoning[0].category).toBe('调料');
    });
  });

  describe('getAlerts', () => {
    it('should return items that need attention', () => {
      inventoryDataService.create({
        name: 'Normal Item',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      inventoryDataService.create({
        name: 'Low Item',
        category: 'Test',
        current_stock: 15,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      inventoryDataService.create({
        name: 'Critical Item',
        category: 'Test',
        current_stock: 5,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      const alerts = inventoryDataService.getAlerts();
      expect(alerts).toHaveLength(2); // low and critical, not normal
      expect(alerts.every((item) => item.status !== 'normal')).toBe(true);
    });
  });

  describe('initializeSampleData', () => {
    it('should initialize sample data when empty', () => {
      inventoryDataService.initializeSampleData();
      const items = inventoryDataService.getAll();
      expect(items.length).toBeGreaterThan(0);
    });

    it('should not initialize if data already exists', () => {
      inventoryDataService.create({
        name: 'Existing Item',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });

      const countBefore = inventoryDataService.getAll().length;
      inventoryDataService.initializeSampleData();
      const countAfter = inventoryDataService.getAll().length;

      expect(countAfter).toBe(countBefore);
    });
  });

  describe('status calculation logic', () => {
    it('should calculate out status when stock is 0', () => {
      const item = inventoryDataService.create({
        name: 'Test',
        category: 'Test',
        current_stock: 0,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });
      expect(item.status).toBe('out');
    });

    it('should calculate critical status when stock < min_stock * 0.5', () => {
      const item = inventoryDataService.create({
        name: 'Test',
        category: 'Test',
        current_stock: 9, // Less than 20 * 0.5 = 10
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });
      expect(item.status).toBe('critical');
    });

    it('should calculate low status when stock < min_stock', () => {
      const item = inventoryDataService.create({
        name: 'Test',
        category: 'Test',
        current_stock: 15, // Less than 20 but more than 10
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });
      expect(item.status).toBe('low');
    });

    it('should calculate normal status when stock >= min_stock', () => {
      const item = inventoryDataService.create({
        name: 'Test',
        category: 'Test',
        current_stock: 50,
        min_stock: 20,
        max_stock: 100,
        unit: 'kg',
      });
      expect(item.status).toBe('normal');
    });
  });
});
