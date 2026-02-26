import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Statistic, Row, Col, Modal, Input, Tabs } from 'antd';
import { CheckOutlined, CloseOutlined, EditOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { TextArea } = Input;

const statusColor: Record<string, string> = { pending: 'orange', approved: 'green', rejected: 'red', modified: 'blue' };
const statusLabel: Record<string, string> = { pending: '待审批', approved: '已批准', rejected: '已拒绝', modified: '已修改' };

const ApprovalManagementPage: React.FC = () => {
  const [approvals, setApprovals] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalType, setModalType] = useState<'approve' | 'reject' | 'modify'>('approve');
  const [currentItem, setCurrentItem] = useState<any>(null);
  const [reason, setReason] = useState('');
  const [storeFilter, setStoreFilter] = useState('');

  const loadApprovals = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { status: 'pending' };
      if (storeFilter) params.store_id = storeFilter;
      const res = await apiClient.get('/approvals', { params });
      setApprovals(res.data?.approvals || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载审批列表失败');
    } finally {
      setLoading(false);
    }
  }, [storeFilter]);

  const loadStats = useCallback(async () => {
    try {
      const res = await apiClient.get('/approvals/statistics');
      setStats(res.data);
    } catch (err: any) {
      handleApiError(err, '加载统计数据失败');
    }
  }, []);

  useEffect(() => {
    loadApprovals();
    loadStats();
  }, [loadApprovals, loadStats]);

  const openModal = (item: any, type: 'approve' | 'reject' | 'modify') => {
    setCurrentItem(item);
    setModalType(type);
    setReason('');
    setModalVisible(true);
  };

  const submitAction = async () => {
    const id = currentItem?.decision_id || currentItem?.id;
    setSubmitting(true);
    try {
      if (modalType === 'approve') {
        await apiClient.post(`/approvals/${id}/approve`, { reason });
        showSuccess('已批准');
      } else if (modalType === 'reject') {
        await apiClient.post(`/approvals/${id}/reject`, { reason });
        showSuccess('已拒绝');
      } else {
        await apiClient.post(`/approvals/${id}/modify`, { modified_decision: reason });
        showSuccess('已修改');
      }
      setModalVisible(false);
      loadApprovals();
      loadStats();
    } catch (err: any) {
      handleApiError(err, '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<any> = [
    { title: '决策ID', dataIndex: 'decision_id', key: 'decision_id', ellipsis: true },
    { title: '门店', dataIndex: 'store_id', key: 'store_id' },
    { title: '决策类型', dataIndex: 'decision_type', key: 'decision_type' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '置信度', dataIndex: 'confidence', key: 'confidence', render: (v: number) => v ? `${(v * 100).toFixed(0)}%` : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={statusColor[v] || 'default'}>{statusLabel[v] || v}</Tag> },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => record.status === 'pending' ? (
        <Space>
          <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => openModal(record, 'approve')}>批准</Button>
          <Button size="small" danger icon={<CloseOutlined />} onClick={() => openModal(record, 'reject')}>拒绝</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openModal(record, 'modify')}>修改</Button>
        </Space>
      ) : null,
    },
  ];

  const tabItems = [
    {
      key: 'pending', label: '待审批',
      children: (
        <div>
          <div style={{ marginBottom: 12 }}>
            <Space>
              <span>门店筛选：</span>
              <Input placeholder="输入门店ID" value={storeFilter} onChange={e => setStoreFilter(e.target.value)} style={{ width: 160 }} allowClear />
              <Button onClick={loadApprovals}>查询</Button>
            </Space>
          </div>
          <Table columns={columns} dataSource={approvals} rowKey={(r) => r.decision_id || r.id} loading={loading} />
        </div>
      ),
    },
    {
      key: 'stats', label: '统计数据',
      children: stats ? (
        <Row gutter={16}>
          <Col span={6}><Card><Statistic title="总审批数" value={stats.total || 0} /></Card></Col>
          <Col span={6}><Card><Statistic title="批准率" value={((stats.approval_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
          <Col span={6}><Card><Statistic title="拒绝率" value={((stats.rejection_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
          <Col span={6}><Card><Statistic title="修改率" value={((stats.modification_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
        </Row>
      ) : <Card loading />,
    },
  ];

  const modalTitle = { approve: '批准决策', reject: '拒绝决策', modify: '修改决策' }[modalType];
  const modalLabel = { approve: '批准原因（可选）', reject: '拒绝原因', modify: '修改后的决策内容' }[modalType];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="待审批" value={approvals.length} /></Card></Col>
        <Col span={6}><Card><Statistic title="总审批数" value={stats?.total || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="批准率" value={((stats?.approval_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
        <Col span={6}><Card><Statistic title="修改率" value={((stats?.modification_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
      </Row>

      <Card><Tabs items={tabItems} /></Card>

      <Modal title={modalTitle} open={modalVisible} onCancel={() => setModalVisible(false)} onOk={submitAction} okText="确认" confirmLoading={submitting}>
        <p>决策类型：{currentItem?.decision_type}</p>
        <p>描述：{currentItem?.description}</p>
        <div style={{ marginTop: 12 }}>
          <div style={{ marginBottom: 4 }}>{modalLabel}：</div>
          <TextArea rows={3} value={reason} onChange={e => setReason(e.target.value)} />
        </div>
      </Modal>
    </div>
  );
};

export default ApprovalManagementPage;
