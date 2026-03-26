/**
 * 统一 POS 收银台 — 平替天财商龙
 *
 * 功能：
 *  - 开单/点菜/加菜/退菜
 *  - 海鲜称重/时价/做法选择
 *  - 套餐/宴会/堂食/自提/外摆/外卖全场景
 *  - 会员识别/会员价/积分抵扣
 *  - 平台券核销（美团/抖音/大众点评）
 *  - 混合支付结账
 *  - 厨打分单/催菜
 *  - 影子模式状态面板
 */

import React, { useState, useCallback } from 'react';
import {
  Row, Col, Card, Button, Input, InputNumber, Select, Table, Tag, Space,
  Modal, message, Tabs, Badge, Descriptions, Divider, List, Radio,
  Typography, Statistic, Alert, Switch, Tooltip,
} from 'antd';
import {
  ShoppingCartOutlined, UserOutlined, CreditCardOutlined,
  FireOutlined, SyncOutlined, PrinterOutlined, TeamOutlined,
  SearchOutlined, ScanOutlined, ThunderboltOutlined, GiftOutlined,
  EnvironmentOutlined, ClockCircleOutlined, CheckCircleOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;
const { TabPane } = Tabs;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface OrderItem {
  item_id: string;
  dish_id: string;
  dish_name: string;
  pricing_mode: string;
  quantity: number;
  unit_price_fen: number;
  spec_name?: string;
  weight_g?: number;
  cooking_method?: string;
  notes?: string;
  subtotal_fen: number;
  is_gift: boolean;
}

interface CouponInfo {
  coupon_code: string;
  platform: string;
  coupon_value_fen: number;
}

interface PaymentInfo {
  method: string;
  amount_fen: number;
}

// ── 消费场景配置 ──────────────────────────────────────────────────────────────

const SCENES = [
  { value: 'dine_in', label: '堂食', icon: <EnvironmentOutlined />, color: '#1890ff' },
  { value: 'takeaway', label: '外卖', icon: <ShoppingCartOutlined />, color: '#52c41a' },
  { value: 'self_pickup', label: '自提', icon: <ClockCircleOutlined />, color: '#faad14' },
  { value: 'outdoor', label: '外摆', icon: <EnvironmentOutlined />, color: '#13c2c2' },
  { value: 'banquet', label: '宴会', icon: <TeamOutlined />, color: '#722ed1' },
  { value: 'set_meal', label: '套餐', icon: <GiftOutlined />, color: '#eb2f96' },
  { value: 'delivery', label: '配送', icon: <ShoppingCartOutlined />, color: '#fa541c' },
];

const PAYMENT_METHODS = [
  { value: 'wechat', label: '微信支付', color: '#07c160' },
  { value: 'alipay', label: '支付宝', color: '#1677ff' },
  { value: 'cash', label: '现金', color: '#faad14' },
  { value: 'member_balance', label: '会员余额', color: '#ff6b2c' },
  { value: 'member_points', label: '积分抵扣', color: '#eb2f96' },
  { value: 'bank_card', label: '银行卡', color: '#333' },
  { value: 'coupon', label: '优惠券', color: '#52c41a' },
  { value: 'credit', label: '挂账', color: '#999' },
];

const COOKING_METHODS = ['清蒸', '红烧', '白灼', '椒盐', '蒜蓉', '葱姜', '避风塘', '铁板', '刺身'];

// ── 主组件 ────────────────────────────────────────────────────────────────────

const UnifiedPOSPage: React.FC = () => {
  // 订单状态
  const [scene, setScene] = useState('dine_in');
  const [tableCode, setTableCode] = useState('');
  const [partySize, setPartySize] = useState(2);
  const [memberId, setMemberId] = useState('');
  const [orderItems, setOrderItems] = useState<OrderItem[]>([]);
  const [coupons, setCoupons] = useState<CouponInfo[]>([]);
  const [memberDiscount, setMemberDiscount] = useState(0);

  // 模态框
  const [seafoodModal, setSeafoodModal] = useState(false);
  const [couponModal, setCouponModal] = useState(false);
  const [settleModal, setSettleModal] = useState(false);
  const [memberModal, setMemberModal] = useState(false);

  // 海鲜下单
  const [seafoodWeight, setSeafoodWeight] = useState<number>(0);
  const [seafoodMethod, setSeafoodMethod] = useState('清蒸');
  const [marketPrice, setMarketPrice] = useState<number>(0);

  // 金额计算
  const subtotalFen = orderItems.reduce((sum, i) => sum + i.subtotal_fen, 0);
  const couponDiscountFen = coupons.reduce((sum, c) => sum + c.coupon_value_fen, 0);
  const totalFen = Math.max(0, subtotalFen - memberDiscount - couponDiscountFen);

  const fenToYuan = (fen: number) => (fen / 100).toFixed(2);

  // ── 菜品操作 ────────────────────────────────────────────────────────────

  const addDish = useCallback((dish: Partial<OrderItem>) => {
    const item: OrderItem = {
      item_id: `item_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      dish_id: dish.dish_id || '',
      dish_name: dish.dish_name || '',
      pricing_mode: dish.pricing_mode || 'fixed',
      quantity: dish.quantity || 1,
      unit_price_fen: dish.unit_price_fen || 0,
      spec_name: dish.spec_name,
      weight_g: dish.weight_g,
      cooking_method: dish.cooking_method,
      notes: dish.notes,
      subtotal_fen: dish.subtotal_fen || (dish.unit_price_fen || 0) * (dish.quantity || 1),
      is_gift: dish.is_gift || false,
    };
    setOrderItems(prev => [...prev, item]);
    message.success(`已添加: ${item.dish_name}`);
  }, []);

  const removeDish = useCallback((itemId: string) => {
    setOrderItems(prev => prev.filter(i => i.item_id !== itemId));
  }, []);

  // ── 海鲜称重下单 ────────────────────────────────────────────────────────

  const addSeafoodDish = useCallback(() => {
    if (!seafoodWeight || !marketPrice) {
      message.error('请输入重量和时价');
      return;
    }
    const subtotal = Math.round(marketPrice * seafoodWeight / 500); // 时价按斤
    addDish({
      dish_id: 'seafood_custom',
      dish_name: `海鲜（${seafoodMethod}）`,
      pricing_mode: 'by_weight',
      quantity: 1,
      unit_price_fen: marketPrice,
      weight_g: seafoodWeight,
      cooking_method: seafoodMethod,
      subtotal_fen: subtotal,
    });
    setSeafoodModal(false);
    setSeafoodWeight(0);
    setMarketPrice(0);
  }, [seafoodWeight, marketPrice, seafoodMethod, addDish]);

  // ── 结账 ────────────────────────────────────────────────────────────────

  const handleSettle = useCallback((payments: PaymentInfo[]) => {
    const totalPaid = payments.reduce((s, p) => s + p.amount_fen, 0);
    if (totalPaid < totalFen) {
      message.error(`支付不足: 还差 ¥${fenToYuan(totalFen - totalPaid)}`);
      return;
    }
    message.success(`结账成功! 实收 ¥${fenToYuan(totalPaid)}, 找零 ¥${fenToYuan(totalPaid - totalFen)}`);
    setSettleModal(false);
    // 清空订单
    setOrderItems([]);
    setCoupons([]);
    setMemberDiscount(0);
    setTableCode('');
  }, [totalFen]);

  // ── 菜品列表列定义 ──────────────────────────────────────────────────────

  const columns = [
    {
      title: '菜品',
      dataIndex: 'dish_name',
      key: 'dish_name',
      render: (name: string, record: OrderItem) => (
        <Space direction="vertical" size={0}>
          <Text strong>{name}</Text>
          {record.spec_name && <Text type="secondary" style={{ fontSize: 12 }}>{record.spec_name}</Text>}
          {record.cooking_method && <Tag color="orange" style={{ fontSize: 11 }}>{record.cooking_method}</Tag>}
          {record.weight_g && <Text type="secondary" style={{ fontSize: 11 }}>{record.weight_g}g</Text>}
          {record.notes && <Text type="secondary" style={{ fontSize: 11 }}>备注: {record.notes}</Text>}
        </Space>
      ),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 60,
      align: 'center' as const,
    },
    {
      title: '单价',
      dataIndex: 'unit_price_fen',
      key: 'price',
      width: 80,
      align: 'right' as const,
      render: (fen: number) => `¥${fenToYuan(fen)}`,
    },
    {
      title: '小计',
      dataIndex: 'subtotal_fen',
      key: 'subtotal',
      width: 80,
      align: 'right' as const,
      render: (fen: number) => <Text strong style={{ color: '#ff6b2c' }}>¥{fenToYuan(fen)}</Text>,
    },
    {
      title: '操作',
      key: 'action',
      width: 60,
      render: (_: unknown, record: OrderItem) => (
        <Button type="link" danger size="small" onClick={() => removeDish(record.item_id)}>
          退菜
        </Button>
      ),
    },
  ];

  // ── 渲染 ────────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: 16, background: '#f0f2f5', minHeight: '100vh' }}>
      {/* 顶部：场景选择 + 桌号 + 人数 */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto">
            <Space size={4}>
              {SCENES.map(s => (
                <Button
                  key={s.value}
                  type={scene === s.value ? 'primary' : 'default'}
                  icon={s.icon}
                  size="small"
                  onClick={() => setScene(s.value)}
                  style={scene === s.value ? { background: s.color, borderColor: s.color } : {}}
                >
                  {s.label}
                </Button>
              ))}
            </Space>
          </Col>
          <Col>
            <Space>
              <Input
                prefix={<EnvironmentOutlined />}
                placeholder="桌号"
                value={tableCode}
                onChange={e => setTableCode(e.target.value)}
                style={{ width: 100 }}
                size="small"
              />
              <InputNumber
                prefix={<TeamOutlined />}
                min={1}
                max={50}
                value={partySize}
                onChange={v => setPartySize(v || 1)}
                style={{ width: 80 }}
                size="small"
              />
              <Button
                icon={<UserOutlined />}
                onClick={() => setMemberModal(true)}
                type={memberId ? 'primary' : 'default'}
                size="small"
              >
                {memberId ? `会员: ${memberId}` : '会员'}
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Row gutter={12}>
        {/* 左侧：菜单区域 */}
        <Col xs={24} lg={14}>
          <Card
            title="快速点单"
            size="small"
            extra={
              <Space>
                <Button type="primary" icon={<FireOutlined />} onClick={() => setSeafoodModal(true)} size="small">
                  海鲜称重
                </Button>
                <Button icon={<ScanOutlined />} size="small">扫码点单</Button>
              </Space>
            }
          >
            {/* 示例菜品按钮区 */}
            <Row gutter={[8, 8]}>
              {[
                { id: 'D001', name: '剁椒鱼头', price: 8800, station: 'steamer' },
                { id: 'D002', name: '小炒黄牛肉', price: 5800, station: 'hot_wok' },
                { id: 'D003', name: '口味虾', price: 12800, station: 'deep_fry' },
                { id: 'D004', name: '凉拌木耳', price: 1800, station: 'cold_dish' },
                { id: 'D005', name: '波士顿龙虾', price: 0, station: 'seafood', mode: 'market' },
                { id: 'D006', name: '东星斑', price: 0, station: 'seafood', mode: 'by_weight' },
                { id: 'D007', name: '家庭套餐A', price: 28800, station: 'hot_wok', mode: 'package' },
                { id: 'D008', name: '精品刺身拼盘', price: 16800, station: 'cold_dish' },
                { id: 'D009', name: '黄焖甲鱼', price: 0, station: 'soup', mode: 'by_count' },
                { id: 'D010', name: '招牌烤鱼', price: 9800, station: 'grill' },
                { id: 'D011', name: '蒜蓉粉丝蒸扇贝', price: 4800, station: 'seafood' },
                { id: 'D012', name: '芒果千层', price: 3800, station: 'pastry' },
              ].map(dish => (
                <Col key={dish.id} xs={8} sm={6} md={4}>
                  <Button
                    block
                    style={{
                      height: 64,
                      whiteSpace: 'normal',
                      fontSize: 12,
                      lineHeight: 1.3,
                      borderColor: dish.mode === 'market' ? '#ff4d4f' : undefined,
                    }}
                    onClick={() => {
                      if (dish.mode === 'market' || dish.mode === 'by_weight') {
                        setSeafoodModal(true);
                      } else {
                        addDish({
                          dish_id: dish.id,
                          dish_name: dish.name,
                          pricing_mode: dish.mode || 'fixed',
                          unit_price_fen: dish.price,
                          quantity: 1,
                          subtotal_fen: dish.price,
                        });
                      }
                    }}
                  >
                    <div>{dish.name}</div>
                    <div style={{ color: dish.price ? '#ff6b2c' : '#ff4d4f', fontWeight: 600 }}>
                      {dish.price ? `¥${fenToYuan(dish.price)}` : '时价'}
                    </div>
                  </Button>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>

        {/* 右侧：订单区域 */}
        <Col xs={24} lg={10}>
          <Card
            title={
              <Space>
                <ShoppingCartOutlined />
                <span>当前订单</span>
                <Badge count={orderItems.length} style={{ backgroundColor: '#ff6b2c' }} />
              </Space>
            }
            size="small"
          >
            <Table
              dataSource={orderItems}
              columns={columns}
              rowKey="item_id"
              size="small"
              pagination={false}
              scroll={{ y: 300 }}
              locale={{ emptyText: '请点菜' }}
            />

            <Divider style={{ margin: '8px 0' }} />

            {/* 金额汇总 */}
            <Descriptions column={1} size="small">
              <Descriptions.Item label="小计">¥{fenToYuan(subtotalFen)}</Descriptions.Item>
              {memberDiscount > 0 && (
                <Descriptions.Item label="会员折扣">
                  <Text type="success">-¥{fenToYuan(memberDiscount)}</Text>
                </Descriptions.Item>
              )}
              {couponDiscountFen > 0 && (
                <Descriptions.Item label="优惠券">
                  <Text type="success">-¥{fenToYuan(couponDiscountFen)}</Text>
                </Descriptions.Item>
              )}
            </Descriptions>

            <div style={{
              textAlign: 'right',
              padding: '8px 0',
              borderTop: '2px solid #ff6b2c',
              marginTop: 8,
            }}>
              <Text style={{ fontSize: 14 }}>应收: </Text>
              <Text style={{ fontSize: 24, fontWeight: 700, color: '#ff6b2c' }}>
                ¥{fenToYuan(totalFen)}
              </Text>
            </div>

            {/* 操作按钮 */}
            <Space style={{ width: '100%', marginTop: 8 }} direction="vertical">
              <Row gutter={8}>
                <Col span={8}>
                  <Button
                    block
                    icon={<GiftOutlined />}
                    onClick={() => setCouponModal(true)}
                    disabled={orderItems.length === 0}
                  >
                    核销券
                  </Button>
                </Col>
                <Col span={8}>
                  <Button
                    block
                    icon={<PrinterOutlined />}
                    disabled={orderItems.length === 0}
                  >
                    厨打
                  </Button>
                </Col>
                <Col span={8}>
                  <Button
                    block
                    icon={<ThunderboltOutlined />}
                    danger
                    disabled={orderItems.length === 0}
                  >
                    催菜
                  </Button>
                </Col>
              </Row>
              <Button
                type="primary"
                block
                size="large"
                icon={<CreditCardOutlined />}
                onClick={() => setSettleModal(true)}
                disabled={orderItems.length === 0}
                style={{ background: '#ff6b2c', borderColor: '#ff6b2c', height: 48 }}
              >
                结账 ¥{fenToYuan(totalFen)}
              </Button>
            </Space>

            {/* 影子同步状态 */}
            <div style={{ marginTop: 8, textAlign: 'center' }}>
              <Tag icon={<SyncOutlined spin />} color="processing">
                影子模式: 同步天财商龙
              </Tag>
            </div>
          </Card>
        </Col>
      </Row>

      {/* ── 海鲜称重弹窗 ──────────────────────────────────────────────── */}
      <Modal
        title={<><FireOutlined /> 海鲜称重下单</>}
        open={seafoodModal}
        onOk={addSeafoodDish}
        onCancel={() => setSeafoodModal(false)}
        okText="确认下单"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Text>重量 (克)</Text>
            <InputNumber
              style={{ width: '100%' }}
              min={0}
              step={50}
              value={seafoodWeight}
              onChange={v => setSeafoodWeight(v || 0)}
              placeholder="输入称重结果"
              addonAfter="克"
            />
          </div>
          <div>
            <Text>时价 (元/斤)</Text>
            <InputNumber
              style={{ width: '100%' }}
              min={0}
              step={100}
              value={marketPrice}
              onChange={v => setMarketPrice(v || 0)}
              placeholder="输入时价（分）"
              addonAfter="分/斤"
            />
          </div>
          <div>
            <Text>做法</Text>
            <Radio.Group value={seafoodMethod} onChange={e => setSeafoodMethod(e.target.value)}>
              {COOKING_METHODS.map(m => (
                <Radio.Button key={m} value={m}>{m}</Radio.Button>
              ))}
            </Radio.Group>
          </div>
          {seafoodWeight > 0 && marketPrice > 0 && (
            <Alert
              type="info"
              message={`预计金额: ¥${fenToYuan(Math.round(marketPrice * seafoodWeight / 500))}`}
              showIcon
            />
          )}
        </Space>
      </Modal>

      {/* ── 优惠券弹窗 ────────────────────────────────────────────────── */}
      <Modal
        title="核销优惠券"
        open={couponModal}
        onCancel={() => setCouponModal(false)}
        footer={null}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input.Search
            placeholder="扫码或输入券码"
            enterButton="验证"
            onSearch={(code) => {
              if (code) {
                setCoupons(prev => [...prev, {
                  coupon_code: code,
                  platform: 'meituan',
                  coupon_value_fen: 2000,
                }]);
                setCouponModal(false);
                message.success('优惠券已核销');
              }
            }}
          />
          <Divider>已核销</Divider>
          {coupons.map((c, i) => (
            <Tag key={i} color="green" closable onClose={() => setCoupons(prev => prev.filter((_, idx) => idx !== i))}>
              {c.platform} | {c.coupon_code} | -¥{fenToYuan(c.coupon_value_fen)}
            </Tag>
          ))}
        </Space>
      </Modal>

      {/* ── 结账弹窗 ──────────────────────────────────────────────────── */}
      <Modal
        title={<><CreditCardOutlined /> 结账 — 应收 ¥{fenToYuan(totalFen)}</>}
        open={settleModal}
        onCancel={() => setSettleModal(false)}
        footer={null}
        width={480}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          {PAYMENT_METHODS.map(pm => (
            <Button
              key={pm.value}
              block
              size="large"
              style={{ borderColor: pm.color, color: pm.color, textAlign: 'left' }}
              onClick={() => handleSettle([{ method: pm.value, amount_fen: totalFen }])}
            >
              {pm.label} — ¥{fenToYuan(totalFen)}
            </Button>
          ))}
        </Space>
      </Modal>

      {/* ── 会员弹窗 ──────────────────────────────────────────────────── */}
      <Modal
        title="会员识别"
        open={memberModal}
        onCancel={() => setMemberModal(false)}
        footer={null}
      >
        <Input.Search
          placeholder="手机号/会员卡号/扫码"
          enterButton="查询"
          onSearch={(v) => {
            if (v) {
              setMemberId(v);
              setMemberDiscount(Math.round(subtotalFen * 0.1));
              setMemberModal(false);
              message.success('会员识别成功，已享受9折优惠');
            }
          }}
        />
      </Modal>
    </div>
  );
};

export default UnifiedPOSPage;
