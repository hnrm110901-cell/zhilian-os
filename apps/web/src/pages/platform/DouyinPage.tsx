/**
 * 抖音生活服务集成管理页 — /platform/douyin
 *
 * 三个 Tab：团购订单、券核销、结算管理
 * 后端 API: /api/v1/douyin/*
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Tabs, Table, Button, Space, Badge, Card, Statistic, Row, Col,
  Select, Input, Tag, Modal, DatePicker, message,
  Empty, Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  SyncOutlined, CheckCircleOutlined, ScanOutlined,
  SearchOutlined, DollarOutlined,
} from '@ant-design/icons';
import { apiClient } from '../../services/api';
import styles from './DouyinPage.module.css';

const { Text, Title } = Typography;
const { RangePicker } = DatePicker;

// ── 类型 ─────────────────────────────────────────────────────────

interface DouyinOrder {
  id: string;
  external_order_id: string;
  store_id: string;
  status: string;
  total_amount: number;
  discount_amount: number;
  final_amount: number;
  order_time: string | null;
  items_count: number;
}

interface OrderListResponse {
  total: number;
  page: number;
  page_size: number;
  orders: DouyinOrder[];
}

interface DouyinCoupon {
  coupon_id: string;
  coupon_name: string;
  original_price: number;
  selling_price: number;
  stock: number;
  sold_count: number;
  status: string;
  start_time: string;
  end_time: string;
}

interface CouponListResponse {
  coupon_list: DouyinCoupon[];
  total: number;
}

interface Settlement {
  settlement_id: string;
  period: string;
  total_amount: number;
  commission_amount: number;
  settle_amount: number;
  status: string;
  settle_time: string | null;
}

interface SettlementResponse {
  settlement_list: Settlement[];
  total: number;
}

interface DouyinStats {
  order_count: number;
  revenue_fen: number;
  verified_count: number;
}

// ── 工具函数 ─────────────────────────────────────────────────────

function formatYuan(fen: number): string {
  return `\u00A5${(fen / 100).toFixed(2)}`;
}

const ORDER_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待核销', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
  verified: { label: '已核销', color: 'processing' },
  refunded: { label: '已退款', color: 'error' },
  cancelled: { label: '已取消', color: 'default' },
};

const COUPON_STATUS_MAP: Record<string, { label: string; color: string }> = {
  online: { label: '在线', color: 'success' },
  offline: { label: '已下线', color: 'default' },
  soldout: { label: '已售罄', color: 'error' },
};

const SETTLE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  settled: { label: '已结算', color: 'success' },
  pending: { label: '待结算', color: 'warning' },
  processing: { label: '处理中', color: 'processing' },
};

// ── 主组件 ────────────────────────────────────────────────────────

const DouyinPage: React.FC = () => {
  const brandId = 'default';
  const [activeTab, setActiveTab] = useState('orders');

  // ── 统计 ─────────────────────────────
  const [stats, setStats] = useState<DouyinStats>({
    order_count: 0,
    revenue_fen: 0,
    verified_count: 0,
  });

  // ── 订单状态 ─────────────────────────
  const [orders, setOrders] = useState<DouyinOrder[]>([]);
  const [orderTotal, setOrderTotal] = useState(0);
  const [orderPage, setOrderPage] = useState(1);
  const [orderLoading, setOrderLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [orderStatusFilter, setOrderStatusFilter] = useState<string | undefined>(undefined);
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null);

  // ── 团购券状态 ───────────────────────
  const [coupons, setCoupons] = useState<DouyinCoupon[]>([]);
  const [couponTotal, setCouponTotal] = useState(0);
  const [couponPage, setCouponPage] = useState(1);
  const [couponLoading, setCouponLoading] = useState(false);
  const [verifyModalVisible, setVerifyModalVisible] = useState(false);
  const [verifyCode, setVerifyCode] = useState('');
  const [verifyShopId, setVerifyShopId] = useState('');
  const [verifying, setVerifying] = useState(false);

  // ── 结算状态 ─────────────────────────
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [settlementLoading, setSettlementLoading] = useState(false);
  const [settleDateRange, setSettleDateRange] = useState<[string, string] | null>(null);

  // ── 统计加载 ─────────────────────────

  const fetchStats = useCallback(async () => {
    try {
      const result = await apiClient.get<DouyinStats>(
        '/api/v1/douyin/stats',
        { params: { brand_id: brandId } },
      );
      setStats(result);
    } catch {
      // 静默失败，保留默认值
    }
  }, [brandId]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  // ── 订单操作 ─────────────────────────

  const fetchOrders = useCallback(async () => {
    setOrderLoading(true);
    try {
      const params: Record<string, any> = {
        brand_id: brandId,
        page: orderPage,
        page_size: 20,
      };
      if (orderStatusFilter) params.status = orderStatusFilter;

      const resp = await apiClient.get<OrderListResponse>(
        '/api/v1/douyin/orders',
        { params },
      );
      setOrders(resp.orders || []);
      setOrderTotal(resp.total || 0);
    } catch {
      message.error('获取订单失败');
    } finally {
      setOrderLoading(false);
    }
  }, [brandId, orderPage, orderStatusFilter]);

  useEffect(() => {
    if (activeTab === 'orders') {
      fetchOrders();
    }
  }, [fetchOrders, activeTab]);

  const handleSyncOrders = async () => {
    setSyncing(true);
    try {
      const result = await apiClient.post<{ synced: number; skipped: number; errors: number }>(
        '/api/v1/douyin/orders/sync',
        { brand_id: brandId, store_id: 'default' },
      );
      message.success(`同步完成: ${result.synced} 新增, ${result.skipped} 跳过`);
      setLastSyncTime(new Date().toLocaleString('zh-CN'));
      await fetchOrders();
      await fetchStats();
    } catch {
      message.error('同步失败');
    } finally {
      setSyncing(false);
    }
  };

  // ── 团购券操作 ───────────────────────

  const fetchCoupons = useCallback(async () => {
    setCouponLoading(true);
    try {
      const resp = await apiClient.get<CouponListResponse>(
        '/api/v1/douyin/coupons',
        { params: { brand_id: brandId, page: couponPage, page_size: 20 } },
      );
      setCoupons(resp.coupon_list || []);
      setCouponTotal(resp.total || 0);
    } catch {
      message.error('获取团购券失败');
    } finally {
      setCouponLoading(false);
    }
  }, [brandId, couponPage]);

  useEffect(() => {
    if (activeTab === 'coupons') {
      fetchCoupons();
    }
  }, [fetchCoupons, activeTab]);

  const handleVerifyCoupon = async () => {
    if (!verifyCode.trim()) {
      message.warning('请输入券码');
      return;
    }
    if (!verifyShopId.trim()) {
      message.warning('请输入门店ID');
      return;
    }
    setVerifying(true);
    try {
      await apiClient.post<{ success: boolean }>(
        '/api/v1/douyin/coupons/verify',
        {
          brand_id: brandId,
          code: verifyCode.trim(),
          shop_id: verifyShopId.trim(),
        },
      );
      message.success('核销成功');
      setVerifyModalVisible(false);
      setVerifyCode('');
      setVerifyShopId('');
      await fetchStats();
    } catch {
      message.error('核销失败');
    } finally {
      setVerifying(false);
    }
  };

  // ── 结算操作 ─────────────────────────

  const fetchSettlements = async () => {
    if (!settleDateRange) {
      message.warning('请选择日期范围');
      return;
    }
    setSettlementLoading(true);
    try {
      const resp = await apiClient.get<SettlementResponse>(
        '/api/v1/douyin/settlements',
        {
          params: {
            brand_id: brandId,
            start_date: settleDateRange[0],
            end_date: settleDateRange[1],
          },
        },
      );
      setSettlements(resp.settlement_list || []);
    } catch {
      message.error('获取结算数据失败');
    } finally {
      setSettlementLoading(false);
    }
  };

  // ── 订单表格列 ───────────────────────

  const orderColumns: ColumnsType<DouyinOrder> = [
    {
      title: '订单号',
      dataIndex: 'external_order_id',
      key: 'external_order_id',
      width: 200,
      render: (id: string) => <Text copyable={{ text: id }}>{id}</Text>,
    },
    {
      title: '下单时间',
      dataIndex: 'order_time',
      key: 'order_time',
      width: 160,
      render: (t: string | null) =>
        t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => {
        const info = ORDER_STATUS_MAP[s] || { label: s, color: 'default' };
        return <Badge status={info.color as any} text={info.label} />;
      },
    },
    {
      title: '原价',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 100,
      render: (v: number) => formatYuan(v),
    },
    {
      title: '优惠',
      dataIndex: 'discount_amount',
      key: 'discount_amount',
      width: 100,
      render: (v: number) => v > 0 ? `-${formatYuan(v)}` : '-',
    },
    {
      title: '实付',
      dataIndex: 'final_amount',
      key: 'final_amount',
      width: 100,
      render: (v: number) => <Text strong>{formatYuan(v)}</Text>,
    },
    {
      title: '商品数',
      dataIndex: 'items_count',
      key: 'items_count',
      width: 80,
      align: 'center',
    },
  ];

  // ── 团购券表格列 ─────────────────────

  const couponColumns: ColumnsType<DouyinCoupon> = [
    {
      title: '券名称',
      dataIndex: 'coupon_name',
      key: 'coupon_name',
      ellipsis: true,
    },
    {
      title: '原价',
      dataIndex: 'original_price',
      key: 'original_price',
      width: 100,
      render: (v: number) => formatYuan(v),
    },
    {
      title: '售价',
      dataIndex: 'selling_price',
      key: 'selling_price',
      width: 100,
      render: (v: number) => <Text strong>{formatYuan(v)}</Text>,
    },
    {
      title: '库存',
      dataIndex: 'stock',
      key: 'stock',
      width: 80,
      align: 'center',
    },
    {
      title: '已售',
      dataIndex: 'sold_count',
      key: 'sold_count',
      width: 80,
      align: 'center',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (s: string) => {
        const info = COUPON_STATUS_MAP[s] || { label: s, color: 'default' };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: '有效期',
      key: 'validity',
      width: 200,
      render: (_: any, r: DouyinCoupon) => {
        const start = r.start_time ? new Date(r.start_time).toLocaleDateString('zh-CN') : '';
        const end = r.end_time ? new Date(r.end_time).toLocaleDateString('zh-CN') : '';
        return start && end ? `${start} ~ ${end}` : '-';
      },
    },
  ];

  // ── 结算表格列 ───────────────────────

  const settlementColumns: ColumnsType<Settlement> = [
    {
      title: '结算单号',
      dataIndex: 'settlement_id',
      key: 'settlement_id',
      width: 180,
    },
    {
      title: '结算周期',
      dataIndex: 'period',
      key: 'period',
      width: 200,
    },
    {
      title: '订单总额',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 120,
      render: (v: number) => formatYuan(v),
    },
    {
      title: '平台佣金',
      dataIndex: 'commission_amount',
      key: 'commission_amount',
      width: 120,
      render: (v: number) => (
        <span className={styles.amountNegative}>-{formatYuan(v)}</span>
      ),
    },
    {
      title: '结算金额',
      dataIndex: 'settle_amount',
      key: 'settle_amount',
      width: 120,
      render: (v: number) => (
        <span className={styles.amountPositive}>{formatYuan(v)}</span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => {
        const info = SETTLE_STATUS_MAP[s] || { label: s, color: 'default' };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: '结算时间',
      dataIndex: 'settle_time',
      key: 'settle_time',
      width: 160,
      render: (t: string | null) =>
        t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
  ];

  // ── 渲染 ─────────────────────────────

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            抖音生活服务
          </Title>
          <Text type="secondary">管理抖音团购订单、券核销与结算</Text>
        </div>
        <Space>
          <Badge
            status={lastSyncTime ? 'success' : 'default'}
            text={lastSyncTime ? `上次同步: ${lastSyncTime}` : '尚未同步'}
          />
        </Space>
      </div>

      {/* 统计行 */}
      <Row gutter={16} className={styles.statsRow}>
        <Col span={8}>
          <Card size="small" className={styles.statsCard}>
            <Statistic
              title="今日团购订单"
              value={stats.order_count}
              suffix="单"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" className={styles.statsCard}>
            <Statistic
              title="今日营收"
              value={stats.revenue_fen / 100}
              precision={2}
              prefix={'\u00A5'}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" className={styles.statsCard}>
            <Statistic
              title="今日核销"
              value={stats.verified_count}
              prefix={<CheckCircleOutlined />}
              suffix="张"
            />
          </Card>
        </Col>
      </Row>

      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key)}
        items={[
          {
            key: 'orders',
            label: '团购订单',
            children: (
              <div>
                <div className={styles.toolbar}>
                  <Space wrap>
                    <Select
                      placeholder="状态筛选"
                      allowClear
                      style={{ width: 120 }}
                      value={orderStatusFilter}
                      onChange={(v) => {
                        setOrderStatusFilter(v);
                        setOrderPage(1);
                      }}
                      options={[
                        { value: 'pending', label: '待核销' },
                        { value: 'verified', label: '已核销' },
                        { value: 'completed', label: '已完成' },
                        { value: 'refunded', label: '已退款' },
                        { value: 'cancelled', label: '已取消' },
                      ]}
                    />
                  </Space>
                  <Button
                    type="primary"
                    icon={<SyncOutlined spin={syncing} />}
                    loading={syncing}
                    onClick={handleSyncOrders}
                  >
                    同步订单
                  </Button>
                </div>
                <Table
                  columns={orderColumns}
                  dataSource={orders}
                  rowKey="id"
                  loading={orderLoading}
                  size="middle"
                  pagination={{
                    current: orderPage,
                    pageSize: 20,
                    total: orderTotal,
                    showTotal: (t) => `共 ${t} 条`,
                    onChange: (p) => setOrderPage(p),
                  }}
                  locale={{ emptyText: <Empty description="暂无抖音团购订单" /> }}
                />
              </div>
            ),
          },
          {
            key: 'coupons',
            label: '券核销',
            children: (
              <div>
                <div className={styles.toolbar}>
                  <Text type="secondary">
                    共 {couponTotal} 个团购券
                  </Text>
                  <Space>
                    <Button
                      type="primary"
                      icon={<ScanOutlined />}
                      onClick={() => setVerifyModalVisible(true)}
                    >
                      核销团购券
                    </Button>
                  </Space>
                </div>
                <Table
                  columns={couponColumns}
                  dataSource={coupons}
                  rowKey="coupon_id"
                  loading={couponLoading}
                  size="middle"
                  pagination={{
                    current: couponPage,
                    pageSize: 20,
                    total: couponTotal,
                    showTotal: (t) => `共 ${t} 个`,
                    onChange: (p) => setCouponPage(p),
                  }}
                  locale={{ emptyText: <Empty description="暂无团购券数据" /> }}
                />
              </div>
            ),
          },
          {
            key: 'settlements',
            label: '结算管理',
            children: (
              <div>
                <div className={styles.toolbar}>
                  <Space wrap>
                    <RangePicker
                      onChange={(_dates, dateStrings) => {
                        if (dateStrings[0] && dateStrings[1]) {
                          setSettleDateRange([dateStrings[0], dateStrings[1]]);
                        } else {
                          setSettleDateRange(null);
                        }
                      }}
                    />
                  </Space>
                  <Button
                    type="primary"
                    icon={<SearchOutlined />}
                    loading={settlementLoading}
                    onClick={fetchSettlements}
                  >
                    查询结算
                  </Button>
                </div>
                <Table
                  columns={settlementColumns}
                  dataSource={settlements}
                  rowKey="settlement_id"
                  loading={settlementLoading}
                  size="middle"
                  pagination={{
                    pageSize: 20,
                    showTotal: (t) => `共 ${t} 条`,
                  }}
                  locale={{ emptyText: <Empty description="选择日期范围查询结算数据" /> }}
                />
              </div>
            ),
          },
        ]}
      />

      {/* 核销弹窗 */}
      <Modal
        title="核销团购券"
        open={verifyModalVisible}
        onOk={handleVerifyCoupon}
        onCancel={() => {
          setVerifyModalVisible(false);
          setVerifyCode('');
          setVerifyShopId('');
        }}
        okText="确认核销"
        cancelText="取消"
        confirmLoading={verifying}
      >
        <div className={styles.verifyForm}>
          <div className={styles.verifyFormItem}>
            <Text>券码</Text>
            <Input
              placeholder="请扫码或输入券码"
              prefix={<ScanOutlined />}
              value={verifyCode}
              onChange={(e) => setVerifyCode(e.target.value)}
              autoFocus
            />
          </div>
          <div className={styles.verifyFormItem}>
            <Text>门店ID</Text>
            <Input
              placeholder="请输入抖音门店ID"
              prefix={<DollarOutlined />}
              value={verifyShopId}
              onChange={(e) => setVerifyShopId(e.target.value)}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default DouyinPage;
