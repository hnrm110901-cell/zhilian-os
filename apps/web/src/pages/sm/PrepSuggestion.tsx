import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../../services/api';
import { ZCard, ZButton, ZEmpty, ZSkeleton, ZBadge } from '../../design-system/components';
import styles from './PrepSuggestion.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

interface SuggestionItem {
  ingredient_id: string;
  ingredient_name: string;
  category: string;
  unit: string;
  current_stock: number;
  predicted_demand: number;
  suggested_qty: number;
  estimated_cost_yuan: number;
  sources: { reservation: number; history: number; waste_buffer: number };
  confidence: 'high' | 'medium' | 'low';
}

interface SuggestionResult {
  suggestion_id: string | null;
  store_id: string;
  target_date: string;
  generated_at: string;
  items: SuggestionItem[];
  total_estimated_cost_yuan: number;
}

interface HistoryItem {
  purchase_order_id: string;
  order_number: string;
  status: string;
  total_amount_yuan: number;
  item_count: number;
  created_at: string;
  created_by: string;
}

const CONFIDENCE_MAP: Record<string, { label: string; color: string }> = {
  high:   { label: '高', color: '#52c41a' },
  medium: { label: '中', color: '#faad14' },
  low:    { label: '低', color: '#ff4d4f' },
};

const CATEGORY_LABELS: Record<string, string> = {
  vegetables: '蔬菜', meat: '肉类', seafood: '海鲜',
  dry_goods: '干货', beverage: '饮品', condiment: '调料',
  dairy: '奶制品', frozen: '冻品', other: '其他',
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending:   { label: '待审批', color: '#faad14' },
  approved:  { label: '已审批', color: '#1890ff' },
  ordered:   { label: '已下单', color: '#722ed1' },
  delivered: { label: '已到货', color: '#52c41a' },
  completed: { label: '已完成', color: '#8c8c8c' },
  cancelled: { label: '已取消', color: '#ff4d4f' },
};

type TabKey = 'suggestion' | 'history';

