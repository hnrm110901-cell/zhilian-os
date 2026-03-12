import React, { useState, useEffect } from 'react';
import { Tabs, Card, Statistic, Row, Col, Table, Tag, Button, Space, Empty, Spin } from 'antd';
import { BankOutlined, TeamOutlined, FileTextOutlined, SyncOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';

/* ────────────────────── types ────────────────────── */

interface DashboardData {
  bank_treasury: {
    total_accounts: number;
    unmatched_transactions: number;
    last_sync: string | null;
  };
  consolidation: {
    total_entities: number;
    last_run_period: string | null;
    last_run_status: string | null;
  };
  tax_declaration: {
    pending_declarations: number;
    next_deadline: string | null;
  };
}

/* ────────────────────── component ────────────────────── */

const FctAdvancedPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.get<DashboardData>('/api/v1/fct-advanced/dashboard')
      .then((d) => setDashboard(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '120px auto' }} />;

  const items = [
    {
      key: 'dashboard',
      label: '驾驶舱',
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8}>
            <Card title={<><BankOutlined /> 银企直连</>} size="small">
              <Statistic title="绑定账户" value={dashboard?.bank_treasury.total_accounts ?? 0} />
              <Statistic
                title="待匹配流水"
                value={dashboard?.bank_treasury.unmatched_transactions ?? 0}
                valueStyle={
                  (dashboard?.bank_treasury.unmatched_transactions ?? 0) > 0
                    ? { color: '#cf1322' }
                    : undefined
                }
              />
              <div style={{ marginTop: 8, color: 'rgba(0,0,0,0.45)', fontSize: 12 }}>
                最近同步：{dashboard?.bank_treasury.last_sync ?? '暂无'}
              </div>
            </Card>
          </Col>

          <Col xs={24} md={8}>
            <Card title={<><TeamOutlined /> 多实体合并</>} size="small">
              <Statistic title="合并实体数" value={dashboard?.consolidation.total_entities ?? 0} />
              <div style={{ marginTop: 8 }}>
                <span style={{ color: 'rgba(0,0,0,0.45)', fontSize: 12 }}>
                  上次合并：{dashboard?.consolidation.last_run_period ?? '暂无'}
                </span>
                {dashboard?.consolidation.last_run_status && (
                  <Tag
                    color={dashboard.consolidation.last_run_status === 'completed' ? 'green' : 'orange'}
                    style={{ marginLeft: 8 }}
                  >
                    {dashboard.consolidation.last_run_status}
                  </Tag>
                )}
              </div>
            </Card>
          </Col>

          <Col xs={24} md={8}>
            <Card title={<><FileTextOutlined /> 税务申报</>} size="small">
              <Statistic
                title="待提交申报"
                value={dashboard?.tax_declaration.pending_declarations ?? 0}
                valueStyle={
                  (dashboard?.tax_declaration.pending_declarations ?? 0) > 0
                    ? { color: '#faad14' }
                    : undefined
                }
              />
              <div style={{ marginTop: 8, color: 'rgba(0,0,0,0.45)', fontSize: 12 }}>
                下一截止日：{dashboard?.tax_declaration.next_deadline ?? '暂无'}
              </div>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'bank',
      label: '银企直连',
      children: (
        <Card>
          <Empty description="银行账户管理（开发中）">
            <p style={{ color: 'rgba(0,0,0,0.45)' }}>
              支持绑定银行账户、自动拉取流水、智能匹配凭证
            </p>
            <Space>
              <Button type="primary" icon={<BankOutlined />}>绑定银行账户</Button>
              <Button icon={<SyncOutlined />}>导入CSV流水</Button>
            </Space>
          </Empty>
        </Card>
      ),
    },
    {
      key: 'consolidation',
      label: '多实体合并',
      children: (
        <Card>
          <Empty description="财务合并报表（开发中）">
            <p style={{ color: 'rgba(0,0,0,0.45)' }}>
              总部汇总所有门店/子公司财务数据，自动抵消内部交易
            </p>
            <Button type="primary" icon={<TeamOutlined />}>执行合并</Button>
          </Empty>
        </Card>
      ),
    },
    {
      key: 'tax',
      label: '税务申报',
      children: (
        <Card>
          <Empty description="税务申报自动提取（开发中）">
            <p style={{ color: 'rgba(0,0,0,0.45)' }}>
              从凭证和发票数据自动提取增值税、企业所得税、附加税申报字段
            </p>
            <Space>
              <Button type="primary" icon={<FileTextOutlined />}>生成本月申报</Button>
              <Button>查看提取规则</Button>
            </Space>
          </Empty>
        </Card>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <h2 style={{ marginBottom: 16 }}>FCT 高级功能</h2>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={items}
      />
    </div>
  );
};

export default FctAdvancedPage;
