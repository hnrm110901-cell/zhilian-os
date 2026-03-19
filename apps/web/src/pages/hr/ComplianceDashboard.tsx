/**
 * 合规看板 — 健康证/合同/身份证到期预警
 */
import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Table, Tag, Statistic, Button, message, Typography, Spin } from 'antd';
import { SafetyCertificateOutlined, AlertOutlined, BellOutlined } from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { ComplianceDashboardData } from '../../services/hrService';
import { useAuthStore } from '../../stores/authStore';

const { Title } = Typography;

const levelColor = (level: string) => {
  switch (level) {
    case 'expired': return 'red';
    case 'critical': return 'orange';
    case 'warning': return 'gold';
    default: return 'blue';
  }
};

const levelText = (level: string) => {
  switch (level) {
    case 'expired': return '已过期';
    case 'critical': return '紧急';
    case 'warning': return '预警';
    default: return '提醒';
  }
};

const ComplianceDashboard: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ComplianceDashboardData | null>(null);
  const [sending, setSending] = useState(false);
  const user = useAuthStore((s) => s.user);
  const storeId = user?.store_id || '';

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const res = await hrService.getComplianceDashboard(storeId);
      setData(res);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  const handleSendAlerts = async () => {
    setSending(true);
    try {
      const res = await hrService.sendComplianceAlerts(storeId);
      if (res.sent) {
        message.success('告警已推送到店长IM');
      } else {
        message.info('当前无需推送告警');
      }
    } catch {
      message.error('推送失败');
    } finally {
      setSending(false);
    }
  };

  const columns = [
    { title: '员工', dataIndex: 'employee_name', key: 'name' },
    { title: '岗位', dataIndex: 'position', key: 'position' },
    {
      title: '剩余天数', dataIndex: 'days_remaining', key: 'days',
      render: (d: number) => <span style={{ color: d <= 0 ? 'red' : d <= 7 ? 'orange' : 'inherit' }}>{d}天</span>,
    },
    {
      title: '级别', dataIndex: 'level', key: 'level',
      render: (l: string) => <Tag color={levelColor(l)}>{levelText(l)}</Tag>,
    },
  ];

  if (loading) return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  if (!data) return null;

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3}><SafetyCertificateOutlined /> 合规看板</Title>
        <Button icon={<BellOutlined />} onClick={handleSendAlerts} loading={sending}>
          推送告警到IM
        </Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="健康证已过期"
              value={data.health_cert.expired}
              valueStyle={{ color: data.health_cert.expired > 0 ? '#ff4d4f' : '#52c41a' }}
              suffix="人"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="健康证即将到期" value={data.health_cert.critical + data.health_cert.warning} suffix="人" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="合同即将到期" value={data.contract.total} suffix="份" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="身份证即将到期" value={data.id_card.total} suffix="人" />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={8}>
          <Card title={<><AlertOutlined /> 健康证告警</>} size="small">
            <Table dataSource={data.health_cert.items.map((i, idx) => ({ ...i, key: idx }))} columns={columns} pagination={false} size="small" />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="合同到期" size="small">
            <Table dataSource={data.contract.items.map((i, idx) => ({ ...i, key: idx }))} columns={columns} pagination={false} size="small" />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="身份证到期" size="small">
            <Table dataSource={data.id_card.items.map((i, idx) => ({ ...i, key: idx }))} columns={columns} pagination={false} size="small" />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default ComplianceDashboard;