export default function PrepSuggestion() {
  const [activeTab, setActiveTab] = useState<TabKey>('suggestion');
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [suggestion, setSuggestion] = useState<SuggestionResult | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adjustments, setAdjustments] = useState<Record<string, number>>({});

  const fetchSuggestion = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.post<SuggestionResult>(
        '/api/v1/prep-suggestion/generate',
        { store_id: STORE_ID },
      );
      setSuggestion(data);
      // Select all by default
      const ids = new Set(data.items.map((i: SuggestionItem) => i.ingredient_id));
      setSelected(ids);
      // Init adjustments to suggested values
      const adj: Record<string, number> = {};
      data.items.forEach((i: SuggestionItem) => { adj[i.ingredient_id] = i.suggested_qty; });
      setAdjustments(adj);
    } catch {
      setSuggestion(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const data = await apiClient.get<HistoryItem[]>(
        `/api/v1/prep-suggestion/history?store_id=${STORE_ID}&limit=20`,
      );
      setHistory(data);
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'suggestion') fetchSuggestion();
    else fetchHistory();
  }, [activeTab, fetchSuggestion, fetchHistory]);

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (!suggestion) return;
    if (selected.size === suggestion.items.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(suggestion.items.map(i => i.ingredient_id)));
    }
  };

  const handleAdjust = (id: string, val: number) => {
    setAdjustments(prev => ({ ...prev, [id]: Math.max(0, val) }));
  };

  const handleConfirm = async () => {
    if (!suggestion || selected.size === 0) return;
    setConfirming(true);
    try {
      const items = suggestion.items
        .filter(i => selected.has(i.ingredient_id))
        .map(i => ({
          ingredient_id: i.ingredient_id,
          qty: adjustments[i.ingredient_id] ?? i.suggested_qty,
        }));

      await apiClient.post('/api/v1/prep-suggestion/confirm', {
        store_id: STORE_ID,
        items,
        notes: `目标日期: ${suggestion.target_date}`,
      });
      // Switch to history tab to see result
      setActiveTab('history');
    } catch {
      // error handled by interceptor
    } finally {
      setConfirming(false);
    }
  };

  const selectedCost = suggestion
    ? suggestion.items
        .filter(i => selected.has(i.ingredient_id))
        .reduce((sum, i) => {
          const ratio = (adjustments[i.ingredient_id] ?? i.suggested_qty) / (i.suggested_qty || 1);
          return sum + i.estimated_cost_yuan * ratio;
        }, 0)
    : 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>智能备料</h1>
        <p className={styles.subtitle}>AI 根据预订 + 历史数据自动生成备料建议</p>
      </header>

      {/* Tab Bar */}
      <div className={styles.tabBar}>
        <button
          className={`${styles.tab} ${activeTab === 'suggestion' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('suggestion')}
        >
          备料建议
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'history' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('history')}
        >
          历史记录
        </button>
      </div>

      {/* Suggestion Tab */}
      {activeTab === 'suggestion' && (
        <>
          {loading ? (
            <div className={styles.skeletons}>
              {[1, 2, 3].map(i => <ZSkeleton key={i} style={{ height: 100, marginBottom: 12, borderRadius: 12 }} />)}
            </div>
          ) : !suggestion || suggestion.items.length === 0 ? (
            <ZEmpty description="暂无备料建议，可能 BOM 数据尚未配置" />
          ) : (
            <>
              {/* Summary strip */}
              <div className={styles.summary}>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>目标日期</span>
                  <span className={styles.summaryValue}>{suggestion.target_date}</span>
                </div>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>食材种类</span>
                  <span className={styles.summaryValue}>{suggestion.items.length}</span>
                </div>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>预估总额</span>
                  <span className={styles.summaryValue}>
                    ¥{selectedCost.toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Select all */}
              <div className={styles.selectBar}>
                <label className={styles.checkLabel} onClick={toggleAll}>
                  <span className={`${styles.checkbox} ${selected.size === suggestion.items.length ? styles.checked : ''}`} />
                  全选 ({selected.size}/{suggestion.items.length})
                </label>
                <ZButton size="sm" onClick={fetchSuggestion}>刷新</ZButton>
              </div>

              {/* Item list */}
              <div className={styles.itemList}>
                {suggestion.items.map(item => {
                  const conf = CONFIDENCE_MAP[item.confidence] || CONFIDENCE_MAP.low;
                  const isSelected = selected.has(item.ingredient_id);
                  return (
                    <ZCard key={item.ingredient_id} className={`${styles.itemCard} ${isSelected ? styles.itemSelected : ''}`}>
                      <div className={styles.itemHeader}>
                        <span
                          className={`${styles.checkbox} ${isSelected ? styles.checked : ''}`}
                          onClick={() => toggleSelect(item.ingredient_id)}
                        />
                        <div className={styles.itemInfo}>
                          <span className={styles.itemName}>{item.ingredient_name}</span>
                          <span className={styles.itemCategory}>
                            {CATEGORY_LABELS[item.category] || item.category}
                          </span>
                        </div>
                        <ZBadge type={item.confidence === 'high' ? 'success' : item.confidence === 'medium' ? 'warning' : 'critical'} text={conf.label} />
                      </div>

                      <div className={styles.itemBody}>
                        <div className={styles.itemMetric}>
                          <span className={styles.metricLabel}>当前库存</span>
                          <span className={styles.metricValue}>{item.current_stock} {item.unit}</span>
                        </div>
                        <div className={styles.itemMetric}>
                          <span className={styles.metricLabel}>预测需求</span>
                          <span className={styles.metricValue}>{item.predicted_demand.toFixed(1)} {item.unit}</span>
                        </div>
                        <div className={styles.itemMetric}>
                          <span className={styles.metricLabel}>建议采购</span>
                          <input
                            type="number"
                            className={styles.qtyInput}
                            value={adjustments[item.ingredient_id] ?? item.suggested_qty}
                            onChange={e => handleAdjust(item.ingredient_id, parseFloat(e.target.value) || 0)}
                            min={0}
                            step={0.1}
                          />
                          <span className={styles.unitLabel}>{item.unit}</span>
                        </div>
                      </div>

                      <div className={styles.itemSources}>
                        <span>预订: {item.sources.reservation.toFixed(1)}</span>
                        <span>历史: {item.sources.history.toFixed(1)}</span>
                        <span>损耗: {item.sources.waste_buffer.toFixed(1)}</span>
                        <span className={styles.costTag}>¥{item.estimated_cost_yuan.toFixed(2)}</span>
                      </div>
                    </ZCard>
                  );
                })}
              </div>

              {/* Confirm button */}
              <div className={styles.confirmBar}>
                <div className={styles.confirmInfo}>
                  <span>已选 {selected.size} 项</span>
                  <span className={styles.confirmCost}>¥{selectedCost.toFixed(2)}</span>
                </div>
                <ZButton
                  variant="primary"
                  onClick={handleConfirm}
                  disabled={selected.size === 0 || confirming}
                >
                  {confirming ? '提交中...' : '确认并生成采购单'}
                </ZButton>
              </div>
            </>
          )}
        </>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div className={styles.historyList}>
          {history.length === 0 ? (
            <ZEmpty description="暂无备料记录" />
          ) : (
            history.map(h => {
              const st = STATUS_LABELS[h.status] || { label: h.status, color: '#8c8c8c' };
              return (
                <ZCard key={h.purchase_order_id} className={styles.historyCard}>
                  <div className={styles.historyHeader}>
                    <span className={styles.historyNo}>{h.order_number}</span>
                    <ZBadge type={h.status === 'completed' || h.status === 'delivered' ? 'success' : h.status === 'cancelled' ? 'critical' : 'info'} text={st.label} />
                  </div>
                  <div className={styles.historyBody}>
                    <span>{h.item_count} 种食材</span>
                    <span>¥{h.total_amount_yuan.toFixed(2)}</span>
                    <span>{h.created_at ? new Date(h.created_at).toLocaleDateString('zh-CN') : '-'}</span>
                  </div>
                </ZCard>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
