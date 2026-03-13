/**
 * 预订AI助手 — Phase P4 (屯象独有)
 * 智能跟进话术 · 意向预测排名 · 退订分析 · AI日报
 */
import React, { useEffect, useState } from 'react';
import {
  Card, Row, Col, Table, Statistic, Tabs, Tag, Button, Spin,
  Typography, Space, message, Progress, List, Alert, Descriptions,
  Collapse, Tooltip, Empty, Badge,
} from 'antd';
import {
  RobotOutlined, ThunderboltOutlined, PieChartOutlined,
  FileTextOutlined, PhoneOutlined, WechatOutlined,
  ArrowUpOutlined, ArrowDownOutlined, WarningOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';

const { Title, Text, Paragraph } = Typography;

interface DailyReport {
  date: string;
  summary: {
    total_active_leads: number;
    pipeline_value_yuan: number;
    signed_today: number;
    completed_today: number;
    lost_today: number;
    lost_value_yuan: number;
  };
  funnel_snapshot: Array<{ stage: string; count: number; total_value_yuan: number }>;
  cancellation_snapshot: {
    top_reasons: Array<{ category: string; label: string; count: number; percentage: number }>;
    insights: string[];
  };
  ai_message: string;
}

interface CancellationAnalysis {
  total_lost: number;
  total_lost_value_yuan: number;
  categories: Array<{ category: string; label: string; count: number; percentage: number }>;
  competitor_analysis: Array<{ name: string; count: number; percentage: number }>;
  insights: string[];
  suggestions: Array<{ category: string; action: string; expected_impact: string }>;
}

const STAGE_LABELS: Record<string, string> = {
  lead: '线索', intent: '意向', room_lock: '锁厅',
  negotiation: '议价', signed: '签约', preparation: '筹备',
  completed: '完成', lost: '输单',
};

export default function ReservationAIPage() {
  const [loading, setLoading] = useState(true);
  const [storeId] = useState('STORE001');
  const [activeTab, setActiveTab] = useState('report');

  const [dailyReport, setDailyReport] = useState<DailyReport | null>(null);
  const [cancellationData, setCancellationData] = useState<CancellationAnalysis | null>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [report, cancellation] = await Promise.all([
        apiClient.get<DailyReport>(`/api/v1/reservation-ai/daily-report?store_id=${storeId}`),
        apiClient.get<CancellationAnalysis>(`/api/v1/reservation-ai/cancellation-analysis?store_id=${storeId}`),
      ]);
      setDailyReport(report);
      setCancellationData(cancellation);
    } catch (e: any) {
      message.error(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const summary = dailyReport?.summary;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <RobotOutlined /> 预订AI助手
        </Title>
        <Button onClick={fetchData}>刷新</Button>
      </div>

      <Spin spinning={loading}>
        {/* 核心指标 */}
        {summary && (
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={4}>
              <Card size="small">
                <Statistic title="活跃线索" value={summary.total_active_leads} suffix="条" />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic title="管道总额" value={summary.pipeline_value_yuan} prefix="¥" precision={0} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic title="今日签约" value={summary.signed_today} suffix="单" valueStyle={{ color: '#52c41a' }} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic title="今日完成" value={summary.completed_today} suffix="单" valueStyle={{ color: '#1890ff' }} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic title="今日输单" value={summary.lost_today} suffix="单" valueStyle={{ color: '#ff4d4f' }} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic title="输单金额" value={summary.lost_value_yuan} prefix="¥" precision={0} valueStyle={{ color: '#ff4d4f' }} />
              </Card>
            </Col>
          </Row>
        )}

        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'report',
            label: <span><FileTextOutlined /> AI日报</span>,
            children: dailyReport ? (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {/* AI 消息卡片 */}
                <Card size="small" style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', border: 'none' }}>
                  <pre style={{ color: '#fff', margin: 0, fontFamily: 'inherit', whiteSpace: 'pre-wrap' }}>
                    {dailyReport.ai_message}
                  </pre>
                </Card>

                {/* 漏斗快照 */}
                <Card size="small" title="漏斗快照">
                  <Row gutter={8}>
                    {dailyReport.funnel_snapshot
                      .filter(s => s.stage !== 'lost')
                      .map(s => (
                        <Col key={s.stage} flex="auto">
                          <div style={{ textAlign: 'center', padding: '8px 4px', background: '#fafafa', borderRadius: 6 }}>
                            <div style={{ fontSize: 20, fontWeight: 700 }}>{s.count}</div>
                            <Tag>{STAGE_LABELS[s.stage] || s.stage}</Tag>
                            <div style={{ fontSize: 11, color: '#999' }}>¥{s.total_value_yuan?.toFixed(0) || 0}</div>
                          </div>
                        </Col>
                      ))
                    }
                  </Row>
                </Card>

                {/* 退订洞察 */}
                {dailyReport.cancellation_snapshot.insights.length > 0 && (
                  <Card size="small" title="退订洞察">
                    {dailyReport.cancellation_snapshot.insights.map((insight, i) => (
                      <Alert
                        key={i}
                        message={insight}
                        type={insight.includes('⚠️') ? 'warning' : 'info'}
                        showIcon
                        style={{ marginBottom: 8 }}
                      />
                    ))}
                  </Card>
                )}
              </Space>
            ) : <Empty description="暂无日报数据" />,
          },
          {
            key: 'cancellation',
            label: <span><PieChartOutlined /> 退订分析</span>,
            children: cancellationData ? (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {/* 退订原因分布 */}
                <Card size="small" title={`退订原因分布（共${cancellationData.total_lost}笔，¥${cancellationData.total_lost_value_yuan?.toFixed(0) || 0}）`}>
                  {cancellationData.categories.length === 0 ? (
                    <Empty description="暂无输单数据" />
                  ) : (
                    <List
                      size="small"
                      dataSource={cancellationData.categories}
                      renderItem={cat => (
                        <List.Item
                          extra={<Text strong>{cat.count}笔</Text>}
                        >
                          <Space style={{ width: '100%' }}>
                            <Text style={{ width: 80, display: 'inline-block' }}>{cat.label}</Text>
                            <Progress
                              percent={cat.percentage}
                              size="small"
                              style={{ flex: 1 }}
                              strokeColor={cat.percentage >= 30 ? '#ff4d4f' : cat.percentage >= 15 ? '#faad14' : '#52c41a'}
                            />
                          </Space>
                        </List.Item>
                      )}
                    />
                  )}
                </Card>

                {/* 竞对流失 */}
                {cancellationData.competitor_analysis.length > 0 && (
                  <Card size="small" title="竞对流失分析">
                    <Table
                      dataSource={cancellationData.competitor_analysis}
                      columns={[
                        { title: '竞对', dataIndex: 'name', key: 'name' },
                        {
                          title: '输单数',
                          dataIndex: 'count',
                          key: 'count',
                          render: (v: number) => <Text type="danger">{v}笔</Text>,
                        },
                        {
                          title: '占比',
                          dataIndex: 'percentage',
                          key: 'pct',
                          render: (v: number) => `${v}%`,
                        },
                      ]}
                      rowKey="name"
                      size="small"
                      pagination={false}
                    />
                  </Card>
                )}

                {/* AI洞察 */}
                {cancellationData.insights.length > 0 && (
                  <Card size="small" title="AI洞察">
                    {cancellationData.insights.map((insight, i) => (
                      <Alert
                        key={i}
                        message={insight}
                        type={insight.includes('⚠️') ? 'warning' : 'info'}
                        showIcon
                        style={{ marginBottom: 8 }}
                      />
                    ))}
                  </Card>
                )}

                {/* 改进建议 */}
                {cancellationData.suggestions.length > 0 && (
                  <Card size="small" title="AI改进建议">
                    <Collapse ghost items={cancellationData.suggestions.map((s, i) => ({
                      key: String(i),
                      label: <Space><Tag color="blue">{s.category}</Tag><Text>{s.action}</Text></Space>,
                      children: <Text type="secondary">预期效果：{s.expected_impact}</Text>,
                    }))} />
                  </Card>
                )}
              </Space>
            ) : <Empty description="暂无退订分析" />,
          },
        ]} />
      </Spin>
    </div>
  );
}
