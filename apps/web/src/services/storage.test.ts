import { describe, it, expect, beforeEach } from 'vitest';
import { storageService } from './storage';

describe('StorageService', () => {
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();
  });

  describe('set and get', () => {
    it('should store and retrieve a string value', () => {
      storageService.set('test-key', 'test-value');
      const value = storageService.get<string>('test-key');
      expect(value).toBe('test-value');
    });

    it('should store and retrieve an object', () => {
      const testObject = { name: 'Test', age: 25 };
      storageService.set('test-object', testObject);
      const value = storageService.get<typeof testObject>('test-object');
      expect(value).toEqual(testObject);
    });

    it('should store and retrieve an array', () => {
      const testArray = [1, 2, 3, 4, 5];
      storageService.set('test-array', testArray);
      const value = storageService.get<number[]>('test-array');
      expect(value).toEqual(testArray);
    });

    it('should return null for non-existent key', () => {
      const value = storageService.get('non-existent');
      expect(value).toBeNull();
    });

    it('should handle complex nested objects', () => {
      const complexObject = {
        user: {
          name: 'John',
          profile: {
            age: 30,
            hobbies: ['reading', 'coding'],
          },
        },
        settings: {
          theme: 'dark',
          notifications: true,
        },
      };
      storageService.set('complex', complexObject);
      const value = storageService.get<typeof complexObject>('complex');
      expect(value).toEqual(complexObject);
    });
  });

  describe('remove', () => {
    it('should remove a stored value', () => {
      storageService.set('test-key', 'test-value');
      expect(storageService.get('test-key')).toBe('test-value');

      storageService.remove('test-key');
      expect(storageService.get('test-key')).toBeNull();
    });

    it('should not throw error when removing non-existent key', () => {
      expect(() => storageService.remove('non-existent')).not.toThrow();
    });
  });

  describe('clear', () => {
    it('should clear all zhilian_os_ prefixed items', () => {
      storageService.set('key1', 'value1');
      storageService.set('key2', 'value2');
      storageService.set('key3', 'value3');

      // Add a non-prefixed item
      localStorage.setItem('other-key', 'other-value');

      storageService.clear();

      expect(storageService.get('key1')).toBeNull();
      expect(storageService.get('key2')).toBeNull();
      expect(storageService.get('key3')).toBeNull();
      // Non-prefixed item should still exist
      expect(localStorage.getItem('other-key')).toBe('other-value');
    });
  });

  describe('key prefixing', () => {
    it('should add prefix to keys', () => {
      storageService.set('test', 'value');
      // Check that the actual localStorage key has the prefix
      expect(localStorage.getItem('zhilian_os_test')).toBeTruthy();
    });

    it('should handle keys with special characters', () => {
      const specialKey = 'test-key_with.special@chars';
      storageService.set(specialKey, 'value');
      expect(storageService.get(specialKey)).toBe('value');
    });
  });

  describe('error handling', () => {
    it('should handle invalid JSON gracefully', () => {
      // Manually set invalid JSON
      localStorage.setItem('zhilian_os_invalid', '{invalid json}');
      const value = storageService.get('invalid');
      expect(value).toBeNull();
    });

    it('should handle circular references', () => {
      const circular: any = { name: 'test' };
      circular.self = circular;

      // This should not throw, but might not store correctly
      expect(() => storageService.set('circular', circular)).not.toThrow();
    });
  });

  describe('type safety', () => {
    it('should maintain type information', () => {
      interface User {
        id: number;
        name: string;
        email: string;
      }

      const user: User = {
        id: 1,
        name: 'John Doe',
        email: 'john@example.com',
      };

      storageService.set('user', user);
      const retrieved = storageService.get<User>('user');

      expect(retrieved).toEqual(user);
      expect(retrieved?.id).toBe(1);
      expect(retrieved?.name).toBe('John Doe');
    });
  });
});
