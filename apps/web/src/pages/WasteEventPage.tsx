/**
 * 损耗事件管理页面
 *
 * 功能：
 *   - 门店损耗事件列表（支持状态/类型/时间范围过滤）
 *   - 事件详情：食材、实际用量、BOM偏差、根因、置信度
 *   - 手动触发五步推理
 *   - 人工验证推理结论
 *   - 根因分布饼图（ECharts）
 *   - 损耗汇总排行（按食材）
 */
import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Table, Button, Tag, Space, Select, InputNumber,
  Drawer, Descriptions, Form, Input, Modal, Progress,
  Row, Col, Statistic, Tabs, Badge, Popconfirm, Alert,
  Divider,
} from 'antd';
import {
  ReloadOutlined, ThunderboltOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, EyeOutlined, FireOutlined,
  BarChartOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TabPane } = Tabs;
const { TextArea } = Input;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface WasteEvent {
  id: string;
  event_id: string;
  store_id: string;
  event_type: string;
  status: string;
  ingredient_id: string;
  dish_id: string | null;
  quantity: number;
  unit: string;
  theoretical_qty: number | null;
  variance_qty: number | null;
  variance_pct: number | null;
  occurred_at: string;
  reported_by: string | null;
  assigned_staff_id: string | null;
  root_cause: string | null;
  confidence: number | null;
  evidence: any;
  scores: any;
  action_taken: string | null;
  notes: string | null;
  created_at: string;
}

// ── 配置映射 ──────────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  pending:   { color: 'default',   label: '待推理' },
  analyzing: { color: 'processing', label: '推理中' },
  analyzed:  { color: 'blue',      label: '已推理' },
  verified:  { color: 'success',   label: '已验证' },
  closed:    { color: 'default',   label: '已关闭' },
};

const TYPE_CONFIG: Record<string, { color: string; label: string }> = {
  cooking_loss:   { color: 'orange',  label: '烹饪损耗' },
  spoilage:       { color: 'red',     label: '食材变质' },
  over_prep:      { color: 'gold',    label: '过量备餐' },
  drop_damage:    { color: 'volcano', label: '操作失误' },
  quality_reject: { color: 'purple',  label: '质检退回' },
  transfer_loss:  { color: 'cyan',    label: '称重损耗' },
  unknown:        { color: 'default', label: '未分类' },
};

