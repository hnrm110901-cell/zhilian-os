/**
 * 菜品研发 Agent — 菜品详情页（Phase 10）
 * 6个Tab：概览 / 配方BOM / 成本仿真 / 试点管理 / 发布管理 / 复盘
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Tabs, Table, Tag, Space, Button, Modal, Form, Input,
  Select, Spin, Typography, Alert, Descriptions, Divider, Badge,
  Progress, List, message, InputNumber,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ArrowLeftOutlined, ExperimentOutlined, RocketOutlined,
  CheckCircleOutlined, CloseCircleOutlined, PlayCircleOutlined,
  ReloadOutlined, PlusOutlined,
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';
import { ZCard, ZKpi, ZSkeleton } from '../design-system/components';

const { Text, Title } = Typography;
const { Option }      = Select;
const { TextArea }    = Input;

// ── 常量 ───────────────────────────────────────────────────────────────────────
const DISH_STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft:         { label: '草稿',   color: 'default' },
  ideation:      { label: '洞察',   color: 'cyan' },
  in_dev:        { label: '研发中', color: 'processing' },
  sampling:      { label: '样品',   color: 'blue' },
  pilot_pending: { label: '待试点', color: 'warning' },
  piloting:      { label: '试点中', color: 'gold' },
  launch_ready:  { label: '待上市', color: 'lime' },
  launched:      { label: '已上市', color: 'success' },
  optimizing:    { label: '优化中', color: 'purple' },
  discontinued:  { label: '停售',   color: 'error' },
  archived:      { label: '归档',   color: 'default' },
};

const PILOT_STATUS_MAP: Record<string, { label: string; color: string }> = {
  planned:    { label: '计划中', color: 'default' },
  running:    { label: '进行中', color: 'processing' },
  completed:  { label: '已完成', color: 'success' },
  cancelled:  { label: '已取消', color: 'error' },
};

const DECISION_MAP: Record<string, { label: string; color: string }> = {
  go:     { label: '通过 GO',   color: 'success' },
  revise: { label: '修改 REVISE', color: 'warning' },
  stop:   { label: '终止 STOP',  color: 'error' },
};

// ── 类型 ───────────────────────────────────────────────────────────────────────
interface DishDetail {
  dish_id:            string;
  dish_code:          string;
  dish_name:          string;
  dish_alias:         string | null;
  dish_type:          string;
  status:             string;
  lifecycle_stage:    string | null;
  positioning_type:   string | null;
  target_price_yuan:  number | null;
  target_margin_rate: number | null;
  description:        string | null;
  highlight_tags:     string[];
  flavor_tags:        string[];
  health_tags:        string[];
  created_at:         string | null;
  cost_summary: {
    total_cost_yuan:      number | null;
    suggested_price_yuan: number | null;
    margin_rate:          number | null;
    calculated_at:        string | null;
  } | null;
  pilot_summary: {
    pilot_id:     string;
    pilot_status: string;
    decision:     string | null;
  } | null;
}

interface RecipeVersion {
  id:               string;
  version_no:       string;
  version_type:     string;
  status:           string;
  serving_size:     number | null;
  serving_unit:     string | null;
  prep_time_min:    number | null;
  cook_time_min:    number | null;
  complexity_score: number | null;
  created_at:       string | null;
}

interface RecipeItem {
  id:             string;
  ingredient_id:  string | null;
  semi_product_id:string | null;
  item_name:      string;
  quantity:       number;
  unit:           string;
  loss_rate:      number;
  unit_price:     number;
  line_cost:      number;
  is_key:         boolean;
}

interface CostSimResult {
  total_cost:            number;
  labor_cost:            number;
  utility_cost:          number;
  suggested_price_yuan:  number;
  margin_rate:           number;
  price_scenarios:       Array<{ margin_rate: number; price: number; label: string }>;
  stress_tests:          Array<{ price_change_pct: number; resulting_margin: number }>;
}

interface PilotTest {
  id:           string;
  store_id:     string;
  pilot_status: string;
  decision:     string | null;
  start_date:   string | null;
  end_date:     string | null;
  note:         string | null;
}

interface LaunchReadiness {
  ready_to_launch: boolean;
  score:           number;
  checklist: Array<{ item: string; passed: boolean; note: string | null }>;
  missing_items: string[];
}

interface FeedbackItem {
  id:            string;
  feedback_type: string;
  source:        string;
  rating:        number | null;
  content:       string | null;
  created_at:    string | null;
}

interface RetroReport {
  report_id:              string;
  retrospective_period:   string;
  lifecycle_assessment:   string;
  conclusion:             string | null;
  generated_at:           string | null;
}

// ── 概览 Tab ──────────────────────────────────────────────────────────────────
const OverviewTab: React.FC<{ dish: DishDetail; brandId: string; onRefresh: () => void }> = ({
  dish, brandId, onRefresh,
}) => {
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusModal,   setStatusModal]   = useState(false);
  const [newStatus,     setNewStatus]     = useState('');

  const handleStatusChange = async () => {
    setStatusLoading(true);
    try {
      await apiClient.patch(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dish.dish_id}`,
        { status: newStatus }
      );
      showSuccess('状态已更新');
      setStatusModal(false);
      onRefresh();
    } catch (e) {
      handleApiError(e, '更新失败');
    } finally {
      setStatusLoading(false);
    }
  };

  const statusCfg = DISH_STATUS_MAP[dish.status] ?? { label: dish.status, color: 'default' };
  const cost      = dish.cost_summary;
  const pilot     = dish.pilot_summary;

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <ZCard
            title="基本信息"
            extra={
              <Button size="small" onClick={() => { setNewStatus(dish.status); setStatusModal(true); }}>
                推进状态
              </Button>
            }
          >
            <Descriptions column={3} size="small">
              <Descriptions.Item label="编码">
                <Text code>{dish.dish_code}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusCfg.color}>{statusCfg.label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="目标售价">
                {dish.target_price_yuan != null ? `¥${dish.target_price_yuan.toFixed(0)}` : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="产品定位">
                {dish.positioning_type ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="目标毛利率">
                {dish.target_margin_rate != null
                  ? `${(dish.target_margin_rate * 100).toFixed(1)}%`
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="生命周期阶段">
                {dish.lifecycle_stage ?? '—'}
              </Descriptions.Item>
            </Descriptions>
            {dish.description && (
              <div style={{ marginTop: 8, color: 'var(--text-secondary)' }}>
                {dish.description}
              </div>
            )}
            <div style={{ marginTop: 12 }}>
              {(dish.flavor_tags ?? []).map(t => <Tag key={t} color="cyan">{t}</Tag>)}
              {(dish.highlight_tags ?? []).map(t => <Tag key={t} color="gold">{t}</Tag>)}
              {(dish.health_tags ?? []).map(t => <Tag key={t} color="green">{t}</Tag>)}
            </div>
          </ZCard>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <ZCard title="成本快照">
            {cost ? (
              <Row gutter={12}>
                <Col span={8}>
                  <ZKpi label="食材成本" value={`¥${(cost.total_cost_yuan ?? 0).toFixed(2)}`} />
                </Col>
                <Col span={8}>
                  <ZKpi label="建议售价" value={cost.suggested_price_yuan != null ? `¥${cost.suggested_price_yuan.toFixed(0)}` : '—'} />
                </Col>
                <Col span={8}>
                  <ZKpi
                    label="毛利率"
                    value={cost.margin_rate != null ? `${(cost.margin_rate * 100).toFixed(1)}%` : '—'}
                  />
                </Col>
              </Row>
            ) : (
              <Text type="secondary">暂无成本数据，请在「成本仿真」Tab 运行 Agent</Text>
            )}
          </ZCard>
        </Col>
        <Col span={12}>
          <ZCard title="试点状态">
            {pilot ? (
              <Row gutter={12}>
                <Col span={12}>
                  <ZKpi
                    label="试点状态"
                    value={PILOT_STATUS_MAP[pilot.pilot_status]?.label ?? pilot.pilot_status}
                  />
                </Col>
                <Col span={12}>
                  <ZKpi
                    label="决策结论"
                    value={pilot.decision
                      ? (DECISION_MAP[pilot.decision]?.label ?? pilot.decision)
                      : '待决策'}
                  />
                </Col>
              </Row>
            ) : (
              <Text type="secondary">暂无试点，请在「试点管理」Tab 创建试点</Text>
            )}
          </ZCard>
        </Col>
      </Row>

      <Modal
        title="推进菜品状态"
        open={statusModal}
        onCancel={() => setStatusModal(false)}
        onOk={handleStatusChange}
        confirmLoading={statusLoading}
      >
        <Form layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="新状态">
            <Select value={newStatus} onChange={setNewStatus} style={{ width: '100%' }}>
              {Object.entries(DISH_STATUS_MAP).map(([k, v]) => (
                <Option key={k} value={k}>{v.label}</Option>
              )) : null}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ── 配方BOM Tab ───────────────────────────────────────────────────────────────
const RecipeBomTab: React.FC<{ dishId: string; brandId: string }> = ({ dishId, brandId }) => {
  const [versions,    setVersions]    = useState<RecipeVersion[]>([]);
  const [selVersion,  setSelVersion]  = useState<string | null>(null);
  const [bom,         setBom]         = useState<RecipeItem[]>([]);
  const [verLoading,  setVerLoading]  = useState(false);
  const [bomLoading,  setBomLoading]  = useState(false);

  // 新建版本
  const [newVerOpen,    setNewVerOpen]    = useState(false);
  const [newVerLoading, setNewVerLoading] = useState(false);
  const [verForm] = Form.useForm();

  const loadVersions = useCallback(async () => {
    setVerLoading(true);
    try {
      const res = await apiClient.get<RecipeVersion[]>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/recipe-versions`
      );
      setVersions(res);
      if (res.length > 0 && !selVersion) {
        setSelVersion(res[0].id);
      }
    } catch (e) {
      handleApiError(e, '加载配方版本失败');
    } finally {
      setVerLoading(false);
    }
  }, [brandId, dishId, selVersion]);

  const loadBom = useCallback(async (versionId: string) => {
    setBomLoading(true);
    try {
      const res = await apiClient.get<RecipeItem[]>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/recipe-versions/${versionId}/items`
      );
      setBom(res);
    } catch (e) {
      handleApiError(e, '加载BOM失败');
    } finally {
      setBomLoading(false);
    }
  }, [brandId, dishId]);

  useEffect(() => { loadVersions(); }, [loadVersions]);
  useEffect(() => { if (selVersion) loadBom(selVersion); }, [selVersion, loadBom]);

  const handleCreateVersion = async () => {
    try {
      const values = await verForm.validateFields();
      setNewVerLoading(true);
      await apiClient.post(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/recipe-versions`,
        values
      );
      showSuccess('配方版本已创建');
      setNewVerOpen(false);
      verForm.resetFields();
      await loadVersions();
    } catch (e: any) {
      if (e?.errorFields) return;
      handleApiError(e, '创建失败');
    } finally {
      setNewVerLoading(false);
    }
  };

  const totalCost = bom.reduce((s, r) => s + (r.line_cost ?? 0), 0);

  const bomCols: ColumnsType<RecipeItem> = [
    { title: '食材/半成品', dataIndex: 'item_name', width: 140 },
    { title: '用量', dataIndex: 'quantity', width: 70, render: (v, r) => `${v} ${r.unit}` },
    { title: '损耗率', dataIndex: 'loss_rate', width: 80, render: (v: number) => `${(v * 100).toFixed(1)}%` },
    { title: '单价(元)', dataIndex: 'unit_price', width: 90, render: (v: number) => `¥${v.toFixed(3)}` },
    {
      title: '行成本(元)', dataIndex: 'line_cost', width: 100,
      render: (v: number) => <Text strong>¥{v.toFixed(3)}</Text>,
    },
    { title: '关键食材', dataIndex: 'is_key', width: 80, render: (v: boolean) => v ? <Tag color="red">关键</Tag> : null },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Text>选择版本：</Text>
        {verLoading ? <Spin size="small" /> : (
          <Select
            style={{ width: 180 }}
            value={selVersion}
            onChange={setSelVersion}
            placeholder="请选择配方版本"
          >
            {versions.map(v => (
              <Option key={v.id} value={v.id}>
                {v.version_no} · {v.status}
              </Option>
            )) : null}
          </Select>
        )}
        <Button icon={<PlusOutlined />} onClick={() => setNewVerOpen(true)}>
          新建版本
        </Button>
      </Space>

      {selVersion && (
        <>
          <Table
            loading={bomLoading}
            dataSource={bom}
            columns={bomCols}
            rowKey="id"
            size="small"
            pagination={false}
            footer={() => (
              <Row justify="end">
                <Text strong>合计食材成本：¥{totalCost.toFixed(3)}</Text>
              </Row>
            )}
          />
          {bom.length === 0 && !bomLoading && (
            <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-secondary)' }}>
              暂无BOM条目，请通过API添加食材
            </div>
          )}
        </>
      )}

      <Modal
        title="新建配方版本"
        open={newVerOpen}
        onCancel={() => { setNewVerOpen(false); verForm.resetFields(); }}
        onOk={handleCreateVersion}
        confirmLoading={newVerLoading}
        destroyOnClose
      >
        <Form form={verForm} layout="vertical" style={{ marginTop: 16 }}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="version_type" label="版本类型" rules={[{ required: true }]}>
                <Select>
                  <Option value="initial">初始版</Option>
                  <Option value="improved">改良版</Option>
                  <Option value="cost_opt">成本优化版</Option>
                  <Option value="seasonal">季节版</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="serving_size" label="出品份量">
                <InputNumber min={0.1} step={0.1} style={{ width: '100%' }} placeholder="1" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="prep_time_min" label="备料时间(min)">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="cook_time_min" label="烹饪时间(min)">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="备注">
            <TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ── 成本仿真 Tab ──────────────────────────────────────────────────────────────
const CostSimTab: React.FC<{ dishId: string; brandId: string }> = ({ dishId, brandId }) => {
  const [versions,    setVersions]    = useState<RecipeVersion[]>([]);
  const [selVersion,  setSelVersion]  = useState<string | null>(null);
  const [result,      setResult]      = useState<CostSimResult | null>(null);
  const [loading,     setLoading]     = useState(false);
  const [verLoading,  setVerLoading]  = useState(false);

  const loadVersions = useCallback(async () => {
    setVerLoading(true);
    try {
      const res = await apiClient.get<RecipeVersion[]>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/recipe-versions`
      );
      setVersions(res);
      if (res.length > 0) setSelVersion(res[0].id);
    } catch (e) {
      handleApiError(e, '加载配方版本失败');
    } finally {
      setVerLoading(false);
    }
  }, [brandId, dishId]);

  useEffect(() => { loadVersions(); }, [loadVersions]);

  const runSim = async () => {
    if (!selVersion) { message.warning('请先选择配方版本'); return; }
    setLoading(true);
    try {
      const res = await apiClient.post<CostSimResult>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/agent/cost-sim`,
        null,
        { params: { recipe_version_id: selVersion, save: true } }
      );
      setResult(res);
    } catch (e) {
      handleApiError(e, '成本仿真失败');
    } finally {
      setLoading(false);
    }
  };

  const scenarioCols: ColumnsType<{ margin_rate: number; price: number; label: string }> = [
    { title: '方案', dataIndex: 'label' },
    { title: '目标毛利率', dataIndex: 'margin_rate', render: (v: number) => `${(v * 100).toFixed(0)}%` },
    { title: '建议售价', dataIndex: 'price', render: (v: number) => <Text strong>¥{v.toFixed(1)}</Text> },
    {
      title: '毛利额',
      render: (_: any, r: any) => result
        ? `¥${(r.price - result.total_cost).toFixed(2)}`
        : '—',
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Text>配方版本：</Text>
        {verLoading ? <Spin size="small" /> : (
          <Select
            style={{ width: 200 }}
            value={selVersion}
            onChange={setSelVersion}
            placeholder="请选择版本"
          >
            {versions.map(v => (
              <Option key={v.id} value={v.id}>{v.version_no} · {v.status}</Option>
            )) : null}
          </Select>
        )}
        <Button
          type="primary"
          icon={<ExperimentOutlined />}
          loading={loading}
          onClick={runSim}
        >
          运行成本仿真
        </Button>
      </Space>

      {loading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" tip="Agent 计算中..." />
        </div>
      )}

      {result && !loading && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <ZCard><ZKpi label="食材成本" value={`¥${result.total_cost.toFixed(3)}`} /></ZCard>
            </Col>
            <Col span={6}>
              <ZCard><ZKpi label="人工成本" value={`¥${result.labor_cost.toFixed(2)}`} /></ZCard>
            </Col>
            <Col span={6}>
              <ZCard><ZKpi label="建议售价" value={`¥${result.suggested_price_yuan.toFixed(1)}`} /></ZCard>
            </Col>
            <Col span={6}>
              <ZCard>
                <ZKpi
                  label="建议毛利率"
                  value={`${(result.margin_rate * 100).toFixed(1)}%`}
                  status={result.margin_rate >= 0.6 ? 'good' : result.margin_rate >= 0.5 ? 'warning' : 'critical'}
                />
              </ZCard>
            </Col>
          </Row>

          <ZCard title="定价方案（4档毛利率）" style={{ marginBottom: 16 }}>
            <Table
              dataSource={result.price_scenarios}
              columns={scenarioCols}
              rowKey="label"
              pagination={false}
              size="small"
            />
          </ZCard>

          {result.stress_tests?.length > 0 && (
            <ZCard title="压力测试（食材价格波动）">
              <Table
                dataSource={result.stress_tests}
                columns={[
                  {
                    title: '食材价格变化',
                    dataIndex: 'price_change_pct',
                    render: (v: number) => (
                      <Tag color={v > 0 ? 'red' : 'green'}>{v > 0 ? `+${v}%` : `${v}%`}</Tag>
                    ),
                  },
                  {
                    title: '毛利率',
                    dataIndex: 'resulting_margin',
                    render: (v: number) => {
                      const pct = (v * 100).toFixed(1);
                      return <Text type={v < 0.5 ? 'danger' : undefined}>{pct}%</Text>;
                    },
                  },
                ]}
                rowKey="price_change_pct"
                pagination={false}
                size="small"
              />
            </ZCard>
          )}
        </>
      )}

      {!result && !loading && (
        <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-secondary)' }}>
          选择配方版本后点击「运行成本仿真」，Agent 将基于BOM自动计算食材成本和定价方案
        </div>
      )}
    </div>
  );
};

// ── 试点管理 Tab ──────────────────────────────────────────────────────────────
const PilotTab: React.FC<{ dishId: string; brandId: string }> = ({ dishId, brandId }) => {
  const [pilots,      setPilots]      = useState<PilotTest[]>([]);
  const [recResult,   setRecResult]   = useState<any>(null);
  const [pilotLoading,setPilotLoading]= useState(false);
  const [recLoading,  setRecLoading]  = useState(false);

  // 新建试点
  const [createOpen,    setCreateOpen]    = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createForm] = Form.useForm();

  // 记录决策
  const [decisionOpen,    setDecisionOpen]    = useState(false);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [decisionPilotId, setDecisionPilotId] = useState<string | null>(null);
  const [decisionForm] = Form.useForm();

  const loadPilots = useCallback(async () => {
    setPilotLoading(true);
    try {
      const res = await apiClient.get<PilotTest[]>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/pilot-tests`
      );
      setPilots(res);
    } catch (e) {
      handleApiError(e, '加载试点列表失败');
    } finally {
      setPilotLoading(false);
    }
  }, [brandId, dishId]);

  useEffect(() => { loadPilots(); }, [loadPilots]);

  const getRecommend = async () => {
    setRecLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/agent/pilot-recommend`);
      setRecResult(res);
    } catch (e) {
      handleApiError(e, '获取推荐失败');
    } finally {
      setRecLoading(false);
    }
  };

  const handleCreatePilot = async () => {
    try {
      const values = await createForm.validateFields();
      setCreateLoading(true);
      await apiClient.post(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/pilot-tests`,
        values
      );
      showSuccess('试点已创建');
      setCreateOpen(false);
      createForm.resetFields();
      loadPilots();
    } catch (e: any) {
      if (e?.errorFields) return;
      handleApiError(e, '创建失败');
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDecision = async () => {
    if (!decisionPilotId) return;
    try {
      const values = await decisionForm.validateFields();
      setDecisionLoading(true);
      await apiClient.post(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/pilot-tests/${decisionPilotId}/decision`,
        values
      );
      showSuccess('决策已记录');
      setDecisionOpen(false);
      decisionForm.resetFields();
      loadPilots();
    } catch (e: any) {
      if (e?.errorFields) return;
      handleApiError(e, '记录失败');
    } finally {
      setDecisionLoading(false);
    }
  };

  const pilotCols: ColumnsType<PilotTest> = [
    { title: '门店', dataIndex: 'store_id', width: 120 },
    {
      title: '状态', dataIndex: 'pilot_status', width: 100,
      render: (v: string) => {
        const cfg = PILOT_STATUS_MAP[v] ?? { label: v, color: 'default' };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: '决策', dataIndex: 'decision', width: 120,
      render: (v: string | null) => {
        if (!v) return <Text type="secondary">待决策</Text>;
        const cfg = DECISION_MAP[v] ?? { label: v, color: 'default' };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    { title: '开始日期', dataIndex: 'start_date', width: 110 },
    { title: '结束日期', dataIndex: 'end_date',   width: 110 },
    {
      title: '操作', width: 100,
      render: (_: any, row) => (
        <Button
          size="small" type="link"
          disabled={!!row.decision}
          onClick={() => { setDecisionPilotId(row.id); setDecisionOpen(true); }}
        >
          {row.decision ? '已决策' : '记录决策'}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<RocketOutlined />} loading={recLoading} onClick={getRecommend}>
          AI推荐试点门店
        </Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          创建试点
        </Button>
      </Space>

      {recResult && (
        <ZCard title="AI 推荐试点门店" style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
            推荐理由：{recResult.reason ?? '—'}
          </Text>
          <List
            size="small"
            dataSource={recResult.recommended_stores ?? []}
            renderItem={(item: any) => (
              <List.Item>
                <Space>
                  <Text strong>{item.store_id}</Text>
                  <Tag color="blue">{item.store_level ?? ''}</Tag>
                  <Text type="secondary">{item.reason ?? ''}</Text>
                  <Text>匹配分：{(item.match_score ?? 0).toFixed(2)}</Text>
                </Space>
              </List.Item>
            )}
          />
        </ZCard>
      )}

      <Table
        loading={pilotLoading}
        dataSource={pilots}
        columns={pilotCols}
        rowKey="id"
        size="middle"
        pagination={false}
      />

      {/* 创建试点 Modal */}
      <Modal
        title="创建试点"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        onOk={handleCreatePilot}
        confirmLoading={createLoading}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="store_id" label="试点门店ID" rules={[{ required: true }]}>
            <Input placeholder="如：STORE001" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="start_date" label="开始日期">
                <Input type="date" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="end_date" label="结束日期">
                <Input type="date" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="note" label="备注">
            <TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 记录决策 Modal */}
      <Modal
        title="记录试点决策"
        open={decisionOpen}
        onCancel={() => { setDecisionOpen(false); decisionForm.resetFields(); }}
        onOk={handleDecision}
        confirmLoading={decisionLoading}
        destroyOnClose
      >
        <Form form={decisionForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="decision" label="决策结论" rules={[{ required: true }]}>
            <Select>
              <Option value="go"><Tag color="success">GO — 通过试点，推进上市</Tag></Option>
              <Option value="revise"><Tag color="warning">REVISE — 需优化后再试</Tag></Option>
              <Option value="stop"><Tag color="error">STOP — 终止研发</Tag></Option>
            </Select>
          </Form.Item>
          <Form.Item name="decision_note" label="决策理由">
            <TextArea rows={3} placeholder="请填写决策依据..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ── 发布管理 Tab ──────────────────────────────────────────────────────────────
const LaunchTab: React.FC<{ dishId: string; brandId: string }> = ({ dishId, brandId }) => {
  const [readiness,        setReadiness]        = useState<LaunchReadiness | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [createOpen,       setCreateOpen]       = useState(false);
  const [createLoading,    setCreateLoading]    = useState(false);
  const [form] = Form.useForm();

  const checkReadiness = async () => {
    setReadinessLoading(true);
    try {
      const res = await apiClient.get<LaunchReadiness>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/agent/launch-readiness`
      );
      setReadiness(res);
    } catch (e) {
      handleApiError(e, '检查失败');
    } finally {
      setReadinessLoading(false);
    }
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreateLoading(true);
      await apiClient.post(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/launch-projects`,
        values
      );
      showSuccess('发布项目已创建');
      setCreateOpen(false);
      form.resetFields();
      checkReadiness();
    } catch (e: any) {
      if (e?.errorFields) return;
      handleApiError(e, '创建失败');
    } finally {
      setCreateLoading(false);
    }
  };

  const readyPct = readiness
    ? Math.round((readiness.checklist.filter(c => c.passed).length / readiness.checklist.length) * 100)
    : 0;

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<CheckCircleOutlined />}
          loading={readinessLoading}
          onClick={checkReadiness}
        >
          检查上市就绪度
        </Button>
        <Button icon={<RocketOutlined />} onClick={() => setCreateOpen(true)}>
          创建发布项目
        </Button>
      </Space>

      {readinessLoading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" tip="Agent 检查中..." />
        </div>
      )}

      {readiness && !readinessLoading && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <ZCard>
                <ZKpi
                  label="就绪度"
                  value={`${readyPct}%`}
                  status={readiness.ready_to_launch ? 'good' : 'warning'}
                />
                <div style={{ marginTop: 8 }}>
                  {readiness.ready_to_launch
                    ? <Alert type="success" message="✅ 可以上市" showIcon />
                    : <Alert type="warning" message="⏳ 尚有前置项未完成" showIcon />}
                </div>
              </ZCard>
            </Col>
            <Col span={16}>
              {readiness.missing_items.length > 0 && (
                <Alert
                  type="error"
                  message="缺失项"
                  description={readiness.missing_items.join(' · ')}
                  showIcon
                  style={{ marginBottom: 12 }}
                />
              )}
              <Progress percent={readyPct} strokeColor={readiness.ready_to_launch ? '#1A7A52' : '#C8923A'} />
            </Col>
          </Row>

          <ZCard title="前置条件清单">
            <List
              size="small"
              dataSource={readiness.checklist}
              renderItem={item => (
                <List.Item>
                  <Space>
                    {item.passed
                      ? <CheckCircleOutlined style={{ color: '#1A7A52' }} />
                      : <CloseCircleOutlined style={{ color: '#C53030' }} />}
                    <Text type={item.passed ? undefined : 'danger'}>{item.item}</Text>
                    {item.note && <Text type="secondary">（{item.note}）</Text>}
                  </Space>
                </List.Item>
              )}
            />
          </ZCard>
        </>
      )}

      {!readiness && !readinessLoading && (
        <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-secondary)' }}>
          点击「检查上市就绪度」，LaunchAssistAgent 将自动检查配方、成本、试点、SOP等前置条件
        </div>
      )}

      <Modal
        title="创建发布项目"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); form.resetFields(); }}
        onOk={handleCreate}
        confirmLoading={createLoading}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="launch_type" label="上市类型" rules={[{ required: true }]}>
            <Select>
              <Option value="national">全国上市</Option>
              <Option value="regional">区域上市</Option>
              <Option value="pilot_expansion">试点扩张</Option>
              <Option value="seasonal">季节上市</Option>
            </Select>
          </Form.Item>
          <Form.Item name="planned_launch_date" label="计划上市日期">
            <Input type="date" />
          </Form.Item>
          <Form.Item name="target_stores" label="目标门店数量">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="launch_goal" label="上市目标">
            <TextArea rows={2} placeholder="如：本季度新品销量目标500份/月" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ── 复盘 Tab ──────────────────────────────────────────────────────────────────
