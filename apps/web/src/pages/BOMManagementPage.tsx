/**
 * BOM 管理页面（配方版本化管理）
 *
 * 功能：
 *   - 门店 BOM 列表（按菜品分组，当前激活版本高亮）
 *   - BOM 明细行：食材 / 标准用量 / 单位 / 出成率
 *   - 版本历史浏览
 *   - 版本激活（将选中版本设为当前版本）
 *   - 新建 BOM 及添加食材行
 *   - Excel 批量导入入口
 */
import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Select, InputNumber,
  Tag, Space, Tabs, Descriptions, Upload, message, Badge,
  Row, Col, Statistic, Popconfirm, Drawer, Divider, Tooltip,
  Alert,
} from 'antd';
import {
  PlusOutlined, UploadOutlined, CheckCircleOutlined,
  HistoryOutlined, EyeOutlined, ThunderboltOutlined,
  ReloadOutlined, BookOutlined, EditOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { UploadProps } from 'antd';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TabPane } = Tabs;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface BOMItem {
  id: string;
  ingredient_id: string;
  standard_qty: number;
  raw_qty: number | null;
  unit: string;
  unit_cost: number | null;
  waste_factor: number;
  is_key_ingredient: boolean;
  is_optional: boolean;
  prep_notes: string | null;
}

interface BOMTemplate {
  id: string;
  store_id: string;
  dish_id: string;
  version: string;
  effective_date: string;
  expiry_date: string | null;
  yield_rate: number;
  standard_portion: number | null;
  prep_time_minutes: number | null;
  is_active: boolean;
  is_approved: boolean;
  approved_by: string | null;
  notes: string | null;
  created_by: string | null;
  items: BOMItem[];
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

const BOMManagementPage: React.FC = () => {
  const [storeId, setStoreId] = useState('STORE001');
  const [boms, setBoms] = useState<BOMTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedBom, setSelectedBom] = useState<BOMTemplate | null>(null);
  const [historyBoms, setHistoryBoms] = useState<BOMTemplate[]>([]);
  const [historyDishId, setHistoryDishId] = useState<string | null>(null);

