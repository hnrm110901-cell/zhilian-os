import React, { useState } from 'react';
import {
  Card, Form, Input, Button, DatePicker, Row, Col, Typography,
  Tag, Collapse, Table, Alert, Divider, Progress, Space, Badge,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ExperimentOutlined, FireOutlined, ThunderboltOutlined,
  CheckCircleOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text, Paragraph } = Typography;
const { Panel } = Collapse;

interface RootCause {
  dimension: string;
  reason: string;
  score: number;
  staff_id?: string;
  ing_id?: string;
}

interface ReasoningResult {
  tenant_id: string;
  store_id: string;
  date_start: string;
  date_end: string | null;
  step1_inventory_variance: any[];
  step2_bom_deviation: any[];
  step3_staff_in_window: any[];
  step4_supplier_batches: any[];
  top3_root_causes: RootCause[];
}

const DIMENSION_LABEL: Record<string, string> = {
  inventory_variance: '库存盘点偏差',
  bom_deviation: 'BOM 用料偏差',
  time_window_staff: '时间窗口员工关联',
  supplier_batch: '供应商批次异常',
  staff_error: '员工操作失误',
  process_deviation: '流程偏差',
  food_quality: '食材品质问题',
  equipment_fault: '设备故障',
  supply_chain: '供应链异常',
};

const RANK_COLOR = ['#f5222d', '#fa8c16', '#1890ff'];
const RANK_LABEL = ['P1 最高风险', 'P2 次要风险', 'P3 一般风险'];

const WasteReasoningPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ReasoningResult | null>(null);

  const handleSubmit = async (values: any) => {
    setLoading(true);
    setResult(null);
    try {
      const payload = {
        tenant_id: values.tenant_id || 'default',
        store_id: values.store_id,
        date_start: values.date_start.format('YYYY-MM-DD'),
        date_end: values.date_end ? values.date_end.format('YYYY-MM-DD') : undefined,
      };
      const res = await apiClient.post<ReasoningResult>('/api/v1/ontology/reasoning/waste', payload);
      setResult(res as any);
    } catch (err: any) {
      handleApiError(err, '推理失败');
    } finally {
      setLoading(false);
    }
  };

  const maxScore = result?.top3_root_causes?.reduce((m, r) => Math.max(m, r.score), 1) || 1;

  const colsGeneric: ColumnsType<any> = [
    { title: 'Key', dataIndex: 0, key: 'k', render: (_: any, row: any) => Object.keys(row)[0] },
  ];
  const renderJsonTable = (data: any[], title: string) => {
    if (!data || data.length === 0) return <Text type="secondary">无数据</Text>;
    const cols: ColumnsType<any> = Object.keys(data[0]).map(k => ({
      title: k,
      dataIndex: k,
      key: k,
      ellipsis: true,
      render: (v: any) => {
        if (v === null || v === undefined) return '—';
        if (typeof v === 'number') return v.toFixed ? v.toFixed(3) : v;
        if (typeof v === 'object') return JSON.stringify(v).slice(0, 60);
        return String(v);
      },
    }));
    return (
      <Table
        size="small"
        dataSource={data.map((r, i) => ({ ...r, _key: i }))}
        columns={cols}
        rowKey="_key"
        pagination={{ pageSize: 5, size: 'small' }}
        scroll={{ x: true }}
      />
    );
  };

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 0' }}>
      <Title level={3}>
        <ExperimentOutlined style={{ marginRight: 8 }} />
        损耗五步推理引擎
      </Title>
      <Paragraph type="secondary">
        输入门店和日期范围，系统将自动执行库存差异→BOM偏差→员工时间窗口→供应商批次→根因评分五步推理，
        输出 Top3 根因并自动派发培训推荐。
      </Paragraph>

      <Card title="推理参数" style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" onFinish={handleSubmit} initialValues={{ date_start: dayjs().subtract(7, 'day') }}>
          <Form.Item name="tenant_id" label="租户 ID">
            <Input placeholder="default" style={{ width: 140 }} allowClear />
          </Form.Item>
          <Form.Item name="store_id" label="门店 ID" rules={[{ required: true, message: '请输入门店 ID' }]}>
            <Input placeholder="如 STORE_001" style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="date_start" label="开始日期" rules={[{ required: true, message: '请选择日期' }]}>
            <DatePicker format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="date_end" label="结束日期">
            <DatePicker format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              icon={<ThunderboltOutlined />}
            >
              执行推理
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {result && (
        <>
          {/* Top3 根因 */}
          <Card
            title={
              <Space>
                <FireOutlined style={{ color: '#f5222d' }} />
                Top3 根因评分
                <Tag color="red">{result.top3_root_causes.length} 项</Tag>
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            {result.top3_root_causes.length === 0 ? (
              <Alert type="success" message="未发现显著损耗根因，门店运营状态良好。" showIcon />
            ) : (
              <Row gutter={16}>
                {result.top3_root_causes.map((cause, idx) => (
                  <Col span={8} key={idx}>
                    <Card
                      size="small"
                      style={{ borderColor: RANK_COLOR[idx], borderWidth: 2 }}
                      title={
                        <Space>
                          <Badge color={RANK_COLOR[idx]} text={RANK_LABEL[idx]} />
                        </Space>
                      }
                    >
                      <div style={{ marginBottom: 8 }}>
                        <Tag color={idx === 0 ? 'red' : idx === 1 ? 'orange' : 'blue'} style={{ fontSize: 13 }}>
                          {DIMENSION_LABEL[cause.dimension] || cause.dimension}
                        </Tag>
                      </div>
                      <Progress
                        percent={Math.round((cause.score / maxScore) * 100)}
                        strokeColor={RANK_COLOR[idx]}
                        size="small"
                        format={() => `${cause.score.toFixed(2)}`}
                      />
                      <Paragraph style={{ marginTop: 8, fontSize: 12, color: '#555' }}>
                        {cause.reason || '—'}
                      </Paragraph>
                      {cause.staff_id && (
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          关联员工：{cause.staff_id}
                        </Text>
                      )}
                      {cause.ing_id && (
                        <div>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            关联食材：{cause.ing_id}
                          </Text>
                        </div>
                      )}
                    </Card>
                  </Col>
                ))}
              </Row>
            )}

            {result.top3_root_causes.length > 0 && (
              <Alert
                style={{ marginTop: 16 }}
                type="info"
                icon={<CheckCircleOutlined />}
                showIcon
                message="已自动派发培训推荐"
                description="系统已根据根因自动触发培训推荐任务，请前往「培训辅导 → 废料驱动培训」标签查看详情。"
              />
            )}
          </Card>

          {/* 五步推理详情 */}
          <Card title="推理过程详情" style={{ marginBottom: 16 }}>
            <Collapse ghost>
              <Panel
                header={
                  <Space>
                    <ClockCircleOutlined />
                    <Text strong>Step 1：库存盘点差异</Text>
                    <Tag>{result.step1_inventory_variance.length} 条</Tag>
                  </Space>
                }
                key="1"
              >
                {renderJsonTable(result.step1_inventory_variance, 'step1')}
              </Panel>
              <Panel
                header={
                  <Space>
                    <ClockCircleOutlined />
                    <Text strong>Step 2：BOM 用料偏差</Text>
                    <Tag>{result.step2_bom_deviation.length} 条</Tag>
                  </Space>
                }
                key="2"
              >
                {renderJsonTable(result.step2_bom_deviation, 'step2')}
              </Panel>
              <Panel
                header={
                  <Space>
                    <ClockCircleOutlined />
                    <Text strong>Step 3：时间窗口在岗员工</Text>
                    <Tag>{result.step3_staff_in_window.length} 条</Tag>
                  </Space>
                }
                key="3"
              >
                {renderJsonTable(result.step3_staff_in_window, 'step3')}
              </Panel>
              <Panel
                header={
                  <Space>
                    <ClockCircleOutlined />
                    <Text strong>Step 4：供应商批次</Text>
                    <Tag>{result.step4_supplier_batches.length} 条</Tag>
                  </Space>
                }
                key="4"
              >
                {renderJsonTable(result.step4_supplier_batches, 'step4')}
              </Panel>
            </Collapse>
          </Card>

          <Card size="small" style={{ background: '#fafafa' }}>
            <Text type="secondary" style={{ fontSize: 11 }}>
              推理范围：门店 {result.store_id}｜租户 {result.tenant_id}｜
              {result.date_start} ~ {result.date_end || result.date_start}
            </Text>
          </Card>
        </>
      )}
    </div>
  );
};

export default WasteReasoningPage;
