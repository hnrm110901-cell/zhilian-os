import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Col, Row, Select, DatePicker, Tabs, Statistic, Table, Tag,
  Button, Form, InputNumber, Input, Space, Modal, Progress,
} from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { RangePicker } = DatePicker;

const statusColor: Record<string, string> = {
  on_track: 'green', at_risk: 'orange', off_track: 'red',
};
const statusLabel: Record<string, string> = {
  on_track: '达标', at_risk: '预警', off_track: '未达标',
};
const categoryColor: Record<string, string> = {
  revenue: 'blue', cost: 'orange', efficiency: 'green', quality: 'purple', customer: 'gold',
};
const categoryLabel: Record<string, string> = {
  revenue: '营收', cost: '成本', efficiency: '效率', quality: '质量', customer: '客户',
};

const KPIDashboardPage: React.FC = () => {
  const [kpis, setKpis] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [selectedKpi, setSelectedKpi] = useState<string | null>(null);
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [dateRange, setDateRange] = useState<[string, string]>([
    dayjs().subtract(30, 'day').format('YYYY-MM-DD'),
    dayjs().format('YYYY-MM-DD'),
  ]);
  const [loading, setLoading] = useState(false);
  const [addModal, setAddModal] = useState(false);
  const [addForm] = Form.useForm();
  const [editThresholdModal, setEditThresholdModal] = useState(false);
  const [editingKpi, setEditingKpi] = useState<any>(null);
  const [thresholdForm] = Form.useForm();

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) { handleApiError(err, '加载门店失败'); }
  }, []);

  const loadKpis = useCallback(async () => {
    try {
      const res = await apiClient.get('/kpis');
      setKpis(res.data || []);
      if (!selectedKpi && res.data?.length > 0) setSelectedKpi(res.data[0].id);
    } catch (err: any) { handleApiError(err, '加载KPI定义失败'); }
  }, [selectedKpi]);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/kpis/records/store', {
        params: { store_id: selectedStore, start_date: dateRange[0], end_date: dateRange[1] },
      });
      setRecords(res.data || []);
    } catch (err: any) { handleApiError(err, '加载KPI记录失败'); }
    finally { setLoading(false); }
  }, [selectedStore, dateRange]);

  useEffect(() => { loadStores(); loadKpis(); }, [loadStores, loadKpis]);
  useEffect(() => { loadRecords(); }, [loadRecords]);

  const addRecord = async (values: any) => {
    try {
      await apiClient.post('/kpis/records', {
        ...values,
        store_id: selectedStore,
        record_date: values.record_date?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'),
      });
      showSuccess('KPI数据已录入');
      setAddModal(false);
      addForm.resetFields();
      loadRecords();
    } catch (err: any) { handleApiError(err, '录入失败'); }
  };

  const openEditThreshold = (kpi: any) => {
    setEditingKpi(kpi);
    thresholdForm.setFieldsValue({
      target_value: kpi.target_value,
      warning_threshold: kpi.warning_threshold,
      critical_threshold: kpi.critical_threshold,
    });
    setEditThresholdModal(true);
  };

  const saveThresholds = async (values: any) => {
    try {
      await apiClient.patch(`/kpis/${editingKpi.id}/thresholds`, values);
      showSuccess('阈值已更新');
      setEditThresholdModal(false);
      loadKpis();
    } catch (err: any) { handleApiError(err, '更新失败'); }
  };

  // 按 KPI 分组记录，构建折线图
  const buildChartOption = () => {
    const kpiMap: Record<string, any[]> = {};
    records.forEach(r => {
      if (!kpiMap[r.kpi_id]) kpiMap[r.kpi_id] = [];
      kpiMap[r.kpi_id].push(r);
    });
    const dates = [...new Set(records.map(r => r.record_date))].sort();
    const series = Object.entries(kpiMap)
      .filter(([id]) => !selectedKpi || id === selectedKpi)
      .map(([id, recs]) => {
        const kpiDef = kpis.find(k => k.id === id);
        const dataMap: Record<string, number> = {};
        recs.forEach(r => { dataMap[r.record_date] = r.value; });
        return {
          name: kpiDef?.name || id,
          type: 'line',
          smooth: true,
          data: dates.map(d => dataMap[d] ?? null),
          connectNulls: true,
        };
      });

    return {
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      xAxis: { type: 'category', data: dates },
      yAxis: { type: 'value' },
      series,
    };
  };

  // 统计卡片：按分类汇总最新值
  const latestByKpi: Record<string, any> = {};
  records.forEach(r => {
    if (!latestByKpi[r.kpi_id] || r.record_date > latestByKpi[r.kpi_id].record_date) {
      latestByKpi[r.kpi_id] = r;
    }
  });

  const kpiColumns: ColumnsType<any> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 180 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '分类', dataIndex: 'category', key: 'category', render: (v: string) => <Tag color={categoryColor[v]}>{categoryLabel[v] || v}</Tag> },
    { title: '单位', dataIndex: 'unit', key: 'unit', render: (v: string) => v || '-' },
    { title: '目标值', dataIndex: 'target_value', key: 'target_value', render: (v: number) => v ?? '-' },
    { title: '预警阈值', dataIndex: 'warning_threshold', key: 'warning_threshold', render: (v: number) => v ?? '-' },
    { title: '状态', dataIndex: 'is_active', key: 'is_active', render: (v: string) => <Tag color={v === 'true' ? 'green' : 'default'}>{v === 'true' ? '启用' : '停用'}</Tag> },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEditThreshold(record)}>编辑阈值</Button>
      ),
    },
  ];

  const recordColumns: ColumnsType<any> = [
    { title: 'KPI', dataIndex: 'kpi_id', key: 'kpi_id', render: (v: string) => kpis.find(k => k.id === v)?.name || v },
    { title: '日期', dataIndex: 'record_date', key: 'record_date' },
    { title: '实际值', dataIndex: 'value', key: 'value' },
    { title: '目标值', dataIndex: 'target_value', key: 'target_value', render: (v: number) => v ?? '-' },
    { title: '达成率', dataIndex: 'achievement_rate', key: 'achievement_rate', render: (v: number) => v != null ? <Progress percent={Math.round(v * 100)} size="small" status={v >= 1 ? 'success' : v >= 0.8 ? 'normal' : 'exception'} /> : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => v ? <Tag color={statusColor[v]}>{statusLabel[v] || v}</Tag> : '-' },
    { title: '趋势', dataIndex: 'trend', key: 'trend', render: (v: string) => ({ increasing: '↑ 上升', decreasing: '↓ 下降', stable: '→ 稳定', volatile: '~ 波动' }[v] || v || '-') },
    { title: '备注', dataIndex: 'notes', key: 'notes', ellipsis: true, render: (v: string) => v || '-' },
  ];

  const tabItems = [
    {
      key: 'chart', label: '趋势图',
      children: (
        <div>
          <Space wrap style={{ marginBottom: 12 }}>
            <Select value={selectedKpi || undefined} onChange={setSelectedKpi} style={{ width: 200 }} placeholder="选择KPI指标" allowClear>
              {kpis.map(k => <Option key={k.id} value={k.id}>{k.name}</Option>)}
            </Select>
          </Space>
          <ReactECharts option={buildChartOption()} style={{ height: 360 }} />
        </div>
      ),
    },
    {
      key: 'records', label: `历史记录 (${records.length})`,
      children: <Table columns={recordColumns} dataSource={records} rowKey={(r, i) => `${r.id || i}`} loading={loading} size="small" />,
    },
    {
      key: 'definitions', label: 'KPI定义',
      children: <Table columns={kpiColumns} dataSource={kpis} rowKey="id" size="small" />,
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }}>
          {stores.length > 0 ? stores.map((s: any) => (
            <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
          )) : <Option value="STORE001">STORE001</Option>}
        </Select>
        <RangePicker
          defaultValue={[dayjs().subtract(30, 'day'), dayjs()]}
          onChange={(_, ds) => ds[0] && ds[1] && setDateRange([ds[0], ds[1]])}
        />
        <Button icon={<ReloadOutlined />} onClick={loadRecords}>刷新</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModal(true)}>录入KPI数据</Button>
      </Space>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {kpis.slice(0, 4).map(k => {
          const latest = latestByKpi[k.id];
          const rate = latest?.achievement_rate;
          return (
            <Col span={6} key={k.id}>
              <Card size="small">
                <Statistic
                  title={<><Tag color={categoryColor[k.category]} style={{ marginRight: 4 }}>{categoryLabel[k.category]}</Tag>{k.name}</>}
                  value={latest?.value ?? '--'}
                  suffix={k.unit || ''}
                  valueStyle={{ color: rate == null ? undefined : rate >= 1 ? '#52c41a' : rate >= 0.8 ? '#fa8c16' : '#ff4d4f' }}
                />
                {k.target_value && <div style={{ fontSize: 11, color: '#999' }}>目标 {k.target_value}{k.unit}</div>}
              </Card>
            </Col>
          );
        })}
      </Row>

      <Card><Tabs items={tabItems} /></Card>

      <Modal title=\"录入KPI数据\" open={addModal} onCancel={() => setAddModal(false)} footer={null}>
        <Form form={addForm} layout=\"vertical\" onFinish={addRecord}>
          <Form.Item name=\"kpi_id\" label=\"KPI指标\" rules={[{ required: true }]}>
            <Select placeholder=\"选择KPI\">
              {kpis.map(k => <Option key={k.id} value={k.id}>{k.name}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name=\"record_date\" label=\"日期\" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="value" label="实际值" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block>录入</Button></Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑阈值 — ${editingKpi?.name || ''}`}
        open={editThresholdModal}
        onCancel={() => setEditThresholdModal(false)}
        footer={null}
      >
        <Form form={thresholdForm} layout="vertical" onFinish={saveThresholds}>
          <Form.Item name="target_value" label="目标值">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="warning_threshold" label="预警阈值（低于此值触发黄色预警）">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="critical_threshold" label="严重阈值（低于此值触发红色告警）">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block>保存</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default KPIDashboardPage;
