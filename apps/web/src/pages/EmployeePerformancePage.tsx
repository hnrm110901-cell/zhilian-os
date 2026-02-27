import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Select, Statistic, Table, Tag, Button,
  Typography, Space, Spin, Modal, Form, InputNumber, Input, DatePicker,
  Progress, Badge,
} from 'antd';
import { TrophyOutlined, ReloadOutlined, PlusOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Title, Text } = Typography;
const { Option } = Select;

const EmployeePerformancePage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState('STORE001');
  const [employees, setEmployees] = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [recordModal, setRecordModal] = useState(false);
  const [selectedEmp, setSelectedEmp] = useState<string | undefined>(undefined);
  const [form] = Form.useForm();

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [empRes, lbRes] = await Promise.all([
        apiClient.get('/employees', { params: { store_id: storeId } }),
        apiClient.get('/employees/performance/leaderboard', { params: { store_id: storeId } }),
      ]);
      setEmployees(empRes.data || []);
      setLeaderboard(lbRes.data?.leaderboard || []);
    } catch (err: any) {
      handleApiError(err, '加载数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadData(); }, [loadData]);

  const submitPerformance = async (values: any) => {
    try {
      await apiClient.post(`/employees/${selectedEmp}/performance`, {
        ...values,
        period: values.period?.format('YYYY-MM') || '',
      });
      showSuccess('绩效已录入');
      setRecordModal(false);
      form.resetFields();
      loadData();
    } catch (err: any) {
      handleApiError(err, '录入失败');
    }
  };

  const rankColor = (rank: number) => {
    if (rank === 1) return '#ffd700';
    if (rank === 2) return '#c0c0c0';
    if (rank === 3) return '#cd7f32';
    return undefined;
  };

  const lbColumns = [
    {
      title: '排名',
      dataIndex: 'rank',
      width: 60,
      render: (v: number) => (
        <span style={{ fontWeight: 'bold', color: rankColor(v) }}>
          {v <= 3 ? ['🥇', '🥈', '🥉'][v - 1] : v}
        </span>
      ),
    },
    { title: '姓名', dataIndex: 'name' },
    { title: '岗位', dataIndex: 'position', render: (v: string) => v || '-' },
    {
      title: '综合评分',
      dataIndex: 'performance_score',
      render: (v: number) => (
        <Progress
          percent={v}
          size="small"
          status={v >= 80 ? 'success' : v >= 60 ? 'normal' : 'exception'}
          format={(p) => `${p}`}
        />
      ),
    },
  ];

  const empColumns = [
    { title: '姓名', dataIndex: 'name' },
    { title: '岗位', dataIndex: 'position', render: (v: string) => v || '-' },
    {
      title: '当前评分',
      dataIndex: 'performance_score',
      render: (v: string) => v
        ? <Tag color={parseFloat(v) >= 80 ? 'green' : parseFloat(v) >= 60 ? 'orange' : 'red'}>{v}</Tag>
        : <Badge status="default" text="未评分" />,
    },
    { title: '状态', dataIndex: 'is_active', render: (v: boolean) => v ? <Tag color="green">在职</Tag> : <Tag>离职</Tag> },
    {
      title: '操作',
      render: (_: any, record: any) => (
        <Button
          size="small"
          icon={<PlusOutlined />}
          onClick={() => { setSelectedEmp(record.id); setRecordModal(true); }}
        >
          录入绩效
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}><TrophyOutlined /> 员工绩效看板</Title>
        <Space>
          <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
            {stores.length > 0
              ? stores.map((s: any) => <Option key={s.id || s.store_id} value={s.id || s.store_id}>{s.name}</Option>)
              : <Option value="STORE001">STORE001</Option>}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card>
              <Statistic title="在职员工" value={employees.filter((e: any) => e.is_active).length} suffix="人" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="已评分员工" value={leaderboard.length} suffix="人" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="平均评分"
                value={leaderboard.length > 0
                  ? (leaderboard.reduce((s: number, e: any) => s + e.performance_score, 0) / leaderboard.length).toFixed(1)
                  : '--'}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="Top 员工"
                value={leaderboard[0]?.name || '--'}
                suffix={leaderboard[0] ? `(${leaderboard[0].performance_score})` : ''}
              />
            </Card>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={10}>
            <Card title="绩效排行榜">
              <Table
                dataSource={leaderboard}
                columns={lbColumns}
                rowKey="employee_id"
                pagination={false}
                size="small"
              />
            </Card>
          </Col>
          <Col span={14}>
            <Card title="员工列表">
              <Table
                dataSource={employees}
                columns={empColumns}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 10 }}
              />
            </Card>
          </Col>
        </Row>
      </Spin>

      <Modal
        title="录入员工绩效"
        open={recordModal}
        onCancel={() => setRecordModal(false)}
        footer={null}
      >
        <Form form={form} layout="vertical" onFinish={submitPerformance}>
          <Form.Item name="period" label="考核周期" rules={[{ required: true }]}>
            <DatePicker picker="month" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="attendance_rate" label="出勤率 (0-100)">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="customer_rating" label="顾客评分 (1-5)">
            <InputNumber min={1} max={5} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="efficiency_score" label="效率评分 (0-100)">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="sales_amount" label="销售额 (元)">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>提交</Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default EmployeePerformancePage;
