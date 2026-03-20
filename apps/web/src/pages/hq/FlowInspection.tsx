/**
 * 总部巡检看板 — 多店全天流程巡检
 * 路由: /hq/flow-inspection
 *
 * 功能：
 * 1. 多门店流程进度一览（风险排序）
 * 2. 风险等级统计（高/中/低）
 * 3. 单店流程详情钻取
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Table, Tag, Progress, Statistic, Row, Col, Button,
  Typography, Spin, message, DatePicker, Space, Badge, Modal, Timeline
} from 'antd';
import {
  ShopOutlined, WarningOutlined, CheckCircleOutlined,
  EyeOutlined, ClockCircleOutlined
} from '@ant-design/icons';
import apiClient from '../../services/apiClient';

const { Title, Text } = Typography;

interface StoreSummary {
  store_id: string;
  biz_date: string;
  flow_status: string;
  progress_pct: number;
  current_node_name: string | null;
  completed_nodes: number;
  total_nodes: number;
  overdue_count: number;
  overdue_nodes: string[];
  risk_level: string;
  incident_summary: Record<string, number>;
  settlement_status: string;
}

interface InspectionData {
  biz_date: string;
  total_stores: number;
  risk_high: number;
  risk_medium: number;
  risk_low: number;
  avg_progress_pct: number;
  stores: StoreSummary[];
}

const RISK_COLORS: Record<string, string> = {
  high: 'red', medium: 'orange', low: 'green',
};
const RISK_LABELS: Record<string, string> = {
  high: '高风险', medium: '中风险', low: '正常',
};

const FlowInspection: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<InspectionData | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const today = new Date().toISOString().slice(0, 10);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/daily-flow/hq/inspection?biz_date=${today}`);
      setData(resp.data);
    } catch {
      message.error('加载失败');
    } finally {
      setLoading(false);
    }
  };

  const showDetail = async (storeId: string) => {
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/daily-flow/hq/store/${storeId}/detail?biz_date=${today}`);
      setDetailData(resp.data);
    } catch {
      message.error('加载详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const columns = [
    {
      title: '风险', dataIndex: 'risk_level', width: 80,
      render: (r: string) => <Tag color={RISK_COLORS[r]}>{RISK_LABELS[r]}</Tag>,
      sorter: (a: StoreSummary, b: StoreSummary) => {
        const ord: Record<string, number> = { high: 3, medium: 2, low: 1 };
        return (ord[b.risk_level] || 0) - (ord[a.risk_level] || 0);
      },
      defaultSortOrder: 'ascend' as const,
    },
    { title: '门店', dataIndex: 'store_id', width: 140 },
    {
      title: '进度', dataIndex: 'progress_pct', width: 140,
      render: (v: number) => <Progress percent={v} size="small" status={v >= 100 ? 'success' : 'active'} />,
      sorter: (a: StoreSummary, b: StoreSummary) => a.progress_pct - b.progress_pct,
    },
    {
      title: '当前节点', dataIndex: 'current_node_name', width: 120,
      render: (v: string | null) => v || <Text type="secondary">--</Text>,
    },
    {
      title: '完成', dataIndex: 'completed_nodes', width: 80,
      render: (_: number, r: StoreSummary) => `${r.completed_nodes}/${r.total_nodes}`,
    },
    {
      title: '超时', dataIndex: 'overdue_count', width: 70,
      render: (v: number) => v > 0 ? <Badge count={v} style={{ backgroundColor: '#ff4d4f' }} /> : <CheckCircleOutlined style={{ color: '#52c41a' }} />,
    },
    {
      title: '异常', width: 100,
      render: (_: any, r: StoreSummary) => {
        const total = Object.values(r.incident_summary || {}).reduce((a, b) => a + b, 0);
        return total > 0 ? <Tag color="red">{total}条</Tag> : <Tag color="green">无</Tag>;
      },
    },
    {
      title: '操作', width: 80,
      render: (_: any, r: StoreSummary) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => showDetail(r.store_id)}>详情</Button>
      ),
    },
  ];

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div style={{ padding: 24 }}>
      <Title level={4}><ShopOutlined /> 全天流程巡检</Title>

      {/* KPI 概览 */}
      {data && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card size="small"><Statistic title="门店总数" value={data.total_stores} prefix={<ShopOutlined />} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="平均进度" value={`${data.avg_progress_pct}%`} valueStyle={{ color: data.avg_progress_pct >= 60 ? '#3f8600' : '#cf1322' }} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="高风险" value={data.risk_high} valueStyle={{ color: '#cf1322' }} prefix={<WarningOutlined />} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="中风险" value={data.risk_medium} valueStyle={{ color: '#d48806' }} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="正常" value={data.risk_low} valueStyle={{ color: '#3f8600' }} prefix={<CheckCircleOutlined />} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="日期" value={data.biz_date} /></Card>
          </Col>
        </Row>
      )}

      {/* 门店列表 */}
      <Card title="门店流程状态" size="small">
        <Table
          dataSource={data?.stores || []}
          columns={columns}
          rowKey="store_id"
          size="small"
          pagination={false}
        />
      </Card>

      {/* 门店详情弹窗 */}
      <Modal
        title={`门店详情 — ${detailData?.store_id || ''}`}
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        width={700}
        footer={null}
      >
        {detailLoading ? <Spin /> : detailData && (
          <>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <Statistic title="进度" value={`${detailData.progress?.progress_pct || 0}%`} />
              </Col>
              <Col span={8}>
                <Statistic title="完成节点" value={`${detailData.progress?.completed_nodes || 0}/${detailData.progress?.total_nodes || 0}`} />
              </Col>
              <Col span={8}>
                <Statistic title="超时" value={detailData.progress?.overdue_nodes?.length || 0} valueStyle={{ color: '#cf1322' }} />
              </Col>
            </Row>
            <Timeline>
              {(detailData.nodes || []).map((n: any) => (
                <Timeline.Item
                  key={n.id}
                  color={n.status === 'completed' ? 'green' : n.status === 'in_progress' ? 'blue' : n.status === 'overdue' ? 'red' : 'gray'}
                >
                  <Space>
                    <strong>{n.node_name}</strong>
                    <Tag>{n.status}</Tag>
                    <Text type="secondary">{n.completed_tasks}/{n.total_tasks} 任务</Text>
                  </Space>
                </Timeline.Item>
              ))}
            </Timeline>
            {detailData.incidents?.length > 0 && (
              <>
                <Title level={5} style={{ marginTop: 16 }}>异常事件</Title>
                {detailData.incidents.map((inc: any) => (
                  <Card key={inc.id} size="small" style={{ marginBottom: 8 }}>
                    <Tag color={inc.severity === 'critical' ? 'red' : inc.severity === 'high' ? 'orange' : 'blue'}>{inc.severity}</Tag>
                    {inc.title} — <Tag>{inc.status}</Tag>
                  </Card>
                ))}
              </>
            )}
          </>
        )}
      </Modal>
    </div>
  );
};

export default FlowInspection;
