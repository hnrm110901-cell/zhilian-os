import React, { useState, useCallback } from 'react';
import {
  Card, Tabs, Form, Input, Select, Button, Table, Tag,
  Space, Modal, Descriptions, Statistic, Row, Col, InputNumber, message,
} from 'antd';
import { SearchOutlined, PlusOutlined, GiftOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const sexLabel: Record<number, string> = { 1: '男', 2: '女' };

const MemberSystemPage: React.FC = () => {
  const [queryForm] = Form.useForm();
  const [addForm] = Form.useForm();
  const [rechargeForm] = Form.useForm();
  const [couponForm] = Form.useForm();

  const [member, setMember] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [recharges, setRecharges] = useState<any[]>([]);
  const [coupons, setCoupons] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [addModal, setAddModal] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [editForm] = Form.useForm();
  const [connectionStatus, setConnectionStatus] = useState<any>(null);

  const testConnection = async () => {
    try {
      const res = await apiClient.get('/members/test-connection');
      setConnectionStatus(res.data);
      if (res.data.success) showSuccess('连接正常');
      else message.error(res.data.error || '连接失败');
    } catch (err: any) { handleApiError(err, '连接测试失败'); }
  };

  const queryMember = useCallback(async (values: any) => {
    setLoading(true);
    setMember(null);
    setTrades([]);
    setRecharges([]);
    setCoupons([]);
    try {
      const res = await apiClient.get('/members/query', { params: values });
      setMember(res.data);
      // 同时加载交易/充值/优惠券
      const cardNo = res.data.cardNo;
      const [t, r, c] = await Promise.allSettled([
        apiClient.get('/members/trade/query', { params: { card_no: cardNo } }),
        apiClient.get('/members/recharge/query', { params: { card_no: cardNo } }),
        apiClient.get('/members/coupon/list', { params: { card_no: cardNo } }),
      ]);
      if (t.status === 'fulfilled') setTrades(t.value.data?.trades || t.value.data || []);
      if (r.status === 'fulfilled') setRecharges(r.value.data?.records || r.value.data || []);
      if (c.status === 'fulfilled') setCoupons(c.value.data?.coupons || c.value.data || []);
    } catch (err: any) { handleApiError(err, '查询会员失败'); }
    finally { setLoading(false); }
  }, []);

  const addMember = async (values: any) => {
    try {
      await apiClient.post('/members/add', values);
      showSuccess('会员添加成功');
      setAddModal(false);
      addForm.resetFields();
    } catch (err: any) { handleApiError(err, '添加会员失败'); }
  };

  const updateMember = async (values: any) => {
    if (!member?.cardNo) return;
    try {
      await apiClient.put(`/members/${member.cardNo}`, values);
      showSuccess('会员信息已更新');
      setEditModal(false);
      queryMember({ card_no: member.cardNo });
    } catch (err: any) { handleApiError(err, '更新会员失败'); }
  };

  const submitRecharge = async (values: any) => {
    if (!member?.cardNo) return;
    try {
      await apiClient.post('/members/recharge/submit', {
        ...values,
        card_no: member.cardNo,
        amount: Math.round(values.amount * 100),
      });
      showSuccess('充值成功');
      rechargeForm.resetFields();
      queryMember({ card_no: member.cardNo });
    } catch (err: any) { handleApiError(err, '充值失败'); }
  };

  const useCoupon = async (values: any) => {
    try {
      await apiClient.post('/members/coupon/use', {
        ...values,
        amount: Math.round(values.amount * 100),
      });
      showSuccess('优惠券核销成功');
      couponForm.resetFields();
    } catch (err: any) { handleApiError(err, '核销失败'); }
  };

  const tradeColumns: ColumnsType<any> = [
    { title: '交易ID', dataIndex: 'trade_id', key: 'trade_id', ellipsis: true },
    { title: '金额', dataIndex: 'amount', key: 'amount', render: (v: number) => `¥${(v / 100).toFixed(2)}` },
    { title: '支付方式', dataIndex: 'pay_type', key: 'pay_type' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'success' ? 'green' : 'red'}>{v}</Tag> },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => v?.slice(0, 16) },
  ];

  const rechargeColumns: ColumnsType<any> = [
    { title: '充值ID', dataIndex: 'recharge_id', key: 'recharge_id', ellipsis: true },
    { title: '充值金额', dataIndex: 'amount', key: 'amount', render: (v: number) => `¥${(v / 100).toFixed(2)}` },
    { title: '支付方式', dataIndex: 'pay_type', key: 'pay_type' },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => v?.slice(0, 16) },
  ];

  const couponColumns: ColumnsType<any> = [
    { title: '优惠券名称', dataIndex: 'coupon_name', key: 'coupon_name' },
    { title: '面值', dataIndex: 'value', key: 'value', render: (v: number) => `¥${(v / 100).toFixed(0)}` },
    { title: '有效期', dataIndex: 'expire_date', key: 'expire_date' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'valid' ? 'green' : 'default'}>{v === 'valid' ? '可用' : '已用'}</Tag> },
  ];

  const memberTabItems = member ? [
    {
      key: 'info', label: '会员信息',
      children: (
        <div>
          <Descriptions bordered column={2} size="small">
            <Descriptions.Item label="卡号">{member.cardNo}</Descriptions.Item>
            <Descriptions.Item label="姓名">{member.name}</Descriptions.Item>
            <Descriptions.Item label="手机">{member.mobile}</Descriptions.Item>
            <Descriptions.Item label="性别">{sexLabel[member.sex] || '-'}</Descriptions.Item>
            <Descriptions.Item label="生日">{member.birthday || '-'}</Descriptions.Item>
            <Descriptions.Item label="等级">Lv.{member.level}</Descriptions.Item>
            <Descriptions.Item label="积分">{member.points}</Descriptions.Item>
            <Descriptions.Item label="余额">¥{(member.balance / 100).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="注册门店">{member.regStore || '-'}</Descriptions.Item>
            <Descriptions.Item label="注册时间">{member.regTime || '-'}</Descriptions.Item>
          </Descriptions>
          <Space style={{ marginTop: 12 }}>
            <Button onClick={() => { editForm.setFieldsValue({ name: member.name, sex: member.sex, birthday: member.birthday }); setEditModal(true); }}>编辑信息</Button>
          </Space>
        </div>
      ),
    },
    {
      key: 'trades', label: `交易记录 (${trades.length})`,
      children: <Table columns={tradeColumns} dataSource={trades} rowKey={(r, i) => `${r.trade_id || i}`} size="small" />,
    },
    {
      key: 'recharge', label: `充值记录 (${recharges.length})`,
      children: (
        <div>
          <Card size="small" title="快速充值" style={{ marginBottom: 12 }}>
            <Form form={rechargeForm} layout="inline" onFinish={submitRecharge}>
              <Form.Item name="amount" label="充值金额(元)" rules={[{ required: true }]}><InputNumber min={1} /></Form.Item>
              <Form.Item name="pay_type" label="支付方式" initialValue={1}><Select style={{ width: 100 }}><Option value={1}>微信</Option><Option value={2}>支付宝</Option><Option value={3}>现金</Option></Select></Form.Item>
              <Form.Item name="cashier" label="收银员" rules={[{ required: true }]}><Input placeholder="收银员ID" /></Form.Item>
              <Form.Item name="store_id" label="门店" rules={[{ required: true }]}><Input placeholder="门店ID" /></Form.Item>
              <Form.Item name="trade_no" label="流水号" rules={[{ required: true }]}><Input placeholder="第三方流水号" /></Form.Item>
              <Form.Item><Button type="primary" htmlType="submit">充值</Button></Form.Item>
            </Form>
          </Card>
          <Table columns={rechargeColumns} dataSource={recharges} rowKey={(r, i) => `${r.recharge_id || i}`} size="small" />
        </div>
      ),
    },
    {
      key: 'coupons', label: `优惠券 (${coupons.length})`,
      children: (
        <div>
          <Card size="small" title="核销优惠券" style={{ marginBottom: 12 }}>
            <Form form={couponForm} layout="inline" onFinish={useCoupon}>
              <Form.Item name="code" label="券码" rules={[{ required: true }]}><Input placeholder="优惠券码" /></Form.Item>
              <Form.Item name="store_id" label="门店" rules={[{ required: true }]}><Input placeholder="门店ID" /></Form.Item>
              <Form.Item name="cashier" label="收银员" rules={[{ required: true }]}><Input placeholder="收银员ID" /></Form.Item>
              <Form.Item name="amount" label="消费金额(元)" rules={[{ required: true }]}><InputNumber min={0} /></Form.Item>
              <Form.Item><Button type="primary" icon={<GiftOutlined />} htmlType="submit">核销</Button></Form.Item>
            </Form>
          </Card>
          <Table columns={couponColumns} dataSource={coupons} rowKey={(r, i) => `${r.coupon_id || i}`} size="small" />
        </div>
      ),
    },
  ] : [];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={testConnection}>
          测试连接 {connectionStatus && (connectionStatus.success ? '✅' : '❌')}
        </Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModal(true)}>新增会员</Button>
      </Space>

      <Card title="会员查询" style={{ marginBottom: 16 }}>
        <Form form={queryForm} layout="inline" onFinish={queryMember}>
          <Form.Item name="card_no" label="卡号"><Input placeholder="会员卡号" /></Form.Item>
          <Form.Item name="mobile" label="手机号"><Input placeholder="手机号" /></Form.Item>
          <Form.Item><Button type="primary" icon={<SearchOutlined />} htmlType="submit" loading={loading}>查询</Button></Form.Item>
        </Form>
      </Card>

      {member && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}><Card size="small"><Statistic title="积分" value={member.points} /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="余额" value={(member.balance / 100).toFixed(2)} prefix="¥" /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="等级" value={`Lv.${member.level}`} /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="优惠券" value={coupons.filter((c: any) => c.status === 'valid').length} suffix="张可用" /></Card></Col>
        </Row>
      )}

      {member && <Card><Tabs items={memberTabItems} /></Card>}

      {/* 新增会员 Modal */}
      <Modal title="新增会员" open={addModal} onCancel={() => setAddModal(false)} footer={null}>
        <Form form={addForm} layout="vertical" onFinish={addMember}>
          <Form.Item name="mobile" label="手机号" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="sex" label="性别" initialValue={1}><Select><Option value={1}>男</Option><Option value={2}>女</Option></Select></Form.Item>
          <Form.Item name="birthday" label="生日"><Input placeholder="YYYY-MM-DD" /></Form.Item>
          <Form.Item name="store_id" label="注册门店"><Input /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block>添加</Button></Form.Item>
        </Form>
      </Modal>

      {/* 编辑会员 Modal */}
      <Modal title="编辑会员信息" open={editModal} onCancel={() => setEditModal(false)} footer={null}>
        <Form form={editForm} layout="vertical" onFinish={updateMember}>
          <Form.Item name="name" label="姓名"><Input /></Form.Item>
          <Form.Item name="sex" label="性别"><Select><Option value={1}>男</Option><Option value={2}>女</Option></Select></Form.Item>
          <Form.Item name="birthday" label="生日"><Input placeholder="YYYY-MM-DD" /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block>保存</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default MemberSystemPage;
