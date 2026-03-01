/**
 * 推理规则库管理页面（Phase 3 M3.3）
 *
 * 功能：
 *   - 规则列表：按类别/状态筛选，展示 rule_code/名称/置信度/命中率/准确率
 *   - 规则详情：condition JSON、conclusion JSON、标签、版本信息
 *   - 激活 / 归档 操作
 *   - 规则匹配模拟器：输入 KPI 上下文，点击匹配，显示 Top-10 结果
 *   - 行业基准对比：选行业、输入指标值，展示分位区间
 */
import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Table, Button, Tag, Space, Select, Modal, Tabs,
  Form, Input, Badge, Row, Col, Statistic, Popconfirm,
  Descriptions, Drawer, Progress, Alert, Divider,
  InputNumber,
} from 'antd';
import {
  ReloadOutlined, ThunderboltOutlined, CheckCircleOutlined,
  InboxOutlined, SearchOutlined, BarChartOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TabPane } = Tabs;
const { TextArea } = Input;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface KnowledgeRule {
  id: string;
  rule_code: string;
  name: string;
  category: string;
  rule_type: string;
  condition: any;
  conclusion: any;
  base_confidence: number;
  weight: number;
  status: string;
  hit_count: number;
  correct_count: number;
  accuracy_rate: number | null;
  industry_type: string | null;
  source: string;
  is_public: boolean;
  tags: string[];
}

// ── 配置映射 ──────────────────────────────────────────────────────────────────

const CATEGORY_CONFIG: Record<string, { color: string; label: string }> = {
  waste:      { color: 'red',     label: '损耗' },
  efficiency: { color: 'blue',    label: '效率' },
  quality:    { color: 'purple',  label: '质量' },
  cost:       { color: 'orange',  label: '成本' },
  inventory:  { color: 'cyan',    label: '库存' },
  traffic:    { color: 'green',   label: '客流' },
  compliance: { color: 'gold',    label: '合规' },
  benchmark:  { color: 'default', label: '基准' },
};

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  draft:    { color: 'default',  label: '草稿' },
  active:   { color: 'success',  label: '激活' },
  inactive: { color: 'warning',  label: '停用' },
  archived: { color: 'default',  label: '归档' },
};

const INDUSTRY_LABELS: Record<string, string> = {
  seafood:  '海鲜',
  hotpot:   '火锅',
  fastfood: '快餐',
  general:  '通用',
};

