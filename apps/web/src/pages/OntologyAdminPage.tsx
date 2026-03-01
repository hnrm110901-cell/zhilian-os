import React, { useState, useCallback } from 'react';
import {
  Card, Row, Col, Button, Table, Tag, Space, Alert, Statistic,
  Form, Input, InputNumber, Typography, Descriptions, Divider,
  Badge, Tooltip, message,
} from 'antd';
import {
  SyncOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ApartmentOutlined, ThunderboltOutlined, ShareAltOutlined,
  BarChartOutlined, ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Paragraph, Text } = Typography;

// 节点类型颜色
const NODE_COLORS: Record<string, string> = {
  Store: '#1890ff', Dish: '#52c41a', BOM: '#faad14',
  Ingredient: '#f5222d', InventorySnapshot: '#722ed1',
  Staff: '#13c2c2', WasteEvent: '#cf1322', TrainingModule: '#d46b08',
};

const OntologyAdminPage: React.FC = () => {
  const [simForm] = Form.useForm();

  // 图谱健康
  const [health, setHealth] = useState<any>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  // 手动同步
  const [syncResult, setSyncResult] = useState<any>(null);
  const [syncLoading, setSyncLoading] = useState(false);

  // 训练知识传播
  const [propResult, setPropResult] = useState<any>(null);
  const [propLoading, setPropLoading] = useState(false);

  // 节点统计
  const [graphStats, setGraphStats] = useState<any>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // WasteEvent 列表
  const [wasteEvents, setWasteEvents] = useState<any[]>([]);
  const [wasteLoading, setWasteLoading] = useState(false);
  const [wasteStoreFilter, setWasteStoreFilter] = useState('');

  // 门店相似度录入
  const [simLoading, setSimLoading] = useState(false);

  const checkHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const res: any = await apiClient.get('/api/v1/ontology/health');
      setHealth(res);
    } catch (err: any) {
      handleApiError(err, '健康检查失败');
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const triggerSync = useCallback(async () => {
    setSyncLoading(true);
    try {
      const res: any = await apiClient.post('/api/v1/ontology/admin/sync-graph');
      setSyncResult(res);
      message.success('同步任务已触发');
    } catch (err: any) {
      handleApiError(err, '触发同步失败');
    } finally {
      setSyncLoading(false);
    }
  }, []);

  const triggerPropagate = useCallback(async () => {
    setPropLoading(true);
    try {
      const res: any = await apiClient.post('/api/v1/agents/admin/propagate-training-knowledge');
      setPropResult(res);
      message.success('知识传播任务已触发');
    } catch (err: any) {
      handleApiError(err, '触发知识传播失败');
    } finally {
      setPropLoading(false);
    }
  }, []);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const res: any = await apiClient.get('/api/v1/ontology/graph-stats');
      setGraphStats(res);
    } catch (err: any) {
      handleApiError(err, '节点统计加载失败');
    } finally {
      setStatsLoading(false);
    }
  }, []);

  const loadWasteEvents = useCallback(async () => {
    setWasteLoading(true);
    try {
      const params: any = { limit: 50 };
      if (wasteStoreFilter) params.store_id = wasteStoreFilter;
      const res: any = await apiClient.get('/api/v1/ontology/waste-events', { params });
      setWasteEvents(res?.waste_events || []);
    } catch (err: any) {
      handleApiError(err, '损耗事件加载失败');
    } finally {
      setWasteLoading(false);
    }
  }, [wasteStoreFilter]);

  const addSimilarity = async (values: any) => {
    setSimLoading(true);
    try {
      await apiClient.post('/api/v1/ontology/stores/similarity', {
        store_id_a: values.store_id_a,
        store_id_b: values.store_id_b,
        similarity_score: values.similarity_score,
        reason: values.reason || 'manual',
      });
      message.success('相似度关系已写入图谱');
      simForm.resetFields();
    } catch (err: any) {
      handleApiError(err, '写入相似度失败');
    } finally {
      setSimLoading(false);
    }
  };

  const wasteColumns: ColumnsType<any> = [
    { title: '事件 ID', dataIndex: 'event_id', width: 200, render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text> },
    { title: '门店', dataIndex: 'store_id', width: 120 },
    {
      title: '类型',
      dataIndex: 'event_type',
      width: 120,
      render: (t: string) => <Tag color="orange">{t || '—'}</Tag>,
    },
    {
      title: '根因',
      dataIndex: 'root_cause',
      width: 150,
      render: (r: string) => r ? <Tag color="red">{r}</Tag> : <Text type="secondary">—</Text>,
    },
    { title: '损耗量', dataIndex: 'amount', width: 100, render: (v: number) => v != null ? v.toFixed(2) : '—' },
  ];

  return (
    <div style={{ maxWidth: 1300, margin: '0 auto', padding: '24px 0' }}>
      <Title level={3}>
        <ApartmentOutlined style={{ marginRight: 8 }} />
        图谱运维管理
      </Title>
      <Paragraph type="secondary">
        Neo4j 本体层运维控制台：健康检查、手动同步、知识传播触发、WasteEvent 历史、门店相似度管理。
      </Paragraph>

      {/* Row 1: 健康 + 同步 + 知识传播 + 节点统计 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>

        {/* 健康检查 */}
        <Col span={6}>
          <Card
            title={<Space><BarChartOutlined />图谱健康</Space>}
            extra={
              <Button size="small" loading={healthLoading} onClick={checkHealth} icon={<ReloadOutlined />}>
                检查
              </Button>
            }
          >
            {health ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                  {health.status === 'healthy'
                    ? <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 20 }} />
                    : <CloseCircleOutlined style={{ color: '#f5222d', fontSize: 20 }} />}
                  <Text strong style={{ color: health.status === 'healthy' ? '#52c41a' : '#f5222d' }}>
                    {health.status === 'healthy' ? '正常' : '异常'}
                  </Text>
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>Neo4j：{health.neo4j}</Text>
              </Space>
            ) : (
              <Text type="secondary">点击「检查」</Text>
            )}
          </Card>
        </Col>

        {/* 手动同步 */}
        <Col span={6}>
          <Card
            title={<Space><SyncOutlined />手动同步</Space>}
            extra={
              <Button
                size="small" type="primary" loading={syncLoading}
                onClick={triggerSync} icon={<SyncOutlined />}
              >
                触发
              </Button>
            }
          >
            {syncResult ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Tag color={syncResult.ok ? 'green' : 'red'}>
                  {syncResult.ok ? '已触发' : '失败'}
                </Tag>
                {syncResult.task_id && (
                  <Text type="secondary" style={{ fontSize: 11 }}>任务ID: {syncResult.task_id}</Text>
                )}
                <Text type="secondary" style={{ fontSize: 11 }}>PG→Neo4j 全量同步</Text>
              </Space>
            ) : (
              <Text type="secondary">将 PG 主数据同步到 Neo4j</Text>
            )}
          </Card>
        </Col>

        {/* 知识传播 */}
        <Col span={6}>
          <Card
            title={<Space><ThunderboltOutlined />知识传播</Space>}
            extra={
              <Button
                size="small" loading={propLoading}
                onClick={triggerPropagate} icon={<ShareAltOutlined />}
              >
                触发
              </Button>
            }
          >
            {propResult ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Tag color="blue">已触发</Tag>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {propResult.message || '跨门店培训知识传播任务已提交'}
                </Text>
              </Space>
            ) : (
              <Text type="secondary">将最佳培训实践传播到相似门店</Text>
            )}
          </Card>
        </Col>

        {/* 节点统计 */}
        <Col span={6}>
          <Card
            title={<Space><BarChartOutlined />节点统计</Space>}
            extra={
              <Button size="small" loading={statsLoading} onClick={loadStats} icon={<ReloadOutlined />}>
                刷新
              </Button>
            }
          >
            {graphStats ? (
              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                <Statistic
                  title="总节点"
                  value={graphStats.total_nodes}
                  valueStyle={{ fontSize: 22 }}
                />
                <Statistic
                  title="总关系"
                  value={graphStats.total_relations}
                  valueStyle={{ fontSize: 18, color: '#1890ff' }}
                />
              </Space>
            ) : (
              <Text type="secondary">点击「刷新」获取统计</Text>
            )}
          </Card>
        </Col>
      </Row>

      {/* 节点类型明细 */}
      {graphStats && (
        <Card style={{ marginBottom: 16 }}>
          <Row gutter={8}>
            {Object.entries(graphStats.nodes || {}).map(([label, cnt]) => (
              <Col key={label}>
                <Card size="small" bodyStyle={{ padding: '8px 12px', textAlign: 'center' }}>
                  <div style={{ color: NODE_COLORS[label] || '#aaa', fontWeight: 700, fontSize: 20 }}>
                    {String(cnt)}
                  </div>
                  <div style={{ fontSize: 11, color: '#888' }}>{label}</div>
                </Card>
              </Col>
            ))}
            <Col>
              <Divider type="vertical" style={{ height: '100%' }} />
            </Col>
            {Object.entries(graphStats.relations || {}).map(([rel, cnt]) => (
              <Col key={rel}>
                <Tooltip title={`关系类型：${rel}`}>
                  <Card size="small" bodyStyle={{ padding: '8px 12px', textAlign: 'center' }}>
                    <div style={{ fontWeight: 700, fontSize: 18, color: '#1890ff' }}>{String(cnt)}</div>
                    <div style={{ fontSize: 10, color: '#888', maxWidth: 90, wordBreak: 'break-all' }}>{rel}</div>
                  </Card>
                </Tooltip>
              </Col>
            ))}
          </Row>
        </Card>
      )}

      <Row gutter={16}>
        {/* WasteEvent 历史 */}
        <Col span={16}>
          <Card
            title="损耗事件历史（Neo4j WasteEvent 节点）"
            extra={
              <Space>
                <Input
                  placeholder="门店 ID 过滤"
                  style={{ width: 140 }}
                  value={wasteStoreFilter}
                  onChange={e => setWasteStoreFilter(e.target.value)}
                  allowClear
                />
                <Button
                  type="primary"
                  loading={wasteLoading}
                  onClick={loadWasteEvents}
                  icon={<ReloadOutlined />}
                >
                  加载
                </Button>
              </Space>
            }
          >
            <Table
              dataSource={wasteEvents}
              columns={wasteColumns}
              rowKey="event_id"
              loading={wasteLoading}
              size="small"
              pagination={{ pageSize: 15 }}
              locale={{ emptyText: '点击「加载」获取损耗事件（需 Neo4j 已写入数据）' }}
            />
          </Card>
        </Col>

        {/* 门店相似度录入 */}
        <Col span={8}>
          <Card title="录入门店相似度">
            <Paragraph type="secondary" style={{ fontSize: 12 }}>
              手动建立两门店间 SIMILAR_TO 关系（双向幂等）。日常由门店同步自动计算，此处用于手动补录。
            </Paragraph>
            <Form form={simForm} layout="vertical" onFinish={addSimilarity}>
              <Form.Item name="store_id_a" label="门店 A" rules={[{ required: true }]}>
                <Input placeholder="store_001" />
              </Form.Item>
              <Form.Item name="store_id_b" label="门店 B" rules={[{ required: true }]}>
                <Input placeholder="store_002" />
              </Form.Item>
              <Form.Item
                name="similarity_score"
                label="相似度（0.0–1.0）"
                initialValue={0.8}
                rules={[{ required: true }]}
              >
                <InputNumber min={0} max={1} step={0.05} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="reason" label="原因标签" initialValue="manual">
                <Input placeholder="city / region / manual" />
              </Form.Item>
              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={simLoading}
                  block
                  icon={<ApartmentOutlined />}
                >
                  写入图谱
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default OntologyAdminPage;
