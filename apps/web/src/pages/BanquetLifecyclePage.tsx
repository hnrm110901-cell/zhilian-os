import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Col, Row, Tabs, Statistic, Tag, Space, Button, Form, Input,
  Modal, Badge, Spin, Alert, Calendar, Tooltip, Select, Empty,
  Typography, Progress, DatePicker,
} from 'antd';
import {
  FunnelPlotOutlined, CalendarOutlined, BarChartOutlined,
  ArrowRightOutlined, RightCircleOutlined, ReloadOutlined,
  StarFilled, WarningOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Title, Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;

// ── Stage definitions ───────────────────────────────────────────────────
const STAGES = [
  { key: 'lead',        label: '商机',  color: '#8c8c8c', bg: '#f5f5f5' },
  { key: 'intent',      label: '意向',  color: '#0AAF9A', bg: '#e6f7ff' },
  { key: 'room_lock',   label: '锁台',  color: '#C8923A', bg: 'rgba(200,146,58,0.08)' },
  { key: 'signed',      label: '签约',  color: '#1A7A52', bg: 'rgba(26,122,82,0.08)' },
  { key: 'preparation', label: '准备',  color: '#722ed1', bg: '#f9f0ff' },
  { key: 'service',     label: '服务中', color: '#eb2f96', bg: '#fff0f6' },
  { key: 'completed',   label: '已完成', color: '#13c2c2', bg: '#e6fffb' },
];
const STAGE_MAP: Record<string, typeof STAGES[0]> = Object.fromEntries(
  STAGES.map(s => [s.key, s])
);
const NEXT_STAGES: Record<string, string[]> = {
  lead:        ['intent', 'cancelled'],
  intent:      ['room_lock', 'cancelled'],
  room_lock:   ['signed', 'lead', 'cancelled'],
  signed:      ['preparation', 'cancelled'],
  preparation: ['service', 'cancelled'],
  service:     ['completed', 'cancelled'],
  completed:   [],
  cancelled:   [],
};

// ── Pipeline Kanban ───────────────────────────────────────────────────────

interface PipelineItem {
  id: string;
  customer_name: string;
  reservation_date: string;
  party_size: number;
  estimated_budget: number | null;
  stage_days: number;
  room_name?: string;
}

interface PipelineStage {
  stage:             string;
  label:             string;
  count:             number;
  confirmed_revenue: number;
  items:             PipelineItem[];
}

const BudgetDisplay: React.FC<{ cents: number | null }> = ({ cents }) => {
  if (!cents) return <Text type="secondary">未报价</Text>;
  return <Text style={{ color: '#1A7A52' }}>¥{(cents / 100).toLocaleString()}</Text>;
};

const PipelineKanban: React.FC<{
  pipeline:    PipelineStage[];
  onAdvance:   (item: PipelineItem, currentStage: string) => void;
  loading:     boolean;
}> = ({ pipeline, onAdvance, loading }) => (
  <Spin spinning={loading}>
    <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 8 }}>
      {STAGES.map(stageDef => {
        const col = pipeline.find(p => p.stage === stageDef.key);
        const items = col?.items ?? [];
        const count = col?.count ?? 0;
        const revenue = col?.confirmed_revenue ?? 0;
        return (
          <div key={stageDef.key} style={{ minWidth: 200, flex: '0 0 200px' }}>
            {/* Column header */}
            <div style={{
              background: stageDef.bg, borderRadius: '8px 8px 0 0',
              padding: '8px 12px', borderBottom: `3px solid ${stageDef.color}`,
            }}>
              <Space>
                <Badge count={count} style={{ backgroundColor: stageDef.color }} />
                <Text strong style={{ color: stageDef.color }}>{stageDef.label}</Text>
              </Space>
              {revenue > 0 && (
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    签约额 ¥{(revenue / 100).toLocaleString()}
                  </Text>
                </div>
              )}
            </div>
            {/* Cards */}
            <div style={{
              background: '#fafafa', borderRadius: '0 0 8px 8px',
              minHeight: 300, padding: 8, display: 'flex', flexDirection: 'column', gap: 8,
            }}>
              {items.length === 0 && (
                <div style={{ textAlign: 'center', paddingTop: 40 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>暂无</Text>
                </div>
              )}
              {items.map(item => (
                <Card
                  key={item.id}
                  size="small"
                  hoverable
                  style={{ borderLeft: `3px solid ${stageDef.color}`, cursor: 'pointer' }}
                  onClick={() => onAdvance(item, stageDef.key)}
                  bodyStyle={{ padding: '8px 10px' }}
                >
                  <Text strong style={{ fontSize: 13 }}>{item.customer_name}</Text>
                  <div style={{ marginTop: 2 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {item.reservation_date} · {item.party_size}人
                    </Text>
                  </div>
                  <div style={{ marginTop: 2 }}>
                    <BudgetDisplay cents={item.estimated_budget} />
                  </div>
                  {item.stage_days > 0 && (
                    <div style={{ marginTop: 4 }}>
                      <Tag color={item.stage_days > 7 ? 'red' : 'default'} style={{ fontSize: 10 }}>
                        已停留 {item.stage_days}天
                      </Tag>
                    </div>
                  )}
                  {item.room_name && (
                    <div style={{ marginTop: 2 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>🏠 {item.room_name}</Text>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  </Spin>
);

// ── Funnel Stats ──────────────────────────────────────────────────────────

const FunnelStats: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [stats, setStats]   = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [daysBack, setDaysBack] = useState(90);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(
        `/api/v1/banquet-lifecycle/${storeId}/funnel`,
        { params: { days_back: daysBack } },
      );
      setStats(res);
    } catch (err: any) {
      handleApiError(err, '加载漏斗统计失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, daysBack]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <Spin />;
  if (!stats)  return <Empty description="暂无统计数据" />;

  const stages: Record<string, number> = stats.stage_counts ?? {};
  const rates:  Record<string, number> = stats.conversion_rates ?? {};
  const totalLead = stages['lead'] ?? 0;

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Text>统计周期：</Text>
        <Select value={daysBack} onChange={v => { setDaysBack(v); }} style={{ width: 120 }}>
          <Option value={30}>近 30 天</Option>
          <Option value={90}>近 90 天</Option>
          <Option value={180}>近 180 天</Option>
          <Option value={365}>近 1 年</Option>
        </Select>
        <Button icon={<ReloadOutlined />} onClick={load} size="small">刷新</Button>
      </Space>

      {/* Stage counts */}
      <Row gutter={[12, 12]} style={{ marginBottom: 24 }}>
        {STAGES.map(s => (
          <Col key={s.key} xs={12} sm={8} md={4}>
            <Card size="small" style={{ borderTop: `3px solid ${s.color}`, textAlign: 'center' }}>
              <Statistic
                title={<Text style={{ color: s.color, fontSize: 12 }}>{s.label}</Text>}
                value={stages[s.key] ?? 0}
                valueStyle={{ color: s.color, fontSize: 20 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* Conversion rates */}
      <Card title="阶段转化率" size="small" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'center' }}>
          {STAGES.slice(0, -1).map((s, i) => {
            const nextKey = STAGES[i + 1]?.key;
            const rateKey = `${s.key}_to_${nextKey}`;
            const rate = rates[rateKey];
            return (
              <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ textAlign: 'center' }}>
                  <Text style={{ color: s.color, display: 'block', fontSize: 11 }}>{s.label}</Text>
                  <Text strong>{stages[s.key] ?? 0}</Text>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <ArrowRightOutlined style={{ color: '#bbb' }} />
                  {rate !== undefined && (
                    <Text
                      style={{
                        display: 'block', fontSize: 10,
                        color: rate >= 50 ? '#1A7A52' : rate >= 20 ? '#C8923A' : '#C53030',
                      }}
                    >
                      {rate.toFixed(0)}%
                    </Text>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Summary */}
      <Row gutter={16}>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="商机总量"
              value={totalLead}
              suffix="个"
              valueStyle={{ color: '#0AAF9A' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="平均签约周期"
              value={stats.avg_days_to_signed?.toFixed(1) ?? '-'}
              suffix="天"
              valueStyle={{ color: '#C8923A' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="lead→signed 总转化率"
              value={
                totalLead > 0
                  ? ((stages['signed'] ?? 0) / totalLead * 100).toFixed(1)
                  : 0
              }
              suffix="%"
              valueStyle={{ color: '#1A7A52' }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

// ── Availability Calendar ─────────────────────────────────────────────────

interface CalDay {
  date:            string;
  confirmed_count: number;
  locked_count:    number;
  total_guests:    number;
  available:       boolean;
  demand_factor:   number;
  is_auspicious:   boolean;
}

const AvailabilityCalendar: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [year,     setYear]     = useState(dayjs().year());
  const [month,    setMonth]    = useState(dayjs().month() + 1);
  const [calData,  setCalData]  = useState<Record<string, CalDay>>({});
  const [loading,  setLoading]  = useState(false);
  const [capacity, setCapacity] = useState(200);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(
        `/api/v1/banquet-lifecycle/${storeId}/availability/${year}/${month}`,
        { params: { max_capacity: capacity } },
      );
      const map: Record<string, CalDay> = {};
      (res?.days ?? []).forEach((d: CalDay) => { map[d.date] = d; });
      setCalData(map);
    } catch (err: any) {
      handleApiError(err, '加载销控日历失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, year, month, capacity]);

  useEffect(() => { load(); }, [load]);

  const dateCellRender = (value: dayjs.Dayjs) => {
    const key = value.format('YYYY-MM-DD');
    const d = calData[key];
    if (!d) return null;
    return (
      <div style={{ fontSize: 10, lineHeight: 1.4 }}>
        {d.is_auspicious && (
          <Tooltip title={`吉日 ×${d.demand_factor.toFixed(1)}`}>
            <StarFilled style={{ color: '#faad14', marginRight: 2 }} />
          </Tooltip>
        )}
        {d.confirmed_count > 0 && (
          <Tag color="green" style={{ fontSize: 9, padding: '0 3px', marginRight: 2 }}>
            签{d.confirmed_count}
          </Tag>
        )}
        {d.locked_count > 0 && (
          <Tag color="mint" style={{ fontSize: 9, padding: '0 3px' }}>
            锁{d.locked_count}
          </Tag>
        )}
        {d.total_guests > 0 && (
          <div style={{ color: '#666' }}>{d.total_guests}人</div>
        )}
        {!d.available && (
          <Tag color="red" style={{ fontSize: 9, padding: '0 2px' }}>满</Tag>
        )}
      </div>
    );
  };

  return (
    <Spin spinning={loading}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col>
          <Space>
            <Text>年月：</Text>
            <DatePicker
              picker="month"
              value={dayjs(`${year}-${String(month).padStart(2, '0')}-01`)}
              onChange={v => {
                if (v) { setYear(v.year()); setMonth(v.month() + 1); }
              }}
            />
          </Space>
        </Col>
        <Col>
          <Space>
            <Text>场地容量：</Text>
            <Select value={capacity} onChange={v => setCapacity(v)} style={{ width: 100 }}>
              <Option value={100}>100人</Option>
              <Option value={200}>200人</Option>
              <Option value={300}>300人</Option>
              <Option value={500}>500人</Option>
            </Select>
          </Space>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={load} size="small">刷新</Button>
        </Col>
      </Row>

      {/* Legend */}
      <Space style={{ marginBottom: 12 }} wrap>
        <Tag color="green">签约</Tag>
        <Tag color="mint">锁台（未签）</Tag>
        <Tag color="red">已满</Tag>
        <Space size={4}><StarFilled style={{ color: '#faad14' }} /><Text style={{ fontSize: 12 }}>吉日</Text></Space>
      </Space>

      <Card>
        <Calendar
          value={dayjs(`${year}-${String(month).padStart(2, '0')}-01`)}
          fullscreen
          dateCellRender={dateCellRender}
          onPanelChange={v => { setYear(v.year()); setMonth(v.month() + 1); }}
        />
      </Card>
    </Spin>
  );
};

// ── Main Page ─────────────────────────────────────────────────────────────

const BanquetLifecyclePage: React.FC = () => {
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [pipeline,      setPipeline]      = useState<PipelineStage[]>([]);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [activeTab,     setActiveTab]     = useState('pipeline');

  // Advance-stage modal
  const [advanceModal,  setAdvanceModal]  = useState(false);
  const [advanceItem,   setAdvanceItem]   = useState<PipelineItem | null>(null);
  const [currentStage,  setCurrentStage]  = useState('');
  const [targetStage,   setTargetStage]   = useState('');
  const [advanceReason, setAdvanceReason] = useState('');
  const [advancing,     setAdvancing]     = useState(false);
  const [advanceForm]                     = Form.useForm();

  // Date range filter
  const [dateGte, setDateGte] = useState<string>('');
  const [dateLte, setDateLte] = useState<string>('');

  const loadPipeline = useCallback(async () => {
    setPipelineLoading(true);
    try {
      const params: any = {};
      if (dateGte) params.event_date_gte = dateGte;
      if (dateLte) params.event_date_lte = dateLte;
      const res = await apiClient.get(
        `/api/v1/banquet-lifecycle/${storeId}/pipeline`, { params },
      );
      // Normalize: API returns {stages: [...]} or [{stage, items, ...}]
      const raw: any = res;
      const stages: PipelineStage[] = Array.isArray(raw)
        ? raw
        : (raw?.stages ?? []);
      setPipeline(stages);
    } catch (err: any) {
      handleApiError(err, '加载销售漏斗失败');
    } finally {
      setPipelineLoading(false);
    }
  }, [storeId, dateGte, dateLte]);

  useEffect(() => {
    const loadStores = async () => {
      try {
        const res = await apiClient.get('/api/v1/stores');
        const list: any[] = res.stores || res || [];
        setStores(list);
        if (list.length > 0) setStoreId(list[0].store_id || list[0].id || 'STORE001');
      } catch { /* ignore */ }
    };
    loadStores();
  }, []);

  useEffect(() => {
    if (activeTab === 'pipeline') loadPipeline();
  }, [activeTab, loadPipeline]);

  const openAdvanceModal = (item: PipelineItem, stage: string) => {
    setAdvanceItem(item);
    setCurrentStage(stage);
    const nexts = NEXT_STAGES[stage] ?? [];
    setTargetStage(nexts.find(s => s !== 'cancelled') ?? nexts[0] ?? '');
    setAdvanceReason('');
    advanceForm.resetFields();
    setAdvanceModal(true);
  };

  const handleAdvance = async () => {
    if (!advanceItem || !targetStage) return;
    setAdvancing(true);
    try {
      await apiClient.put(
        `/api/v1/banquet-lifecycle/${storeId}/${advanceItem.id}/stage`,
        { to_stage: targetStage, reason: advanceReason || undefined },
      );
      showSuccess(`${advanceItem.customer_name} 已推进至「${STAGE_MAP[targetStage]?.label ?? targetStage}」`);
      setAdvanceModal(false);
      loadPipeline();
    } catch (err: any) {
      handleApiError(err, '阶段推进失败');
    } finally {
      setAdvancing(false);
    }
  };

  // Compute total pipeline summary
  const totalCount     = pipeline.reduce((s, p) => s + p.count, 0);
  const totalRevenue   = pipeline.reduce((s, p) => s + p.confirmed_revenue, 0);
  const signedCount    = pipeline.find(p => p.stage === 'signed')?.count ?? 0;
  const roomLockCount  = pipeline.find(p => p.stage === 'room_lock')?.count ?? 0;

  const tabItems = [
    {
      key:      'pipeline',
      label:    <span><FunnelPlotOutlined /> 销售漏斗</span>,
      children: (
        <>
          {/* Summary bar */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card size="small">
                <Statistic title="漏斗总量" value={totalCount} suffix="个" valueStyle={{ color: '#0AAF9A' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title="已签约" value={signedCount} suffix="个" valueStyle={{ color: '#1A7A52' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="锁台待签"
                  value={roomLockCount}
                  suffix="个"
                  valueStyle={{ color: roomLockCount > 0 ? '#C8923A' : '#666' }}
                  prefix={roomLockCount > 3 ? <WarningOutlined /> : undefined}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="签约总额"
                  value={(totalRevenue / 100).toLocaleString()}
                  prefix="¥"
                  valueStyle={{ color: '#1A7A52' }}
                />
              </Card>
            </Col>
          </Row>

          {/* Filters */}
          <Space style={{ marginBottom: 12 }} wrap>
            <Text type="secondary">宴会日期：</Text>
            <DatePicker
              placeholder="开始日期"
              onChange={v => setDateGte(v ? v.format('YYYY-MM-DD') : '')}
              style={{ width: 140 }}
            />
            <Text type="secondary">—</Text>
            <DatePicker
              placeholder="结束日期"
              onChange={v => setDateLte(v ? v.format('YYYY-MM-DD') : '')}
              style={{ width: 140 }}
            />
            <Button icon={<ReloadOutlined />} onClick={loadPipeline} size="small">刷新</Button>
          </Space>

          <PipelineKanban
            pipeline={pipeline}
            onAdvance={openAdvanceModal}
            loading={pipelineLoading}
          />

          <Alert
            style={{ marginTop: 16 }}
            type="info"
            showIcon
            message="点击任意预约卡片可推进阶段；橙色「锁台」卡片超过 7 天未签约将自动回退至意向阶段。"
          />
        </>
      ),
    },
    {
      key:      'calendar',
      label:    <span><CalendarOutlined /> 销控日历</span>,
      children: <AvailabilityCalendar storeId={storeId} />,
    },
    {
      key:      'funnel',
      label:    <span><BarChartOutlined /> 漏斗统计</span>,
      children: <FunnelStats storeId={storeId} />,
    },
  ];

  const nextOptions = NEXT_STAGES[currentStage] ?? [];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <FunnelPlotOutlined style={{ marginRight: 8, color: '#722ed1' }} />
            宴会全生命周期管理
          </Title>
          <Text type="secondary">
            宴会销售漏斗 · 销控日历 · 7阶段全流程追踪
          </Text>
        </div>
        <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
          {stores.length > 0
            ? stores.map((s: any) => <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>)
            : <Option value="STORE001">STORE001</Option>}
        </Select>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />

      {/* Advance Stage Modal */}
      <Modal
        title={
          <Space>
            <RightCircleOutlined style={{ color: '#722ed1' }} />
            推进阶段 — {advanceItem?.customer_name}
          </Space>
        }
        open={advanceModal}
        onCancel={() => setAdvanceModal(false)}
        onOk={handleAdvance}
        okText="确认推进"
        confirmLoading={advancing}
        okButtonProps={{ disabled: !targetStage }}
        width={480}
      >
        {advanceItem && (
          <>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Text type="secondary">宴会日期：</Text>
                <Text>{advanceItem.reservation_date}</Text>
              </Col>
              <Col span={12}>
                <Text type="secondary">人数：</Text>
                <Text>{advanceItem.party_size} 人</Text>
              </Col>
              <Col span={12} style={{ marginTop: 8 }}>
                <Text type="secondary">预算：</Text>
                <BudgetDisplay cents={advanceItem.estimated_budget} />
              </Col>
              <Col span={12} style={{ marginTop: 8 }}>
                <Text type="secondary">当前阶段：</Text>
                <Tag color={STAGE_MAP[currentStage]?.color}>
                  {STAGE_MAP[currentStage]?.label ?? currentStage}
                </Tag>
              </Col>
            </Row>

            <Form form={advanceForm} layout="vertical">
              <Form.Item label="目标阶段" required>
                <Select
                  value={targetStage}
                  onChange={setTargetStage}
                  style={{ width: '100%' }}
                >
                  {nextOptions.map(s => (
                    <Option key={s} value={s}>
                      <Tag color={s === 'cancelled' ? 'red' : STAGE_MAP[s]?.color}>
                        {STAGE_MAP[s]?.label ?? s}
                      </Tag>
                      {s === 'cancelled' && ' (终态)'}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item label="变更原因">
                <TextArea
                  rows={3}
                  placeholder="可选：填写推进原因（如：客户已确认合同）"
                  value={advanceReason}
                  onChange={e => setAdvanceReason(e.target.value)}
                />
              </Form.Item>
            </Form>

            {targetStage === 'room_lock' && (
              <Alert
                type="warning"
                showIcon
                message="锁台后 7 天内未完成签约，系统将自动回退至意向阶段。"
                style={{ marginTop: 0 }}
              />
            )}
            {targetStage === 'signed' && (
              <Alert
                type="success"
                showIcon
                message="签约后系统将自动生成/更新 BEO 宴会工单。"
              />
            )}
            {targetStage === 'cancelled' && (
              <Alert
                type="error"
                showIcon
                message="取消为终态，无法再恢复。请确认后操作。"
              />
            )}
          </>
        )}
      </Modal>
    </div>
  );
};

export default BanquetLifecyclePage;
