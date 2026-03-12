import React, { useState, useCallback, useEffect } from 'react';
import { DatePicker } from 'antd';
import {
  ReloadOutlined, WarningOutlined, FireOutlined,
  ArrowUpOutlined, ArrowDownOutlined, MinusOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZSelect, ZTable, ZKpi, ZEmpty,
} from '../design-system/components';
import type { ZTableColumn } from '../design-system/components/ZTable';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';
import styles from './WasteReasoningPage.module.css';

const { RangePicker } = DatePicker;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface RootCause {
  root_cause:  string;
  event_type:  string | null;
  event_count: number;
}

interface WasteItem {
  rank:            number;
  item_id:         string;
  item_name:       string;
  category:        string;
  unit:            string;
  waste_cost_fen:  number;
  waste_cost_yuan: number;
  waste_qty:       number;
  cost_share_pct:  number;
  root_causes:     RootCause[];
  action:          string;
}

interface BomDeviationItem {
  rank:               number;
  ingredient_id:      string;
  item_name:          string;
  unit:               string;
  total_variance_qty: number;
  variance_cost_yuan: number;
  avg_variance_pct:   number;
  event_count:        number;
}

interface WasteReport {
  store_id:          string;
  start_date:        string;
  end_date:          string;
  waste_rate_pct:    number;
  waste_rate_status: string;
  total_waste_yuan:  number;
  waste_change_yuan: number;
  top5:              WasteItem[];
  bom_deviation:     BomDeviationItem[];
}

// ── 辅助函数 ──────────────────────────────────────────────────────────────────

const wasteRateStatusType = (status: string): 'success' | 'warning' | 'critical' | 'default' => {
  if (status === 'ok')       return 'success';
  if (status === 'warning')  return 'warning';
  if (status === 'critical') return 'critical';
  return 'default';
};

const rootCauseBadgeType = (cause: string): 'critical' | 'warning' | 'info' | 'accent' | 'default' => {
  const map: Record<string, 'critical' | 'warning' | 'info' | 'accent' | 'default'> = {
    staff_error:   'critical',
    food_quality:  'warning',
    over_prep:     'warning',
    spoilage:      'warning',
    bom_deviation: 'accent',
    transfer_loss: 'info',
    drop_damage:   'info',
    unknown:       'default',
  };
  return map[cause] ?? 'default';
};

const rootCauseLabel = (cause: string) => {
  const map: Record<string, string> = {
    staff_error:   '操作失误',
    food_quality:  '食材质量',
    over_prep:     '备料过多',
    spoilage:      '自然腐败',
    bom_deviation: 'BOM偏差',
    transfer_loss: '转运损耗',
    drop_damage:   '跌落损坏',
    unknown:       '待追因',
  };
  return map[cause] || cause;
};

// ── 表格列定义 ────────────────────────────────────────────────────────────────

const top5Columns: ZTableColumn<WasteItem>[] = [
  {
    key: 'rank',
    title: '排名',
    width: 56,
    align: 'center',
    render: (rank) => (
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 28, height: 28, borderRadius: '50%',
        background: rank <= 3 ? '#C53030' : '#d9d9d9',
        color: rank <= 3 ? '#fff' : '#666',
        fontWeight: 'bold', fontSize: 13,
      }}>
        {rank}
      </span>
    ),
  },
  {
    key: 'item_name',
    title: '食材名称',
    render: (name, row) => (
      <div>
        <strong style={{ color: 'var(--text-primary)' }}>{name}</strong>
        {row.category && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 1 }}>{row.category}</div>
        )}
      </div>
    ),
  },
  {
    key: 'waste_cost_yuan',
    title: '损耗金额',
    align: 'right',
    render: (yuan) => (
      <strong style={{ color: '#cf1322' }}>
        ¥{(yuan as number).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
      </strong>
    ),
  },
  {
    key: 'waste_qty',
    title: '损耗数量',
    render: (_, row) => `${row.waste_qty.toFixed(2)} ${row.unit}`,
  },
  {
    key: 'cost_share_pct',
    title: '占总损耗',
    render: (pct) => {
      const p = pct as number;
      const barColor = p >= 30 ? 'var(--red)' : p >= 15 ? 'var(--yellow)' : 'var(--green)';
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 80, height: 5, background: '#f0f0f0', borderRadius: 3, overflow: 'hidden', flexShrink: 0 }}>
            <div style={{ width: `${Math.min(p, 100)}%`, height: '100%', borderRadius: 3, background: barColor }} />
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{p.toFixed(1)}%</span>
        </div>
      );
    },
  },
  {
    key: 'root_causes',
    title: '归因',
    render: (causes: RootCause[]) => {
      if (!causes || causes.length === 0) {
        return <ZBadge type="default" text="待记录" />;
      }
      return (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {causes.slice(0, 2).map((c, i) => (
            <ZBadge key={i} type={rootCauseBadgeType(c.root_cause)}
              text={`${rootCauseLabel(c.root_cause)}×${c.event_count}`} />
          ))}
        </div>
      );
    },
  },
  {
    key: 'action',
    title: '建议行动',
    width: 240,
    render: (action) => (
      <span style={{ fontSize: 12, color: 'var(--accent)' }}>{action}</span>
    ),
  },
];

