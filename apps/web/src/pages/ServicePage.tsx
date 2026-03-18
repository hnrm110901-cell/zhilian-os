import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Title } = Typography;
const { RangePicker } = DatePicker;
const { Option } = Select;

const ServicePage: React.FC = () => {
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState(localStorage.getItem('store_id') || '');
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().subtract(6, 'day'), dayjs()]);
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordVisible, setRecordVisible] = useState(false);
  const [metrics, setMetrics] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [staffPerformance, setStaffPerformance] = useState<any[]>([]);
  const [recordForm] = Form.useForm();

  const dateParams = {
    store_id: storeId,
    start_date: range[0].format('YYYY-MM-DD'),
    end_date: range[1].format('YYYY-MM-DD'),
  };

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res?.stores || res || []);
    } catch {
      // ignore and keep fallback STORE001
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [m, r, s] = await Promise.all([
        apiClient.callAgent('service', {
          action: 'get_service_quality_metrics',
          params: dateParams,
        }),
        apiClient.callAgent('service', {
          action: 'get_service_report',
          params: dateParams,
        }),
        apiClient.callAgent('service', {
          action: 'get_staff_performance',
          params: dateParams,
        }),
      ]);
      setMetrics(m?.output_data?.data || null);
      setReport(r?.output_data?.data || null);
      setStaffPerformance(s?.output_data?.data || []);
    } catch (err: any) {
      handleApiError(err, '加载服务质量数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, range]);

  useEffect(() => {
    loadStores();
  }, [loadStores]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const submitRecord = async (values: any) => {
    setRecording(true);
    try {
      await apiClient.callAgent('service', {
        action: 'record_service_quality',
        params: {
          ...dateParams,
          metric_name: values.metric_name,
          value: values.value,
          unit: values.unit || 'score',
          target_value: values.target_value,
          warning_threshold: values.warning_threshold,
          critical_threshold: values.critical_threshold,
          record_date: values.record_date?.format?.('YYYY-MM-DD'),
        },
      });
      showSuccess('服务质量指标录入成功');
      setRecordVisible(false);
      recordForm.resetFields();
      loadData();
    } catch (err: any) {
      handleApiError(err, '录入失败');
    } finally {
      setRecording(false);
    }
  };

  const staffColumns = [
    { title: '员工ID', dataIndex: 'staff_id', key: 'staff_id' },
    { title: '员工姓名', dataIndex: 'staff_name', key: 'staff_name' },
    { title: '岗位', dataIndex: 'position', key: 'position', render: (v: string) => v || '-' },
    {
      title: '服务次数',
      key: 'total_services',
      render: (_: any, r: any) => r?.metrics?.total_services ?? '-',
    },
    {
      title: '评分',
      key: 'customer_rating',
      render: (_: any, r: any) => r?.metrics?.customer_rating ?? '-',
    },
    {
      title: '综合分',
      dataIndex: 'performance_score',
      key: 'performance_score',
      render: (v: number) => (
        <Tag color={v >= 90 ? 'green' : v >= 75 ? 'orange' : 'red'}>{v ?? '-'} </Tag>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>服务质量 Agent</Title>
        <Space wrap>
          <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
            {stores.length > 0
              ? stores.map((s: any) => (
                  <Option key={s.id || s.store_id} value={s.id || s.store_id}>
                    {s.name || s.id || s.store_id}
                  </Option>
                ))
          </Select>
          <RangePicker
            value={range}
            onChange={(v) => v && v[0] && v[1] && setRange([v[0], v[1]])}
            allowClear={false}
          />
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadData}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setRecordVisible(true)}>
            录入指标
          </Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="服务质量分" value={metrics?.quality_score ?? 0} precision={2} /></Card></Col>
        <Col span={6}><Card><Statistic title="满意度" value={metrics?.satisfaction?.average_rating ?? 0} precision={2} /></Card></Col>
        <Col span={6}><Card><Statistic title="完成率" value={metrics?.service_metrics?.completion_rate ?? 0} suffix="%" precision={2} /></Card></Col>
        <Col span={6}><Card><Statistic title="平均服务时长" value={metrics?.service_metrics?.average_service_time_minutes ?? 0} suffix="分钟" precision={1} /></Card></Col>
      </Row>

      {report?.improvements?.length > 0 && (
        <Alert
          style={{ marginBottom: 16 }}
          type="warning"
          message="重点改进项"
          description={report.improvements.map((i: any) => `【${i.priority || 'normal'}】${i.issue}: ${i.recommendation}`).join('；')}
          showIcon
        />
      )}

      <Card title={`员工服务表现 (${staffPerformance.length})`}>
        <Table
          rowKey={(r) => r.staff_id}
          columns={staffColumns}
          dataSource={staffPerformance}
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal title="录入服务质量指标" open={recordVisible} onCancel={() => setRecordVisible(false)} footer={null}>
        <Form form={recordForm} layout="vertical" onFinish={submitRecord}>
          <Form.Item name="metric_name" label="指标名称" rules={[{ required: true }]}><Input placeholder="如：客户满意度" /></Form.Item>
          <Form.Item name="value" label="指标值" rules={[{ required: true }]}><InputNumber style={{ width: '100%' }} min={0} /></Form.Item>
          <Form.Item name="unit" label="单位"><Input placeholder="score/%/minutes" /></Form.Item>
          <Form.Item name="target_value" label="目标值"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item>
          <Form.Item name="warning_threshold" label="预警阈值"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item>
          <Form.Item name="critical_threshold" label="严重阈值"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item>
          <Form.Item name="record_date" label="记录日期"><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" loading={recording} block>提交</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ServicePage;
