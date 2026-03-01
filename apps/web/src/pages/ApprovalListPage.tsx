import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Table, Button, Tag, Space, Statistic, Row, Col, Input,
  Select, Drawer, Descriptions, Divider, Badge, DatePicker, Tooltip,
} from 'antd';
import { ReloadOutlined, EyeOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { RangePicker } = DatePicker;

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

const DECISION_TYPE_LABEL: Record<string, string> = {
  inventory_adjustment: '库存调整',
  price_change: '价格变更',
  staff_scheduling: '排班调整',
  promotion: '促销决策',
  menu_change: '菜单变更',
  supplier_change: '供应商变更',
};

interface Approval {
  id: string;
  decision_id: string;
  store_id: string;
  decision_type: string;
  description: string;
  confidence: number;
  status: string;
  reason?: string;
  modified_decision?: string;
  original_value?: any;
  suggested_value?: any;
  impact_level?: string;
  approved_by?: string;
  rejected_by?: string;
  created_at: string;
  updated_at: string;
}

const ApprovalListPage: React.FC = () => {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [storeFilter, setStoreFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [dateRange, setDateRange] = useState<[any, any] | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selected, setSelected] = useState<Approval | null>(null);

  const loadApprovals = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      if (storeFilter) params.store_id = storeFilter;
      if (typeFilter !== 'all') params.decision_type = typeFilter;
      if (dateRange) {
        params.start_date = dateRange[0]?.format('YYYY-MM-DD');
        params.end_date = dateRange[1]?.format('YYYY-MM-DD');
      }
      const res = await apiClient.get('/api/v1/approvals', { params });
      setApprovals(res.data?.approvals || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载审批列表失败');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, storeFilter, typeFilter, dateRange]);

  useEffect(() => {
    loadApprovals();
  }, [loadApprovals]);

  const openDetail = (record: Approval) => {
    setSelected(record);
    setDrawerOpen(true);
  };

  const counts = {
    all: approvals.length,
    pending: approvals.filter(a => a.status === 'pending').length,
    approved: approvals.filter(a => a.status === 'approved').length,
    rejected: approvals.filter(a => a.status === 'rejected').length,
    modified: approvals.filter(a => a.status === 'modified').length,
  };

  const columns: ColumnsType<Approval> = [
    {
      title: '决策ID',
      dataIndex: 'decision_id',
      key: 'decision_id',
      ellipsis: true,
      width: 180,
      render: (v: string) => <Tooltip title={v}><span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v?.slice(0, 16)}…</span></Tooltip>,
    },
    { title: '门店', dataIndex: 'store_id', key: 'store_id', width: 120 },
    {
      title: '决策类型',
      dataIndex: 'decision_type',
      key: 'decision_type',
      width: 120,
      render: (v: string) => DECISION_TYPE_LABEL[v] || v,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 80,
      render: (v: number) => v != null ? `${(v * 100).toFixed(0)}%` : '—',
      sorter: (a, b) => (a.confidence || 0) - (b.confidence || 0),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string) => <Tag color={STATUS_COLOR[v] || 'default'}>{STATUS_LABEL[v] || v}</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—',
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: any, record: Approval) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => openDetail(record)}>
          详情
        </Button>
      ),
    },
  ];

  return (
    <div>
      {/* Summary cards */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="全部" value={counts.all} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="待审批" value={counts.pending} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="已批准" value={counts.approved} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="已拒绝" value={counts.rejected} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="已修改" value={counts.modified} valueStyle={{ color: '#1677ff' }} /></Card></Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="批准率"
              value={counts.all ? ((counts.approved + counts.modified) / counts.all * 100).toFixed(1) : 0}
              suffix="%"
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>状态：</span>
          <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }}>
            <Select.Option value="all">全部</Select.Option>
            <Select.Option value="pending">待审批</Select.Option>
            <Select.Option value="approved">已批准</Select.Option>
            <Select.Option value="rejected">已拒绝</Select.Option>
            <Select.Option value="modified">已修改</Select.Option>
          </Select>
          <span>门店：</span>
          <Input
            placeholder="输入门店ID"
            value={storeFilter}
            onChange={e => setStoreFilter(e.target.value)}
            style={{ width: 160 }}
            allowClear
          />
          <span>类型：</span>
          <Select value={typeFilter} onChange={setTypeFilter} style={{ width: 130 }}>
            <Select.Option value="all">全部类型</Select.Option>
            {Object.entries(DECISION_TYPE_LABEL).map(([k, v]) => (
              <Select.Option key={k} value={k}>{v}</Select.Option>
            ))}
          </Select>
          <span>时间：</span>
          <RangePicker onChange={(v: any) => setDateRange(v)} />
          <Button icon={<ReloadOutlined />} onClick={loadApprovals}>刷新</Button>
        </Space>
      </Card>

      {/* Table */}
      <Card>
        <Table<Approval>
          columns={columns}
          dataSource={approvals}
          rowKey={r => r.decision_id || r.id}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: true, showQuickJumper: true }}
          size="small"
        />
      </Card>

      {/* Detail Drawer */}
      <Drawer
        title="审批详情"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={560}
      >
        {selected && (
          <>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="决策ID">
                <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{selected.decision_id}</span>
              </Descriptions.Item>
              <Descriptions.Item label="门店">{selected.store_id}</Descriptions.Item>
              <Descriptions.Item label="决策类型">
                {DECISION_TYPE_LABEL[selected.decision_type] || selected.decision_type}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Badge
                  color={STATUS_COLOR[selected.status]}
                  text={STATUS_LABEL[selected.status] || selected.status}
                />
              </Descriptions.Item>
              <Descriptions.Item label="置信度">
                {selected.confidence != null ? `${(selected.confidence * 100).toFixed(1)}%` : '—'}
              </Descriptions.Item>
              {selected.impact_level && (
                <Descriptions.Item label="影响级别">
                  <Tag color={selected.impact_level === 'high' ? 'red' : selected.impact_level === 'medium' ? 'orange' : 'blue'}>
                    {selected.impact_level === 'high' ? '高' : selected.impact_level === 'medium' ? '中' : '低'}
                  </Tag>
                </Descriptions.Item>
              )}
            </Descriptions>

            <Divider orientation="left" plain>决策描述</Divider>
            <p style={{ whiteSpace: 'pre-wrap' }}>{selected.description || '—'}</p>

            {(selected.original_value != null || selected.suggested_value != null) && (
              <>
                <Divider orientation="left" plain>数值变化</Divider>
                <Descriptions column={2} bordered size="small">
                  <Descriptions.Item label="原始值">
                    {JSON.stringify(selected.original_value)}
                  </Descriptions.Item>
                  <Descriptions.Item label="建议值">
                    {JSON.stringify(selected.suggested_value)}
                  </Descriptions.Item>
                </Descriptions>
              </>
            )}

            {selected.reason && (
              <>
                <Divider orientation="left" plain>审批意见</Divider>
                <p style={{ whiteSpace: 'pre-wrap' }}>{selected.reason}</p>
              </>
            )}

            {selected.modified_decision && (
              <>
                <Divider orientation="left" plain>修改后决策</Divider>
                <p style={{ whiteSpace: 'pre-wrap' }}>{selected.modified_decision}</p>
              </>
            )}

            <Divider orientation="left" plain>时间信息</Divider>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="创建时间">
                {selected.created_at ? new Date(selected.created_at).toLocaleString('zh-CN') : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {selected.updated_at ? new Date(selected.updated_at).toLocaleString('zh-CN') : '—'}
              </Descriptions.Item>
              {selected.approved_by && (
                <Descriptions.Item label="批准人">{selected.approved_by}</Descriptions.Item>
              )}
              {selected.rejected_by && (
                <Descriptions.Item label="拒绝人">{selected.rejected_by}</Descriptions.Item>
              )}
            </Descriptions>
          </>
        )}
      </Drawer>
    </div>
  );
};

export default ApprovalListPage;
