import React, { useState, useEffect } from 'react';
import { Card, Table, Tabs, Statistic, Row, Col, Progress, Tag, Space, Select, DatePicker } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ArrowUpOutlined, ArrowDownOutlined, TrophyOutlined, WarningOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';

const { TabPane } = Tabs;
const { Option } = Select;
const { RangePicker } = DatePicker;

interface BusinessMetric {
  id: string;
  name: string;
  value: number;
  target: number;
  trend: 'up' | 'down' | 'stable';
  changeRate: number;
  status: 'excellent' | 'good' | 'warning' | 'danger';
}

interface DecisionRecommendation {
  id: string;
  category: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  impact: string;
  actionItems: string[];
  createdAt: string;
}

interface PerformanceData {
  department: string;
  revenue: number;
  growth: number;
  efficiency: number;
  satisfaction: number;
}

const DecisionPage: React.FC = () => {
  const [metrics, setMetrics] = useState<BusinessMetric[]>([]);
  const [recommendations, setRecommendations] = useState<DecisionRecommendation[]>([]);
  const [performanceData, setPerformanceData] = useState<PerformanceData[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<string>('month');

  useEffect(() => {
    loadMockData();
    initCharts();
  }, []);

  const loadMockData = () => {
    const mockMetrics: BusinessMetric[] = [
      {
        id: '1',
        name: '月度营收',
        value: 1250000,
        target: 1200000,
        trend: 'up',
        changeRate: 15.5,
        status: 'excellent'
      },
      {
        id: '2',
        name: '客户满意度',
        value: 92,
        target: 90,
        trend: 'up',
        changeRate: 3.2,
        status: 'excellent'
      },
      {
        id: '3',
        name: '订单转化率',
        value: 68,
        target: 75,
        trend: 'down',
        changeRate: -2.5,
        status: 'warning'
      },
      {
        id: '4',
        name: '员工效率',
        value: 85,
        target: 80,
        trend: 'up',
        changeRate: 5.8,
        status: 'good'
      },
      {
        id: '5',
        name: '库存周转率',
        value: 72,
        target: 85,
        trend: 'down',
        changeRate: -8.3,
        status: 'danger'
      },
      {
        id: '6',
        name: '客户留存率',
        value: 88,
        target: 85,
        trend: 'stable',
        changeRate: 0.5,
        status: 'good'
      }
    ];

    const mockRecommendations: DecisionRecommendation[] = [
      {
        id: '1',
        category: '销售优化',
        title: '提升订单转化率策略',
        description: '当前订单转化率68%低于目标75%，建议优化销售流程和话术',
        priority: 'high',
        impact: '预计可提升转化率5-8个百分点，增加月度营收约15万',
        actionItems: [
          '优化销售话术模板，增加成功案例分享',
          '加强销售团队培训，重点提升异议处理能力',
          '实施客户跟进自动化，减少客户流失'
        ],
        createdAt: '2024-03-15'
      },
      {
        id: '2',
        category: '库存管理',
        title: '库存周转率改善方案',
        description: '库存周转率72%远低于目标85%，存在积压风险',
        priority: 'high',
        impact: '优化库存可释放资金约50万，降低仓储成本20%',
        actionItems: [
          '对滞销产品实施促销清仓',
          '优化采购计划，采用JIT模式',
          '建立动态库存预警机制'
        ],
        createdAt: '2024-03-14'
      },
      {
        id: '3',
        category: '客户体验',
        title: '客户满意度持续提升计划',
        description: '客户满意度92%表现优秀，建议继续保持并提升',
        priority: 'medium',
        impact: '维持高满意度可提升客户留存率3-5个百分点',
        actionItems: [
          '建立客户反馈快速响应机制',
          '定期开展客户满意度调研',
          '优化售后服务流程'
        ],
        createdAt: '2024-03-13'
      },
      {
        id: '4',
        category: '团队建设',
        title: '员工效率提升方案',
        description: '员工效率85%超过目标，建议进一步优化工作流程',
        priority: 'low',
        impact: '效率提升5%可节省人力成本约10万/月',
        actionItems: [
          '引入自动化工具减少重复劳动',
          '优化工作流程，消除冗余环节',
          '建立绩效激励机制'
        ],
        createdAt: '2024-03-12'
      }
    ];

    const mockPerformanceData: PerformanceData[] = [
      {
        department: '销售部',
        revenue: 580000,
        growth: 18.5,
        efficiency: 88,
        satisfaction: 91
      },
      {
        department: '客服部',
        revenue: 0,
        growth: 0,
        efficiency: 92,
        satisfaction: 95
      },
      {
        department: '运营部',
        revenue: 420000,
        growth: 12.3,
        efficiency: 85,
        satisfaction: 88
      },
      {
        department: '技术部',
        revenue: 250000,
        growth: 25.6,
        efficiency: 90,
        satisfaction: 87
      }
    ];

    setMetrics(mockMetrics);
    setRecommendations(mockRecommendations);
    setPerformanceData(mockPerformanceData);
  };

  const initCharts = () => {
    setTimeout(() => {
      const trendChart = echarts.init(document.getElementById('trendChart'));
      const radarChart = echarts.init(document.getElementById('radarChart'));

      const trendOption = {
        title: { text: '关键指标趋势分析', left: 'center' },
        tooltip: { trigger: 'axis' },
        legend: { data: ['营收', '满意度', '转化率'], bottom: 0 },
        xAxis: {
          type: 'category',
          data: ['1月', '2月', '3月', '4月', '5月', '6月']
        },
        yAxis: { type: 'value' },
        series: [
          {
            name: '营收',
            type: 'line',
            data: [980000, 1050000, 1120000, 1180000, 1220000, 1250000],
            smooth: true
          },
          {
            name: '满意度',
            type: 'line',
            data: [85, 87, 88, 90, 91, 92],
            smooth: true
          },
          {
            name: '转化率',
            type: 'line',
            data: [72, 73, 71, 70, 69, 68],
            smooth: true
          }
        ]
      };

      const radarOption = {
        title: { text: '部门综合能力评估', left: 'center' },
        tooltip: {},
        legend: { data: ['销售部', '客服部', '运营部', '技术部'], bottom: 0 },
        radar: {
          indicator: [
            { name: '营收贡献', max: 100 },
            { name: '增长率', max: 100 },
            { name: '工作效率', max: 100 },
            { name: '客户满意度', max: 100 }
          ]
        },
        series: [{
          type: 'radar',
          data: [
            { value: [95, 75, 88, 91], name: '销售部' },
            { value: [0, 0, 92, 95], name: '客服部' },
            { value: [70, 50, 85, 88], name: '运营部' },
            { value: [40, 100, 90, 87], name: '技术部' }
          ]
        }]
      };

      trendChart.setOption(trendOption);
      radarChart.setOption(radarOption);
    }, 100);
  };

  const metricColumns: ColumnsType<BusinessMetric> = [
    {
      title: '指标名称',
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: '当前值',
      dataIndex: 'value',
      key: 'value',
      render: (value: number, record) => {
        if (record.name.includes('营收')) {
          return `¥${(value / 10000).toFixed(1)}万`;
        }
        return `${value}%`;
      }
    },
    {
      title: '目标值',
      dataIndex: 'target',
      key: 'target',
      render: (value: number, record) => {
        if (record.name.includes('营收')) {
          return `¥${(value / 10000).toFixed(1)}万`;
        }
        return `${value}%`;
      }
    },
    {
      title: '完成度',
      key: 'completion',
      render: (_, record) => {
        const completion = Math.round((record.value / record.target) * 100);
        return (
          <Progress
            percent={completion}
            size="small"
            status={completion >= 100 ? 'success' : completion >= 80 ? 'active' : 'exception'}
          />
        );
      }
    },
    {
      title: '趋势',
      dataIndex: 'trend',
      key: 'trend',
      render: (trend: string, record) => {
        const trendMap = {
          up: { icon: <ArrowUpOutlined />, color: 'green', text: `+${record.changeRate}%` },
          down: { icon: <ArrowDownOutlined />, color: 'red', text: `${record.changeRate}%` },
          stable: { icon: null, color: 'blue', text: `${record.changeRate}%` }
        };
        const config = trendMap[trend as keyof typeof trendMap];
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        );
      }
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap = {
          excellent: { text: '优秀', color: 'green', icon: <TrophyOutlined /> },
          good: { text: '良好', color: 'blue', icon: null },
          warning: { text: '预警', color: 'orange', icon: <WarningOutlined /> },
          danger: { text: '危险', color: 'red', icon: <WarningOutlined /> }
        };
        const config = statusMap[status as keyof typeof statusMap];
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        );
      }
    }
  ];

  const recommendationColumns: ColumnsType<DecisionRecommendation> = [
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      render: (category: string) => <Tag color="blue">{category}</Tag>
    },
    {
      title: '建议标题',
      dataIndex: 'title',
      key: 'title'
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (priority: string) => {
        const priorityMap = {
          high: { text: '高', color: 'red' },
          medium: { text: '中', color: 'orange' },
          low: { text: '低', color: 'green' }
        };
        return <Tag color={priorityMap[priority as keyof typeof priorityMap].color}>
          {priorityMap[priority as keyof typeof priorityMap].text}
        </Tag>;
      }
    },
    {
      title: '预期影响',
      dataIndex: 'impact',
      key: 'impact'
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt'
    }
  ];

  const performanceColumns: ColumnsType<PerformanceData> = [
    {
      title: '部门',
      dataIndex: 'department',
      key: 'department'
    },
    {
      title: '营收贡献',
      dataIndex: 'revenue',
      key: 'revenue',
      render: (revenue: number) => revenue > 0 ? `¥${(revenue / 10000).toFixed(1)}万` : '-'
    },
    {
      title: '增长率',
      dataIndex: 'growth',
      key: 'growth',
      render: (growth: number) => growth > 0 ? (
        <Tag color="green" icon={<ArrowUpOutlined />}>
          +{growth}%
        </Tag>
      ) : '-'
    },
    {
      title: '工作效率',
      dataIndex: 'efficiency',
      key: 'efficiency',
      render: (efficiency: number) => (
        <Progress
          percent={efficiency}
          size="small"
          status={efficiency >= 90 ? 'success' : 'active'}
        />
      )
    },
    {
      title: '客户满意度',
      dataIndex: 'satisfaction',
      key: 'satisfaction',
      render: (satisfaction: number) => (
        <Progress
          percent={satisfaction}
          size="small"
          status={satisfaction >= 90 ? 'success' : 'active'}
        />
      )
    }
  ];

  const excellentMetrics = metrics.filter(m => m.status === 'excellent').length;
  const warningMetrics = metrics.filter(m => m.status === 'warning' || m.status === 'danger').length;
  const highPriorityRecommendations = recommendations.filter(r => r.priority === 'high').length;
  const avgGrowth = performanceData.length > 0
    ? Math.round(performanceData.reduce((sum, p) => sum + p.growth, 0) / performanceData.filter(p => p.growth > 0).length * 10) / 10
    : 0;

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>决策支持Agent</h1>

      <Space style={{ marginBottom: 16 }}>
        <Select
          value={selectedPeriod}
          onChange={setSelectedPeriod}
          style={{ width: 120 }}
        >
          <Option value="week">本周</Option>
          <Option value="month">本月</Option>
          <Option value="quarter">本季度</Option>
          <Option value="year">本年</Option>
        </Select>
        <RangePicker />
      </Space>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="优秀指标数"
              value={excellentMetrics}
              suffix={`/ ${metrics.length}`}
              valueStyle={{ color: '#3f8600' }}
              prefix={<TrophyOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="预警指标数"
              value={warningMetrics}
              suffix={`/ ${metrics.length}`}
              valueStyle={{ color: '#cf1322' }}
              prefix={<WarningOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="高优先级建议"
              value={highPriorityRecommendations}
              suffix="条"
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均增长率"
              value={avgGrowth}
              suffix="%"
              valueStyle={{ color: '#3f8600' }}
              prefix={<ArrowUpOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card>
            <div id="trendChart" style={{ width: '100%', height: 300 }}></div>
          </Card>
        </Col>
        <Col span={12}>
          <Card>
            <div id="radarChart" style={{ width: '100%', height: 300 }}></div>
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs defaultActiveKey="1">
          <TabPane tab="关键指标" key="1">
            <Table
              columns={metricColumns}
              dataSource={metrics}
              rowKey="id"
              pagination={false}
            />
          </TabPane>

          <TabPane tab="决策建议" key="2">
            <Table
              columns={recommendationColumns}
              dataSource={recommendations}
              rowKey="id"
              pagination={false}
              expandable={{
                expandedRowRender: (record) => (
                  <div style={{ padding: '16px', background: '#fafafa' }}>
                    <p><strong>详细描述：</strong>{record.description}</p>
                    <p><strong>行动建议：</strong></p>
                    <ul>
                      {record.actionItems.map((item, index) => (
                        <li key={index}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )
              }}
            />
          </TabPane>

          <TabPane tab="部门绩效" key="3">
            <Table
              columns={performanceColumns}
              dataSource={performanceData}
              rowKey="department"
              pagination={false}
            />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default DecisionPage;