const bomColumns: ZTableColumn<BomDeviationItem>[] = [
  {
    key: 'rank',
    title: '排名',
    width: 56,
    align: 'center',
    render: (rank) => (
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 28, height: 28, borderRadius: '50%',
        background: rank <= 3 ? '#C8923A' : '#d9d9d9',
        color: rank <= 3 ? '#fff' : '#666',
        fontWeight: 'bold', fontSize: 13,
      }}>
        {rank}
      </span>
    ),
  },
  {
    key: 'item_name',
    title: '食材名称',
    render: (name) => <strong style={{ color: 'var(--text-primary)' }}>{name}</strong>,
  },
  {
    key: 'variance_cost_yuan',
    title: '偏差成本',
    align: 'right',
    render: (yuan) => (
      <strong style={{ color: '#d46b08' }}>
        ¥{(yuan as number).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
      </strong>
    ),
  },
  {
    key: 'total_variance_qty',
    title: '超用数量',
    render: (_, row) => `+${row.total_variance_qty.toFixed(2)} ${row.unit}`,
  },
  {
    key: 'avg_variance_pct',
    title: '平均偏差率',
    align: 'center',
    render: (pct) => {
      const p = pct as number;
      const type = p >= 20 ? 'critical' : p >= 10 ? 'warning' : 'default';
      return <ZBadge type={type} text={`+${p.toFixed(1)}%`} />;
    },
  },
  {
    key: 'event_count',
    title: '事件次数',
    align: 'right',
  },
];

// ── 主组件 ────────────────────────────────────────────────────────────────────

