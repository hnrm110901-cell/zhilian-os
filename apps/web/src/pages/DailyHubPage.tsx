import React, { useState, useCallback, useEffect } from 'react';
import {
  Row, Col, Card, Select, Button, Alert, Tag, Table, Statistic,
  Space, Spin, Typography, Divider,
} from 'antd';
import { CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { Text } = Typography;

const DailyHubPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [stores, setStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [board, setBoard] = useState<any>(null);

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
      </Spin>
    </div>
  );
};

export default DailyHubPage;
