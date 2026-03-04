import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, InputNumber, Button, Space, Tag, Typography,
  Spin, Alert, Tooltip, message,
} from 'antd';
import {
  EditOutlined, SaveOutlined, CloseOutlined,
  BellOutlined, WarningOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text } = Typography;

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

// ── 类别标签颜色 ──────────────────────────────────────────────────────────────

const categoryColor = (cat: string) => {
  const map: Record<string, string> = {
    food_cost:  'blue',
    waste:      'orange',
    revenue:    'green',
    decision:   'purple',
    operations: 'cyan',
  };
  return map[cat] || 'default';
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
// AlertThresholdsPage — 异常告警阈值配置
// ════════════════════════════════════════════════════════════════════════════════

const AlertThresholdsPage: React.FC = () => {
  const [loading,  setLoading]  = useState(false);
  const [saving,   setSaving]   = useState<string | null>(null);
  const [kpis,     setKpis]     = useState<KPIItem[]>([]);
  const [editRows, setEditRows] = useState<Record<string, EditState>>({});

  // ── 加载 KPI 列表 ──────────────────────────────────────────────────────────

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

  // ── 编辑行操作 ────────────────────────────────────────────────────────────

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

  // ── 表格列定义 ────────────────────────────────────────────────────────────

  const columns = [
    {
      title:     '指标名称',
      dataIndex: 'name',
      width:     180,
      render:    (name: string, row: KPIItem) => (
        <Space direction="vertical" size={0}>
          <Text strong>{name}</Text>
          {row.description && (
            <Text type="secondary" style={{ fontSize: 12 }}>{row.description}</Text>
          )}
        </Space>
      ),
    },
    {
      title:     '类别',
      dataIndex: 'category',
      width:     110,
      render:    (cat: string) => (
        <Tag color={categoryColor(cat)}>{categoryLabel(cat)}</Tag>
      ),
      filters: [
        { text: '食材成本', value: 'food_cost' },
        { text: '损耗管理', value: 'waste' },
        { text: '营业收入', value: 'revenue' },
        { text: '决策执行', value: 'decision' },
      ],
      onFilter: (value: any, row: KPIItem) => row.category === value,
    },
    {
      title:     '单位',
      dataIndex: 'unit',
      width:     70,
      render:    (u: string | null) => u || '—',
    },
    {
      title:     '目标值',
      dataIndex: 'target_value',
      width:     90,
      render:    (v: number | null, row: KPIItem) =>
        v != null ? `${v}${row.unit || ''}` : '—',
    },
    {
      title: (
        <Space>
          <WarningOutlined style={{ color: '#faad14' }} />
          警告阈值
        </Space>
      ),
      dataIndex: 'warning_threshold',
      width:     140,
      render:    (v: number | null, row: KPIItem) => {
        const editing = editRows[row.id];
        if (editing) {
          return (
            <InputNumber
              value={editing.warning_threshold ?? undefined}
              onChange={val => setEditRows(prev => ({
                ...prev,
                [row.id]: { ...prev[row.id], warning_threshold: val ?? null },
              }))}
              style={{ width: 110 }}
              suffix={row.unit || undefined}
              step={0.1}
              precision={1}
            />
          );
        }
        return v != null
          ? <Tag color="warning">{v}{row.unit || ''}</Tag>
          : <Text type="secondary">未设置</Text>;
      },
    },
    {
      title: (
        <Space>
          <WarningOutlined style={{ color: '#f5222d' }} />
          超标阈值
        </Space>
      ),
      dataIndex: 'critical_threshold',
      width:     140,
      render:    (v: number | null, row: KPIItem) => {
        const editing = editRows[row.id];
        if (editing) {
          return (
            <InputNumber
              value={editing.critical_threshold ?? undefined}
              onChange={val => setEditRows(prev => ({
                ...prev,
                [row.id]: { ...prev[row.id], critical_threshold: val ?? null },
              }))}
              style={{ width: 110 }}
              suffix={row.unit || undefined}
              step={0.1}
              precision={1}
            />
          );
        }
        return v != null
          ? <Tag color="error">{v}{row.unit || ''}</Tag>
          : <Text type="secondary">未设置</Text>;
      },
    },
    {
      title:  '操作',
      width:  120,
      render: (_: any, row: KPIItem) => {
        const editing = editRows[row.id];
        if (editing) {
          return (
            <Space>
              <Tooltip title="保存">
                <Button
                  type="primary"
                  size="small"
                  icon={<SaveOutlined />}
                  loading={saving === row.id}
                  onClick={() => saveThreshold(row.id)}
                />
              </Tooltip>
              <Tooltip title="取消">
                <Button
                  size="small"
                  icon={<CloseOutlined />}
                  onClick={() => cancelEdit(row.id)}
                />
              </Tooltip>
            </Space>
          );
        }
        return (
          <Tooltip title="编辑阈值">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => startEdit(row)}
            />
          </Tooltip>
        );
      },
    },
  ];

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <BellOutlined style={{ marginRight: 8 }} />
        异常告警阈值配置
      </Title>

      <Alert
        message="配置说明"
        description="超过「警告阈值」时系统发送橙色告警推送；超过「超标阈值」时发送红色紧急推送并推送至企业微信。阈值调整立即生效。"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Card>
        <Spin spinning={loading}>
          <Table
            dataSource={kpis}
            columns={columns}
            rowKey="id"
            pagination={{ pageSize: 20, hideOnSinglePage: true }}
            size="small"
            rowClassName={(row) =>
              editRows[row.id] ? 'ant-table-row-selected' : ''
            }
          />
        </Spin>
      </Card>
    </div>
  );
};

export default AlertThresholdsPage;
