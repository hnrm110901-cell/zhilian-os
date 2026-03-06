import React, { useState, useCallback, useEffect } from 'react';
import {
  Row, Col, Card, Select, Button, Alert, Tag, Table, Statistic,
  Space, Spin, Typography, Divider, Progress, Tooltip,
} from 'antd';
import {
  CheckCircleOutlined, ReloadOutlined, ThunderboltOutlined,
  DollarOutlined, ClockCircleOutlined, RiseOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { Text, Title } = Typography;

// ── 状态颜色 ──────────────────────────────────────────────────────────────────

const sourceTag = (src: string) => {
  const map: Record<string, { color: string; text: string }> = {
    inventory:  { color: 'orange',  text: '库存' },
    food_cost:  { color: 'blue',    text: '成本' },
    reasoning:  { color: 'purple',  text: '综合' },
  };
  const cfg = map[src] || { color: 'default', text: src };
  return <Tag color={cfg.color}>{cfg.text}</Tag>;
};

const difficultyTag = (d: string) => {
  const map: Record<string, { color: string; text: string }> = {
    low:    { color: 'success', text: '易执行' },
    medium: { color: 'warning', text: '中等' },
    high:   { color: 'error',   text: '较复杂' },
  };
  const cfg = map[d] || { color: 'default', text: d };
  return <Tag color={cfg.color}>{cfg.text}</Tag>;
};

const DailyHubPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [stores, setStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState(localStorage.getItem('store_id') || 'STORE001');
  const [board, setBoard] = useState<any>(null);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [decisionsLoading, setDecisionsLoading] = useState(false);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载门店列表失败');
    }
  }, []);

  const loadBoard = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/daily-hub/${selectedStore}`);
      setBoard(res.data);
    } catch (err: any) {
      handleApiError(err, '加载备战板失败');
    } finally {
      setLoading(false);
    }
  }, [selectedStore]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadBoard(); }, [loadBoard]);

  const loadDecisions = useCallback(async () => {
    if (!selectedStore) return;
    setDecisionsLoading(true);
    try {
      const res = await apiClient.get('/api/v1/decisions/top3', {
        params: { store_id: selectedStore },
      });
      setDecisions(res.data?.decisions || []);
    } catch {
      // 决策加载失败不阻断页面，静默降级
      setDecisions([]);
    } finally {
      setDecisionsLoading(false);
    }
  }, [selectedStore]);

  useEffect(() => { loadDecisions(); }, [loadDecisions]);

  const handleApprove = async () => {
    if (!board) return;
    setApproving(true);
    try {
      const res = await apiClient.post(`/api/v1/daily-hub/${selectedStore}/approve`, {
        target_date: board.target_date,
      });
      setBoard(res.data);
      showSuccess('备战板已确认');
    } catch (err: any) {
      handleApiError(err, '审批失败');
    } finally {
      setApproving(false);
    }
  };

  const forecast = board?.tomorrow_forecast;
  const banquet = forecast?.banquet_track;
  const regular = forecast?.regular_track;
  const review = board?.yesterday_review;

  const barChartOption = {
    title: { text: '明日营收构成', left: 'center', textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['宴会（确定性）', '散客（概率性）'] },
    yAxis: { type: 'value', name: '元' },
    series: [{
      type: 'bar',
      data: [
        { value: (banquet?.deterministic_revenue || 0) / 100, itemStyle: { color: '#f5a623' } },
        { value: (regular?.predicted_revenue || 0) / 100, itemStyle: { color: '#1890ff' } },
      ],
    }],
  };

  const purchaseColumns = [
    { title: '物料名称', dataIndex: 'item_name', key: 'item_name' },
    { title: '当前库存', dataIndex: 'current_stock', key: 'current_stock' },
    { title: '建议采购量', dataIndex: 'recommended_quantity', key: 'recommended_quantity' },
    {
      title: '预警级别', dataIndex: 'alert_level', key: 'alert_level',
      render: (v: string) => {
        const color = v === 'critical' ? 'red' : v === 'urgent' ? 'orange' : 'gold';
        return <Tag color={color}>{v}</Tag>;
      },
    },
    { title: '供应商', dataIndex: 'supplier_name', key: 'supplier_name' },
  ];

  const shiftColumns = [
    { title: '员工ID', dataIndex: 'employee_id', key: 'employee_id' },
    { title: '班次', dataIndex: 'shift_type', key: 'shift_type' },
    { title: '开始', dataIndex: 'start_time', key: 'start_time' },
    { title: '结束', dataIndex: 'end_time', key: 'end_time' },
    { title: '岗位', dataIndex: 'position', key: 'position' },
  ];

  const approvalStatus = board?.approval_status;
  const isApproved = approvalStatus === 'approved' || approvalStatus === 'adjusted';

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }} placeholder="选择门店">
          {stores.length > 0
            ? stores.map((s: any) => (
                <Option key={s.store_id || s.id} value={s.store_id || s.id}>
                  {s.name || s.store_id || s.id}
                </Option>
              ))
            : <Option value="STORE001">STORE001</Option>}
        </Select>
        <Button icon={<ReloadOutlined />} onClick={loadBoard}>刷新</Button>
        {board && (
          <Tag color={isApproved ? 'green' : 'orange'}>
            {isApproved ? '已确认' : '待确认'}
          </Tag>
        )}
      </Space>

      <Spin spinning={loading}>
        <Row gutter={16}>
          {/* 左栏：昨日复盘 */}
          <Col xs={24} md={8}>
            <Card title="昨日复盘" size="small" style={{ marginBottom: 16 }}>
              <Row gutter={8}>
                <Col span={12}>
                  <Statistic title="总营收" value={(review?.total_revenue || 0) / 100} prefix="¥" precision={2} />
                </Col>
                <Col span={12}>
                  <Statistic title="订单数" value={review?.order_count || 0} />
                </Col>
              </Row>
              {review?.health_score != null && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">健康评分：</Text>
                  <Text strong>{review.health_score}</Text>
                </div>
              )}

              {/* 食材成本率 */}
              {review?.food_cost && (
                <>
                  <Divider style={{ margin: '8px 0' }} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>食材成本率</Text>
                    <Space size={4}>
                      <Text
                        strong
                        style={{
                          color: review.food_cost.variance_status === 'critical' ? '#f5222d'
                               : review.food_cost.variance_status === 'warning'  ? '#faad14'
                               : '#52c41a',
                          fontSize: 14,
                        }}
                      >
                        {review.food_cost.actual_cost_pct?.toFixed(1)}%
                      </Text>
                      <Tag
                        color={
                          review.food_cost.variance_status === 'critical' ? 'error'
                          : review.food_cost.variance_status === 'warning' ? 'warning'
                          : 'success'
                        }
                        style={{ fontSize: 11, padding: '0 4px' }}
                      >
                        {review.food_cost.variance_status === 'critical' ? '超标'
                         : review.food_cost.variance_status === 'warning' ? '偏高'
                         : '正常'}
                      </Tag>
                    </Space>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginTop: 2 }}>
                    <Text type="secondary">理论 {review.food_cost.theoretical_pct?.toFixed(1)}%</Text>
                    <Text style={{ color: review.food_cost.variance_pct > 0 ? '#f5222d' : '#52c41a', fontWeight: 600 }}>
                      {review.food_cost.variance_pct > 0 ? '+' : ''}{review.food_cost.variance_pct?.toFixed(1)}%
                    </Text>
                  </div>
                  {review.food_cost.variance_status !== 'ok' && (review.food_cost.top_ingredients || []).length > 0 && (
                    <div style={{ marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>主要消耗：</Text>
                      {review.food_cost.top_ingredients.slice(0, 2).map((ing: any, i: number) => (
                        <div key={i} style={{ fontSize: 11, color: '#fa8c16' }}>
                          • {ing.name} ¥{ing.usage_cost_yuan?.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
              {(review?.highlights || []).length > 0 && (
                <>
                  <Divider style={{ margin: '8px 0' }} />
                  <Text type="secondary" style={{ fontSize: 12 }}>亮点</Text>
                  {review.highlights.map((h: string, i: number) => (
                    <div key={i} style={{ fontSize: 12 }}>• {h}</div>
                  ))}
                </>
              )}
              {(review?.alerts || []).length > 0 && (
                <>
                  <Divider style={{ margin: '8px 0' }} />
                  <Text type="warning" style={{ fontSize: 12 }}>关注</Text>
                  {review.alerts.map((a: string, i: number) => (
                    <div key={i} style={{ fontSize: 12, color: '#fa8c16' }}>• {a}</div>
                  ))}
                </>
              )}
            </Card>
          </Col>

          {/* 中栏：明日预测 */}
          <Col xs={24} md={8}>
            <Card title="明日预测" size="small" style={{ marginBottom: 16 }}>
              {banquet?.active && (
                <Alert
                  message={`宴会熔断：${banquet.banquets.length} 场宴会，确定性营收 ¥${((banquet.deterministic_revenue || 0) / 100).toFixed(0)}`}
                  type="warning"
                  showIcon
                  style={{ marginBottom: 8 }}
                />
              )}
              <Row gutter={8} style={{ marginBottom: 8 }}>
                <Col span={12}>
                  <Statistic
                    title="预测总营收"
                    value={(forecast?.total_predicted_revenue || 0) / 100}
                    prefix="¥"
                    precision={0}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
                    置信区间<br />
                    ¥{((forecast?.total_lower || 0) / 100).toFixed(0)} ~ ¥{((forecast?.total_upper || 0) / 100).toFixed(0)}
                  </div>
                </Col>
              </Row>
              <Space wrap size={4} style={{ marginBottom: 8 }}>
                {forecast?.weather && (
                  <Tag color="blue">
                    {forecast.weather.condition} {forecast.weather.temperature}°C
                  </Tag>
                )}
                {forecast?.holiday && (
                  <Tag color="red">{forecast.holiday.name}</Tag>
                )}
              </Space>
              <ReactECharts option={barChartOption} style={{ height: 180 }} />
            </Card>
          </Col>

          {/* 右栏：行动面板 */}
          <Col xs={24} md={8}>
            <Card title="行动面板" size="small" style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 12 }}>
                <Text strong style={{ fontSize: 13 }}>采购清单</Text>
                <Table
                  dataSource={board?.purchase_order || []}
                  columns={purchaseColumns}
                  rowKey={(r: any) => r.item_name}
                  size="small"
                  pagination={false}
                  scroll={{ y: 160 }}
                  style={{ marginTop: 4 }}
                />
              </div>
              <Divider style={{ margin: '8px 0' }} />
              <div style={{ marginBottom: 12 }}>
                <Text strong style={{ fontSize: 13 }}>
                  排班计划（{board?.staffing_plan?.total_staff || 0} 人）
                </Text>
                <Table
                  dataSource={board?.staffing_plan?.shifts || []}
                  columns={shiftColumns}
                  rowKey={(r: any, i: any) => i}
                  size="small"
                  pagination={false}
                  scroll={{ y: 160 }}
                  style={{ marginTop: 4 }}
                />
              </div>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                block
                loading={approving}
                disabled={isApproved}
                onClick={handleApprove}
              >
                {isApproved ? '已确认备战' : '一键确认备战'}
              </Button>
            </Card>
          </Col>
        </Row>

        {/* Top3 AI 决策推荐 */}
        <Card
          title={
            <Space>
              <ThunderboltOutlined style={{ color: '#faad14' }} />
              <span>今日 AI 决策推荐</span>
              <Tag color="blue">Top 3</Tag>
            </Space>
          }
          extra={
            <Button size="small" icon={<ReloadOutlined />} onClick={loadDecisions} loading={decisionsLoading}>
              刷新
            </Button>
          }
          style={{ marginTop: 16 }}
        >
          <Spin spinning={decisionsLoading}>
            {decisions.length === 0 && !decisionsLoading ? (
              <Alert message="暂无决策推荐，系统正在分析中" type="info" showIcon />
            ) : (
              <Row gutter={16}>
                {decisions.map((d: any) => (
                  <Col key={d.rank} xs={24} md={8}>
                    <Card
                      size="small"
                      style={{
                        borderLeft: `4px solid ${d.rank === 1 ? '#f5222d' : d.rank === 2 ? '#fa8c16' : '#1890ff'}`,
                        marginBottom: 8,
                      }}
                    >
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        <Space>
                          <Tag color={d.rank === 1 ? 'red' : d.rank === 2 ? 'orange' : 'blue'}>
                            #{d.rank}
                          </Tag>
                          {sourceTag(d.source)}
                          {difficultyTag(d.execution_difficulty)}
                        </Space>

                        <Text strong style={{ fontSize: 14 }}>{d.title}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>{d.action}</Text>

                        <Row gutter={8} style={{ marginTop: 4 }}>
                          <Col span={12}>
                            <Tooltip title="预期净收益">
                              <Space size={4}>
                                <DollarOutlined style={{ color: '#52c41a' }} />
                                <Text style={{ color: '#52c41a', fontWeight: 600 }}>
                                  ¥{d.net_benefit_yuan?.toLocaleString()}
                                </Text>
                              </Space>
                            </Tooltip>
                          </Col>
                          <Col span={12}>
                            <Tooltip title="执行窗口">
                              <Space size={4}>
                                <ClockCircleOutlined style={{ color: '#fa8c16' }} />
                                <Text style={{ fontSize: 12 }}>{d.decision_window_label}</Text>
                              </Space>
                            </Tooltip>
                          </Col>
                        </Row>

                        <div>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            置信度 {d.confidence_pct?.toFixed(0)}%
                          </Text>
                          <Progress
                            percent={d.confidence_pct}
                            size="small"
                            showInfo={false}
                            strokeColor={d.confidence_pct >= 80 ? '#52c41a' : d.confidence_pct >= 60 ? '#faad14' : '#f5222d'}
                          />
                        </div>

                        <Button
                          type={d.rank === 1 ? 'primary' : 'default'}
                          size="small"
                          icon={<RiseOutlined />}
                          block
                          href="/approval-list"
                        >
                          去审批
                        </Button>
                      </Space>
                    </Card>
                  </Col>
                ))}
              </Row>
            )}
          </Spin>
        </Card>
      </Spin>
    </div>
  );
};

export default DailyHubPage;
