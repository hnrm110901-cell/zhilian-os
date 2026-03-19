/**
 * 考勤规则管理页面
 * 路由: /attendance-rules
 * 功能: 考勤规则查看/创建/更新（GPS围栏、扣款标准、加班倍数）
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, InputNumber,
  Select, Space, message, Typography, Switch, Descriptions,
  Drawer,
} from 'antd';
import {
  PlusOutlined, EditOutlined, SafetyCertificateOutlined,
  EnvironmentOutlined,
} from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { AttendanceRuleItem } from '../../services/hrService';

const { Title, Text } = Typography;

const BRAND_ID = localStorage.getItem('brand_id') || '';

const WORK_HOUR_LABELS: Record<string, string> = {
  standard: '标准工时', flexible: '弹性工时', comprehensive: '综合工时',
};

const AttendanceRulePage: React.FC = () => {
  const [items, setItems] = useState<AttendanceRuleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editItem, setEditItem] = useState<AttendanceRuleItem | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [detailItem, setDetailItem] = useState<AttendanceRuleItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await hrService.getAttendanceRules(BRAND_ID);
      setItems(res.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const openEdit = (item?: AttendanceRuleItem) => {
    setEditItem(item || null);
    if (item) {
      form.setFieldsValue({
        store_id: item.store_id || '',
        employment_type: item.employment_type || undefined,
        clock_methods: item.clock_methods || ['wechat'],
        gps_fence_enabled: item.gps_fence_enabled,
        gps_latitude: item.gps_latitude,
        gps_longitude: item.gps_longitude,
        gps_radius_meters: item.gps_radius_meters,
        late_deduction_yuan: item.late_deduction_yuan,
        absent_deduction_yuan: item.absent_deduction_yuan,
        early_leave_deduction_yuan: item.early_leave_deduction_yuan,
        weekday_overtime_rate: item.weekday_overtime_rate,
        weekend_overtime_rate: item.weekend_overtime_rate,
        holiday_overtime_rate: item.holiday_overtime_rate,
        work_hour_type: item.work_hour_type,
        monthly_standard_hours: item.monthly_standard_hours,
        is_active: item.is_active,
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        clock_methods: ['wechat'],
        gps_fence_enabled: false,
        gps_radius_meters: 200,
        late_deduction_yuan: 50,
        absent_deduction_yuan: 200,
        early_leave_deduction_yuan: 50,
        weekday_overtime_rate: 1.5,
        weekend_overtime_rate: 2.0,
        holiday_overtime_rate: 3.0,
        work_hour_type: 'standard',
        monthly_standard_hours: 174,
        is_active: true,
      });
    }
    setModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await hrService.createOrUpdateAttendanceRule({
        brand_id: BRAND_ID,
        store_id: values.store_id || null,
        employment_type: values.employment_type || null,
        clock_methods: values.clock_methods,
        gps_fence_enabled: values.gps_fence_enabled || false,
        gps_latitude: values.gps_latitude || null,
        gps_longitude: values.gps_longitude || null,
        gps_radius_meters: values.gps_radius_meters || 200,
        late_deduction_fen: Math.round((values.late_deduction_yuan || 0) * 100),
        absent_deduction_fen: Math.round((values.absent_deduction_yuan || 0) * 100),
        early_leave_deduction_fen: Math.round((values.early_leave_deduction_yuan || 0) * 100),
        weekday_overtime_rate: values.weekday_overtime_rate,
        weekend_overtime_rate: values.weekend_overtime_rate,
        holiday_overtime_rate: values.holiday_overtime_rate,
        work_hour_type: values.work_hour_type,
        monthly_standard_hours: values.monthly_standard_hours,
        is_active: values.is_active,
      });
      message.success('考勤规则已保存');
      setModalOpen(false);
      load();
    } catch {
      message.error('保存失败');
    }
    setSubmitting(false);
  };

  const columns = [
    {
      title: '适用范围', key: 'scope', width: 160,
      render: (_: unknown, r: AttendanceRuleItem) => (
        <span>
          {r.store_id ? <Tag>{r.store_id}</Tag> : <Tag color="blue">品牌级</Tag>}
          {r.employment_type && <Tag color="cyan" style={{ marginLeft: 4 }}>{r.employment_type}</Tag>}
        </span>
      ),
    },
    {
      title: '迟到扣款', dataIndex: 'late_deduction_yuan', key: 'late', width: 100,
      render: (v: number) => <span>¥{v.toFixed(2)}</span>,
    },
    {
      title: '旷工扣款', dataIndex: 'absent_deduction_yuan', key: 'absent', width: 100,
      render: (v: number) => <span>¥{v.toFixed(2)}</span>,
    },
    {
      title: '早退扣款', dataIndex: 'early_leave_deduction_yuan', key: 'early', width: 100,
      render: (v: number) => <span>¥{v.toFixed(2)}</span>,
    },
    {
      title: '加班倍数', key: 'overtime', width: 200,
      render: (_: unknown, r: AttendanceRuleItem) => (
        <Space size={4}>
          <Tag>工作日{r.weekday_overtime_rate}x</Tag>
          <Tag>周末{r.weekend_overtime_rate}x</Tag>
          <Tag color="red">节假日{r.holiday_overtime_rate}x</Tag>
        </Space>
      ),
    },
    {
      title: '工时制', dataIndex: 'work_hour_type', key: 'work_hour', width: 100,
      render: (v: string) => WORK_HOUR_LABELS[v] || v,
    },
    {
      title: 'GPS', dataIndex: 'gps_fence_enabled', key: 'gps', width: 80,
      render: (v: boolean) => v
        ? <Tag icon={<EnvironmentOutlined />} color="green">开启</Tag>
        : <Tag color="default">关闭</Tag>,
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag color="default">禁用</Tag>,
    },
    {
      title: '操作', key: 'actions', width: 140,
      render: (_: unknown, record: AttendanceRuleItem) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Button size="small" onClick={() => setDetailItem(record)}>详情</Button>
        </Space>
      ),
    },
  ];

  const gpsEnabled = Form.useWatch('gps_fence_enabled', form);

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <SafetyCertificateOutlined style={{ marginRight: 8 }} />
        考勤规则管理
      </Title>

      <Card bordered={false}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Text type="secondary">配置迟到/早退/旷工扣款标准、加班倍率、GPS围栏等考勤规则。</Text>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>
            新建规则
          </Button>
        </div>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={false}
          locale={{ emptyText: '暂无考勤规则' }}
          scroll={{ x: 1200 }}
        />
      </Card>

      {/* 创建/编辑 Modal */}
      <Modal
        title={editItem ? '编辑考勤规则' : '新建考勤规则'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        okText="保存"
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="store_id" label="门店ID（留空为品牌级）">
            <Input placeholder="留空=品牌级默认" />
          </Form.Item>
          <Form.Item name="employment_type" label="用工类型">
            <Select allowClear placeholder="选择用工类型，留空为通用" options={[
              { label: '全职', value: 'full_time' },
              { label: '兼职', value: 'part_time' },
              { label: '小时工', value: 'hourly' },
            ]} />
          </Form.Item>
          <Form.Item name="clock_methods" label="打卡方式">
            <Select mode="multiple" options={[
              { label: '企业微信', value: 'wechat' },
              { label: '钉钉', value: 'dingtalk' },
              { label: '考勤机', value: 'machine' },
              { label: '人脸识别', value: 'face' },
            ]} />
          </Form.Item>

          <Title level={5}>扣款标准（元）</Title>
          <Space size={16} style={{ width: '100%' }}>
            <Form.Item name="late_deduction_yuan" label="迟到扣款">
              <InputNumber min={0} precision={2} addonAfter="元/次" style={{ width: 150 }} />
            </Form.Item>
            <Form.Item name="absent_deduction_yuan" label="旷工扣款">
              <InputNumber min={0} precision={2} addonAfter="元/天" style={{ width: 150 }} />
            </Form.Item>
            <Form.Item name="early_leave_deduction_yuan" label="早退扣款">
              <InputNumber min={0} precision={2} addonAfter="元/次" style={{ width: 150 }} />
            </Form.Item>
          </Space>

          <Title level={5}>加班倍率</Title>
          <Space size={16} style={{ width: '100%' }}>
            <Form.Item name="weekday_overtime_rate" label="工作日">
              <InputNumber min={1} max={5} step={0.5} precision={1} addonAfter="倍" style={{ width: 120 }} />
            </Form.Item>
            <Form.Item name="weekend_overtime_rate" label="周末">
              <InputNumber min={1} max={5} step={0.5} precision={1} addonAfter="倍" style={{ width: 120 }} />
            </Form.Item>
            <Form.Item name="holiday_overtime_rate" label="节假日">
              <InputNumber min={1} max={5} step={0.5} precision={1} addonAfter="倍" style={{ width: 120 }} />
            </Form.Item>
          </Space>

          <Title level={5}>工时制度</Title>
          <Space size={16} style={{ width: '100%' }}>
            <Form.Item name="work_hour_type" label="工时类型">
              <Select style={{ width: 150 }} options={Object.entries(WORK_HOUR_LABELS).map(([k, v]) => ({ label: v, value: k }))} />
            </Form.Item>
            <Form.Item name="monthly_standard_hours" label="月标准工时">
              <InputNumber min={100} max={250} addonAfter="小时" style={{ width: 150 }} />
            </Form.Item>
          </Space>

          <Title level={5}>GPS围栏</Title>
          <Form.Item name="gps_fence_enabled" label="启用GPS围栏" valuePropName="checked">
            <Switch />
          </Form.Item>
          {gpsEnabled && (
            <Space size={16} style={{ width: '100%' }}>
              <Form.Item name="gps_latitude" label="纬度">
                <InputNumber precision={6} style={{ width: 150 }} />
              </Form.Item>
              <Form.Item name="gps_longitude" label="经度">
                <InputNumber precision={6} style={{ width: 150 }} />
              </Form.Item>
              <Form.Item name="gps_radius_meters" label="半径(米)">
                <InputNumber min={50} max={2000} style={{ width: 120 }} />
              </Form.Item>
            </Space>
          )}

          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情抽屉 */}
      <Drawer
        title="考勤规则详情"
        open={!!detailItem}
        onClose={() => setDetailItem(null)}
        width={480}
      >
        {detailItem && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="适用范围">{detailItem.store_id || '品牌级'}</Descriptions.Item>
            <Descriptions.Item label="用工类型">{detailItem.employment_type || '通用'}</Descriptions.Item>
            <Descriptions.Item label="打卡方式">{(detailItem.clock_methods || []).join(', ')}</Descriptions.Item>
            <Descriptions.Item label="工时类型">{WORK_HOUR_LABELS[detailItem.work_hour_type] || detailItem.work_hour_type}</Descriptions.Item>
            <Descriptions.Item label="月标准工时">{detailItem.monthly_standard_hours}小时</Descriptions.Item>
            <Descriptions.Item label="迟到扣款">¥{detailItem.late_deduction_yuan.toFixed(2)}/次</Descriptions.Item>
            <Descriptions.Item label="旷工扣款">¥{detailItem.absent_deduction_yuan.toFixed(2)}/天</Descriptions.Item>
            <Descriptions.Item label="早退扣款">¥{detailItem.early_leave_deduction_yuan.toFixed(2)}/次</Descriptions.Item>
            <Descriptions.Item label="工作日加班">{detailItem.weekday_overtime_rate}倍</Descriptions.Item>
            <Descriptions.Item label="周末加班">{detailItem.weekend_overtime_rate}倍</Descriptions.Item>
            <Descriptions.Item label="节假日加班">{detailItem.holiday_overtime_rate}倍</Descriptions.Item>
            <Descriptions.Item label="GPS围栏">{detailItem.gps_fence_enabled ? '已开启' : '未开启'}</Descriptions.Item>
            {detailItem.gps_fence_enabled && (
              <>
                <Descriptions.Item label="GPS坐标">{detailItem.gps_latitude}, {detailItem.gps_longitude}</Descriptions.Item>
                <Descriptions.Item label="GPS半径">{detailItem.gps_radius_meters}米</Descriptions.Item>
              </>
            )}
            <Descriptions.Item label="状态">{detailItem.is_active ? '启用' : '禁用'}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
};

export default AttendanceRulePage;