  // 创建 BOM modal
  const [createVisible, setCreateVisible] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createForm] = Form.useForm();

  // 添加食材行 modal
  const [itemVisible, setItemVisible] = useState(false);
  const [itemLoading, setItemLoading] = useState(false);
  const [itemForm] = Form.useForm();
  const [targetBomId, setTargetBomId] = useState<string | null>(null);

  // BOM 详情 drawer
  const [detailVisible, setDetailVisible] = useState(false);

  // 版本历史 drawer
  const [historyVisible, setHistoryVisible] = useState(false);

  // ── 数据加载 ────────────────────────────────────────────────────────────────

  const loadBoms = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/bom/store/${storeId}`);
      setBoms(res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载 BOM 列表失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadBoms(); }, [loadBoms]);

  // ── 查看 BOM 详情 ───────────────────────────────────────────────────────────

  const viewDetail = useCallback(async (bom: BOMTemplate) => {
    try {
      const res = await apiClient.get(`/api/v1/bom/${bom.id}`);
      setSelectedBom(res.data);
      setDetailVisible(true);
    } catch (err: any) {
      handleApiError(err, '加载 BOM 详情失败');
    }
  }, []);

  // ── 查看版本历史 ────────────────────────────────────────────────────────────

  const viewHistory = useCallback(async (dishId: string) => {
    setHistoryDishId(dishId);
    try {
      const res = await apiClient.get(`/api/v1/bom/dish/${dishId}/history`);
      setHistoryBoms(res.data || []);
      setHistoryVisible(true);
    } catch (err: any) {
      handleApiError(err, '加载版本历史失败');
    }
  }, []);

  // ── 激活版本 ────────────────────────────────────────────────────────────────

  const activateBom = useCallback(async (bomId: string) => {
    try {
      await apiClient.post(`/api/v1/bom/${bomId}/activate`);
      showSuccess('版本已激活');
      loadBoms();
      if (historyDishId) {
        const res = await apiClient.get(`/api/v1/bom/history/${historyDishId}`);
        setHistoryBoms(res.data || []);
      }
    } catch (err: any) {
      handleApiError(err, '激活失败');
    }
  }, [loadBoms, historyDishId]);

  // ── 审核 BOM ────────────────────────────────────────────────────────────────

  const approveBom = useCallback(async (bomId: string) => {
    try {
      await apiClient.post(`/api/v1/bom/${bomId}/approve`);
      showSuccess('BOM 审核通过');
      loadBoms();
    } catch (err: any) {
      handleApiError(err, '审核失败');
    }
  }, [loadBoms]);

  // ── 新建 BOM ────────────────────────────────────────────────────────────────

  const handleCreateBom = async (values: any) => {
    setCreateLoading(true);
    try {
      await apiClient.post('/api/v1/bom/', {
        ...values,
        store_id: storeId,
        activate: values.activate !== false,
      });
      showSuccess('BOM 创建成功');
      setCreateVisible(false);
      createForm.resetFields();
      loadBoms();
    } catch (err: any) {
      handleApiError(err, '创建 BOM 失败');
    } finally {
      setCreateLoading(false);
    }
  };

  // ── 添加食材行 ──────────────────────────────────────────────────────────────

  const openAddItem = (bomId: string) => {
    setTargetBomId(bomId);
    itemForm.resetFields();
    setItemVisible(true);
  };

  const handleAddItem = async (values: any) => {
    if (!targetBomId) return;
    setItemLoading(true);
    try {
      await apiClient.post(`/api/v1/bom/${targetBomId}/items`, values);
      showSuccess('食材行已添加');
      setItemVisible(false);
      // 刷新详情
      const res = await apiClient.get(`/api/v1/bom/${targetBomId}`);
      setSelectedBom(res.data);
      loadBoms();
    } catch (err: any) {
      handleApiError(err, '添加食材行失败');
    } finally {
      setItemLoading(false);
    }
  };

  // ── Excel 导入 ──────────────────────────────────────────────────────────────

  const uploadProps: UploadProps = {
    name: 'file',
    accept: '.xlsx,.xls',
    action: `/api/v1/bom/import/excel?store_id=${storeId}`,
    headers: {
      Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
    },
    showUploadList: false,
    onChange(info) {
      if (info.file.status === 'done') {
        const result = info.file.response;
        showSuccess(`导入完成：新建 ${result?.created ?? 0} 条，跳过 ${result?.skipped ?? 0} 条`);
        loadBoms();
      } else if (info.file.status === 'error') {
        message.error('Excel 导入失败，请检查文件格式');
      }
    },
  };

  // ── 统计数据 ────────────────────────────────────────────────────────────────

  const totalBoms = boms.length;
  const activeBoms = boms.filter(b => b.is_active).length;
  const approvedBoms = boms.filter(b => b.is_approved).length;
  const avgYieldRate =
    boms.length > 0
      ? (boms.reduce((s, b) => s + b.yield_rate, 0) / boms.length * 100).toFixed(1)
      : '0.0';

  // ── BOM 列表列定义 ──────────────────────────────────────────────────────────

  const bomColumns: ColumnsType<BOMTemplate> = [
    {
      title: '菜品 ID',
      dataIndex: 'dish_id',
      width: 200,
      ellipsis: true,
      render: (v) => <code style={{ fontSize: 12 }}>{v}</code>,
    },
    {
      title: '版本',
      dataIndex: 'version',
      width: 90,
      render: (v, rec) => (
        <Space>
          <Tag color={rec.is_active ? 'green' : 'default'}>{v}</Tag>
          {rec.is_active && <Badge status="processing" />}
        </Space>
      ),
    },
    {
      title: '出成率',
      dataIndex: 'yield_rate',
      width: 90,
      render: (v) => <Tag color="blue">{(v * 100).toFixed(1)}%</Tag>,
    },
    {
      title: '食材数',
      dataIndex: 'items',
      width: 80,
      render: (items: BOMItem[]) => items?.length ?? 0,
    },
    {
      title: '生效日期',
      dataIndex: 'effective_date',
      width: 120,
      render: (v) => v?.slice(0, 10),
    },
    {
      title: '状态',
      width: 120,
      render: (_, rec) => (
        <Space size={4}>
          {rec.is_active && <Tag color="success" icon={<CheckCircleOutlined />}>当前</Tag>}
          {rec.is_approved ? (
            <Tag color="processing">已审核</Tag>
          ) : (
            <Tag color="warning">待审核</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '操作',
      width: 200,
      fixed: 'right',
      render: (_, rec) => (
        <Space size={4}>
          <Tooltip title="查看详情">
            <Button size="small" icon={<EyeOutlined />} onClick={() => viewDetail(rec)} />
          </Tooltip>
          <Tooltip title="版本历史">
            <Button
              size="small"
              icon={<HistoryOutlined />}
              onClick={() => viewHistory(rec.dish_id)}
            />
          </Tooltip>
          {!rec.is_active && (
            <Popconfirm
              title="激活此版本将停用同菜品的当前版本，确认？"
              onConfirm={() => activateBom(rec.id)}
            >
              <Tooltip title="激活版本">
                <Button size="small" type="primary" icon={<ThunderboltOutlined />} />
              </Tooltip>
            </Popconfirm>
          )}
          {!rec.is_approved && (
            <Popconfirm title="审核通过此 BOM？" onConfirm={() => approveBom(rec.id)}>
              <Button size="small" type="dashed">审核</Button>
            </Popconfirm>
          )}
          <Tooltip title="添加食材行">
            <Button
              size="small"
              icon={<PlusOutlined />}
              onClick={() => openAddItem(rec.id)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  // ── BOM 明细列定义 ──────────────────────────────────────────────────────────

  const itemColumns: ColumnsType<BOMItem> = [
    {
      title: '食材 ID',
      dataIndex: 'ingredient_id',
      ellipsis: true,
      render: (v) => <code style={{ fontSize: 12 }}>{v}</code>,
    },
    {
      title: '标准用量',
      dataIndex: 'standard_qty',
      width: 90,
      render: (v, rec) => `${v} ${rec.unit}`,
    },
    {
      title: '毛料用量',
      dataIndex: 'raw_qty',
      width: 90,
      render: (v, rec) => v != null ? `${v} ${rec.unit}` : '—',
    },
    {
      title: '损耗系数',
      dataIndex: 'waste_factor',
      width: 90,
      render: (v) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: '单价(分)',
      dataIndex: 'unit_cost',
      width: 90,
      render: (v) => v != null ? `¥${(v / 100).toFixed(2)}` : '—',
    },
    {
      title: '标签',
      width: 120,
      render: (_, rec) => (
        <Space size={4}>
          {rec.is_key_ingredient && <Tag color="red">核心</Tag>}
          {rec.is_optional && <Tag color="default">可选</Tag>}
        </Space>
      ),
    },
    {
      title: '加工说明',
      dataIndex: 'prep_notes',
      ellipsis: true,
      render: (v) => v || '—',
    },
  ];

  // ── 版本历史列定义 ──────────────────────────────────────────────────────────

  const historyColumns: ColumnsType<BOMTemplate> = [
    { title: '版本', dataIndex: 'version', width: 80 },
    {
      title: '生效日期',
      dataIndex: 'effective_date',
      width: 110,
      render: (v) => v?.slice(0, 10),
    },
    {
      title: '失效日期',
      dataIndex: 'expiry_date',
      width: 110,
      render: (v) => v ? v.slice(0, 10) : <Tag color="green">当前</Tag>,
    },
    {
      title: '出成率',
      dataIndex: 'yield_rate',
      width: 80,
      render: (v) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: '食材数',
      dataIndex: 'items',
      width: 70,
      render: (items) => items?.length ?? 0,
    },
    {
      title: '状态',
      width: 100,
      render: (_, rec) => (
        <Space size={4}>
          {rec.is_active ? (
            <Tag color="success" icon={<CheckCircleOutlined />}>激活</Tag>
          ) : (
            <Tag>历史</Tag>
          )}
          {rec.is_approved && <Tag color="blue">已审核</Tag>}
        </Space>
      ),
    },
    {
      title: '操作',
      width: 100,
      render: (_, rec) =>
        !rec.is_active ? (
          <Popconfirm
            title="激活此版本将停用当前版本，确认？"
            onConfirm={() => activateBom(rec.id)}
          >
            <Button size="small" type="primary" icon={<ThunderboltOutlined />}>
              激活
            </Button>
          </Popconfirm>
        ) : null,
    },
  ];

  // ── 渲染 ────────────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: 24 }}>
      {/* 页头 */}
      <Row gutter={16} align="middle" style={{ marginBottom: 16 }}>
        <Col flex="1">
          <h2 style={{ margin: 0 }}>
            <BookOutlined style={{ marginRight: 8 }} />
            BOM 配方管理
          </h2>
          <p style={{ color: '#888', margin: 0, fontSize: 13 }}>
            管理门店菜品的标准配方版本、食材用量及出成率
          </p>
        </Col>
        <Col>
          <Space>
            <Select
              value={storeId}
              onChange={setStoreId}
              style={{ width: 160 }}
              placeholder="选择门店"
            >
              <Option value="STORE001">北京旗舰店</Option>
              <Option value="STORE002">上海直营店</Option>
              <Option value="STORE003">广州加盟店</Option>
            </Select>
            <Upload {...uploadProps}>
              <Button icon={<UploadOutlined />}>Excel 导入</Button>
            </Upload>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateVisible(true)}
            >
              新建 BOM
            </Button>
            <Button icon={<ReloadOutlined />} onClick={loadBoms} loading={loading} />
          </Space>
        </Col>
      </Row>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="BOM 总数" value={totalBoms} suffix="个" />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="激活版本"
              value={activeBoms}
              suffix="个"
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="已审核"
              value={approvedBoms}
              suffix={`/ ${totalBoms}`}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="平均出成率" value={avgYieldRate} suffix="%" />
          </Card>
        </Col>
      </Row>

      {/* BOM 列表 */}
      <Card
        title="配方版本列表"
        extra={
          <Alert
            type="info"
            message="绿色 = 当前激活版本"
            showIcon
            style={{ padding: '2px 8px', marginBottom: 0 }}
            banner
          />
        }
      >
        <Table
          rowKey="id"
          columns={bomColumns}
          dataSource={boms}
          loading={loading}
          scroll={{ x: 900 }}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
          rowClassName={(rec) => rec.is_active ? 'ant-table-row-selected' : ''}
          onRow={(rec) => ({
            style: rec.is_active ? { background: '#f6ffed' } : {},
          })}
        />
      </Card>

      {/* ── BOM 详情 Drawer ──────────────────────────────────────────────────── */}
      <Drawer
        title={
          selectedBom ? (
            <Space>
              <BookOutlined />
              BOM 详情
              <Tag color={selectedBom.is_active ? 'green' : 'default'}>
                {selectedBom.version}
              </Tag>
            </Space>
          ) : 'BOM 详情'
        }
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
        width={720}
        extra={
          selectedBom && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => openAddItem(selectedBom.id)}
            >
              添加食材行
            </Button>
          )
        }
      >
        {selectedBom && (
          <>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="菜品 ID" span={2}>
                <code>{selectedBom.dish_id}</code>
              </Descriptions.Item>
              <Descriptions.Item label="版本">{selectedBom.version}</Descriptions.Item>
              <Descriptions.Item label="出成率">
                {(selectedBom.yield_rate * 100).toFixed(2)}%
              </Descriptions.Item>
              <Descriptions.Item label="生效日期">
                {selectedBom.effective_date?.slice(0, 10)}
              </Descriptions.Item>
              <Descriptions.Item label="失效日期">
                {selectedBom.expiry_date?.slice(0, 10) ?? '—'}
              </Descriptions.Item>
              {selectedBom.standard_portion != null && (
                <Descriptions.Item label="标准份重">
                  {selectedBom.standard_portion} g
                </Descriptions.Item>
              )}
              {selectedBom.prep_time_minutes != null && (
                <Descriptions.Item label="制作工时">
                  {selectedBom.prep_time_minutes} min
                </Descriptions.Item>
              )}
              <Descriptions.Item label="审核状态" span={2}>
                <Space>
                  {selectedBom.is_approved ? (
                    <Tag color="processing">已审核（{selectedBom.approved_by}）</Tag>
                  ) : (
                    <Tag color="warning">待审核</Tag>
                  )}
                </Space>
              </Descriptions.Item>
              {selectedBom.notes && (
                <Descriptions.Item label="备注" span={2}>
                  {selectedBom.notes}
                </Descriptions.Item>
              )}
            </Descriptions>

            <Divider orientation="left">食材明细（{selectedBom.items?.length ?? 0} 行）</Divider>

            <Table
              rowKey="id"
              columns={itemColumns}
              dataSource={selectedBom.items || []}
              pagination={false}
              size="small"
              scroll={{ x: 600 }}
            />
          </>
        )}
      </Drawer>

      {/* ── 版本历史 Drawer ──────────────────────────────────────────────────── */}
      <Drawer
        title={
          <Space>
            <HistoryOutlined />
            版本历史
          </Space>
        }
        open={historyVisible}
        onClose={() => setHistoryVisible(false)}
        width={760}
      >
        <Table
          rowKey="id"
          columns={historyColumns}
          dataSource={historyBoms}
          pagination={false}
          size="small"
          rowClassName={(rec) => (rec.is_active ? 'ant-table-row-selected' : '')}
          onRow={(rec) => ({
            style: rec.is_active ? { background: '#f6ffed' } : {},
          })}
        />
      </Drawer>

      {/* ── 新建 BOM Modal ───────────────────────────────────────────────────── */}
      <Modal
        title="新建 BOM 版本"
        open={createVisible}
        onCancel={() => setCreateVisible(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createLoading}
        width={560}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateBom}
          initialValues={{ activate: true, yield_rate: 1.0 }}
        >
          <Form.Item
            name="dish_id"
            label="菜品 ID"
            rules={[{ required: true, message: '请输入菜品 ID' }]}
          >
            <Input placeholder="例：DISH-001" />
          </Form.Item>
          <Form.Item
            name="version"
            label="版本号"
            rules={[{ required: true, message: '请输入版本号' }]}
          >
            <Input placeholder="例：v1 / v2 / 2026-03" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="yield_rate" label="出成率">
                <InputNumber
                  min={0.01}
                  max={1.0}
                  step={0.01}
                  style={{ width: '100%' }}
                  formatter={(v) => `${((v as number) * 100).toFixed(0)}%`}
                  parser={(v) => parseFloat((v || '100').replace('%', '')) / 100 as unknown as 1}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="standard_portion" label="标准份重（g）">
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="prep_time_minutes" label="制作工时（分钟）">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="activate" label="创建后立即激活" valuePropName="checked">
            <Select style={{ width: 120 }}>
              <Option value={true}>是</Option>
              <Option value={false}>否（保存为草稿）</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 添加食材行 Modal ─────────────────────────────────────────────────── */}
      <Modal
        title="添加食材行"
        open={itemVisible}
        onCancel={() => setItemVisible(false)}
        onOk={() => itemForm.submit()}
        confirmLoading={itemLoading}
        width={560}
      >
        <Form
          form={itemForm}
          layout="vertical"
          onFinish={handleAddItem}
          initialValues={{ waste_factor: 0, is_key_ingredient: false, is_optional: false }}
        >
          <Form.Item
            name="ingredient_id"
            label="食材 ID"
            rules={[{ required: true, message: '请输入食材 ID' }]}
          >
            <Input placeholder="对应 InventoryItem.id，例：ING-PORK-001" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="standard_qty"
                label="标准用量"
                rules={[{ required: true, message: '请输入用量' }]}
              >
                <InputNumber min={0.001} step={0.5} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="unit"
                label="单位"
                rules={[{ required: true, message: '请选择单位' }]}
              >
                <Select>
                  {['g', 'kg', 'ml', 'L', '个', '份', '片', '条'].map((u) => (
                    <Option key={u} value={u}>{u}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="raw_qty" label="毛料用量（可选）">
                <InputNumber min={0} step={0.5} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="unit_cost" label="单价（分，可选）">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="waste_factor" label="损耗系数（0~1）">
                <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="is_key_ingredient" label="核心食材">
                <Select>
                  <Option value={false}>否</Option>
                  <Option value={true}>是（重点监控）</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="prep_notes" label="加工说明">
            <Input placeholder="例：去骨、切丁、腌制20分钟" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default BOMManagementPage;
