import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Form, Input, Button, Table, Space, Tag, Tabs, Modal,
  Row, Col, Statistic, Progress, Alert, Select, InputNumber,
  Drawer, Popconfirm, Divider, Badge,
} from 'antd';
import {
  InboxOutlined, WarningOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, ReloadOutlined, SearchOutlined,
  PlusOutlined, ArrowUpOutlined, ArrowDownOutlined,
  ThunderboltOutlined, BarChartOutlined, HistoryOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import apiClient from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const STATUS_CONFIG: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  normal:       { color: 'green',   text: '正常', icon: <CheckCircleOutlined /> },
  low:          { color: 'orange',  text: '偏低', icon: <WarningOutlined /> },
  critical:     { color: 'red',     text: '紧急', icon: <ExclamationCircleOutlined /> },
  out_of_stock: { color: 'red',     text: '缺货', icon: <ExclamationCircleOutlined /> },
};

const TXN_CONFIG: Record<string, { color: string; text: string }> = {
  purchase:   { color: 'green',  text: '采购入库' },
  usage:      { color: 'blue',   text: '使用出库' },
  waste:      { color: 'red',    text: '损耗' },
  adjustment: { color: 'purple', text: '盘点调整' },
  transfer:   { color: 'cyan',   text: '调拨' },
};

interface InventoryItem {
  id: string;
  store_id: string;
  name: string;
  category: string | null;
  unit: string | null;
  current_quantity: number;
  min_quantity: number;
  max_quantity: number | null;
  unit_cost: number | null;
  status: string | null;
}

