/**
 * 月度人事报表 — 7张报表Tab切换
 */
import React, { useEffect, useState } from 'react';
import { Card, Tabs, Tag, Statistic, Row, Col, Select, Typography, Spin, List, Alert } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { MonthlyReportData } from '../../services/hrService';

const { Title } = Typography;

const MonthlyReportPage: React.FC = () => {
  const [data, setData] = useState<MonthlyReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const storeId = 'S001';
  const brandId = 'default_brand';

  useEffect(() => { loadData(); }, [month]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await hrService.getMonthlyReport(storeId, month, brandId);
      setData(res);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  if (loading) return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  if (!data) return null;

  const sc = data.salary_changes;
  const hc = data.headcount_inventory;
  const ms = data.mentorship_summary;
  const hw = data.hourly_worker_attendance;
  const ei = data.exit_interview_summary;
  const hs = data.hr_summary;

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <Title level={3}><FileTextOutlined /> 月度人事报表</Title>
        <Select value={month} onChange={setMonth} style={{ width: 150 }}>
          {Array.from({ length: 12 }, (_, i) => {
            const d = new Date();
            d.setMonth(d.getMonth() - i);
            const v = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
            return <Select.Option key={v} value={v}>{v}</Select.Option>;
          })}
        </Select>
      </div>

      <Tabs items={[
        {
          key: '1', label: '工资异动',
          children: (
            <Row gutter={16}>
              <Col span={8}><Card><Statistic title="本月新进" value={sc.new_count} suffix="人" valueStyle={{ color: '#52c41a' }} /></Card></Col>
              <Col span={8}><Card><Statistic title="本月离职" value={sc.resignation_count} suffix="人" valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
              <Col span={8}><Card><Statistic title="调薪" value={sc.adjustment_count} suffix="人" /></Card></Col>
            </Row>
          ),
        },
        {
          key: '2', label: '编制盘存',
          children: (
            <Card>
              <Statistic title="月末在编" value={hc.total_headcount} suffix="人" />
              <div style={{ marginTop: 16 }}>
                <Title level={5}>按岗位分布</Title>
                {Object.entries(hc.by_position).map(([pos, cnt]) => (
                  <Tag key={pos} style={{ margin: 4 }}>{pos}: {cnt}人</Tag>
                ))}
              </div>
              <div style={{ marginTop: 16 }}>
                <Title level={5}>按用工类型</Title>
                {Object.entries(hc.by_employment_type).map(([t, cnt]) => (
                  <Tag key={t} style={{ margin: 4 }}>{t}: {cnt}人</Tag>
                ))}
              </div>
            </Card>
          ),
        },
        {
          key: '3', label: '师徒培养',
          children: (
            <Card>
              <Row gutter={16}>
                <Col span={8}><Statistic title="进行中" value={ms.active_count} suffix="对" /></Col>
                <Col span={8}><Statistic title="本月完成" value={ms.completed_this_month} suffix="对" /></Col>
                <Col span={8}><Statistic title="本月奖励" value={ms.total_reward_yuan} prefix="¥" /></Col>
              </Row>
            </Card>
          ),
        },
        {
          key: '4', label: '灵活用工',
          children: (
            <Card>
              <Row gutter={16}>
                <Col span={8}><Statistic title="灵活用工人数" value={hw.total_workers} /></Col>
                <Col span={8}><Statistic title="总出勤天数" value={hw.total_days} suffix="天" /></Col>
                <Col span={8}><Statistic title="总发薪" value={hw.total_pay_yuan} prefix="¥" /></Col>
              </Row>
            </Card>
          ),
        },
        {
          key: '5', label: '离职回访',
          children: (
            <Card>
              <Row gutter={16}>
                <Col span={6}><Statistic title="本月离职" value={ei.total_exits} suffix="人" /></Col>
                <Col span={6}><Statistic title="已回访" value={ei.interviewed_count} suffix="人" /></Col>
                <Col span={6}><Statistic title="回访率" value={ei.interview_rate_pct} suffix="%" /></Col>
                <Col span={6}>
                  <div>原因分布：</div>
                  {Object.entries(ei.reason_distribution).map(([r, c]) => (
                    <Tag key={r}>{r}: {c}</Tag>
                  ))}
                </Col>
              </Row>
            </Card>
          ),
        },
        {
          key: '6', label: '工作总结',
          children: (
            <Card>
              <Title level={5}>本月亮点</Title>
              <List dataSource={hs.highlights} renderItem={item => <List.Item>{item}</List.Item>} />
              {hs.concerns.length > 0 && (
                <>
                  <Title level={5} style={{ marginTop: 16 }}>关注事项</Title>
                  {hs.concerns.map((c, i) => <Alert key={i} message={c} type="warning" style={{ marginBottom: 8 }} />)}
                </>
              )}
              <Title level={5} style={{ marginTop: 16 }}>下月计划</Title>
              <List dataSource={hs.next_month_plans} renderItem={item => <List.Item>{item}</List.Item>} />
              <div style={{ marginTop: 16 }}>
                <Statistic title="月度离职率" value={hs.turnover_rate_pct} suffix="%" />
              </div>
            </Card>
          ),
        },
      ]} />
    </div>
  );
};

export default MonthlyReportPage;
