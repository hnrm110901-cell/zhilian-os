import React, { useState, useEffect, useCallback } from 'react';
import { InputNumber, message } from 'antd';
import {
  EditOutlined, SaveOutlined, CloseOutlined,
  BellOutlined, WarningOutlined,
} from '@ant-design/icons';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZSelect, ZTable,
} from '../design-system/components';
import type { ZTableColumn } from '../design-system/components/ZTable';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';
import styles from './AlertThresholdsPage.module.css';

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface KPIItem {
  id:                 string;
  name:               string;
  category:           string;
  description:        string | null;
  unit:               string | null;
  target_value:       number | null;
  warning_threshold:  number | null;
  critical_threshold: number | null;
  is_active:          string;
}

interface EditState {
  warning_threshold:  number | null;
  critical_threshold: number | null;
}

// ── 辅助函数 ──────────────────────────────────────────────────────────────────

const categoryBadgeType = (cat: string): 'info' | 'warning' | 'success' | 'accent' | 'default' => {
  const map: Record<string, 'info' | 'warning' | 'success' | 'accent' | 'default'> = {
    food_cost:  'info',
    waste:      'warning',
    revenue:    'success',
    decision:   'accent',
    operations: 'info',
  };
  return map[cat] ?? 'default';
};

const categoryLabel = (cat: string) => {
  const map: Record<string, string> = {
    food_cost:  '食材成本',
    waste:      '损耗管理',
    revenue:    '营业收入',
    decision:   '决策执行',
    operations: '运营效率',
  };
  return map[cat] || cat;
};

// ════════════════════════════════════════════════════════════════════════════════
// AlertThresholdsPage
// ════════════════════════════════════════════════════════════════════════════════

