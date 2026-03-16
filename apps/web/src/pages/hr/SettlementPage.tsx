/**
 * 离职结算页面
 * 路由: /settlement
 * 功能: 结算单列表 + 创建结算 + 明细抽屉 + 审批/打款
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Card, Table, Tag, Button, Drawer, Descriptions, Space,
  Modal, Form, Input, Select, DatePicker, InputNumber,
  message, Typography, Spin, Statistic, Row, Col, Divider,
} from 'antd';
import {
  PlusOutlined, DollarOutlined, CheckOutlined, EyeOutlined,
} from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { SettlementRecordItem } from '../../services/hrService';

const { Title } = Typography;

const STORE_ID = localStorage.getItem('store_id') || 'STORE_001';
const BRAND_ID = localStorage.getItem('brand_id') || 'BRAND_001';

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  pending_approval: { label: '待审批', color: 'processing' },
  approved: { label: '已审批', color: 'success' },
  paid: { label: '已打款', color: 'green' },
  disputed: { label: '争议中', color: 'error' },
};

const SEP_TYPE_LABELS: Record<string, string> = {
  resign: '主动离职', dismiss: '辞退', expire: '合同到期', mutual: '协商解除',
};

const COMP_TYPE_LABELS: Record<string, string> = {
  none: '无补偿', n: 'N倍', n_plus_1: 'N+1倍', '2n': '2N倍',
};

const SettlementPage: React.FC = () => {
  const [items, setItems] = useState<SettlementRecordItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [detailItem, setDetailItem] = useState<SettlementRecordItem | null>(null);
  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await hrService.getSettlements(STORE_ID, BRAND_ID, statusFilter);
      setItems(res.data?.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      setSubmitting(true);
      await hrService.createSettlement({
        store_id: STORE_ID,
        brand_id: BRAND_ID,
        employee_id: values.employee_id,
        last_work_date: values.last_work_date.format('YYYY-MM-DD'),
        separation_type: values.separation_type || 'resign',
        compensation_type: values.compensation_type || 'none',
        annual_leave_method: values.annual_leave_method || 'legal',
        overtime_pay_fen: Math.round((values.overtime_pay_yuan || 0) * 100),
        bonus_fen: Math.round((values.bonus_yuan || 0) * 100),
        deduction_fen: Math.round((values.deduction_yuan || 0) * 100),
        deduction_detail: values.deduction_detail || '',
        remark: values.remark || '',
      });
      message.success('结算单创建成功');
      setCreateModal(false);
      createForm.resetFields();
      load();
    } catch {
      message.error('创建失败');
    }
    setSubmitting(false);
  };

  const handleApprove = async (id: string) => {
    try {
      await hrService.approveSettlement(id, 'current_user');
      message.success('审批通过');
      load();
      if (detailItem?.id === id) {
        const res = await hrService.getSettlement(id);
        setDetailItem(res.data);
      }
    } catch { message.error('审批失败'); }
  };

  const handlePay = async (id: string) => {
    Modal.confirm({
      title: '确认打款',
      content: '确认已完成打款操作？此操作不可撤销。',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        try {
          await hrService.markSettlementPaid(id, 'current_user');
          message.success('已标记打款');
          load();
          if (detailItem?.id === id) {
            const res = await hrService.getSettlement(id);
            setDetailItem(res.data);
          }
        } catch { message.error('操作失败'); }
      },
    });
  };

  const columns = [
    { title: '员工', dataIndex: 'employee_name', key: 'employee_name', width: 100 },
    {
      title: '离职类型', dataIndex: 'separation_type', key: 'separation_type', width: 100,
      render: (v: string) => SEP_TYPE_LABELS[v] || v,
    },
    {
      title: '最后工作日', dataIndex: 'last_work_date', key: 'last_work_date', width: 120,
    },
    {
      title: '补偿方式', dataIndex: 'compensation_type', key: 'compensation_type', width: 100,
      render: (v: string) => COMP_TYPE_LABELS[v] || v,
    },
    {
      title: '应付总额', dataIndex: 'total_payable_yuan', key: 'total_payable_yuan', width: 130,
      render: (v: number) => <span style={{ fontWeight: 600 }}>¥{(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string) => {
        const s = STATUS_MAP[v] || STATUS_MAP.draft;
        return <Tag color={s.color}>{s.label}</Tag>;
      },
    },
    {
      title: '操作', key: 'actions', width: 200,
      render: (_: unknown, record: SettlementRecordItem) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => setDetailItem(record)}>详情</Button>
          {record.status === 'draft' && (
            <Button size="small" type="primary" onClick={() => handleApprove(record.id)}>提交审批</Button>
          )}
          {record.status === 'approved' && (
            <Button size="small" icon={<DollarOutlined />} onClick={() => handlePay(record.id)}>确认打款</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <DollarOutlined style={{ marginRight: 8 }} />
        离职结算
      </Title>

      <Card bordered={false}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Space>
            <Select
              placeholder="状态筛选"
              allowClear
              style={{ width: 140 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={Object.entries(STATUS_MAP).map(([k, v]) => ({ label: v.label, value: k }))}
            />
          </Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
            新建结算
          </Button>
        </div>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: '暂无结算记录' }}
        />
      </Card>

      {/* 详情抽屉 */}
      <Drawer
        title={`结算详情 — ${detailItem?.employee_name || ''}`}
        open={!!detailItem}
        onClose={() => setDetailItem(null)}
        width={520}
      >
        {detailItem && (
          <>
            <Row gutter={16} style={{ marginBottom: 24 }}>
              <Col span={12}>
                <Statistic title="应付总额" prefix="¥" value={detailItem.total_payable_yuan} precision={2} />
              </Col>
              <Col span={12}>
                <Tag color={(STATUS_MAP[detailItem.status] || STATUS_MAP.draft).color} style={{ fontSize: 14, padding: '4px 12px' }}>
                  {(STATUS_MAP[detailItem.status] || STATUS_MAP.draft).label}
                </Tag>
              </Col>
            </Row>

            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="员工">{detailItem.employee_name}</Descriptions.Item>
              <Descriptions.Item label="离职类型">{SEP_TYPE_LABELS[detailItem.separation_type] || detailItem.separation_type}</Descriptions.Item>
              <Descriptions.Item label="最后工作日">{detailItem.last_work_date || '-'}</Descriptions.Item>
              <Descriptions.Item label="离职日期">{detailItem.separation_date || '-'}</Descriptions.Item>
            </Descriptions>

            <Divider>结算明细</Divider>

            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="末月出勤天数">{detailItem.work_days_last_month}天</Descriptions.Item>
              <Descriptions.Item label="末月工资">¥{detailItem.last_month_salary_yuan?.toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="未休年假天数">{detailItem.unused_annual_days}天</Descriptions.Item>
              <Descriptions.Item label="年假补偿">¥{detailItem.annual_leave_compensation_yuan?.toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="工龄(x10)">{detailItem.service_years_x10}</Descriptions.Item>
              <Descriptions.Item label="补偿方式">{COMP_TYPE_LABELS[detailItem.compensation_type] || detailItem.compensation_type}</Descriptions.Item>
              <Descriptions.Item label="经济补偿">¥{detailItem.economic_compensation_yuan?.toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="加班费">¥{detailItem.overtime_pay_yuan?.toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="奖金">¥{detailItem.bonus_yuan?.toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="扣款">
                <span style={{ color: '#ff4d4f' }}>-¥{detailItem.deduction_yuan?.toFixed(2)}</span>
              </Descriptions.Item>
              {detailItem.deduction_detail && (
                <Descriptions.Item label="扣款说明">{detailItem.deduction_detail}</Descriptions.Item>
              )}
            </Descriptions>

            <Divider />

            <Row gutter={16}>
              <Col span={24} style={{ textAlign: 'right' }}>
                <Statistic
                  title="应付总额"
                  prefix="¥"
                  value={detailItem.total_payable_yuan}
                  precision={2}
                  valueStyle={{ color: '#3f8600', fontSize: 24 }}
                />
              </Col>
            </Row>

            {detailItem.status === 'draft' && (
              <div style={{ marginTop: 16, textAlign: 'right' }}>
                <Button type="primary" onClick={() => handleApprove(detailItem.id)}>提交审批</Button>
              </div>
            )}
            {detailItem.status === 'approved' && (
              <div style={{ marginTop: 16, textAlign: 'right' }}>
                <Button type="primary" icon={<CheckOutlined />} onClick={() => handlePay(detailItem.id)}>确认打款</Button>
              </div>
            )}
          </>
        )}
      </Drawer>

      {/* 创建结算 Modal */}
      <Modal
        title="新建离职结算"
        open={createModal}
        onOk={handleCreate}
        onCancel={() => { setCreateModal(false); createForm.resetFields(); }}
        confirmLoading={submitting}
        okText="创建结算单"
        width={560}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="employee_id" label="员工ID" rules={[{ required: true, message: '请输入员工ID' }]}>
            <Input placeholder="员工ID" />
          </Form.Item>
          <Form.Item name="last_work_date" label="最后工作日" rules={[{ required: true, message: '请选择日期' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="separation_type" label="离职类型" initialValue="resign">
                <Select options={Object.entries(SEP_TYPE_LABELS).map(([k, v]) => ({ label: v, value: k }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="compensation_type" label="补偿方式" initialValue="none">
                <Select options={Object.entries(COMP_TYPE_LABELS).map(([k, v]) => ({ label: v, value: k }))} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="overtime_pay_yuan" label="加班费(元)">
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="bonus_yuan" label="奖金(元)">
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="deduction_yuan" label="扣款(元)">
                <InputNumber min={0} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="deduction_detail" label="扣款说明">
            <Input placeholder="如：制服损坏" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SettlementPage;