const ReviewTab: React.FC<{ dishId: string; brandId: string }> = ({ dishId, brandId }) => {
  const [feedbacks,     setFeedbacks]     = useState<FeedbackItem[]>([]);
  const [reports,       setReports]       = useState<RetroReport[]>([]);
  const [reviewResult,  setReviewResult]  = useState<any>(null);
  const [feedLoading,   setFeedLoading]   = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [period,        setPeriod]        = useState('30d');

  // 添加反馈
  const [feedbackOpen,    setFeedbackOpen]    = useState(false);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedForm] = Form.useForm();

  const loadFeedbacks = useCallback(async () => {
    setFeedLoading(true);
    try {
      const res = await apiClient.get<FeedbackItem[]>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/feedbacks`
      );
      setFeedbacks(res);
    } catch (e) {
      handleApiError(e, '加载反馈失败');
    } finally {
      setFeedLoading(false);
    }
  }, [brandId, dishId]);

  const loadReports = useCallback(async () => {
    setReportLoading(true);
    try {
      const res = await apiClient.get<any>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/retrospective-reports`
      );
      setReports(res?.items ?? res ?? []);
    } catch (e) {
      handleApiError(e, '加载复盘报告失败');
    } finally {
      setReportLoading(false);
    }
  }, [brandId, dishId]);

  useEffect(() => { loadFeedbacks(); loadReports(); }, [loadFeedbacks, loadReports]);

  const runReview = async () => {
    setReviewLoading(true);
    try {
      const res = await apiClient.post<any>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/agent/review`,
        null,
        { params: { period, dry_run: false } }
      );
      setReviewResult(res);
      loadReports();
    } catch (e) {
      handleApiError(e, '运行复盘失败');
    } finally {
      setReviewLoading(false);
    }
  };

  const handleAddFeedback = async () => {
    try {
      const values = await feedForm.validateFields();
      setFeedbackLoading(true);
      await apiClient.post(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}/feedbacks`,
        values
      );
      showSuccess('反馈已记录');
      setFeedbackOpen(false);
      feedForm.resetFields();
      loadFeedbacks();
    } catch (e: any) {
      if (e?.errorFields) return;
      handleApiError(e, '记录失败');
    } finally {
      setFeedbackLoading(false);
    }
  };

  const ASSESSMENT_COLOR: Record<string, string> = {
    star:     'gold',
    keep:     'green',
    monitor:  'orange',
    optimize: 'blue',
    retire:   'red',
  };

  return (
    <div>
      <Row gutter={16}>
        {/* 左：反馈列表 */}
        <Col span={12}>
          <ZCard
            title={`顾客反馈 (${feedbacks.length}条)`}
            extra={
              <Button size="small" icon={<PlusOutlined />} onClick={() => setFeedbackOpen(true)}>
                添加
              </Button>
            }
          >
            <List
              loading={feedLoading}
              size="small"
              dataSource={feedbacks.slice(0, 10)}
              renderItem={item => (
                <List.Item>
                  <Space>
                    <Tag color={item.feedback_type === 'complaint' ? 'red' : 'blue'}>
                      {item.feedback_type}
                    </Tag>
                    {item.rating != null && <Text>⭐ {item.rating}</Text>}
                    <Text type="secondary">{item.content?.slice(0, 40) ?? '—'}</Text>
                  </Space>
                </List.Item>
              )}
              locale={{ emptyText: '暂无反馈数据' }}
            />
          </ZCard>
        </Col>

        {/* 右：AI复盘 */}
        <Col span={12}>
          <ZCard title="AI 复盘 Agent">
            <Space style={{ marginBottom: 12 }}>
              <Select value={period} onChange={setPeriod} style={{ width: 100 }}>
                <Option value="30d">近30天</Option>
                <Option value="60d">近60天</Option>
                <Option value="90d">近90天</Option>
              </Select>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={reviewLoading}
                onClick={runReview}
              >
                运行复盘
              </Button>
            </Space>

            {reviewLoading && <Spin tip="Agent 分析中..." />}

            {reviewResult && !reviewLoading && (
              <div>
                <Row gutter={12} style={{ marginBottom: 12 }}>
                  <Col span={12}>
                    <ZKpi label="反馈总数" value={reviewResult.total_feedbacks ?? 0} unit="条" />
                  </Col>
                  <Col span={12}>
                    <ZKpi label="退菜率" value={`${((reviewResult.return_rate ?? 0) * 100).toFixed(1)}%`} />
                  </Col>
                </Row>
                <div style={{ marginBottom: 8 }}>
                  <Text>生命周期评估：</Text>
                  <Tag color={ASSESSMENT_COLOR[reviewResult.lifecycle_assessment] ?? 'default'}>
                    {reviewResult.lifecycle_assessment}
                  </Tag>
                </div>
                {reviewResult.suggestions?.length > 0 && (
                  <List
                    size="small"
                    header={<Text strong>优化建议</Text>}
                    dataSource={reviewResult.suggestions}
                    renderItem={(s: string) => (
                      <List.Item><Text>• {s}</Text></List.Item>
                    )}
                  />
                )}
              </div>
            )}
          </ZCard>
        </Col>
      </Row>

      {/* 复盘报告 */}
      {reports.length > 0 && (
        <ZCard title="历史复盘报告" style={{ marginTop: 16 }}>
          <List
            loading={reportLoading}
            size="small"
            dataSource={reports}
            renderItem={r => (
              <List.Item>
                <Space>
                  <Tag color={ASSESSMENT_COLOR[r.lifecycle_assessment] ?? 'default'}>
                    {r.lifecycle_assessment}
                  </Tag>
                  <Text>{r.retrospective_period}</Text>
                  <Text type="secondary">{r.conclusion?.slice(0, 60) ?? '—'}</Text>
                  <Text type="secondary">{r.generated_at?.slice(0, 10) ?? ''}</Text>
                </Space>
              </List.Item>
            )}
          />
        </ZCard>
      )}

      {/* 添加反馈 Modal */}
      <Modal
        title="添加用户反馈"
        open={feedbackOpen}
        onCancel={() => { setFeedbackOpen(false); feedForm.resetFields(); }}
        onOk={handleAddFeedback}
        confirmLoading={feedbackLoading}
        destroyOnClose
      >
        <Form form={feedForm} layout="vertical" style={{ marginTop: 16 }}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="feedback_type" label="反馈类型" rules={[{ required: true }]}>
                <Select>
                  <Option value="taste">口味</Option>
                  <Option value="portion">分量</Option>
                  <Option value="presentation">摆盘</Option>
                  <Option value="complaint">投诉</Option>
                  <Option value="praise">好评</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="source" label="来源" rules={[{ required: true }]}>
                <Select>
                  <Option value="dine_in">堂食</Option>
                  <Option value="takeout">外卖</Option>
                  <Option value="pilot">试点</Option>
                  <Option value="internal">内部测试</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="rating" label="评分(1-5)">
            <InputNumber min={1} max={5} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="content" label="反馈内容">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ── 主页面 ─────────────────────────────────────────────────────────────────────
export default function DishRdDetailPage() {
  const navigate         = useNavigate();
  const { dishId }       = useParams<{ dishId: string }>();
  const brandId          = localStorage.getItem('brand_id') || 'B001';

  const [dish,    setDish]    = useState<DishDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');

  const loadDish = useCallback(async () => {
    if (!dishId) return;
    setLoading(true);
    try {
      const res = await apiClient.get<DishDetail>(
        `/api/v1/dish-rd/brands/${brandId}/dishes/${dishId}`
      );
      setDish(res);
    } catch (e) {
      handleApiError(e, '加载菜品失败');
    } finally {
      setLoading(false);
    }
  }, [brandId, dishId]);

  useEffect(() => { loadDish(); }, [loadDish]);

  if (!dishId) return <Alert type="error" message="dishId 缺失" />;

  const statusCfg = dish ? (DISH_STATUS_MAP[dish.status] ?? { label: dish.status, color: 'default' }) : null;

  const tabItems = [
    {
      key: 'overview',
      label: '概览',
      children: dish
        ? <OverviewTab dish={dish} brandId={brandId} onRefresh={loadDish} />
        : null,
    },
    {
      key: 'bom',
      label: '配方BOM',
      children: <RecipeBomTab dishId={dishId} brandId={brandId} />,
    },
    {
      key: 'cost',
      label: '成本仿真',
      children: <CostSimTab dishId={dishId} brandId={brandId} />,
    },
    {
      key: 'pilot',
      label: '试点管理',
      children: <PilotTab dishId={dishId} brandId={brandId} />,
    },
    {
      key: 'launch',
      label: '发布管理',
      children: <LaunchTab dishId={dishId} brandId={brandId} />,
    },
    {
      key: 'review',
      label: '复盘',
      children: <ReviewTab dishId={dishId} brandId={brandId} />,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* 顶部导航 */}
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/dish-rd')}>
          返回列表
        </Button>
      </Space>

      {/* 页面标题 */}
      {loading ? (
        <ZSkeleton rows={3} />
      ) : dish ? (
        <ZCard style={{ marginBottom: 16 }}>
          <Row align="middle" justify="space-between">
            <Col>
              <Space align="center">
                <Title level={4} style={{ margin: 0 }}>{dish.dish_name}</Title>
                <Text code>{dish.dish_code}</Text>
                {statusCfg && <Tag color={statusCfg.color}>{statusCfg.label}</Tag>}
                {dish.target_price_yuan != null && (
                  <Text type="secondary">目标售价 ¥{dish.target_price_yuan.toFixed(0)}</Text>
                )}
              </Space>
            </Col>
            <Col>
              <Button icon={<ReloadOutlined />} size="small" onClick={loadDish}>
                刷新
              </Button>
            </Col>
          </Row>
        </ZCard>
      ) : null}

      {/* Tab 内容 */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        type="card"
      />
    </div>
  );
}
