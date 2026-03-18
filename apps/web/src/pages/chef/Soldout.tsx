/**
 * 厨师长沽清管理
 * 路由：/chef/soldout
 * 一键沽清 + 恢复上架 + 当前沽清列表
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZButton, ZEmpty, ZSkeleton, ZBadge,
} from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './Soldout.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

interface DishItem {
  dish_id: string;
  dish_name: string;
  dish_code: string;
  category_id: string | null;
  price_yuan: number;
  kitchen_station: string | null;
  tags?: string[];
}

type ViewMode = 'soldout' | 'available';

export default function Soldout() {
  const [mode, setMode] = useState<ViewMode>('soldout');
  const [soldoutList, setSoldoutList] = useState<DishItem[]>([]);
  const [availableList, setAvailableList] = useState<DishItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [operating, setOperating] = useState<string | null>(null);
  const [keyword, setKeyword] = useState('');

  const fetchSoldout = useCallback(async () => {
    try {
      const data = await apiClient.get<DishItem[]>(
        `/api/v1/soldout/list?store_id=${STORE_ID}`,
      );
      setSoldoutList(data);
    } catch { setSoldoutList([]); }
  }, []);

  const fetchAvailable = useCallback(async () => {
    setLoading(true);
    try {
      const qs = keyword ? `&keyword=${encodeURIComponent(keyword)}` : '';
      const data = await apiClient.get<DishItem[]>(
        `/api/v1/soldout/available?store_id=${STORE_ID}${qs}`,
      );
      setAvailableList(data);
    } catch { setAvailableList([]); }
    finally { setLoading(false); }
  }, [keyword]);

  useEffect(() => {
    fetchSoldout();
  }, [fetchSoldout]);

  useEffect(() => {
    if (mode === 'available') fetchAvailable();
  }, [mode, fetchAvailable]);

  const handleSoldout = async (dishId: string) => {
    setOperating(dishId);
    try {
      await apiClient.post('/api/v1/soldout/trigger', {
        store_id: STORE_ID,
        dish_id: dishId,
        reason: '厨师长手动沽清',
      });
      await fetchSoldout();
      await fetchAvailable();
    } catch { /* interceptor handles */ }
    finally { setOperating(null); }
  };

  const handleRestore = async (dishId: string) => {
    setOperating(dishId);
    try {
      await apiClient.post('/api/v1/soldout/restore', {
        store_id: STORE_ID,
        dish_id: dishId,
      });
      await fetchSoldout();
    } catch { /* interceptor handles */ }
    finally { setOperating(null); }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>沽清管理</h1>
        <p className={styles.subtitle}>一键沽清，全渠道同步下架</p>
      </header>

      {/* Stats */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{soldoutList.length}</span>
          <span className={styles.statLabel}>已沽清</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{availableList.length || '-'}</span>
          <span className={styles.statLabel}>可售菜品</span>
        </div>
      </div>

      {/* Tab switch */}
      <div className={styles.tabBar}>
        <button
          className={`${styles.tab} ${mode === 'soldout' ? styles.tabActive : ''}`}
          onClick={() => setMode('soldout')}
        >
          已沽清 ({soldoutList.length})
        </button>
        <button
          className={`${styles.tab} ${mode === 'available' ? styles.tabActive : ''}`}
          onClick={() => setMode('available')}
        >
          选择沽清
        </button>
      </div>

      {/* Soldout list */}
      {mode === 'soldout' && (
        <div className={styles.list}>
          {soldoutList.length === 0 ? (
            <ZEmpty description="暂无沽清菜品，全部可售" />
          ) : (
            soldoutList.map(dish => (
              <ZCard key={dish.dish_id} className={styles.dishCard}>
                <div className={styles.dishRow}>
                  <div className={styles.dishInfo}>
                    <span className={styles.dishName}>{dish.dish_name}</span>
                    <span className={styles.dishMeta}>
                      {dish.dish_code} {dish.kitchen_station ? `· ${dish.kitchen_station}` : ''}
                    </span>
                  </div>
                  <ZBadge type="critical" text="已沽清" />
                  <ZButton
                    size="sm"
                    variant="primary"
                    onClick={() => handleRestore(dish.dish_id)}
                    disabled={operating === dish.dish_id}
                  >
                    {operating === dish.dish_id ? '...' : '恢复上架'}
                  </ZButton>
                </div>
              </ZCard>
            ))
          )}
        </div>
      )}

      {/* Available list for soldout */}
      {mode === 'available' && (
        <>
          <div className={styles.searchBar}>
            <input
              type="text"
              className={styles.searchInput}
              placeholder="搜索菜品名称..."
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
            />
          </div>

          <div className={styles.list}>
            {loading ? (
              [1, 2, 3].map(i => <ZSkeleton key={i} style={{ height: 64, marginBottom: 8, borderRadius: 10 }} />)
            ) : availableList.length === 0 ? (
              <ZEmpty description="无可售菜品" />
            ) : (
              availableList.map(dish => (
                <ZCard key={dish.dish_id} className={styles.dishCard}>
                  <div className={styles.dishRow}>
                    <div className={styles.dishInfo}>
                      <span className={styles.dishName}>{dish.dish_name}</span>
                      <span className={styles.dishMeta}>
                        ¥{dish.price_yuan} · {dish.dish_code}
                        {dish.kitchen_station ? ` · ${dish.kitchen_station}` : ''}
                      </span>
                    </div>
                    <button
                      className={styles.soldoutBtn}
                      onClick={() => handleSoldout(dish.dish_id)}
                      disabled={operating === dish.dish_id}
                    >
                      {operating === dish.dish_id ? '...' : '沽清'}
                    </button>
                  </div>
                </ZCard>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