const ROOT_CAUSE_LABELS: Record<string, string> = {
  staff_error:       '人员操作失误',
  food_quality:      '食材质量问题',
  equipment_fault:   '设备故障',
  process_deviation: '流程偏差',
  unknown:           '未知',
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

const WasteEventPage: React.FC = () => {
  const [storeId, setStoreId] = useState('STORE001');
  const [events, setEvents] = useState<WasteEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [filterType, setFilterType] = useState<string | undefined>();
  const [days, setDays] = useState(30);

  // 详情 Drawer
  const [selectedEvent, setSelectedEvent] = useState<WasteEvent | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);

  // 分析中状态
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);

  // 验证 Modal
  const [verifyVisible, setVerifyVisible] = useState(false);
  const [verifyEventId, setVerifyEventId] = useState<string | null>(null);
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyForm] = Form.useForm();

  // 汇总数据
  const [summary, setSummary] = useState<any>(null);
  const [rootCauses, setRootCauses] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState('events');

  // ── 数据加载 ──────────────────────────────────────────────────────────────

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = { days };
      if (filterStatus) params.status = filterStatus;
      if (filterType) params.event_type = filterType;
      const res = await apiClient.get(`/api/v1/waste-events/store/${storeId}`, { params });
      setEvents(res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载损耗事件失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, filterStatus, filterType, days]);

  const loadSummary = useCallback(async () => {
    try {
      const [sumRes, rcRes] = await Promise.allSettled([
        apiClient.get(`/api/v1/waste-events/store/${storeId}/summary`, { params: { days } }),
        apiClient.get(`/api/v1/waste-events/store/${storeId}/root-causes`, { params: { days } }),
      ]);
      if (sumRes.status === 'fulfilled') setSummary(sumRes.value.data);
      if (rcRes.status === 'fulfilled') setRootCauses(rcRes.value.data || []);
    } catch (err: any) {
      handleApiError(err, '加载汇总数据失败');
    }
  }, [storeId, days]);

  useEffect(() => {
    loadEvents();
    loadSummary();
  }, [loadEvents, loadSummary]);

  // ── 事件详情 ──────────────────────────────────────────────────────────────

  const viewDetail = useCallback(async (ev: WasteEvent) => {
    try {
      const res = await apiClient.get(`/api/v1/waste-events/${ev.event_id}`);
      setSelectedEvent(res.data);
      setDetailVisible(true);
    } catch {
      setSelectedEvent(ev);
      setDetailVisible(true);
    }
  }, []);

  // ── 手动触发推理 ──────────────────────────────────────────────────────────

  const triggerAnalysis = useCallback(async (eventId: string) => {
    setAnalyzingId(eventId);
    try {
      const res = await apiClient.post(`/api/v1/waste-events/${eventId}/analyze`);
      showSuccess('推理完成');
      loadEvents();
      if (selectedEvent?.event_id === eventId) {
        setSelectedEvent(res.data?.event || null);
      }
    } catch (err: any) {
      handleApiError(err, '推理失败');
    } finally {
      setAnalyzingId(null);
    }
  }, [loadEvents, selectedEvent]);

  // ── 人工验证 ──────────────────────────────────────────────────────────────

  const openVerify = (eventId: string) => {
    setVerifyEventId(eventId);
    verifyForm.resetFields();
    setVerifyVisible(true);
  };

  const submitVerify = async (values: any) => {
    if (!verifyEventId) return;
    setVerifyLoading(true);
    try {
      await apiClient.post(`/api/v1/waste-events/${verifyEventId}/verify`, values);
      showSuccess('验证完成');
      setVerifyVisible(false);
      loadEvents();
      if (selectedEvent?.event_id === verifyEventId) {
        setDetailVisible(false);
      }
    } catch (err: any) {
      handleApiError(err, '验证失败');
    } finally {
      setVerifyLoading(false);
    }
  };

  // ── 关闭事件 ──────────────────────────────────────────────────────────────

  const closeEvent = useCallback(async (eventId: string) => {
    try {
      await apiClient.post(`/api/v1/waste-events/${eventId}/close`);
      showSuccess('事件已关闭');
      loadEvents();
      if (selectedEvent?.event_id === eventId) setDetailVisible(false);
    } catch (err: any) {
      handleApiError(err, '关闭失败');
    }
  }, [loadEvents, selectedEvent]);

  // ── 统计 ──────────────────────────────────────────────────────────────────

  const totalCount = events.length;
  const pendingCount = events.filter(e => e.status === 'pending').length;
  const analyzedCount = events.filter(e => e.status === 'analyzed' || e.status === 'verified').length;
  const highVarianceCount = events.filter(e => e.variance_pct != null && Math.abs(e.variance_pct) >= 0.2).length;

  // ── 根因分布饼图配置 ──────────────────────────────────────────────────────

  const pieOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: 10, top: 'center' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: rootCauses.map(rc => ({
        name: ROOT_CAUSE_LABELS[rc.root_cause] || rc.root_cause,
        value: rc.count,
      })),
    }],
  };

  // ── 事件列表列定义 ────────────────────────────────────────────────────────

  const columns: ColumnsType<WasteEvent> = [
    {
      title: '事件 ID',
      dataIndex: 'event_id',
      width: 140,
      render: (v) => <code style={{ fontSize: 11 }}>{v}</code>,
    },
    {
      title: '类型',
      dataIndex: 'event_type',
      width: 100,
      render: (v) => {
        const cfg = TYPE_CONFIG[v] || { color: 'default', label: v };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: '食材',
      dataIndex: 'ingredient_id',
      width: 120,
      ellipsis: true,
    },
    {
      title: '实际用量',
      width: 100,
      render: (_, rec) => `${rec.quantity} ${rec.unit}`,
    },
    {
      title: '偏差',
      dataIndex: 'variance_pct',
      width: 100,
      render: (v) => {
        if (v == null) return '—';
        const pct = (v * 100).toFixed(1);
        const color = Math.abs(v) >= 0.3 ? 'red' : Math.abs(v) >= 0.2 ? 'orange' : 'default';
        return <Tag color={color}>{v >= 0 ? '+' : ''}{pct}%</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (v) => {
        const cfg = STATUS_CONFIG[v] || { color: 'default', label: v };
        return <Badge status={cfg.color as any} text={cfg.label} />;
      },
    },
    {
      title: '根因',
      dataIndex: 'root_cause',
      width: 120,
      render: (v, rec) =>
        v ? (
          <span>
            {ROOT_CAUSE_LABELS[v] || v}
            {rec.confidence != null && (
              <Tag style={{ marginLeft: 4 }} color="blue">
                {(rec.confidence * 100).toFixed(0)}%
              </Tag>
            )}
          </span>
        ) : '—',
    },
    {
      title: '发生时间',
      dataIndex: 'occurred_at',
      width: 140,
      render: (v) => v?.slice(0, 16).replace('T', ' '),
    },
    {
      title: '操作',
      width: 180,
      fixed: 'right',
      render: (_, rec) => (
        <Space size={4}>
          <Button size="small" icon={<EyeOutlined />} onClick={() => viewDetail(rec)} />
          {(rec.status === 'pending' || rec.status === 'analyzed') && (
            <Button
              size="small"
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={analyzingId === rec.event_id}
              onClick={() => triggerAnalysis(rec.event_id)}
            >
              推理
            </Button>
          )}
          {rec.status === 'analyzed' && (
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => openVerify(rec.event_id)}
            >
              验证
            </Button>
          )}
          {rec.status !== 'closed' && (
            <Popconfirm title="确认关闭此事件？" onConfirm={() => closeEvent(rec.event_id)}>
              <Button size="small" danger icon={<CloseCircleOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: 24 }}>
      {/* 页头 */}
      <Row gutter={16} align="middle" style={{ marginBottom: 16 }}>
        <Col flex="1">
          <h2 style={{ margin: 0 }}>
            <FireOutlined style={{ marginRight: 8 }} />
            损耗事件管理
          </h2>
          <p style={{ color: '#888', margin: 0, fontSize: 13 }}>
            记录、推理、验证门店食材损耗事件
          </p>
        </Col>
        <Col>
          <Space>
            <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
              <Option value="STORE001">北京旗舰店</Option>
              <Option value="STORE002">上海直营店</Option>
              <Option value="STORE003">广州加盟店</Option>
            </Select>
            <Button icon={<ReloadOutlined />} onClick={() => { loadEvents(); loadSummary(); }} loading={loading} />
          </Space>
        </Col>
      </Row>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title={`事件总数（近${days}天）`} value={totalCount} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="待推理" value={pendingCount} valueStyle={{ color: '#faad14' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="已推理/验证" value={analyzedCount} valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="高偏差事件（≥20%）"
              value={highVarianceCount}
              valueStyle={{ color: highVarianceCount > 0 ? '#f5222d' : '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 主区域 */}
      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab="事件列表" key="events">
          {/* 过滤栏 */}
          <Space style={{ marginBottom: 12 }}>
            <Select
              placeholder="事件状态"
              allowClear
              style={{ width: 120 }}
              value={filterStatus}
              onChange={setFilterStatus}
            >
              {Object.entries(STATUS_CONFIG).map(([k, v]) => (
                <Option key={k} value={k}>{v.label}</Option>
              ))}
            </Select>
            <Select
              placeholder="事件类型"
              allowClear
              style={{ width: 120 }}
              value={filterType}
              onChange={setFilterType}
            >
              {Object.entries(TYPE_CONFIG).map(([k, v]) => (
                <Option key={k} value={k}>{v.label}</Option>
              ))}
            </Select>
            <Select
              value={days}
              onChange={setDays}
              style={{ width: 110 }}
            >
              {[7, 14, 30, 60, 90].map(d => (
                <Option key={d} value={d}>最近{d}天</Option>
              ))}
            </Select>
          </Space>

          <Table
            rowKey="event_id"
            columns={columns}
            dataSource={events}
            loading={loading}
            scroll={{ x: 1000 }}
            pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
          />
        </TabPane>

        <TabPane tab="根因分布" key="distribution">
          <Row gutter={24}>
            <Col span={12}>
              <Card title="根因分布（饼图）" size="small">
                {rootCauses.length > 0 ? (
                  <ReactECharts option={pieOption} style={{ height: 320 }} />
                ) : (
                  <Alert type="info" message="暂无已推理事件的根因数据" showIcon />
                )}
              </Card>
            </Col>
            <Col span={12}>
              <Card title="根因明细" size="small">
                <Table
                  rowKey="root_cause"
                  dataSource={rootCauses}
                  pagination={false}
                  size="small"
                  columns={[
                    {
                      title: '根因',
                      dataIndex: 'root_cause',
                      render: (v) => ROOT_CAUSE_LABELS[v] || v,
                    },
                    { title: '事件数', dataIndex: 'count', width: 80 },
                    {
                      title: '平均置信度',
                      dataIndex: 'avg_confidence',
                      width: 110,
                      render: (v) => (
                        <Progress
                          percent={Math.round(v * 100)}
                          size="small"
                          strokeColor={v >= 0.7 ? '#52c41a' : v >= 0.5 ? '#faad14' : '#f5222d'}
                        />
                      ),
                    },
                  ]}
                />
              </Card>
            </Col>
          </Row>
        </TabPane>

        <TabPane tab="食材排行" key="summary">
          <Card title={`食材损耗排行（Top 20，近${days}天）`} size="small">
            <Table
              rowKey="ingredient_id"
              dataSource={summary?.by_ingredient || []}
              pagination={false}
              size="small"
              columns={[
                { title: '排名', width: 60, render: (_, __, idx) => idx + 1 },
                { title: '食材 ID', dataIndex: 'ingredient_id', ellipsis: true },
                {
                  title: '损耗总量',
                  dataIndex: 'total_qty',
                  width: 110,
                  render: (v) => v?.toFixed(2),
                  sorter: (a: any, b: any) => b.total_qty - a.total_qty,
                  defaultSortOrder: 'ascend',
                },
                { title: '事件数', dataIndex: 'event_count', width: 80 },
                {
                  title: '平均偏差%',
                  dataIndex: 'avg_variance_pct',
                  width: 110,
                  render: (v) => {
                    if (v == null) return '—';
                    const pct = (v * 100).toFixed(1);
                    const color = Math.abs(v) >= 0.3 ? 'red' : Math.abs(v) >= 0.2 ? 'orange' : 'default';
                    return <Tag color={color}>{v >= 0 ? '+' : ''}{pct}%</Tag>;
                  },
                },
              ]}
            />
          </Card>
        </TabPane>
      </Tabs>

      {/* ── 事件详情 Drawer ────────────────────────────────────────────────── */}
      <Drawer
        title={
          selectedEvent ? (
            <Space>
              <FireOutlined />
              {selectedEvent.event_id}
              <Tag color={STATUS_CONFIG[selectedEvent.status]?.color || 'default'}>
                {STATUS_CONFIG[selectedEvent.status]?.label || selectedEvent.status}
              </Tag>
            </Space>
          ) : '事件详情'
        }
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
        width={640}
        extra={
          selectedEvent && (
            <Space>
              {(selectedEvent.status === 'pending' || selectedEvent.status === 'analyzed') && (
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  loading={analyzingId === selectedEvent.event_id}
                  onClick={() => triggerAnalysis(selectedEvent.event_id)}
                >
                  触发推理
                </Button>
              )}
              {selectedEvent.status === 'analyzed' && (
                <Button icon={<CheckCircleOutlined />} onClick={() => openVerify(selectedEvent.event_id)}>
                  人工验证
                </Button>
              )}
            </Space>
          )
        }
      >
        {selectedEvent && (
          <>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="食材 ID" span={2}>
                <code>{selectedEvent.ingredient_id}</code>
              </Descriptions.Item>
              {selectedEvent.dish_id && (
                <Descriptions.Item label="菜品 ID" span={2}>
                  <code>{selectedEvent.dish_id}</code>
                </Descriptions.Item>
              )}
              <Descriptions.Item label="事件类型">
                {(() => {
                  const cfg = TYPE_CONFIG[selectedEvent.event_type];
                  return <Tag color={cfg?.color}>{cfg?.label || selectedEvent.event_type}</Tag>;
                })()}
              </Descriptions.Item>
              <Descriptions.Item label="发生时间">
                {selectedEvent.occurred_at?.slice(0, 16).replace('T', ' ')}
              </Descriptions.Item>
              <Descriptions.Item label="实际用量">
                {selectedEvent.quantity} {selectedEvent.unit}
              </Descriptions.Item>
              <Descriptions.Item label="BOM 理论值">
                {selectedEvent.theoretical_qty != null
                  ? `${selectedEvent.theoretical_qty} ${selectedEvent.unit}`
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="偏差量">
                {selectedEvent.variance_qty != null
                  ? `${selectedEvent.variance_qty >= 0 ? '+' : ''}${selectedEvent.variance_qty}`
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="偏差率">
                {selectedEvent.variance_pct != null
                  ? (
                    <Tag color={Math.abs(selectedEvent.variance_pct) >= 0.2 ? 'red' : 'default'}>
                      {(selectedEvent.variance_pct * 100).toFixed(1)}%
                    </Tag>
                  )
                  : '—'}
              </Descriptions.Item>
              {selectedEvent.reported_by && (
                <Descriptions.Item label="记录人">{selectedEvent.reported_by}</Descriptions.Item>
              )}
              {selectedEvent.assigned_staff_id && (
                <Descriptions.Item label="疑似责任人">
                  {selectedEvent.assigned_staff_id}
                </Descriptions.Item>
              )}
            </Descriptions>

            {selectedEvent.root_cause && (
              <>
                <Divider orientation="left">推理结论</Divider>
                <Descriptions bordered size="small" column={2}>
                  <Descriptions.Item label="根因">
                    <Tag color="orange">
                      {ROOT_CAUSE_LABELS[selectedEvent.root_cause] || selectedEvent.root_cause}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="置信度">
                    {selectedEvent.confidence != null ? (
                      <Progress
                        percent={Math.round(selectedEvent.confidence * 100)}
                        size="small"
                        style={{ width: 120 }}
                        strokeColor={
                          selectedEvent.confidence >= 0.7 ? '#52c41a'
                          : selectedEvent.confidence >= 0.5 ? '#faad14'
                          : '#f5222d'
                        }
                      />
                    ) : '—'}
                  </Descriptions.Item>
                </Descriptions>

                {selectedEvent.scores && (
                  <>
                    <Divider orientation="left" style={{ fontSize: 12 }}>各维度评分</Divider>
                    <Row gutter={8}>
                      {Object.entries(selectedEvent.scores as Record<string, number>).map(([k, v]) => (
                        <Col span={12} key={k} style={{ marginBottom: 8 }}>
                          <div style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>
                            {ROOT_CAUSE_LABELS[k] || k}
                          </div>
                          <Progress
                            percent={Math.round(v * 100)}
                            size="small"
                            strokeColor="#1890ff"
                          />
                        </Col>
                      ))}
                    </Row>
                  </>
                )}
              </>
            )}

            {selectedEvent.action_taken && (
              <>
                <Divider orientation="left">处置措施</Divider>
                <Alert type="success" message={selectedEvent.action_taken} showIcon />
              </>
            )}

            {selectedEvent.notes && (
              <>
                <Divider orientation="left">备注</Divider>
                <p>{selectedEvent.notes}</p>
              </>
            )}
          </>
        )}
      </Drawer>

      {/* ── 人工验证 Modal ─────────────────────────────────────────────────── */}
      <Modal
        title="人工验证推理结论"
        open={verifyVisible}
        onCancel={() => setVerifyVisible(false)}
        onOk={() => verifyForm.submit()}
        confirmLoading={verifyLoading}
        width={520}
      >
        <Alert
          type="info"
          message="请根据实际情况确认根因，验证后结论将同步到知识库"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Form form={verifyForm} layout="vertical" onFinish={submitVerify}>
          <Form.Item
            name="verified_root_cause"
            label="确认根因"
            rules={[{ required: true, message: '请选择或输入根因' }]}
          >
            <Select placeholder="选择根因" showSearch allowClear>
              {Object.entries(ROOT_CAUSE_LABELS).map(([k, v]) => (
                <Option key={k} value={k}>{v}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="action_taken" label="实际处置措施">
            <TextArea rows={3} placeholder="描述已采取或将要采取的措施" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default WasteEventPage;
