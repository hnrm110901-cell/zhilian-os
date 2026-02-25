import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Statistic, Row, Col, Select, Tabs, Tag, Progress, Descriptions } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;

const BenchmarkPage: React.FC = () => {
  const [report, setReport] = useState<any>(null);
  const [dimensions, setDimensions] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [storeId, setStoreId] = useState('STORE001');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [reportRes, dimRes, sumRes] = await Promise.allSettled([
        apiClient.get(`/benchmark/report?store_id=${storeId}`),
        apiClient.get('/benchmark/dimensions'),
        apiClient.get(`/benchmark/summary?store_id=${storeId}`),
      ]);
      if (reportRes.status === 'fulfilled') setReport(reportRes.value.data);
      if (dimRes.status === 'fulfilled') setDimensions(dimRes.value.data?.dimensions || dimRes.value.data || []);
      if (sumRes.status === 'fulfilled') setSummary(sumRes.value.data);
    } catch (err: any) {
      handleApiError(err, '加载基准数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadData(); }, [loadData]);

  const rankColor = (rank: string) => {
    if (rank === 'top') return 'green';
    if (rank === 'above_avg') return 'blue';
    if (rank === 'below_avg') return 'orange';
    return 'red';
  };

  const rankLabel: Record<string, string> = { top: '优秀', above_avg: '良好', average: '平均', below_avg: '待改进', bottom: '落后' };

  const dimColumns: ColumnsType<any> = [
    { title: '维度', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'desc', ellipsis: true },
    { title: '单位', dataIndex: 'unit', key: 'unit', render: (v: string) => v || '-' },
    { title: '行业均值', dataIndex: 'industry_avg', key: 'avg', render: (v: number) => v != null ? v.toFixed(2) : '-' },
    { title: '行业最优', dataIndex: 'industry_top', key: 'top', render: (v: number) => v != null ? v.toFixed(2) : '-' },
  ];

  const metricsColumns: ColumnsType<any> = [
    { title: '指标', dataIndex: 'metric', key: 'metric' },
    { title: '当前值', dataIndex: 'current_value', key: 'current', render: (v: number) => v != null ? v.toFixed(2) : '-' },
    { title: '行业均值', dataIndex: 'industry_avg', key: 'avg', render: (v: number) => v != null ? v.toFixed(2) : '-' },
    {
      title: '排名', dataIndex: 'rank', key: 'rank',
      render: (v: string) => <Tag color={rankColor(v)}>{rankLabel[v] || v || '-'}</Tag>,
    },
    {
      title: '达标率', dataIndex: 'percentile', key: 'pct',
      render: (v: number) => v != null ? <Progress percent={Math.round(v)} size="small" /> : '-',
    },
  ];

  const tabItems = [
    {
      key: 'summary',
      label: '综合摘要',
      children: (
        <div>
          {summary && (
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={6}><Card loading={loading}><Statistic title="综合评分" value={summary.overall_score || 0} suffix="/ 100" /></Card></Col>
              <Col span={6}><Card loading={loading}><Statistic title="行业排名" value={summary.industry_rank || '-'} /></Card></Col>
              <Col span={6}><Card loading={loading}><Statistic title="超越门店比例" suffix="%" value={summary.percentile || 0} /></Card></Col>
              <Col span={6}><Card loading={loading}><Statistic title="改进空间" suffix="%" value={summary.improvement_potential || 0} /></Card></Col>
            </Row>
          )}
          {report?.metrics && (
            <Card title="各维度指标" loading={loading}>
              <Table columns={metricsColumns} dataSource={report.metrics} rowKey={(r, i) => r.metric || String(i)} />
            </Card>
          )}
        </div>
      ),
    },
    {
      key: 'dimensions',
      label: '基准维度',
      children: (
        <Card loading={loading}>
          <Table columns={dimColumns} dataSource={dimensions} rowKey={(r, i) => r.id || r.name || String(i)} />
        </Card>
      ),
    },
    {
      key: 'report',
      label: '详细报告',
      children: report ? (
        <Card loading={loading}>
          <Descriptions bordered column={2}>
            <Descriptions.Item label="报告日期">{report.report_date || '-'}</Descriptions.Item>
            <Descriptions.Item label="门店">{report.store_id || storeId}</Descriptions.Item>
            <Descriptions.Item label="综合评级">
              <Tag color={rankColor(report.overall_rank)}>{rankLabel[report.overall_rank] || report.overall_rank || '-'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="对标门店数">{report.benchmark_count || '-'}</Descriptions.Item>
            {report.recommendations && (
              <Descriptions.Item label="改进建议" span={2}>
                {Array.isArray(report.recommendations) ? report.recommendations.join('；') : report.recommendations}
              </Descriptions.Item>
            )}
          </Descriptions>
        </Card>
      ) : <Card loading={loading} />,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
          <Option value="STORE001">门店001</Option>
          <Option value="STORE002">门店002</Option>
        </Select>
      </div>
      <Tabs items={tabItems} />
    </div>
  );
};

export default BenchmarkPage;
