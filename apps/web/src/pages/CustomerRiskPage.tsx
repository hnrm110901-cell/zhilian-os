/**
 * 客户风控面板 — Phase P1 (客必得能力)
 * 客户归属管理 · 离职交接 · 流失预警
 */
import React, { useEffect, useState } from 'react';
import {
  Card, Row, Col, Table, Statistic, Tabs, Tag, Button, Modal, Form,
  Input, Select, Spin, Alert, Typography, Space, message, Tooltip, Badge,
} from 'antd';
import {
  SafetyOutlined, SwapOutlined, WarningOutlined, UserOutlined,
  PhoneOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';

const { Title, Text } = Typography;

interface Ownership {
  id: string;
  customer_phone: string;
  customer_name: string;
  owner_employee_id: string;
  customer_level: string | null;
  total_visits: number;
  total_spent_yuan: number;
  last_visit_at: string | null;
  assigned_at: string;
}

interface RiskAlert {
  id: string;
  customer_phone: string;
  customer_name: string;
  risk_level: string;
  risk_type: string;
  risk_score: number;
  last_visit_days: number;
  predicted_churn_probability: number;
  suggested_action: string;
  suggested_offer: string;
  action_taken: boolean;
  is_resolved: boolean;
  created_at: string;
}

interface EmployeeStat {
  employee_id: string;
  customer_count: number;
  total_revenue_yuan: number;
  avg_visits: number;
}

const RISK_COLORS: Record<string, string> = { high: 'red', medium: 'orange', low: 'blue' };
const RISK_LABELS: Record<string, string> = { high: '高风险', medium: '中风险', low: '低风险' };
const LEVEL_COLORS: Record<string, string> = { VIP: 'gold', GOLD: 'orange', SILVER: 'blue', NORMAL: 'default' };
const RISK_TYPE_LABELS: Record<string, string> = {
  dormant: '沉睡客户',
  declining: '消费下降',
  competitor_lost: '疑似流失',
  negative_feedback: '差评投诉',
};

export default function CustomerRiskPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [storeId] = useState(localStorage.getItem('store_id') || '');
  const [activeTab, setActiveTab] = useState('alerts');

  // 数据
  const [alerts, setAlerts] = useState<RiskAlert[]>([]);
  const [ownerships, setOwnerships] = useState<Ownership[]>([]);
  const [employeeStats, setEmployeeStats] = useState<EmployeeStat[]>([]);

  // Modal
  const [transferVisible, setTransferVisible] = useState(false);
  const [transferForm] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const [alertData, ownerData, statsData] = await Promise.all([
        apiClient.get<RiskAlert[]>(`/api/v1/customer-risk/alerts?store_id=${storeId}`),
        apiClient.get<Ownership[]>(`/api/v1/customer-ownership?store_id=${storeId}`),
        apiClient.get<EmployeeStat[]>(`/api/v1/customer-ownership/stats?store_id=${storeId}`),
      ]);
      setAlerts(alertData);
      setOwnerships(ownerData);
      setEmployeeStats(statsData);
    } catch (e: any) {
      setError(e?.message ?? '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleScan = async () => {
    try {
      const result = await apiClient.post<any>(`/api/v1/customer-risk/scan?store_id=${storeId}`);
      message.success(`扫描完成: 新增${result.alerts_created}条预警`);
      fetchData();
    } catch {
      message.error('扫描失败');
    }
  };

  const handleResolve = async (alertId: string) => {
    try {
      await apiClient.patch(`/api/v1/customer-risk/alerts/${alertId}/resolve`, {
        action_result: '已联系客户，发送优惠券',
      });
      message.success('已标记处理');
      fetchData();
    } catch {
      message.error('操作失败');
    }
  };

  const handleTransfer = async () => {
    try {
      const values = await transferForm.validateFields();
      await apiClient.post('/api/v1/customer-ownership/transfer', {
        store_id: storeId,
        ...values,
      });
      message.success('交接完成');
      setTransferVisible(false);
      transferForm.resetFields();
      fetchData();
    } catch {
      message.error('交接失败');
    }
  };

  // ── 预警表格列 ──
  const alertColumns = [
    {
      title: '客户',
      key: 'customer',
      render: (_: unknown, r: RiskAlert) => (
        <Space direction="vertical" size={0}>
          <Text strong>{r.customer_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}><PhoneOutlined /> {r.customer_phone}</Text>
        </Space>
      ),
    },
    {
      title: '风险',
      key: 'risk',
      render: (_: unknown, r: RiskAlert) => (
        <Space>
          <Tag color={RISK_COLORS[r.risk_level]}>{RISK_LABELS[r.risk_level]}</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>{RISK_TYPE_LABELS[r.risk_type]}</Text>
        </Space>
      ),
    },
    {
      title: '未到店',
      dataIndex: 'last_visit_days',
      key: 'days',
      render: (v: number) => <Text type={v >= 60 ? 'danger' : 'warning'}>{v}天</Text>,
      sorter: (a: RiskAlert, b: RiskAlert) => a.last_visit_days - b.last_visit_days,
    },
    {
      title: '流失概率',
      dataIndex: 'predicted_churn_probability',
      key: 'prob',
      render: (v: number) => (
        <Text style={{ color: v >= 0.7 ? '#ff4d4f' : v >= 0.4 ? '#faad14' : '#52c41a' }}>
          {(v * 100).toFixed(0)}%
        </Text>
      ),
    },
    {
      title: 'AI建议',
      dataIndex: 'suggested_action',
      key: 'action',
      ellipsis: true,
      width: 250,
      render: (v: string) => <Tooltip title={v}><Text style={{ fontSize: 12 }}>{v}</Text></Tooltip>,
    },
    {
      title: '操作',
      key: 'ops',
      render: (_: unknown, r: RiskAlert) =>
        r.is_resolved ? (
          <Tag color="success"><CheckCircleOutlined /> 已处理</Tag>
        ) : (
          <Button size="small" type="primary" onClick={() => handleResolve(r.id)}>
            标记处理
          </Button>
        ),
    },
  ];

  // ── 归属表格列 ──
  const ownerColumns = [
    {
      title: '客户',
      key: 'customer',
      render: (_: unknown, r: Ownership) => (
        <Space>
          <Text strong>{r.customer_name}</Text>
          {r.customer_level && <Tag color={LEVEL_COLORS[r.customer_level]}>{r.customer_level}</Tag>}
        </Space>
      ),
    },
    { title: '手机号', dataIndex: 'customer_phone', key: 'phone' },
    { title: '归属销售', dataIndex: 'owner_employee_id', key: 'owner' },
    { title: '到店次数', dataIndex: 'total_visits', key: 'visits', sorter: (a: Ownership, b: Ownership) => a.total_visits - b.total_visits },
    {
      title: '累计消费',
      dataIndex: 'total_spent_yuan',
      key: 'spent',
      render: (v: number) => <Text strong>¥{v.toFixed(2)}</Text>,
      sorter: (a: Ownership, b: Ownership) => a.total_spent_yuan - b.total_spent_yuan,
    },
  ];

  // ── 销售统计列 ──
  const statColumns = [
    { title: '销售ID', dataIndex: 'employee_id', key: 'id' },
    { title: '客户数', dataIndex: 'customer_count', key: 'count' },
    {
      title: '总消费',
      dataIndex: 'total_revenue_yuan',
      key: 'revenue',
      render: (v: number) => <Text strong>¥{v.toFixed(2)}</Text>,
    },
    {
      title: '平均到店',
      dataIndex: 'avg_visits',
      key: 'avg',
      render: (v: number) => `${v}次`,
    },
  ];

  if (error) return <Alert type="error" message={error} />;

  const highRisk = alerts.filter(a => a.risk_level === 'high' && !a.is_resolved).length;
  const unresolvedCount = alerts.filter(a => !a.is_resolved).length;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <SafetyOutlined /> 客户风控
        </Title>
        <Space>
          <Button icon={<SwapOutlined />} onClick={() => setTransferVisible(true)}>
            客户交接
          </Button>
          <Button type="primary" icon={<WarningOutlined />} onClick={handleScan}>
            扫描风险
          </Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {/* 统计卡片 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="客户总数" value={ownerships.length} suffix="人" />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="未处理预警"
                value={unresolvedCount}
                suffix="条"
                valueStyle={{ color: unresolvedCount > 0 ? '#cf1322' : '#3f8600' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="高风险客户"
                value={highRisk}
                suffix="人"
                valueStyle={{ color: highRisk > 0 ? '#cf1322' : '#3f8600' }}
                prefix={<WarningOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="销售团队" value={employeeStats.length} suffix="人" prefix={<UserOutlined />} />
            </Card>
          </Col>
        </Row>

        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'alerts',
            label: <Badge count={unresolvedCount} offset={[10, 0]}>流失预警</Badge>,
            children: (
              <Table
                dataSource={alerts}
                columns={alertColumns}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 10 }}
              />
            ),
          },
          {
            key: 'ownership',
            label: '客户归属',
            children: (
              <Table
                dataSource={ownerships}
                columns={ownerColumns}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 15 }}
              />
            ),
          },
          {
            key: 'stats',
            label: '销售统计',
            children: (
              <Table
                dataSource={employeeStats}
                columns={statColumns}
                rowKey="employee_id"
                size="small"
                pagination={false}
              />
            ),
          },
        ]} />
      </Spin>

      {/* 客户交接 Modal */}
      <Modal
        title="客户批量交接"
        open={transferVisible}
        onOk={handleTransfer}
        onCancel={() => setTransferVisible(false)}
        okText="确认交接"
      >
        <Alert
          type="warning"
          message="交接后，原销售的所有活跃客户将转移给新销售"
          style={{ marginBottom: 16 }}
        />
        <Form form={transferForm} layout="vertical">
          <Form.Item name="from_employee_id" label="原归属人" rules={[{ required: true }]}>
            <Input placeholder="输入离职/调岗员工ID" />
          </Form.Item>
          <Form.Item name="to_employee_id" label="接收人" rules={[{ required: true }]}>
            <Input placeholder="输入接收员工ID" />
          </Form.Item>
          <Form.Item name="reason" label="交接原因" initialValue="resignation">
            <Select options={[
              { value: 'resignation', label: '离职' },
              { value: 'reorg', label: '组织调整' },
              { value: 'manual', label: '手动转移' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