const WasteReasoningPage: React.FC = () => {
  const [loading, setLoading]     = useState(false);
  const [stores, setStores]       = useState<any[]>([]);
  const [storeId, setStoreId]     = useState(localStorage.getItem('store_id') || 'STORE001');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs().subtract(6, 'day'),
    dayjs(),
  ]);
  const [report, setReport]       = useState<WasteReport | null>(null);
  const [error, setError]         = useState<string | null>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      const list = res.data?.stores || res.data || [];
      setStores(list);
      if (list.length > 0 && !list.find((s: any) => s.id === storeId)) {
        setStoreId(list[0].id || list[0].store_id || 'STORE001');
      }
    } catch {
      // 静默降级，使用默认门店ID
    }
  }, [storeId]);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [start, end] = dateRange;
      const res = await apiClient.get('/api/v1/waste/report', {
        params: {
          store_id:   storeId,
          start_date: start.format('YYYY-MM-DD'),
          end_date:   end.format('YYYY-MM-DD'),
        },
      });
      setReport(res.data);
    } catch (err: any) {
      setError('加载损耗数据失败，请检查网络或联系管理员');
      handleApiError(err, '加载损耗数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, dateRange]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadReport(); }, [loadReport]);

  const storeOptions = stores.length > 0
    ? stores.map((s: any) => ({ value: s.id || s.store_id, label: s.name || s.store_name || s.id }))
    : [{ value: 'STORE001', label: '默认门店' }];

  const change = report?.waste_change_yuan ?? 0;
  const changeColor = change > 0 ? '#cf1322' : change < 0 ? '#3f8600' : 'var(--text-secondary)';
  const ChangeIcon = change > 0 ? ArrowUpOutlined : change < 0 ? ArrowDownOutlined : MinusOutlined;

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.header}>
        <h4 className={styles.pageTitle}>
          <FireOutlined style={{ color: '#C53030', marginRight: 8 }} />
          损耗Top5分析
        </h4>
        <div className={styles.headerControls}>
          <ZSelect
            value={storeId}
            options={storeOptions}
            onChange={(v) => setStoreId(v as string)}
            style={{ width: 160 }}
          />
          <RangePicker
            value={dateRange}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setDateRange([dates[0], dates[1]]);
              }
            }}
            format="YYYY-MM-DD"
            allowClear={false}
          />
          <ZButton icon={<ReloadOutlined />} onClick={loadReport} disabled={loading}>
            刷新
          </ZButton>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className={styles.alertError}>
          <WarningOutlined style={{ marginRight: 6 }} />
          {error}
        </div>
      )}

      {/* 主体内容 */}
      {loading ? (
        <ZSkeleton rows={8} block />
      ) : !report ? (
        <ZCard>
          <div className={styles.alertInfo}>
            请选择门店和日期范围后点击刷新加载损耗数据
          </div>
        </ZCard>
      ) : (
        <>
          {/* KPI 卡片 */}
          <div className={styles.kpiGrid}>
            <ZCard>
              <ZKpi
                value={`¥${report.total_waste_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}`}
                label="总损耗金额"
              />
            </ZCard>
            <ZCard>
              <ZKpi
                value={report.waste_rate_pct.toFixed(2)}
                unit="%"
                label="损耗率"
              />
              <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                <ZBadge
                  type={wasteRateStatusType(report.waste_rate_status)}
                  text={report.waste_rate_status === 'ok' ? '正常' : report.waste_rate_status === 'warning' ? '偏高' : '超标'}
                />
                <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>行业标准：&lt;3%为优秀</span>
              </div>
            </ZCard>
            <ZCard>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4, marginBottom: 4 }}>较上期损耗变化</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: changeColor, lineHeight: 1.2 }}>
                <ChangeIcon style={{ fontSize: 16, marginRight: 2 }} />
                ¥{Math.abs(change).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
              </div>
              <div style={{ marginTop: 4, fontSize: 12, color: changeColor }}>
                {change === 0 ? '持平' : change > 0 ? '损耗增加' : '损耗减少'}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi
                value={report.top5?.length ?? 0}
                unit="种"
                label="Top5食材"
              />
              <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}>
                {report.start_date} 至 {report.end_date}
              </div>
            </ZCard>
          </div>

          {/* Top5 损耗食材表 */}
          <ZCard
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <WarningOutlined style={{ color: '#C53030' }} />
                Top5 损耗食材（按损耗金额排序）
              </div>
            }
            extra={
              report.total_waste_yuan > 0 ? (
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  总损耗 ¥{report.total_waste_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
                </span>
              ) : undefined
            }
            style={{ marginBottom: 14 }}
          >
            {report.top5?.length === 0 ? (
              <ZEmpty description="暂无损耗数据" />
            ) : (
              <ZTable
                columns={top5Columns}
                data={report.top5 ?? []}
                rowKey="item_id"
              />
            )}
          </ZCard>

          {/* BOM 偏差排名 */}
          {report.bom_deviation && report.bom_deviation.length > 0 && (
            <ZCard
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <WarningOutlined style={{ color: '#C8923A' }} />
                  BOM配方偏差排名（实际用量超出标准）
                </div>
              }
            >
              <ZTable
                columns={bomColumns}
                data={report.bom_deviation}
                rowKey="ingredient_id"
                emptyText="暂无BOM偏差数据（需要开启损耗事件追踪）"
              />
            </ZCard>
          )}
        </>
      )}
    </div>
  );
};

export default WasteReasoningPage;
