import React, { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Button,
  Select,
  DatePicker,
  Input,
  Space,
  Tag,
  Statistic,
  Row,
  Col,
  Tabs,
} from 'antd';
import {
  FileTextOutlined,
  SearchOutlined,
  ReloadOutlined,
  DeleteOutlined,
  UserOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { showSuccess, handleApiError } from '../utils/message';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;
const { Option } = Select;
const { TabPane } = Tabs;

const AuditLogPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [systemStats, setSystemStats] = useState<any>(null);
  const [actions, setActions] = useState<string[]>([]);
  const [resourceTypes, setResourceTypes] = useState<string[]>([]);

  // 过滤条件
  const [filters, setFilters] = useState({
    action: undefined,
    resource_type: undefined,
    status: undefined,
    search: '',
    start_date: dayjs().subtract(7, 'days'),
    end_date: dayjs(),
    skip: 0,
    limit: 50,
  });

  useEffect(() => {
    loadLogs();
    loadSystemStats();
    loadActions();
    loadResourceTypes();
  }, []);

  const loadLogs = async () => {
    try {
      setLoading(true);
      const params: any = {
        skip: filters.skip,
        limit: filters.limit,
      };

      if (filters.action) params.action = filters.action;
      if (filters.resource_type) params.resource_type = filters.resource_type;
      if (filters.status) params.status = filters.status;
      if (filters.search) params.search = filters.search;
      if (filters.start_date) params.start_date = filters.start_date.format('YYYY-MM-DD');
      if (filters.end_date) params.end_date = filters.end_date.format('YYYY-MM-DD');

      const response = await apiClient.get('/audit/logs', { params });
      setLogs(response.data.logs || []);
      setTotal(response.data.total || 0);
    } catch (err: any) {
      handleApiError(err, '加载审计日志失败');
    } finally {
      setLoading(false);
    }
  };

  const loadSystemStats = async () => {
    try {
      const response = await apiClient.get('/audit/logs/system/stats', {
        params: { days: 7 },
      });
      setSystemStats(response.data);
    } catch (err: any) {
      handleApiError(err, '加载系统统计失败');
    }
  };

  const loadActions = async () => {
    try {
      const response = await apiClient.get('/audit/logs/actions');
      setActions(response.data.actions || []);
    } catch (err: any) {
      handleApiError(err, '加载操作类型失败');
    }
  };

  const loadResourceTypes = async () => {
    try {
      const response = await apiClient.get('/audit/logs/resource-types');
      setResourceTypes(response.data.resource_types || []);
    } catch (err: any) {
      handleApiError(err, '加载资源类型失败');
    }
  };

  const handleCleanup = async () => {
    try {
      const response = await apiClient.delete('/audit/logs/cleanup', {
        params: { days: 90 },
      });
      showSuccess(`已删除 ${response.data.deleted_count} 条旧日志`);
      loadLogs();
    } catch (err: any) {
      handleApiError(err, '清理日志失败');
    }
  };

  const handleFilterChange = (key: string, value: any) => {
    setFilters({ ...filters, [key]: value, skip: 0 });
  };

  const handleSearch = () => {
    loadLogs();
  };

  const handleReset = () => {
    setFilters({
      action: undefined,
      resource_type: undefined,
      status: undefined,
      search: '',
      start_date: dayjs().subtract(7, 'days'),
      end_date: dayjs(),
      skip: 0,
      limit: 50,
    });
    setTimeout(() => loadLogs(), 100);
  };

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: '用户',
      dataIndex: 'username',
      key: 'username',
      width: 120,
      render: (username: string, record: any) => (
        <div>
          <div>{username || record.user_id}</div>
          {record.user_role && (
            <Tag color="blue">
              {record.user_role}
            </Tag>
          )}
        </div>
      ),
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      width: 150,
      render: (action: string) => <Tag color="purple">{action}</Tag>,
    },
    {
      title: '资源类型',
      dataIndex: 'resource_type',
      key: 'resource_type',
      width: 120,
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: 'IP地址',
      dataIndex: 'ip_address',
      key: 'ip_address',
      width: 140,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Tag color={status === 'success' ? 'green' : 'red'}>
          {status === 'success' ? '成功' : '失败'}
        </Tag>
      ),
    },
  ];

  // 操作类型统计图表
  const actionChartOption = systemStats ? {
    title: {
      text: '操作类型分布',
      left: 'center',
    },
    tooltip: {
      trigger: 'item',
    },
    series: [
      {
        type: 'pie',
        radius: '50%',
        data: systemStats.top_actions.map((item: any) => ({
          name: item.action,
          value: item.count,
        })),
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
  } : null;

  // 资源类型统计图表
  const resourceChartOption = systemStats ? {
    title: {
      text: '资源类型分布',
      left: 'center',
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
    },
    xAxis: {
      type: 'category',
      data: systemStats.resource_stats.map((item: any) => item.resource_type),
      axisLabel: {
        rotate: 45,
      },
    },
    yAxis: {
      type: 'value',
    },
    series: [
      {
        type: 'bar',
        data: systemStats.resource_stats.map((item: any) => item.count),
        itemStyle: {
          color: '#1890ff',
        },
      },
    ],
  } : null;

  return (
    <div>
      <h1 style={{ marginBottom: '24px' }}>
        <FileTextOutlined /> 审计日志
      </h1>

      {/* 统计卡片 */}
      {systemStats && (
        <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="总操作数"
                value={systemStats.total_actions}
                prefix={<ClockCircleOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="活跃用户"
                value={systemStats.active_users}
                prefix={<UserOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="失败操作"
                value={systemStats.failed_actions}
                valueStyle={{ color: '#cf1322' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="成功率"
                value={systemStats.success_rate}
                precision={2}
                suffix="%"
                valueStyle={{ color: '#3f8600' }}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Card>
        <Tabs defaultActiveKey="logs">
          <TabPane tab="日志列表" key="logs">
            {/* 过滤条件 */}
            <Space style={{ marginBottom: '16px' }} wrap>
              <RangePicker
                value={filters.start_date && filters.end_date ? [filters.start_date, filters.end_date] : null}
                onChange={(dates) => {
                  if (dates) {
                    setFilters({
                      ...filters,
                      start_date: dates[0] || dayjs().subtract(7, 'days'),
                      end_date: dates[1] || dayjs(),
                    });
                  } else {
                    setFilters({
                      ...filters,
                      start_date: dayjs().subtract(7, 'days'),
                      end_date: dayjs(),
                    });
                  }
                }}
              />
              <Select
                placeholder="操作类型"
                style={{ width: 150 }}
                value={filters.action}
                onChange={(value) => handleFilterChange('action', value)}
                allowClear
              >
                {actions.map((action) => (
                  <Option key={action} value={action}>
                    {action}
                  </Option>
                ))}
              </Select>
              <Select
                placeholder="资源类型"
                style={{ width: 150 }}
                value={filters.resource_type}
                onChange={(value) => handleFilterChange('resource_type', value)}
                allowClear
              >
                {resourceTypes.map((type) => (
                  <Option key={type} value={type}>
                    {type}
                  </Option>
                ))}
              </Select>
              <Select
                placeholder="状态"
                style={{ width: 120 }}
                value={filters.status}
                onChange={(value) => handleFilterChange('status', value)}
                allowClear
              >
                <Option value="success">成功</Option>
                <Option value="failed">失败</Option>
              </Select>
              <Input
                placeholder="搜索关键词"
                style={{ width: 200 }}
                value={filters.search}
                onChange={(e) => handleFilterChange('search', e.target.value)}
                onPressEnter={handleSearch}
              />
              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={handleSearch}
              >
                搜索
              </Button>
              <Button icon={<ReloadOutlined />} onClick={handleReset}>
                重置
              </Button>
              <Button
                danger
                icon={<DeleteOutlined />}
                onClick={handleCleanup}
              >
                清理旧日志
              </Button>
            </Space>

            {/* 日志表格 */}
            <Table
              columns={columns}
              dataSource={logs}
              rowKey="id"
              loading={loading}
              pagination={{
                current: Math.floor(filters.skip / filters.limit) + 1,
                pageSize: filters.limit,
                total: total,
                onChange: (page, pageSize) => {
                  setFilters({
                    ...filters,
                    skip: (page - 1) * pageSize,
                    limit: pageSize,
                  });
                  setTimeout(() => loadLogs(), 100);
                },
              }}
            />
          </TabPane>

          <TabPane tab="统计分析" key="stats">
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                {actionChartOption && (
                  <ReactECharts option={actionChartOption} style={{ height: '400px' }} />
                )}
              </Col>
              <Col xs={24} md={12}>
                {resourceChartOption && (
                  <ReactECharts option={resourceChartOption} style={{ height: '400px' }} />
                )}
              </Col>
            </Row>
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default AuditLogPage;
