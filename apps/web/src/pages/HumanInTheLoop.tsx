import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Card, Col, Row, Table, Tabs, Statistic, Button, Modal, Input, Tag, Progress, Space } from 'antd';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { TextArea } = Input;

const riskColor: Record<string, string> = { high: 'red', medium: 'orange', low: 'green' };
const riskLabel: Record<string, string> = { high: '高', medium: '中', low: '低' };

const HumanInTheLoop: React.FC = () => {
  const [selectedStore] = useState('STORE001');
  const [pending, setPending] = useState<any[]>([]);
  const [trustPhase, setTrustPhase] = useState<any>(null);
  const [trustMetrics, setTrustMetrics] = useState<any>(null);
  const [riskRules, setRiskRules] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [currentRequest, setCurrentRequest] = useState<any>(null);
  const [approving, setApproving] = useState(true);
  const [comment, setComment] = useState('');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadPending = useCallback(async () => {
    try {
      const res = await apiClient.get(`/human-in-the-loop/pending-approvals/${selectedStore}`);
      setPending(res.data?.approvals || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载待审批列表失败');
    }
  }, [selectedStore]);

  const loadTrustData = useCallback(async () => {
    setLoading(true);
    try {
      const [phase, metrics, rules] = await Promise.allSettled([
        apiClient.get(`/human-in-the-loop/trust-phase/${selectedStore}`),
        apiClient.get(`/human-in-the-loop/trust-metrics/${selectedStore}`),
        apiClient.get('/human-in-the-loop/risk-classification'),
      ]);
      if (phase.status === 'fulfilled') setTrustPhase(phase.value.data);
      if (metrics.status === 'fulfilled') setTrustMetrics(metrics.value.data);
      if (rules.status === 'fulfilled') setRiskRules(rules.value.data?.rules || rules.value.data || []);
    } catch (err: any) {
      handleApiError(err, '加载信任数据失败');
    } finally {
      setLoading(false);
    }
  }, [selectedStore]);

  useEffect(() => {
    loadPending();
    loadTrustData();
    intervalRef.current = setInterval(loadPending, 30000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadPending, loadTrustData]);

  const openApproveModal = (record: any, approve: boolean) => {
    setCurrentRequest(record);
    setApproving(approve);
    setComment('');
    setModalVisible(true);
  };

  const submitApproval = async () => {
    try {
      await apiClient.post('/human-in-the-loop/approve', {
        request_id: currentRequest?.request_id || currentRequest?.id,
        approved: approving,
        comment,
      });
      showSuccess(approving ? '已批准' : '已拒绝');
      setModalVisible(false);
      loadPending();
    } catch (err: any) {
      handleApiError(err, '操作失败');
    }
  };

  const pendingColumns: ColumnsType<any> = [
    { title: '操作类型', dataIndex: 'action_type', key: 'action_type' },
    { title: '风险等级', dataIndex: 'risk_level', key: 'risk_level', render: (v: string) => <Tag color={riskColor[v] || 'default'}>{riskLabel[v] || v}</Tag> },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '置信度', dataIndex: 'confidence', key: 'confidence', render: (v: number) => `${((v || 0) * 100).toFixed(0)}%` },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => openApproveModal(record, true)}>批准</Button>
          <Button size="small" danger icon={<CloseOutlined />} onClick={() => openApproveModal(record, false)}>拒绝</Button>
        </Space>
      ),
    },
  ];

  const riskColumns: ColumnsType<any> = [
    { title: '风险等级', dataIndex: 'risk_level', key: 'risk_level', render: (v: string) => <Tag color={riskColor[v] || 'default'}>{riskLabel[v] || v}</Tag> },
    { title: '操作类型', dataIndex: 'action_type', key: 'action_type' },
    { title: '处理方式', dataIndex: 'handling', key: 'handling' },
  ];

  const tabItems = [
    {
      key: 'pending', label: '待审批列表',
      children: <Table columns={pendingColumns} dataSource={pending} rowKey={(r) => r.request_id || r.id} loading={loading} />,
    },
    {
      key: 'trust', label: '信任指标',
      children: (
        <div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}><Card><Statistic title="采纳率" value={((trustMetrics?.adoption_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
            <Col span={8}><Card><Statistic title="成功率" value={((trustMetrics?.success_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
            <Col span={8}><Card><Statistic title="升级率" value={((trustMetrics?.escalation_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
          </Row>
          <Card title="自主率进度">
            <Progress percent={Math.round((trustMetrics?.autonomy_rate || 0) * 100)} status="active" />
          </Card>
        </div>
      ),
    },
    {
      key: 'risk', label: '风险分类',
      children: <Table columns={riskColumns} dataSource={riskRules} rowKey={(r, i) => `${r.risk_level}-${i}`} />,
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="待审批数" value={pending.length} /></Card></Col>
        <Col span={6}><Card><Statistic title="信任阶段" value={trustPhase?.phase ?? '--'} /></Card></Col>
        <Col span={6}><Card><Statistic title="自主率" value={((trustMetrics?.autonomy_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
        <Col span={6}><Card><Statistic title="成功率" value={((trustMetrics?.success_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
      </Row>

      <Card><Tabs items={tabItems} /></Card>

      <Modal
        title={approving ? '确认批准' : '确认拒绝'}
        open={modalVisible}
        onOk={submitApproval}
        onCancel={() => setModalVisible(false)}
        okText={approving ? '批准' : '拒绝'}
        okButtonProps={{ danger: !approving }}
      >
        <p>{currentRequest?.description}</p>
        <TextArea rows={3} placeholder="备注（可选）" value={comment} onChange={(e) => setComment(e.target.value)} />
      </Modal>
    </div>
  );
};

export default HumanInTheLoop;