const AlertThresholdsPage: React.FC = () => {
  const [loading,    setLoading]    = useState(false);
  const [saving,     setSaving]     = useState<string | null>(null);
  const [kpis,       setKpis]       = useState<KPIItem[]>([]);
  const [editRows,   setEditRows]   = useState<Record<string, EditState>>({});
  const [catFilter,  setCatFilter]  = useState<string>('all');

  const loadKpis = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/kpis');
      setKpis(res.data);
    } catch (err: any) {
      handleApiError(err, '加载 KPI 列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadKpis(); }, [loadKpis]);

  const startEdit = (kpi: KPIItem) => {
    setEditRows(prev => ({
      ...prev,
      [kpi.id]: {
        warning_threshold:  kpi.warning_threshold,
        critical_threshold: kpi.critical_threshold,
      },
    }));
  };

  const cancelEdit = (kpiId: string) => {
    setEditRows(prev => {
      const next = { ...prev };
      delete next[kpiId];
      return next;
    });
  };

  const saveThreshold = async (kpiId: string) => {
    const edit = editRows[kpiId];
    if (!edit) return;

    if (
      edit.warning_threshold  !== null &&
      edit.critical_threshold !== null &&
      edit.warning_threshold  >= edit.critical_threshold
    ) {
      message.error('警告阈值必须小于超标阈值');
      return;
    }

    setSaving(kpiId);
    try {
      await apiClient.patch(`/api/v1/kpis/${kpiId}/thresholds`, {
        warning_threshold:  edit.warning_threshold,
        critical_threshold: edit.critical_threshold,
      });
      message.success('阈值更新成功');
      cancelEdit(kpiId);
      loadKpis();
    } catch (err: any) {
      handleApiError(err, '保存失败');
    } finally {
      setSaving(null);
    }
  };

  const catOptions = [
    { value: 'all',       label: '全部类别' },
    { value: 'food_cost', label: '食材成本' },
    { value: 'waste',     label: '损耗管理' },
    { value: 'revenue',   label: '营业收入' },
    { value: 'decision',  label: '决策执行' },
    { value: 'operations',label: '运营效率' },
  ];

  const displayKpis = catFilter === 'all'
    ? kpis
    : kpis.filter(k => k.category === catFilter);

  const columns: ZTableColumn<KPIItem>[] = [
    {
      key:   'name',
      title: '指标名称',
      width: 180,
      render: (name: string, row: KPIItem) => (
        <div>
          <strong style={{ color: 'var(--text-primary)' }}>{name}</strong>
          {row.description && (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 1 }}>{row.description}</div>
          )}
        </div>
      ),
    },
    {
      key:   'category',
      title: '类别',
      width: 110,
      render: (cat: string) => (
        <ZBadge type={categoryBadgeType(cat)} text={categoryLabel(cat)} />
      ),
    },
    {
      key:   'unit',
      title: '单位',
      width: 70,
      align: 'center',
      render: (u: string | null) => u || '—',
    },
    {
      key:   'target_value',
      title: '目标值',
      width: 90,
      align: 'right',
      render: (v: number | null, row: KPIItem) => v != null ? `${v}${row.unit || ''}` : '—',
    },
    {
      key:   'warning_threshold',
      title: '警告阈值',
      width: 160,
      render: (v: number | null, row: KPIItem) => {
        const editing = editRows[row.id];
        if (editing) {
          return (
            <InputNumber
              value={editing.warning_threshold ?? undefined}
              onChange={val => setEditRows(prev => ({
                ...prev,
                [row.id]: { ...prev[row.id], warning_threshold: val ?? null },
              }))}
              style={{ width: 120 }}
              addonAfter={row.unit || undefined}
              step={0.1}
              precision={1}
            />
          );
        }
        return v != null
          ? <ZBadge type="warning" text={`${v}${row.unit || ''}`} />
          : <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>未设置</span>;
      },
    },
    {
      key:   'critical_threshold',
      title: '超标阈值',
      width: 160,
      render: (v: number | null, row: KPIItem) => {
        const editing = editRows[row.id];
        if (editing) {
          return (
            <InputNumber
              value={editing.critical_threshold ?? undefined}
              onChange={val => setEditRows(prev => ({
                ...prev,
                [row.id]: { ...prev[row.id], critical_threshold: val ?? null },
              }))}
              style={{ width: 120 }}
              addonAfter={row.unit || undefined}
              step={0.1}
              precision={1}
            />
          );
        }
        return v != null
          ? <ZBadge type="critical" text={`${v}${row.unit || ''}`} />
          : <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>未设置</span>;
      },
    },
    {
      key:   'id',
      title: '操作',
      width: 120,
      align: 'center',
      render: (_: any, row: KPIItem) => {
        const editing = editRows[row.id];
        if (editing) {
          return (
            <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
              <ZButton
                size="sm"
                variant="primary"
                icon={<SaveOutlined />}
                disabled={saving === row.id}
                onClick={() => saveThreshold(row.id)}
                title="保存"
              />
              <ZButton
                size="sm"
                icon={<CloseOutlined />}
                onClick={() => cancelEdit(row.id)}
                title="取消"
              />
            </div>
          );
        }
        return (
          <ZButton
            size="sm"
            icon={<EditOutlined />}
            onClick={() => startEdit(row)}
            title="编辑阈值"
          />
        );
      },
    },
  ];

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.header}>
        <h3 className={styles.pageTitle}>
          <BellOutlined style={{ marginRight: 8 }} />
          异常告警阈值配置
        </h3>
      </div>

      {/* 配置说明 */}
      <div className={styles.infoBar}>
        <WarningOutlined style={{ color: '#1677ff', marginRight: 8, flexShrink: 0 }} />
        超过「警告阈值」时系统发送橙色告警推送；超过「超标阈值」时发送红色紧急推送并推送至企业微信。阈值调整立即生效。
      </div>

      {/* 类别筛选 + 表格 */}
      <ZCard>
        <div className={styles.tableHeader}>
          <ZSelect
            value={catFilter}
            options={catOptions}
            onChange={(v) => setCatFilter(v as string)}
            style={{ width: 140 }}
          />
        </div>

        {loading ? (
          <ZSkeleton rows={6} block />
        ) : (
          <ZTable<KPIItem>
            columns={columns}
            data={displayKpis}
            rowKey="id"
            emptyText="暂无 KPI 数据"
          />
        )}
      </ZCard>
    </div>
  );
};

export default AlertThresholdsPage;
