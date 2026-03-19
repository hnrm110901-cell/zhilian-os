/**
 * 获取当前用户关联的门店列表
 * 根据用户 brand_id 从 /api/v1/stores 获取品牌下的门店
 */
import { useState, useEffect } from 'react';
import { apiClient } from '../services/api';
import { useAuthStore } from '../stores/authStore';

export interface UserStore {
  id: string;
  name: string;
  code: string;
  status: string;
  is_active: boolean;
}

export function useUserStores() {
  const user = useAuthStore((s) => s.user);
  const [stores, setStores] = useState<UserStore[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentStoreId, setCurrentStoreId] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    let cancelled = false;
    (async () => {
      try {
        const data = await apiClient.get<UserStore[]>('/api/v1/stores');
        if (!cancelled) {
          setStores(data);
          // 默认选中用户关联的门店，否则选第一个
          const defaultId = user.store_id || (data.length > 0 ? data[0].id : null);
          setCurrentStoreId(defaultId);
        }
      } catch {
        if (!cancelled) setStores([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [user]);

  return { stores, loading, currentStoreId, setCurrentStoreId };
}
