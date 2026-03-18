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
import { BookOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Title } = Typography;
const { RangePicker } = DatePicker;
const { Option } = Select;

const TrainingPage: React.FC = () => {
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState(localStorage.getItem('store_id') || '');
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().subtract(29, 'day'), dayjs()]);
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordVisible, setRecordVisible] = useState(false);
  const [statistics, setStatistics] = useState<any>(null);
  const [progress, setProgress] = useState<any[]>([]);
  const [needs, setNeeds] = useState<any[]>([]);
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
      // ignore and keep fallback
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, progressRes, needsRes] = await Promise.all([
        apiClient.callAgent('training', { action: 'get_training_statistics', params: dateParams }),
        apiClient.callAgent('training', { action: 'get_training_progress', params: dateParams }),
        apiClient.callAgent('training', { action: 'assess_training_needs', params: { store_id: storeId } }),
      ]);
      setStatistics(statsRes?.output_data?.data || null);
      setProgress(progressRes?.output_data?.data || []);
      setNeeds(needsRes?.output_data?.data || []);
    } catch (err: any) {
      handleApiError(err, '加载培训数据失败');
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
      await apiClient.callAgent('training', {
        action: 'record_training_completion',
        params: {
          store_id: storeId,
          staff_id: values.staff_id,
          course_name: values.course_name,
          completion_date: values.completion_date.format('YYYY-MM-DD'),
          score: values.score,
        },
      });
      showSuccess('培训完成记录已录入');
      setRecordVisible(false);
      recordForm.resetFields();
      loadData();
    } catch (err: any) {
      handleApiError(err, '录入失败');
    } finally {
      setRecording(false);
    }
  };

  const progressColumns = [
    { title: '员工ID', dataIndex: 'staff_id', key: 'staff_id' },
    { title: '课程', dataIndex: 'course_name', key: 'course_name' },
    { title: '完成日期', dataIndex: 'completion_date', key: 'completion_date' },
    {
      title: '分数',
      dataIndex: 'score',
      key: 'score',
      render: (v: number) => (v == null ? '-' : v),
    },
    {
      title: '结果',
      dataIndex: 'passed',
      key: 'passed',
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '通过' : '未通过'}</Tag>,
    },
  ];

  const needsColumns = [
    { title: '员工', dataIndex: 'staff_name', key: 'staff_name' },
    { title: '岗位', dataIndex: 'position', key: 'position', render: (v: string) => v || '-' },
    { title: '能力缺口', dataIndex: 'skill_gap', key: 'skill_gap' },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (v: string) => <Tag color={v === 'high' ? 'red' : v === 'medium' ? 'orange' : 'blue'}>{v || 'normal'}</Tag>,
    },
    {
      title: '建议课程',
      key: 'recommended_courses',
      render: (_: any, r: any) => (r.recommended_courses || []).join('、') || '-',
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}><BookOutlined /> 培训辅导 Agent</Title>
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
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setRecordVisible(true)}>录入培训</Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="培训总次数" value={statistics?.total_trainings ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="通过率" value={statistics?.pass_rate ?? 0} suffix="%" precision={2} /></Card></Col>
        <Col span={6}><Card><Statistic title="平均分" value={statistics?.average_score ?? 0} precision={2} /></Card></Col>
        <Col span={6}><Card><Statistic title="参与员工数" value={statistics?.unique_staff_count ?? 0} /></Card></Col>
      </Row>

      {needs.length > 0 && (
        <Alert
          style={{ marginBottom: 16 }}
          type="info"
          message={`当前识别到 ${needs.length} 条培训需求`}
          description="建议优先处理 high/medium 优先级的能力缺口。"
          showIcon
        />
      )}

      <Row gutter={16}>
        <Col span={14}>
          <Card title={`培训进度 (${progress.length})`}>
            <Table
              rowKey={(r) => r.record_id}
              columns={progressColumns}
              dataSource={progress}
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </Card>
        </Col>
        <Col span={10}>
          <Card title="培训需求评估">
            <Table
              rowKey={(r) => r.need_id}
              columns={needsColumns}
              dataSource={needs}
              loading={loading}
              pagination={{ pageSize: 8 }}
            />
          </Card>
        </Col>
      </Row>

      <Modal title="录入培训完成记录" open={recordVisible} onCancel={() => setRecordVisible(false)} footer={null}>
        <Form form={recordForm} layout="vertical" onFinish={submitRecord}>
          <Form.Item name="staff_id" label="员工ID" rules={[{ required: true }]}><Input placeholder="如 EMP001" /></Form.Item>
          <Form.Item name="course_name" label="课程名称" rules={[{ required: true }]}><Input placeholder="如 服务礼仪基础" /></Form.Item>
          <Form.Item name="completion_date" label="完成日期" rules={[{ required: true }]}><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="score" label="分数"><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" loading={recording} block>提交</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TrainingPage;
