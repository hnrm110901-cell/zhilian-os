/**
 * 帕累托分析看板 — 总部视角
 * 路由: /hq/pareto-analysis
 *
 * 功能：
 * 1. 多场景选择（门店/菜品/会员/员工/食材/异常）
 * 2. 帕累托滑块（拖动调整聚焦比例）
 * 3. 贡献曲线图
 * 4. 头部/腰部/尾部对象表格
 * 5. AI洞察 + 行动建议
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Slider, Table, Tag, Button, Select, Space, Statistic, Row, Col,
  Typography, Alert, Spin, message, Tooltip, Progress, Descriptions, Divider
} from 'antd';
import {
  FundOutlined, ShopOutlined, CoffeeOutlined, TeamOutlined,
  UserOutlined, ExperimentOutlined, WarningOutlined,
  RocketOutlined, BulbOutlined, ExportOutlined
} from '@ant-design/icons';
import apiClient from '../../services/api';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

interface ParetoSummary {
  selected_ratio: number;
  selected_object_count: number;
  total_object_count: number;
  selected_contribution: number;
  marginal_gain: number;
  recommend_min_ratio: number;
  recommend_max_ratio: number;
  best_ratio: number;
  total_metric_value: number;
  elbow_point_ratio: number;
}

interface ParetoItemData {
  object_id: string;
  object_name: string;
  rank: number;
  metric_value: number;
  contribution: number;
  cumulative_contribution: number;
  segment_type: string;
  risk_level?: string;
  owner_name?: string;
}

interface InsightData {
  title: string;
  text: string;
  insight_type: string;
  confidence: number;
  tags: string[];
}

interface ActionData {
  action_id: string;
  action_title: string;
  action_desc: string;
  action_type: string;
  priority: string;
  owner_role: string;
  due_in_days: number;
  related_object_count: number;
}

interface SceneOption {
  object_type: string;
  label: string;
  metrics: string[];
}

const SCENE_ICONS: Record<string, React.ReactNode> = {
  store: <ShopOutlined />,
  sku: <CoffeeOutlined />,
  member: <TeamOutlined />,
  employee: <UserOutlined />,
  material: <ExperimentOutlined />,
  issue: <WarningOutlined />,
};

const SEGMENT_COLORS: Record<string, string> = {
  head: 'gold', body: 'blue', tail: 'default',
};

const PRIORITY_COLORS: Record<string, string> = {
  high: 'red', medium: 'orange', low: 'default',
};

const METRIC_LABELS: Record<string, string> = {
  revenue: '营收', gross_profit: '毛利', order_count: '订单量',
  customer_count: '客流', total_spend: '消费总额', visit_count: '到店次数',
  repurchase_rate: '复购率', performance_score: '绩效分', waste_amount: '损耗额',
  occurrence_count: '发生次数', loss_amount: '损失金额',
};

const ParetoAnalysis: React.FC = () => {
  const [scenes, setScenes] = useState<SceneOption[]>([]);
  const [objectType, setObjectType] = useState('store');
  const [metricKey, setMetricKey] = useState('revenue');
  const [ratio, setRatio] = useState(0.2);
  const [loading, setLoading] = useState(false);
  const [analysisId, setAnalysisId] = useState('');
  const [summary, setSummary] = useState<ParetoSummary | null>(null);
  const [items, setItems] = useState<ParetoItemData[]>([]);
  const [insight, setInsight] = useState<InsightData | null>(null);
  const [actions, setActions] = useState<ActionData[]>([]);
  const [actionsLoading, setActionsLoading] = useState(false);

  // 加载分析场景列表
  useEffect(() => {
    apiClient.get('/api/v1/analytics/pareto/scenes').then((r) => {
      setScenes(r.data.scenes || []);
    });
  }, []);

  // 执行分析
  const runAnalysis = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.post('/api/v1/analytics/pareto/analyze', {
        object_type: objectType,
        metric_key: metricKey,
        selected_ratio: ratio,
      });
      const d = resp.data;
      setAnalysisId(d.analysis_id);
      setSummary(d.summary);
      setItems(d.items || []);
      setInsight(d.insight);
      // 使用推荐比例
      if (d.summary.best_ratio) {
        setRatio(d.summary.best_ratio);
      }
    } catch {
      message.error('分析失败');
    } finally {
      setLoading(false);
    }
  }, [objectType, metricKey, ratio]);

  useEffect(() => { runAnalysis(); }, [objectType, metricKey]);

  // 滑块松手后获取行动建议
  const fetchActions = useCallback(async (newRatio: number) => {
    if (!analysisId) return;
    setActionsLoading(true);
    try {
      const resp = await apiClient.post('/api/v1/analytics/pareto/action-suggestion', {
        analysis_id: analysisId,
        selected_ratio: newRatio,
      });
      setActions(resp.data.actions || []);
    } catch {
      setActions([]);
    } finally {
      setActionsLoading(false);
    }
  }, [analysisId]);

  const handleSliderChange = (val: number) => {
    setRatio(val);
  };

  const handleSliderAfterChange = (val: number) => {
    setRatio(val);
    fetchActions(val);
  };

  // 初次加载后获取建议
  useEffect(() => {
    if (analysisId) fetchActions(ratio);
  }, [analysisId]);

  const selectedCount = summary ? summary.selected_object_count : 0;
  const currentScene = scenes.find((s) => s.object_type === objectType);

  const columns = [
    { title: '排名', dataIndex: 'rank', width: 60, render: (r: number) =>
        r <= 3 ? <Tag color="gold">#{r}</Tag> : <span>#{r}</span> },
    { title: '名称', dataIndex: 'object_name', ellipsis: true },
    { title: METRIC_LABELS[metricKey] || '指标值', dataIndex: 'metric_value',
      render: (v: number) => `¥${v.toLocaleString()}`, align: 'right' as const },
    { title: '贡献', dataIndex: 'contribution',
      render: (v: number) => <Progress percent={Math.round(v * 100)} size="small" />, width: 120 },
    { title: '累积', dataIndex: 'cumulative_contribution',
      render: (v: number) => `${(v * 100).toFixed(1)}%` },
    { title: '分段', dataIndex: 'segment_type',
      render: (s: string) => <Tag color={SEGMENT_COLORS[s]}>{s === 'head' ? '头部' : s === 'body' ? '腰部' : '尾部'}</Tag> },
    { title: '风险', dataIndex: 'risk_level',
      render: (r: string) => r ? <Tag color={r === 'high' ? 'red' : r === 'medium' ? 'orange' : 'green'}>{r}</Tag> : '-' },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={4}><FundOutlined /> 帕累托分析</Title>

      {/* 筛选栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select value={objectType} onChange={(v) => { setObjectType(v); setMetricKey(scenes.find(s => s.object_type === v)?.metrics[0] || 'revenue'); }} style={{ width: 160 }}>
            {scenes.map((s) => (
              <Option key={s.object_type} value={s.object_type}>
                {SCENE_ICONS[s.object_type]} {s.label}
              </Option>
            ))}
          </Select>
          <Select value={metricKey} onChange={setMetricKey} style={{ width: 140 }}>
            {(currentScene?.metrics || []).map((m) => (
              <Option key={m} value={m}>{METRIC_LABELS[m] || m}</Option>
            ))}
          </Select>
          <Button type="primary" onClick={runAnalysis} loading={loading}>重新分析</Button>
        </Space>
      </Card>

      {loading ? <Spin size="large" style={{ display: 'block', margin: '60px auto' }} /> : (
        <>
          {/* KPI 摘要 */}
          {summary && (
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={5}>
                <Card size="small"><Statistic title="聚焦比例" value={`${(ratio * 100).toFixed(0)}%`} prefix={<FundOutlined />} /></Card>
              </Col>
              <Col span={5}>
                <Card size="small"><Statistic title="覆盖对象" value={selectedCount} suffix={`/ ${summary.total_object_count}`} /></Card>
              </Col>
              <Col span={5}>
                <Card size="small"><Statistic title="累积贡献" value={`${(summary.selected_contribution * 100).toFixed(1)}%`}
                  valueStyle={{ color: summary.selected_contribution >= 0.7 ? '#3f8600' : '#000' }} /></Card>
              </Col>
              <Col span={5}>
                <Card size="small"><Statistic title="边际收益" value={`${(summary.marginal_gain * 100).toFixed(1)}%`}
                  valueStyle={{ color: summary.marginal_gain < 0.05 ? '#cf1322' : '#000' }} /></Card>
              </Col>
              <Col span={4}>
                <Card size="small"><Statistic title="推荐范围" value={`${(summary.recommend_min_ratio*100).toFixed(0)}-${(summary.recommend_max_ratio*100).toFixed(0)}%`} /></Card>
              </Col>
            </Row>
          )}

          {/* 帕累托滑块 */}
          {summary && (
            <Card title="聚焦比例调节" size="small" style={{ marginBottom: 16 }}
                  extra={<Text type="secondary">拖动滑块调整关注范围</Text>}>
              <div style={{ padding: '0 16px' }}>
                <Slider
                  min={0.05} max={1} step={0.01}
                  value={ratio}
                  onChange={handleSliderChange}
                  onChangeComplete={handleSliderAfterChange}
                  marks={{
                    0.1: '10%', 0.2: '20%', 0.3: '30%', 0.5: '50%', 0.8: '80%', 1: '100%',
                    [summary.best_ratio]: { label: <span style={{ color: '#ff6b2c' }}>推荐</span> },
                  }}
                  tooltip={{ formatter: (v) => `${((v || 0) * 100).toFixed(0)}% — ${Math.ceil((v || 0) * summary.total_object_count)}个对象` }}
                  styles={{ track: { background: '#ff6b2c' }, rail: { background: '#f0f0f0' } }}
                />
              </div>
              <Paragraph style={{ textAlign: 'center', marginTop: 8 }}>
                前 <Text strong>{selectedCount}</Text> 个对象（{(ratio * 100).toFixed(0)}%）贡献了
                <Text strong style={{ color: '#ff6b2c', fontSize: 18 }}> {(summary.selected_contribution * 100).toFixed(1)}% </Text>
                的{METRIC_LABELS[metricKey] || '指标值'}
                {summary.marginal_gain < 0.05 && <Text type="danger"> — 再增加覆盖边际收益已很低</Text>}
              </Paragraph>
            </Card>
          )}

          {/* AI 洞察 */}
          {insight && (
            <Alert
              message={insight.title}
              description={insight.text}
              type={insight.insight_type === 'positive' ? 'success' : insight.insight_type === 'warning' ? 'warning' : 'info'}
              showIcon
              style={{ marginBottom: 16 }}
              action={
                <Space>
                  {insight.tags.map((t) => <Tag key={t}>{t}</Tag>)}
                  <Tag color="blue">置信度 {(insight.confidence * 100).toFixed(0)}%</Tag>
                </Space>
              }
            />
          )}

          {/* 对象表格 */}
          <Card title="对象明细" size="small" style={{ marginBottom: 16 }}>
            <Table
              dataSource={items}
              columns={columns}
              rowKey="object_id"
              size="small"
              pagination={{ pageSize: 20, showSizeChanger: true }}
              rowClassName={(record) =>
                record.rank <= selectedCount ? 'pareto-head-row' : ''
              }
            />
          </Card>

          {/* 行动建议 */}
          <Card title={<Space><RocketOutlined /> 行动建议</Space>} size="small"
                loading={actionsLoading}>
            {actions.length === 0 ? (
              <Text type="secondary">调整滑块后将生成行动建议</Text>
            ) : (
              actions.map((a) => (
                <Card key={a.action_id} size="small" style={{ marginBottom: 8 }}
                      type="inner"
                      title={
                        <Space>
                          <Tag color={PRIORITY_COLORS[a.priority]}>{a.priority === 'high' ? '紧急' : a.priority === 'medium' ? '一般' : '低'}</Tag>
                          {a.action_title}
                        </Space>
                      }
                      extra={
                        <Space>
                          <Tag>{a.owner_role}</Tag>
                          <Tag>{a.due_in_days}天内</Tag>
                          <Tag>{a.related_object_count}个对象</Tag>
                        </Space>
                      }>
                  <Text>{a.action_desc}</Text>
                </Card>
              ))
            )}
          </Card>
        </>
      )}
    </div>
  );
};

export default ParetoAnalysis;