const PERCENTILE_CONFIG: Record<string, { color: string; label: string }> = {
  top_10:     { color: 'success', label: 'Top 10%' },
  '75-90':    { color: 'blue',    label: '75~90%' },
  '50-75':    { color: 'default', label: '50~75%' },
  '25-50':    { color: 'warning', label: '25~50%' },
  bottom_25:  { color: 'error',   label: '末 25%' },
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

const KnowledgeRulesPage: React.FC = () => {
  const [rules, setRules] = useState<KnowledgeRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterCategory, setFilterCategory] = useState<string | undefined>();
  const [filterStatus, setFilterStatus] = useState<string>('active');

  // 详情 Drawer
  const [selectedRule, setSelectedRule] = useState<KnowledgeRule | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);

  // 匹配模拟器
  const [matchContext, setMatchContext] = useState('{\n  "waste_rate": 0.18,\n  "labor_cost_ratio": 0.36\n}');
  const [matchResults, setMatchResults] = useState<any[]>([]);
  const [matchLoading, setMatchLoading] = useState(false);

  // 基准对比
  const [benchIndustry, setBenchIndustry] = useState('seafood');
  const [benchValues, setBenchValues] = useState('{\n  "waste_rate": 0.13,\n  "food_cost_ratio": 0.42\n}');
  const [benchResults, setBenchResults] = useState<any[]>([]);
  const [benchLoading, setBenchLoading] = useState(false);

  const [activeTab, setActiveTab] = useState('rules');

  // ── 数据加载 ──────────────────────────────────────────────────────────────

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = { limit: 500 };
      if (filterCategory) params.category = filterCategory;
      if (filterStatus) params.status = filterStatus;
      const res = await apiClient.get('/api/v1/rules/', { params });
      setRules(res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载规则失败');
    } finally {
      setLoading(false);
    }
  }, [filterCategory, filterStatus]);

  useEffect(() => { loadRules(); }, [loadRules]);

  // ── 激活 / 归档 ──────────────────────────────────────────────────────────

  const activateRule = async (ruleId: string) => {
    try {
      await apiClient.post(`/api/v1/rules/${ruleId}/activate`);
      showSuccess('规则已激活');
      loadRules();
    } catch (err: any) {
      handleApiError(err, '激活失败');
    }
  };

  const archiveRule = async (ruleId: string) => {
    try {
      await apiClient.post(`/api/v1/rules/${ruleId}/archive`);
      showSuccess('规则已归档');
      loadRules();
    } catch (err: any) {
      handleApiError(err, '归档失败');
    }
  };

  // ── 规则匹配模拟 ──────────────────────────────────────────────────────────

  const runMatch = async () => {
    setMatchLoading(true);
    try {
      const context = JSON.parse(matchContext);
      const params: Record<string, any> = { context };
      if (filterCategory) params.category = filterCategory;
      const res = await apiClient.post('/api/v1/rules/match', params);
      setMatchResults(res.data?.matched || res.data || []);
    } catch (err: any) {
      if (err instanceof SyntaxError) {
        handleApiError(null, 'JSON 格式错误，请检查输入');
      } else {
        handleApiError(err, '匹配失败');
      }
    } finally {
      setMatchLoading(false);
    }
  };

  // ── 行业基准对比 ──────────────────────────────────────────────────────────

  const runBenchmark = async () => {
    setBenchLoading(true);
    try {
      const actual_values = JSON.parse(benchValues);
      const res = await apiClient.post('/api/v1/benchmarks/compare', {
        industry_type: benchIndustry,
        actual_values,
      });
      setBenchResults(res.data || []);
    } catch (err: any) {
      if (err instanceof SyntaxError) {
        handleApiError(null, 'JSON 格式错误');
      } else {
        handleApiError(err, '基准对比失败');
      }
    } finally {
      setBenchLoading(false);
    }
  };

  // ── 统计 ──────────────────────────────────────────────────────────────────

  const activeCount = rules.filter(r => r.status === 'active').length;
  const totalHits = rules.reduce((s, r) => s + (r.hit_count || 0), 0);
  const avgAccuracy = rules.filter(r => r.accuracy_rate != null).length > 0
    ? (rules.filter(r => r.accuracy_rate != null)
        .reduce((s, r) => s + (r.accuracy_rate || 0), 0) /
       rules.filter(r => r.accuracy_rate != null).length * 100
      ).toFixed(1)
    : '—';

  // ── 规则列表列定义 ────────────────────────────────────────────────────────

  const columns: ColumnsType<KnowledgeRule> = [
    {
      title: '规则编号',
      dataIndex: 'rule_code',
      width: 110,
      render: (v) => <code style={{ fontSize: 11 }}>{v}</code>,
    },
    {
      title: '规则名称',
      dataIndex: 'name',
      ellipsis: true,
      render: (v) => <span style={{ fontSize: 12 }}>{v}</span>,
    },
    {
      title: '类别',
      dataIndex: 'category',
      width: 80,
      render: (v) => {
        const cfg = CATEGORY_CONFIG[v] || { color: 'default', label: v };
        return <Tag color={cfg.color} style={{ fontSize: 11 }}>{cfg.label}</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 75,
      render: (v) => {
        const cfg = STATUS_CONFIG[v] || { color: 'default', label: v };
        return <Badge status={cfg.color as any} text={cfg.label} />;
      },
    },
    {
      title: '基础置信度',
      dataIndex: 'base_confidence',
      width: 100,
      render: (v) => (
        <Progress
          percent={Math.round(v * 100)}
          size="small"
          strokeColor={v >= 0.7 ? '#52c41a' : v >= 0.5 ? '#faad14' : '#f5222d'}
        />
      ),
    },
    {
      title: '命中次数',
      dataIndex: 'hit_count',
      width: 85,
      sorter: (a, b) => (a.hit_count || 0) - (b.hit_count || 0),
      render: (v) => v || 0,
    },
    {
      title: '准确率',
      dataIndex: 'accuracy_rate',
      width: 85,
      render: (v) =>
        v != null ? (
          <Tag color={v >= 0.8 ? 'success' : v >= 0.6 ? 'warning' : 'error'}>
            {(v * 100).toFixed(0)}%
          </Tag>
        ) : '—',
    },
    {
      title: '操作',
      width: 140,
      fixed: 'right',
      render: (_, rec) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => { setSelectedRule(rec); setDetailVisible(true); }}
          />
          {rec.status !== 'active' && (
            <Popconfirm title="激活此规则？" onConfirm={() => activateRule(rec.id)}>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />}>激活</Button>
            </Popconfirm>
          )}
          {rec.status === 'active' && (
            <Popconfirm title="归档此规则？" onConfirm={() => archiveRule(rec.id)}>
              <Button size="small" danger icon={<InboxOutlined />}>归档</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  // ── 匹配结果列 ────────────────────────────────────────────────────────────

  const matchColumns: ColumnsType<any> = [
    { title: '排名', width: 55, render: (_, __, i) => i + 1 },
    { title: '规则编号', dataIndex: 'rule_code', width: 110, render: (v) => <code style={{ fontSize: 11 }}>{v}</code> },
    { title: '规则名称', dataIndex: 'name', ellipsis: true },
    {
      title: '类别',
      dataIndex: 'category',
      width: 75,
      render: (v) => {
        const cfg = CATEGORY_CONFIG[v] || { color: 'default', label: v };
        return <Tag color={cfg.color} style={{ fontSize: 11 }}>{cfg.label}</Tag>;
      },
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      width: 100,
      render: (v) => (
        <Progress
          percent={Math.round(v * 100)}
          size="small"
          strokeColor={v >= 0.7 ? '#52c41a' : '#faad14'}
        />
      ),
    },
  ];

  // ── 基准结果列 ────────────────────────────────────────────────────────────

  const benchColumns: ColumnsType<any> = [
    { title: '指标', dataIndex: 'metric', width: 140 },
    { title: '说明', dataIndex: 'description', ellipsis: true },
    { title: '实际值', dataIndex: 'actual', width: 80, render: (v) => v?.toFixed(3) },
    { title: 'P50', dataIndex: 'p50', width: 70, render: (v) => v?.toFixed(3) },
    { title: 'P75', dataIndex: 'p75', width: 70, render: (v) => v?.toFixed(3) },
    { title: 'P90', dataIndex: 'p90', width: 70, render: (v) => v?.toFixed(3) },
    { title: '单位', dataIndex: 'unit', width: 60 },
    {
      title: '分位区间',
      dataIndex: 'percentile_band',
      width: 100,
      render: (v) => {
        const cfg = PERCENTILE_CONFIG[v] || { color: 'default', label: v };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: '与中位差距',
      dataIndex: 'gap_to_median',
      width: 100,
      render: (v) => {
        if (v == null) return '—';
        return <Tag color={v >= 0 ? 'success' : 'error'}>{v >= 0 ? '+' : ''}{v?.toFixed(3)}</Tag>;
      },
    },
  ];

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: 24 }}>
      {/* 页头 */}
      <Row gutter={16} align="middle" style={{ marginBottom: 16 }}>
        <Col flex="1">
          <h2 style={{ margin: 0 }}>
            <BarChartOutlined style={{ marginRight: 8 }} />
            推理规则库
          </h2>
          <p style={{ color: '#888', margin: 0, fontSize: 13 }}>
            管理餐饮运营推理规则，支持实时匹配与行业基准对比
          </p>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={loadRules} loading={loading} />
        </Col>
      </Row>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title="规则总数" value={rules.length} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="激活规则" value={activeCount} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="累计命中次数" value={totalHits} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="平均准确率"
              value={avgAccuracy}
              suffix={avgAccuracy !== '—' ? '%' : ''}
            />
          </Card>
        </Col>
      </Row>

      {/* 主 Tabs */}
      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab="规则列表" key="rules">
          <Space style={{ marginBottom: 12 }}>
            <Select
              placeholder="规则类别"
              allowClear
              style={{ width: 110 }}
              value={filterCategory}
              onChange={setFilterCategory}
            >
              {Object.entries(CATEGORY_CONFIG).map(([k, v]) => (
                <Option key={k} value={k}>{v.label}</Option>
              ))}
            </Select>
            <Select
              style={{ width: 100 }}
              value={filterStatus}
              onChange={setFilterStatus}
              allowClear
              placeholder="状态"
            >
              {Object.entries(STATUS_CONFIG).map(([k, v]) => (
                <Option key={k} value={k}>{v.label}</Option>
              ))}
            </Select>
          </Space>

          <Table
            rowKey="id"
            columns={columns}
            dataSource={rules}
            loading={loading}
            scroll={{ x: 900 }}
            pagination={{ pageSize: 25, showTotal: (t) => `共 ${t} 条` }}
            size="small"
          />
        </TabPane>

        <TabPane tab="规则匹配模拟" key="simulator">
          <Card
            title="输入 KPI 上下文"
            extra={
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={matchLoading}
                onClick={runMatch}
              >
                运行匹配
              </Button>
            }
          >
            <Alert
              type="info"
              message='输入当前门店 KPI 指标（JSON），例：{"waste_rate": 0.18, "labor_cost_ratio": 0.36}'
              showIcon
              style={{ marginBottom: 12 }}
            />
            <Input.TextArea
              rows={6}
              value={matchContext}
              onChange={(e) => setMatchContext(e.target.value)}
              style={{ fontFamily: 'monospace', fontSize: 13 }}
            />
          </Card>

          {matchResults.length > 0 && (
            <Card title={`匹配结果（Top ${matchResults.length}）`} style={{ marginTop: 16 }}>
              <Table
                rowKey="rule_code"
                columns={matchColumns}
                dataSource={matchResults}
                pagination={false}
                size="small"
                scroll={{ x: 700 }}
              />
            </Card>
          )}
        </TabPane>

        <TabPane tab="行业基准对比" key="benchmark">
          <Card
            title="行业基准对比"
            extra={
              <Button
                type="primary"
                icon={<BarChartOutlined />}
                loading={benchLoading}
                onClick={runBenchmark}
              >
                对比分析
              </Button>
            }
          >
            <Row gutter={16}>
              <Col span={8}>
                <div style={{ marginBottom: 8 }}>行业</div>
                <Select
                  value={benchIndustry}
                  onChange={setBenchIndustry}
                  style={{ width: '100%' }}
                >
                  {Object.entries(INDUSTRY_LABELS).map(([k, v]) => (
                    <Option key={k} value={k}>{v}</Option>
                  ))}
                </Select>
              </Col>
              <Col span={16}>
                <div style={{ marginBottom: 8 }}>实际指标值（JSON）</div>
                <Input.TextArea
                  rows={4}
                  value={benchValues}
                  onChange={(e) => setBenchValues(e.target.value)}
                  style={{ fontFamily: 'monospace', fontSize: 13 }}
                />
              </Col>
            </Row>
          </Card>

          {benchResults.length > 0 && (
            <Card
              title={`${INDUSTRY_LABELS[benchIndustry] || benchIndustry}行业基准对比结果`}
              style={{ marginTop: 16 }}
            >
              <Table
                rowKey="metric"
                columns={benchColumns}
                dataSource={benchResults}
                pagination={false}
                size="small"
                scroll={{ x: 800 }}
              />
            </Card>
          )}
        </TabPane>
      </Tabs>

      {/* ── 规则详情 Drawer ────────────────────────────────────────────────── */}
      <Drawer
        title={
          selectedRule ? (
            <Space>
              <BarChartOutlined />
              <code>{selectedRule.rule_code}</code>
            </Space>
          ) : '规则详情'
        }
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
        width={640}
      >
        {selectedRule && (
          <>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="规则名称" span={2}>{selectedRule.name}</Descriptions.Item>
              <Descriptions.Item label="类别">
                <Tag color={CATEGORY_CONFIG[selectedRule.category]?.color}>
                  {CATEGORY_CONFIG[selectedRule.category]?.label || selectedRule.category}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Badge
                  status={STATUS_CONFIG[selectedRule.status]?.color as any}
                  text={STATUS_CONFIG[selectedRule.status]?.label || selectedRule.status}
                />
              </Descriptions.Item>
              <Descriptions.Item label="基础置信度">
                {(selectedRule.base_confidence * 100).toFixed(0)}%
              </Descriptions.Item>
              <Descriptions.Item label="权重">{selectedRule.weight}</Descriptions.Item>
              <Descriptions.Item label="行业类型">
                {INDUSTRY_LABELS[selectedRule.industry_type || ''] || selectedRule.industry_type || '通用'}
              </Descriptions.Item>
              <Descriptions.Item label="来源">{selectedRule.source}</Descriptions.Item>
              <Descriptions.Item label="命中次数">{selectedRule.hit_count || 0}</Descriptions.Item>
              <Descriptions.Item label="准确率">
                {selectedRule.accuracy_rate != null
                  ? `${(selectedRule.accuracy_rate * 100).toFixed(1)}%`
                  : '—'}
              </Descriptions.Item>
              {selectedRule.tags?.length > 0 && (
                <Descriptions.Item label="标签" span={2}>
                  <Space size={4}>
                    {selectedRule.tags.map(t => <Tag key={t}>{t}</Tag>)}
                  </Space>
                </Descriptions.Item>
              )}
            </Descriptions>

            <Divider orientation="left">触发条件（Condition）</Divider>
            <pre
              style={{
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 4,
                fontSize: 12,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(selectedRule.condition, null, 2)}
            </pre>

            <Divider orientation="left">推断结论（Conclusion）</Divider>
            <pre
              style={{
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 4,
                fontSize: 12,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(selectedRule.conclusion, null, 2)}
            </pre>
          </>
        )}
      </Drawer>
    </div>
  );
};

export default KnowledgeRulesPage;
