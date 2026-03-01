import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Form, Input, Button, Select, Table, Typography, Tag,
  Space, Progress, Popconfirm, Modal, InputNumber, Tooltip,
  message, Descriptions, Drawer, Badge,
} from 'antd';
import {
  ReadOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  ShareAltOutlined, PlusOutlined, InfoCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Paragraph, Text } = Typography;
const { Option } = Select;

const TYPE_LABEL: Record<string, { text: string; color: string }> = {
  waste_rule:      { text: '损耗规则', color: 'red' },
  bom_baseline:   { text: 'BOM 基准', color: 'blue' },
  anomaly_pattern: { text: '异常模式', color: 'orange' },
};

interface KnowledgeItem {
  id: string;
  tenant_id: string;
  store_id?: string;
  type: string;
  name: string;
  content: Record<string, any>;
  accuracy_rate?: number;
  last_verified_at?: string;
  created_at: string;
  updated_at: string;
}

const accuracyColor = (rate: number) => {
  if (rate >= 0.8) return '#52c41a';
  if (rate >= 0.6) return '#faad14';
  return '#f5222d';
};

const KnowledgeRulePage: React.FC = () => {
  const [filterForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [addForm] = Form.useForm();
  const [distForm] = Form.useForm();

  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [tenantId, setTenantId] = useState('');

  // 编辑弹窗
  const [editVisible, setEditVisible] = useState(false);
  const [editingItem, setEditingItem] = useState<KnowledgeItem | null>(null);
  const [editLoading, setEditLoading] = useState(false);

  // 新增弹窗
  const [addVisible, setAddVisible] = useState(false);
  const [addLoading, setAddLoading] = useState(false);

  // 下发弹窗
  const [distVisible, setDistVisible] = useState(false);
  const [distItem, setDistItem] = useState<KnowledgeItem | null>(null);
  const [distLoading, setDistLoading] = useState(false);

  // 详情抽屉
  const [detailItem, setDetailItem] = useState<KnowledgeItem | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const loadItems = useCallback(async (values?: any) => {
    const v = values || filterForm.getFieldsValue();
    if (!v.tenant_id) {
      message.warning('请先填写租户 ID');
      return;
    }
    setTenantId(v.tenant_id);
    setLoading(true);
    try {
      const params: any = { tenant_id: v.tenant_id };
      if (v.type) params.type = v.type;
      if (v.store_id) params.store_id = v.store_id;
      const res: any = await apiClient.get('/api/v1/ontology/knowledge', { params });
      setItems(res?.items || []);
    } catch (err: any) {
      handleApiError(err, '加载知识库失败');
    } finally {
      setLoading(false);
    }
  }, [filterForm]);

  // 编辑提交
  const handleEditSubmit = async () => {
    if (!editingItem) return;
    let values: any;
    try { values = await editForm.validateFields(); } catch { return; }
    setEditLoading(true);
    try {
      let content = editingItem.content;
      try { content = JSON.parse(values.content_json); } catch {
        message.error('content JSON 格式错误'); setEditLoading(false); return;
      }
      await apiClient.patch(`/api/v1/ontology/knowledge/${editingItem.id}`, {
        name: values.name,
        content,
        store_id: values.store_id || undefined,
      });
      message.success('更新成功');
      setEditVisible(false);
      loadItems();
    } catch (err: any) {
      handleApiError(err, '更新失败');
    } finally {
      setEditLoading(false);
    }
  };

  // 新增提交
  const handleAddSubmit = async () => {
    let values: any;
    try { values = await addForm.validateFields(); } catch { return; }
    setAddLoading(true);
    try {
      let content: any = {};
      try { content = JSON.parse(values.content_json || '{}'); } catch {
        message.error('content JSON 格式错误'); setAddLoading(false); return;
      }
      await apiClient.post('/api/v1/ontology/knowledge', {
        tenant_id: tenantId,
        type: values.type,
        name: values.name,
        content,
        store_id: values.store_id || undefined,
      });
      message.success('新增成功');
      setAddVisible(false);
      addForm.resetFields();
      loadItems();
    } catch (err: any) {
      handleApiError(err, '新增失败');
    } finally {
      setAddLoading(false);
    }
  };

  // 删除
  const handleDelete = async (id: string) => {
    try {
      await apiClient.delete(`/api/v1/ontology/knowledge/${id}`);
      message.success('已删除');
      setItems(prev => prev.filter(x => x.id !== id));
    } catch (err: any) {
      handleApiError(err, '删除失败');
    }
  };

  // 连锁下发提交
  const handleDistSubmit = async () => {
    if (!distItem) return;
    let values: any;
    try { values = await distForm.validateFields(); } catch { return; }
    setDistLoading(true);
    try {
      const store_ids = (values.store_ids || '')
        .split(/[,，\s]+/)
        .map((s: string) => s.trim())
        .filter(Boolean);
      await apiClient.post(`/api/v1/ontology/knowledge/${distItem.id}/distribute`, {
        tenant_id: tenantId,
        target_store_ids: store_ids,
      });
      message.success('下发成功');
      setDistVisible(false);
      distForm.resetFields();
    } catch (err: any) {
      handleApiError(err, '下发失败');
    } finally {
      setDistLoading(false);
    }
  };

  const openEdit = (item: KnowledgeItem) => {
    setEditingItem(item);
    editForm.setFieldsValue({
      name: item.name,
      store_id: item.store_id || '',
      content_json: JSON.stringify(item.content, null, 2),
    });
    setEditVisible(true);
  };

  const columns: ColumnsType<KnowledgeItem> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 200,
      render: (name, row) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => { setDetailItem(row); setDrawerOpen(true); }}>
          {name}
        </Button>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 110,
      render: (t) => {
        const cfg = TYPE_LABEL[t] || { text: t, color: 'default' };
        return <Tag color={cfg.color}>{cfg.text}</Tag>;
      },
    },
    {
      title: '门店',
      dataIndex: 'store_id',
      width: 100,
      render: (sid) => sid || <Text type="secondary">连锁级</Text>,
    },
    {
      title: (
        <Space>
          规则精度
          <Tooltip title="仅 waste_rule 类型有精度，由验证任务自动更新（指数移动平均）">
            <InfoCircleOutlined style={{ color: '#aaa' }} />
          </Tooltip>
        </Space>
      ),
      dataIndex: 'accuracy_rate',
      width: 160,
      sorter: (a, b) => (a.accuracy_rate || 0) - (b.accuracy_rate || 0),
      render: (rate) => {
        if (rate == null) return <Text type="secondary">—</Text>;
        const pct = Math.round(rate * 100);
        return (
          <Space direction="vertical" size={2} style={{ width: 130 }}>
            <Progress
              percent={pct}
              size="small"
              strokeColor={accuracyColor(rate)}
              format={p => `${p}%`}
            />
          </Space>
        );
      },
    },
    {
      title: '最近验证',
      dataIndex: 'last_verified_at',
      width: 170,
      render: (t) => t
        ? <Text style={{ fontSize: 12 }}>{t.replace('T', ' ').slice(0, 19)}</Text>
        : <Text type="secondary">未验证</Text>,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (t) => <Text style={{ fontSize: 12 }}>{t?.replace('T', ' ').slice(0, 19)}</Text>,
    },
    {
      title: '操作',
      width: 150,
      fixed: 'right',
      render: (_, row) => (
        <Space>
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          </Tooltip>
          <Tooltip title="连锁下发">
            <Button size="small" icon={<ShareAltOutlined />} onClick={() => { setDistItem(row); setDistVisible(true); }} />
          </Tooltip>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(row.id)} okText="删除" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // 统计卡片数据
  const wasteRules = items.filter(x => x.type === 'waste_rule');
  const avgAccuracy = wasteRules.length
    ? wasteRules.reduce((s, x) => s + (x.accuracy_rate || 0), 0) / wasteRules.length
    : null;
  const highAccuracy = wasteRules.filter(x => (x.accuracy_rate || 0) >= 0.8).length;

  return (
    <div style={{ maxWidth: 1300, margin: '0 auto', padding: '24px 0' }}>
      <Title level={3}>
        <ReadOutlined style={{ marginRight: 8 }} />
        知识规则库
      </Title>
      <Paragraph type="secondary">
        管理损耗规则库、BOM 基准库和异常模式库。损耗规则精度由培训效果验证任务自动更新（指数移动平均），支持编辑和连锁下发。
      </Paragraph>

      {/* 筛选栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Form form={filterForm} layout="inline" onFinish={loadItems}>
          <Form.Item name="tenant_id" label="租户 ID" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="tenant_id" style={{ width: 150 }} />
          </Form.Item>
          <Form.Item name="type" label="类型">
            <Select placeholder="全部类型" style={{ width: 130 }} allowClear>
              <Option value="waste_rule">损耗规则</Option>
              <Option value="bom_baseline">BOM 基准</Option>
              <Option value="anomaly_pattern">异常模式</Option>
            </Select>
          </Form.Item>
          <Form.Item name="store_id" label="门店 ID">
            <Input placeholder="留空查全部" style={{ width: 140 }} allowClear />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading} icon={<ReloadOutlined />}>
                查询
              </Button>
              <Button icon={<PlusOutlined />} onClick={() => {
                if (!tenantId) { message.warning('请先查询以确定租户 ID'); return; }
                addForm.resetFields();
                setAddVisible(true);
              }}>
                新增
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* 统计卡片行（仅查到数据后显示）*/}
      {items.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <Space size={40}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#1890ff' }}>{items.length}</div>
              <div style={{ color: '#888', fontSize: 13 }}>总条目</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#f5222d' }}>{wasteRules.length}</div>
              <div style={{ color: '#888', fontSize: 13 }}>损耗规则</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: avgAccuracy != null ? accuracyColor(avgAccuracy) : '#aaa' }}>
                {avgAccuracy != null ? `${Math.round(avgAccuracy * 100)}%` : '—'}
              </div>
              <div style={{ color: '#888', fontSize: 13 }}>平均精度</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#52c41a' }}>{highAccuracy}</div>
              <div style={{ color: '#888', fontSize: 13 }}>高精度（≥80%）</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#faad14' }}>
                {wasteRules.filter(x => !x.last_verified_at).length}
              </div>
              <div style={{ color: '#888', fontSize: 13 }}>未验证规则</div>
            </div>
          </Space>
        </Card>
      )}

      {/* 表格 */}
      <Card>
        <Table
          dataSource={items}
          columns={columns}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1000 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          size="small"
        />
      </Card>

      {/* 编辑弹窗 */}
      <Modal
        title={`编辑：${editingItem?.name}`}
        open={editVisible}
        onOk={handleEditSubmit}
        confirmLoading={editLoading}
        onCancel={() => setEditVisible(false)}
        width={600}
        okText="保存"
        cancelText="取消"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="store_id" label="门店 ID（空=连锁级）">
            <Input placeholder="留空为连锁级" />
          </Form.Item>
          <Form.Item name="content_json" label="Content（JSON）" rules={[{ required: true }]}>
            <Input.TextArea rows={8} style={{ fontFamily: 'monospace', fontSize: 12 }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新增弹窗 */}
      <Modal
        title="新增知识库条目"
        open={addVisible}
        onOk={handleAddSubmit}
        confirmLoading={addLoading}
        onCancel={() => setAddVisible(false)}
        width={600}
        okText="创建"
        cancelText="取消"
      >
        <Form form={addForm} layout="vertical">
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Select placeholder="选择类型">
              <Option value="waste_rule">损耗规则</Option>
              <Option value="bom_baseline">BOM 基准</Option>
              <Option value="anomaly_pattern">异常模式</Option>
            </Select>
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="规则名称，如「食材过期损耗规则」" />
          </Form.Item>
          <Form.Item name="store_id" label="门店 ID（空=连锁级）">
            <Input placeholder="留空为连锁级通用规则" />
          </Form.Item>
          <Form.Item name="content_json" label="Content（JSON）" initialValue="{}">
            <Input.TextArea
              rows={6}
              style={{ fontFamily: 'monospace', fontSize: 12 }}
              placeholder='{"root_cause": "staff_error", "threshold": 0.05}'
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 连锁下发弹窗 */}
      <Modal
        title={`连锁下发：${distItem?.name}`}
        open={distVisible}
        onOk={handleDistSubmit}
        confirmLoading={distLoading}
        onCancel={() => setDistVisible(false)}
        okText="下发"
        cancelText="取消"
      >
        <Paragraph type="secondary">
          将此条目复制到指定门店。留空门店 ID 列表则下发为连锁级通用记录（store_id 为空）。
        </Paragraph>
        <Form form={distForm} layout="vertical">
          <Form.Item name="store_ids" label="目标门店 ID（逗号或空格分隔，留空=连锁级）">
            <Input.TextArea rows={3} placeholder="store_001, store_002" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情抽屉 */}
      <Drawer
        title={detailItem ? `${TYPE_LABEL[detailItem.type]?.text || detailItem.type}：${detailItem.name}` : ''}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={400}
      >
        {detailItem && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="类型">
              <Tag color={TYPE_LABEL[detailItem.type]?.color || 'default'}>
                {TYPE_LABEL[detailItem.type]?.text || detailItem.type}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="门店">{detailItem.store_id || '连锁级'}</Descriptions.Item>
            {detailItem.accuracy_rate != null && (
              <Descriptions.Item label="规则精度">
                <Progress
                  percent={Math.round(detailItem.accuracy_rate * 100)}
                  size="small"
                  strokeColor={accuracyColor(detailItem.accuracy_rate)}
                />
              </Descriptions.Item>
            )}
            {detailItem.last_verified_at && (
              <Descriptions.Item label="最近验证">
                {detailItem.last_verified_at.replace('T', ' ').slice(0, 19)}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="创建时间">
              {detailItem.created_at.replace('T', ' ').slice(0, 19)}
            </Descriptions.Item>
            <Descriptions.Item label="更新时间">
              {detailItem.updated_at.replace('T', ' ').slice(0, 19)}
            </Descriptions.Item>
            <Descriptions.Item label="Content">
              <pre style={{ fontSize: 11, maxHeight: 300, overflow: 'auto', margin: 0 }}>
                {JSON.stringify(detailItem.content, null, 2)}
              </pre>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
};

export default KnowledgeRulePage;