const InventoryPage: React.FC = () => {
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [activeTab, setActiveTab] = useState('list');

  // 新增物品
  const [addDrawer, setAddDrawer] = useState(false);
  const [addForm] = Form.useForm();

  // 出入库
  const [txnDrawer, setTxnDrawer] = useState(false);
  const [txnItem, setTxnItem] = useState<InventoryItem | null>(null);
  const [txnForm] = Form.useForm();

  // 流水记录
  const [txnHistoryModal, setTxnHistoryModal] = useState(false);
  const [txnHistory, setTxnHistory] = useState<any[]>([]);
  const [txnHistoryItem, setTxnHistoryItem] = useState<InventoryItem | null>(null);
  const [txnHistoryLoading, setTxnHistoryLoading] = useState(false);

  // 编辑物品
  const [editDrawer, setEditDrawer] = useState(false);
  const [editItem, setEditItem] = useState<InventoryItem | null>(null);
  const [editForm] = Form.useForm();

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadInventory = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiClient.get(`/api/v1/inventory?store_id=${storeId}`);
      setInventory(Array.isArray(res.data) ? res.data : (res.data || []));
    } catch (err: any) { handleApiError(err, '加载库存失败'); }
    finally { setLoading(false); }
  }, [storeId]);

  const loadStats = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/inventory-stats?store_id=${storeId}`);
      setStats(res.data);
    } catch { /* ignore */ }
  }, [storeId]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => {
    loadInventory();
    loadStats();
  }, [loadInventory, loadStats]);

  const handleAddItem = async (values: any) => {
    try {
      await apiClient.post('/api/v1/inventory', {
        id: `INV_${Date.now()}`,
        store_id: storeId,
        ...values,
      });
      showSuccess('物品已添加');
      setAddDrawer(false);
      addForm.resetFields();
      loadInventory();
      loadStats();
    } catch (err: any) { handleApiError(err, '添加失败'); }
  };

  const handleEditItem = async (values: any) => {
    if (!editItem) return;
    try {
      await apiClient.patch(`/api/v1/inventory/${editItem.id}`, values);
      showSuccess('已更新');
      setEditDrawer(false);
      editForm.resetFields();
      loadInventory();
      loadStats();
    } catch (err: any) { handleApiError(err, '更新失败'); }
  };

  const handleTransaction = async (values: any) => {
    if (!txnItem) return;
    try {
      await apiClient.post(`/api/v1/inventory/${txnItem.id}/transaction`, {
        transaction_type: values.transaction_type,
        quantity: values.quantity,
        notes: values.notes,
      });
      showSuccess('库存变动已记录');
      setTxnDrawer(false);
      txnForm.resetFields();
      loadInventory();
      loadStats();
    } catch (err: any) { handleApiError(err, '操作失败'); }
  };

  const handleViewHistory = async (item: InventoryItem) => {
    setTxnHistoryItem(item);
    setTxnHistoryModal(true);
    setTxnHistoryLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/inventory/${item.id}/transactions?limit=50`);
      setTxnHistory(res.data || []);
    } catch (err: any) { handleApiError(err, '加载流水失败'); }
    finally { setTxnHistoryLoading(false); }
  };

  const handleBatchRestock = async () => {
    try {
      const res = await apiClient.post(`/api/v1/inventory/batch-restock?store_id=${storeId}`, { item_ids: null });
      showSuccess(`批量补货完成，共补货 ${res.data?.restocked} 个物品`);
      loadInventory();
      loadStats();
    } catch (err: any) { handleApiError(err, '批量补货失败'); }
  };

  // ── Charts ──
  const categoryDist = stats?.category_distribution || {};
  const statusDist = stats?.status_distribution || {};

  const categoryPieOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['35%', '65%'],
      data: Object.entries(categoryDist).map(([k, v]) => ({ name: k, value: v })),
    }],
  };

  const statusBarOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['正常', '偏低', '紧急', '缺货'] },
    yAxis: { type: 'value' },
    series: [{
      type: 'bar',
      data: [
        { value: statusDist.normal || 0, itemStyle: { color: '#52c41a' } },
        { value: statusDist.low || 0, itemStyle: { color: '#faad14' } },
        { value: statusDist.critical || 0, itemStyle: { color: '#ff4d4f' } },
        { value: statusDist.out_of_stock || 0, itemStyle: { color: '#cf1322' } },
      ],
    }],
  };

  // ── Filters ──
  const categories = ['all', ...Array.from(new Set(inventory.map(i => i.category || '其他')))];
  const filtered = inventory.filter(item => {
    const matchSearch = !searchText ||
      item.name.toLowerCase().includes(searchText.toLowerCase()) ||
      item.id.toLowerCase().includes(searchText.toLowerCase()) ||
      (item.category || '').toLowerCase().includes(searchText.toLowerCase());
    const matchStatus = statusFilter === 'all' || item.status === statusFilter;
    const matchCat = categoryFilter === 'all' || (item.category || '其他') === categoryFilter;
    return matchSearch && matchStatus && matchCat;
  });

  const alerts = inventory.filter(i => i.status && i.status !== 'normal');
  const statCounts = {
    total: inventory.length,
    normal: inventory.filter(i => i.status === 'normal').length,
    low: inventory.filter(i => i.status === 'low').length,
    critical: inventory.filter(i => i.status === 'critical' || i.status === 'out_of_stock').length,
  };

  // ── Columns ──
  const columns: ColumnsType<InventoryItem> = [
    { title: '物品名称', dataIndex: 'name', key: 'name', width: 140 },
    { title: '分类', dataIndex: 'category', key: 'category', width: 90, render: (v: string) => v || '-' },
    {
      title: '当前库存', key: 'qty', width: 160,
      render: (_: any, r: InventoryItem) => {
        const max = r.max_quantity || r.min_quantity * 3;
        const pct = Math.min(100, Math.round((r.current_quantity / max) * 100));
        const status = r.status === 'normal' ? 'success' : r.status === 'low' ? 'normal' : 'exception';
        return (
          <Space direction="vertical" size={0} style={{ width: '100%' }}>
            <span>{r.current_quantity} {r.unit} / {max} {r.unit}</span>
            <Progress percent={pct} status={status} size="small" showInfo={false} />
          </Space>
        );
      },
    },
    { title: '最低库存', dataIndex: 'min_quantity', key: 'min_quantity', width: 90, render: (v: number, r: InventoryItem) => `${v} ${r.unit || ''}` },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => {
        const cfg = STATUS_CONFIG[s] || STATUS_CONFIG.normal;
        return <Tag color={cfg.color} icon={cfg.icon}>{cfg.text}</Tag>;
      },
    },
    { title: '单价', dataIndex: 'unit_cost', key: 'unit_cost', width: 80, render: (v: number) => v ? `¥${(v / 100).toFixed(2)}` : '-' },
    {
      title: '操作', key: 'action', width: 220,
      render: (_: any, record: InventoryItem) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => { setTxnItem(record); txnForm.resetFields(); setTxnDrawer(true); }}>
            <ArrowUpOutlined />出入库
          </Button>
          <Button type="link" size="small" onClick={() => handleViewHistory(record)}>
            <HistoryOutlined />流水
          </Button>
          <Button type="link" size="small" onClick={() => { setEditItem(record); editForm.setFieldsValue({ ...record }); setEditDrawer(true); }}>
            编辑
          </Button>
        </Space>
      ),
    },
  ];

  const txnHistoryColumns: ColumnsType<any> = [
    { title: '类型', dataIndex: 'transaction_type', key: 'transaction_type', width: 100, render: (v: string) => <Tag color={TXN_CONFIG[v]?.color}>{TXN_CONFIG[v]?.text || v}</Tag> },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 80 },
    { title: '变动前', dataIndex: 'quantity_before', key: 'quantity_before', width: 80 },
    { title: '变动后', dataIndex: 'quantity_after', key: 'quantity_after', width: 80 },
    { title: '备注', dataIndex: 'notes', key: 'notes', ellipsis: true },
    { title: '时间', dataIndex: 'transaction_time', key: 'transaction_time', width: 160, render: (v: string) => v?.slice(0, 16) },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>库存预警Agent</h1>
        <Space>
          <Select value={storeId} onChange={v => setStoreId(v)} style={{ width: 160 }}>
            {stores.length > 0 ? stores.map((s: any) => (
              <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
            )) : <Option value="STORE001">STORE001</Option>}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={() => { loadInventory(); loadStats(); }} loading={loading}>刷新</Button>
        </Space>
      </div>

      {alerts.length > 0 && (
        <Alert
          message={`库存预警：${alerts.length} 个物品需要补货`}
          type="warning" showIcon closable style={{ marginBottom: 16 }}
          action={
            <Popconfirm title={`将 ${alerts.length} 个低库存品补至最大库存，确认？`} onConfirm={handleBatchRestock} okText="确认" cancelText="取消">
              <Button size="small" icon={<ThunderboltOutlined />}>一键批量补货</Button>
            </Popconfirm>
          }
        />
      )}

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}><Card size="small"><Statistic title="总物品数" value={statCounts.total} prefix={<InboxOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="库存正常" value={statCounts.normal} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="库存偏低" value={statCounts.low} valueStyle={{ color: '#faad14' }} prefix={<WarningOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="紧急补货" value={statCounts.critical} valueStyle={{ color: '#cf1322' }} prefix={<ExclamationCircleOutlined />} /></Card></Col>
      </Row>

      <Tabs activeKey={activeTab} onChange={setActiveTab}
        tabBarExtraContent={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { addForm.resetFields(); setAddDrawer(true); }}>新增物品</Button>
        }
      >
        <Tabs.TabPane tab="库存列表" key="list">
          <Card size="small">
            <Space style={{ marginBottom: 12, flexWrap: 'wrap' }}>
              <Input
                placeholder="搜索名称/ID/分类"
                prefix={<SearchOutlined />}
                value={searchText}
                onChange={e => setSearchText(e.target.value)}
                style={{ width: 220 }}
                allowClear
              />
              <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 110 }}>
                <Option value="all">全部状态</Option>
                {Object.entries(STATUS_CONFIG).map(([k, v]) => <Option key={k} value={k}>{v.text}</Option>)}
              </Select>
              <Select value={categoryFilter} onChange={setCategoryFilter} style={{ width: 110 }}>
                {categories.map(c => <Option key={c} value={c}>{c === 'all' ? '全部分类' : c}</Option>)}
              </Select>
              <span style={{ color: '#999' }}>共 {filtered.length} 条</span>
            </Space>
            <Table
              dataSource={filtered}
              columns={columns}
              rowKey="id"
              pagination={{ pageSize: 12 }}
              loading={loading}
              size="small"
              locale={{ emptyText: '暂无库存记录' }}
              rowClassName={(r) => r.status && r.status !== 'normal' ? 'ant-table-row-warning' : ''}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab={<span><BarChartOutlined /> 统计分析</span>} key="stats">
          <Row gutter={16}>
            <Col span={8}>
              <Card size="small" style={{ marginBottom: 16 }}>
                <Statistic title="库存总价值" value={((stats?.total_value || 0) / 100).toFixed(2)} prefix="¥" valueStyle={{ color: '#1890ff' }} />
              </Card>
              <Card size="small" title="库存状态分布">
                <ReactECharts option={statusBarOption} style={{ height: 200 }} />
              </Card>
            </Col>
            <Col span={16}>
              <Card size="small" title="分类分布">
                <ReactECharts option={categoryPieOption} style={{ height: 300 }} />
              </Card>
            </Col>
          </Row>
          {stats?.alert_items?.length > 0 && (
            <Card size="small" title={<span><WarningOutlined style={{ color: '#faad14' }} /> 预警物品清单</span>} style={{ marginTop: 16 }}>
              <Table
                dataSource={stats.alert_items}
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  { title: '物品', dataIndex: 'name', key: 'name' },
                  { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Tag color={STATUS_CONFIG[v]?.color}>{STATUS_CONFIG[v]?.text || v}</Tag> },
                  { title: '当前', dataIndex: 'current_quantity', key: 'current_quantity', width: 80, render: (v: number, r: any) => `${v} ${r.unit || ''}` },
                  { title: '最低', dataIndex: 'min_quantity', key: 'min_quantity', width: 80, render: (v: number, r: any) => `${v} ${r.unit || ''}` },
                ]}
              />
            </Card>
          )}
        </Tabs.TabPane>
      </Tabs>

      {/* 新增物品 Drawer */}
      <Drawer title="新增库存物品" open={addDrawer} onClose={() => setAddDrawer(false)} width={440}>
        <Form form={addForm} layout="vertical" onFinish={handleAddItem}>
          <Form.Item label="物品名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Row gutter={8}>
            <Col span={12}>
              <Form.Item label="分类" name="category"><Input placeholder="蔬菜/肉类/调料..." /></Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="单位" name="unit"><Input placeholder="kg/个/瓶..." /></Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label="当前库存" name="current_quantity" initialValue={0} rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="最低库存" name="min_quantity" rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="最大库存" name="max_quantity">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="单价（分）" name="unit_cost" tooltip="以分为单位，如 500 = ¥5.00">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>添加</Button>
          </Form.Item>
        </Form>
      </Drawer>

      {/* 编辑物品 Drawer */}
      <Drawer title={`编辑：${editItem?.name}`} open={editDrawer} onClose={() => setEditDrawer(false)} width={440}>
        <Form form={editForm} layout="vertical" onFinish={handleEditItem}>
          <Form.Item label="物品名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Row gutter={8}>
            <Col span={12}><Form.Item label="分类" name="category"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item label="单位" name="unit"><Input /></Form.Item></Col>
          </Row>
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label="当前库存" name="current_quantity" rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="最低库存" name="min_quantity" rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="最大库存" name="max_quantity">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="单价（分）" name="unit_cost">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>保存</Button>
          </Form.Item>
        </Form>
      </Drawer>

      {/* 出入库 Drawer */}
      <Drawer title={`出入库：${txnItem?.name}`} open={txnDrawer} onClose={() => setTxnDrawer(false)} width={400}>
        {txnItem && (
          <Alert
            message={`当前库存：${txnItem.current_quantity} ${txnItem.unit || ''}`}
            type={txnItem.status === 'normal' ? 'success' : 'warning'}
            showIcon style={{ marginBottom: 16 }}
          />
        )}
        <Form form={txnForm} layout="vertical" onFinish={handleTransaction}>
          <Form.Item label="操作类型" name="transaction_type" rules={[{ required: true }]}>
            <Select placeholder="选择操作类型">
              {Object.entries(TXN_CONFIG).map(([k, v]) => (
                <Option key={k} value={k}><Tag color={v.color}>{v.text}</Tag></Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item label="数量" name="quantity" rules={[{ required: true }, { type: 'number', min: 0.01 }]}>
            <InputNumber min={0.01} step={0.1} style={{ width: '100%' }} placeholder="变动数量" />
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={2} placeholder="选填" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>确认</Button>
          </Form.Item>
        </Form>
      </Drawer>

      {/* 流水记录 Modal */}
      <Modal
        title={`流水记录：${txnHistoryItem?.name}`}
        open={txnHistoryModal}
        onCancel={() => setTxnHistoryModal(false)}
        footer={<Button onClick={() => setTxnHistoryModal(false)}>关闭</Button>}
        width={700}
      >
        <Table
          dataSource={txnHistory}
          columns={txnHistoryColumns}
          rowKey="id"
          loading={txnHistoryLoading}
          pagination={{ pageSize: 10 }}
          size="small"
          locale={{ emptyText: '暂无流水记录' }}
        />
      </Modal>
    </div>
  );
};

export default InventoryPage;
