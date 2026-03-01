import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Row, Col, Statistic, Table, Tag, Select, Progress,
  Divider, Space, Button,
} from 'antd';
import { ReloadOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const DECISION_TYPE_LABEL: Record<string, string> = {
  inventory_adjustment: '库存调整',
  price_change: '价格变更',
  staff_scheduling: '排班调整',
  promotion: '促销决策',
  menu_change: '菜单变更',
  supplier_change: '供应商变更',
};

interface DecisionStats {
  total: number;
  pending: number;
  approved: number;
  rejected: number;
  modified: number;
  approval_rate: number;
  rejection_rate: number;
  modification_rate: number;
  avg_confidence: number;
  by_type?: Array<{ decision_type: string; count: number; approval_rate: number }>;
  by_store?: Array<{ store_id: string; count: number; approval_rate: number; pending: number }>;
  recent_decisions?: Array<{
    decision_id: string;
    store_id: string;
    decision_type: string;
    status: string;
    confidence: number;
    created_at: string;
  }>;
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'orange',
  approved: 'green',
  rejected: 'red',
  modified: 'blue',
};
const STATUS_LABEL: Record<string, string> = {
  pending: '待审批',
  approved: '已批准',
  rejected: '已拒绝',
  modified: '已修改',
};

const DecisionStatisticsDashboard: React.FC = () => {
  const [stats, setStats] = useState<DecisionStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState<string>('30d');

  const loadStats = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/approvals/statistics', {
        params: { period },
      });
      setStats(res.data);
    } catch (err: any) {
      handleApiError(err, '加载统计数据失败');
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const byTypeColumns: ColumnsType<any> = [
    {
      title: '决策类型',
      dataIndex: 'decision_type',
      key: 'decision_type',
      render: (v: string) => DECISION_TYPE_LABEL[v] || v,
    },
    { title: '总数', dataIndex: 'count', key: 'count', width: 80 },
    {
      title: '批准率',
      dataIndex: 'approval_rate',
      key: 'approval_rate',
      width: 200,
      render: (v: number) => (
        <Space>
          <Progress
            percent={Math.round((v || 0) * 100)}
            size="small"
            style={{ width: 120 }}
            strokeColor={v >= 0.7 ? '#52c41a' : v >= 0.4 ? '#fa8c16' : '#ff4d4f'}
          />
          <span>{((v || 0) * 100).toFixed(1)}%</span>
        </Space>
      ),
    },
  ];

  const byStoreColumns: ColumnsType<any> = [
    { title: '门店ID', dataIndex: 'store_id', key: 'store_id', width: 140 },
    { title: '总决策数', dataIndex: 'count', key: 'count', width: 90 },
    {
      title: '待审批',
      dataIndex: 'pending',
      key: 'pending',
      width: 80,
      render: (v: number) => v > 0 ? <Tag color="orange">{v}</Tag> : <span>0</span>,
    },
    {
      title: '批准率',
      dataIndex: 'approval_rate',
      key: 'approval_rate',
      width: 180,
      render: (v: number) => (
        <Space>
          <Progress
            percent={Math.round((v || 0) * 100)}
            size="small"
            style={{ width: 100 }}
            strokeColor={v >= 0.7 ? '#52c41a' : v >= 0.4 ? '#fa8c16' : '#ff4d4f'}
          />
          <span>{((v || 0) * 100).toFixed(1)}%</span>
        </Space>
      ),
    },
  ];

  const recentColumns: ColumnsType<any> = [
    {
      title: '决策ID',
      dataIndex: 'decision_id',
      key: 'decision_id',
      ellipsis: true,
      width: 140,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v?.slice(0, 14)}…</span>,
    },
    { title: '门店', dataIndex: 'store_id', key: 'store_id', width: 110 },
    {
      title: '类型',
      dataIndex: 'decision_type',
      key: 'decision_type',
      width: 110,
      render: (v: string) => DECISION_TYPE_LABEL[v] || v,
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 80,
      render: (v: number) => v != null ? `${(v * 100).toFixed(0)}%` : '—',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string) => <Tag color={STATUS_COLOR[v] || 'default'}>{STATUS_LABEL[v] || v}</Tag>,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—',
    },
  ];

  const approvalRate = (stats?.approval_rate || 0) * 100;
  const rejectionRate = (stats?.rejection_rate || 0) * 100;
  const modificationRate = (stats?.modification_rate || 0) * 100;
  const avgConfidence = (stats?.avg_confidence || 0) * 100;

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontSize: 16, fontWeight: 600 }}>决策统计看板</span>
        <Space>
          <span>时间范围：</span>
          <Select value={period} onChange={setPeriod} style={{ width: 100 }}>
            <Select.Option value="7d">近7天</Select.Option>
            <Select.Option value="30d">近30天</Select.Option>
            <Select.Option value="90d">近90天</Select.Option>
            <Select.Option value="all">全部</Select.Option>
          </Select>
          <Button icon={<ReloadOutlined />} onClick={loadStats} loading={loading}>刷新</Button>
        </Space>
      </div>

      {/* KPI cards */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card loading={loading} size="small">
            <Statistic title="总决策数" value={stats?.total || 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={loading} size="small">
            <Statistic title="待审批" value={stats?.pending || 0} valueStyle={{ color: '#fa8c16' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={loading} size="small">
            <Statistic
              title="批准率"
              value={approvalRate.toFixed(1)}
              suffix="%"
              valueStyle={{ color: '#52c41a' }}
              prefix={<ArrowUpOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={loading} size="small">
            <Statistic
              title="拒绝率"
              value={rejectionRate.toFixed(1)}
              suffix="%"
              valueStyle={{ color: '#ff4d4f' }}
              prefix={<ArrowDownOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={loading} size="small">
            <Statistic
              title="修改率"
              value={modificationRate.toFixed(1)}
              suffix="%"
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card loading={loading} size="small">
            <Statistic
              title="平均置信度"
              value={avgConfidence.toFixed(1)}
              suffix="%"
              valueStyle={{ color: avgConfidence >= 70 ? '#52c41a' : '#fa8c16' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Outcome distribution */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title="决策结果分布" loading={loading} size="small">
            <Space direction="vertical" style={{ width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 60 }}>已批准</span>
                <Progress
                  percent={Math.round(approvalRate)}
                  strokeColor="#52c41a"
                  style={{ flex: 1 }}
                />
                <span style={{ width: 40, textAlign: 'right' }}>{stats?.approved || 0}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 60 }}>已拒绝</span>
                <Progress
                  percent={Math.round(rejectionRate)}
                  strokeColor="#ff4d4f"
                  style={{ flex: 1 }}
                />
                <span style={{ width: 40, textAlign: 'right' }}>{stats?.rejected || 0}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 60 }}>已修改</span>
                <Progress
                  percent={Math.round(modificationRate)}
                  strokeColor="#1677ff"
                  style={{ flex: 1 }}
                />
                <span style={{ width: 40, textAlign: 'right' }}>{stats?.modified || 0}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 60 }}>待审批</span>
                <Progress
                  percent={stats?.total ? Math.round((stats.pending / stats.total) * 100) : 0}
                  strokeColor="#fa8c16"
                  style={{ flex: 1 }}
                />
                <span style={{ width: 40, textAlign: 'right' }}>{stats?.pending || 0}</span>
              </div>
            </Space>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="按决策类型统计" loading={loading} size="small">
            {stats?.by_type?.length ? (
              <Table
                dataSource={stats.by_type}
                columns={byTypeColumns}
                rowKey="decision_type"
                pagination={false}
                size="small"
              />
            ) : (
              <div style={{ textAlign: 'center', color: '#999', padding: '24px 0' }}>暂无数据</div>
            )}
          </Card>
        </Col>
      </Row>

      {/* By store */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <Card title="门店决策汇总" loading={loading} size="small">
            {stats?.by_store?.length ? (
              <Table
                dataSource={stats.by_store}
                columns={byStoreColumns}
                rowKey="store_id"
                pagination={{ pageSize: 10 }}
                size="small"
              />
            ) : (
              <div style={{ textAlign: 'center', color: '#999', padding: '24px 0' }}>暂无数据</div>
            )}
          </Card>
        </Col>
      </Row>

      {/* Recent decisions */}
      <Divider orientation="left" plain>最近决策记录</Divider>
      <Card loading={loading} size="small">
        {stats?.recent_decisions?.length ? (
          <Table
            dataSource={stats.recent_decisions}
            columns={recentColumns}
            rowKey="decision_id"
            pagination={{ pageSize: 10 }}
            size="small"
          />
        ) : (
          <div style={{ textAlign: 'center', color: '#999', padding: '24px 0' }}>暂无最近决策记录</div>
        )}
      </Card>
    </div>
  );
};

export default DecisionStatisticsDashboard;
