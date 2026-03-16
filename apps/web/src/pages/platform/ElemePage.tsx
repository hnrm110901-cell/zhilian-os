/**
 * 饿了么集成管理页 — /platform/eleme
 *
 * 四个 Tab：订单管理、菜单同步、门店状态、配送追踪
 * 后端 API: /api/v1/eleme/*
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Tabs, Table, Button, Space, Badge, Card, Statistic, Row, Col,
  Select, Input, Tag, Modal, InputNumber, message,
  Descriptions, Spin, Empty, Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  SyncOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ShopOutlined, SearchOutlined, CarOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { apiClient } from '../../services/api';
import styles from './ElemePage.module.css';

const { Text, Title } = Typography;

// ── 类型 ─────────────────────────────────────────────────────────

interface ElemeOrder {
  id: string;
  store_id: string;
  status: string;
  total_amount: number;
  discount_amount: number;
  final_amount: number;
  order_time: string | null;
  notes: string | null;
  items_count: number;
  metadata: Record<string, any> | null;
}

interface OrderListResponse {
  total: number;
  page: number;
  page_size: number;
  orders: ElemeOrder[];
}

interface ElemeFood {
  food_id: string;
  food_name?: string;
  name?: string;
  price?: number;
  stock?: number;
  status?: string;
  is_on_sale?: boolean;
  category_name?: string;
}

interface MenuResponse {
  success: boolean;
  foods: ElemeFood[];
  total: number;
}

interface ShopInfo {
  shop_id?: string;
  shop_name?: string;
  name?: string;
  address?: string;
  phone?: string;
  status?: number;
  business_status?: number;
  open_time?: string;
  close_time?: string;
}

interface DeliveryInfo {
  order_id?: string;
  status?: string;
  rider_name?: string;
  rider_phone?: string;
  estimated_time?: string;
  distance?: number;
}

// ── 工具函数 ─────────────────────────────────────────────────────

function formatYuan(fen: number): string {
  return `\u00A5${(fen / 100).toFixed(2)}`;
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待确认', color: 'warning' },
  confirmed: { label: '已接单', color: 'processing' },
  preparing: { label: '制作中', color: 'processing' },
  delivering: { label: '配送中', color: 'blue' },
  completed: { label: '已完成', color: 'success' },
  cancelled: { label: '已取消', color: 'error' },
};

const DELIVERY_STATUS_MAP: Record<string, { label: string; color: string }> = {
  waiting: { label: '等待骑手', color: 'default' },
  accepted: { label: '骑手已接单', color: 'processing' },
  arrived: { label: '骑手已到店', color: 'blue' },
  delivering: { label: '配送中', color: 'processing' },
  completed: { label: '已送达', color: 'success' },
};

// ── 主组件 ────────────────────────────────────────────────────────

const ElemePage: React.FC = () => {
  const brandId = 'default';
  const [activeTab, setActiveTab] = useState('orders');

  // ── 订单状态 ─────────────────────────────
  const [orders, setOrders] = useState<ElemeOrder[]>([]);
  const [orderTotal, setOrderTotal] = useState(0);
  const [orderPage, setOrderPage] = useState(1);
  const [orderLoading, setOrderLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [dateFilter, setDateFilter] = useState<string | undefined>(undefined);
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null);

  // 订单统计
  const [orderStats, setOrderStats] = useState({
    todayCount: 0,
    todayRevenue: 0,
    pendingCount: 0,
  });

  // ── 菜单状态 ─────────────────────────────
  const [foods, setFoods] = useState<ElemeFood[]>([]);
  const [menuLoading, setMenuLoading] = useState(false);
  const [stockModalVisible, setStockModalVisible] = useState(false);
  const [stockFoodId, setStockFoodId] = useState('');
  const [stockValue, setStockValue] = useState(0);

  // ── 门店状态 ─────────────────────────────
  const [shopInfo, setShopInfo] = useState<ShopInfo | null>(null);
  const [shopLoading, setShopLoading] = useState(false);
  const [togglingShop, setTogglingShop] = useState(false);

  // ── 配送状态 ─────────────────────────────
  const [deliveryOrderId, setDeliveryOrderId] = useState('');
  const [deliveryInfo, setDeliveryInfo] = useState<DeliveryInfo | null>(null);
  const [deliveryLoading, setDeliveryLoading] = useState(false);

  // ── 订单操作 ─────────────────────────────

  const fetchOrders = useCallback(async () => {
    setOrderLoading(true);
    try {
      const params: Record<string, any> = {
        brand_id: brandId,
        page: orderPage,
        page_size: 20,
      };
      if (statusFilter) params.status = statusFilter;
      if (dateFilter) params.date = dateFilter;

      const resp = await apiClient.get<OrderListResponse>(
        '/api/v1/eleme/orders',
        { params },
      );
      setOrders(resp.orders || []);
      setOrderTotal(resp.total || 0);

      // 计算统计
      const allOrders = resp.orders || [];
      const pending = allOrders.filter((o) => o.status === 'pending').length;
      const revenue = allOrders.reduce((sum, o) => sum + (o.final_amount || 0), 0);
      setOrderStats({
        todayCount: resp.total || 0,
        todayRevenue: revenue,
        pendingCount: pending,
      });
    } catch {
      message.error('获取订单失败');
    } finally {
      setOrderLoading(false);
    }
  }, [brandId, orderPage, statusFilter, dateFilter]);

  useEffect(() => {
    if (activeTab === 'orders') {
      fetchOrders();
    }
  }, [fetchOrders, activeTab]);

  const handleSyncOrders = async () => {
    setSyncing(true);
    try {
      const result = await apiClient.post<{ synced: number; skipped: number; errors: number }>(
        '/api/v1/eleme/orders/sync',
        { brand_id: brandId },
      );
      message.success(`同步完成: ${result.synced} 新增, ${result.skipped} 跳过`);
      setLastSyncTime(new Date().toLocaleString('zh-CN'));
      await fetchOrders();
    } catch {
      message.error('同步失败');
    } finally {
      setSyncing(false);
    }
  };

  const handleConfirmOrder = async (orderId: string) => {
    try {
      const elemeOrderId = orderId.replace(/^ELEME_/, '');
      await apiClient.post(
        `/api/v1/eleme/orders/${elemeOrderId}/confirm`,
        null,
        { params: { brand_id: brandId } },
      );
      message.success('接单成功');
      await fetchOrders();
    } catch {
      message.error('接单失败');
    }
  };

  const handleCancelOrder = async (orderId: string) => {
    Modal.confirm({
      title: '确认取消订单',
      content: `确定要取消订单 ${orderId} 吗？`,
      okText: '确认取消',
      cancelText: '返回',
      okType: 'danger',
      onOk: async () => {
        try {
          const elemeOrderId = orderId.replace(/^ELEME_/, '');
          await apiClient.post(
            `/api/v1/eleme/orders/${elemeOrderId}/cancel`,
            { reason_code: 1, reason: '商家取消' },
            { params: { brand_id: brandId } },
          );
          message.success('取消成功');
          await fetchOrders();
        } catch {
          message.error('取消失败');
        }
      },
    });
  };

  // ── 菜单操作 ─────────────────────────────

  const fetchMenu = async () => {
    setMenuLoading(true);
    try {
      const resp = await apiClient.get<MenuResponse>(
        '/api/v1/eleme/menu',
        { params: { brand_id: brandId } },
      );
      setFoods(resp.foods || []);
    } catch {
      message.error('获取菜单失败');
    } finally {
      setMenuLoading(false);
    }
  };

  const handleUpdateStock = async () => {
    try {
      await apiClient.post(
        `/api/v1/eleme/menu/${stockFoodId}/stock`,
        { stock: stockValue },
        { params: { brand_id: brandId } },
      );
      message.success('库存更新成功');
      setStockModalVisible(false);
      await fetchMenu();
    } catch {
      message.error('库存更新失败');
    }
  };

  const handleToggleFood = async (foodId: string, onSale: boolean) => {
    try {
      await apiClient.post(
        `/api/v1/eleme/menu/${foodId}/toggle`,
        { on_sale: onSale },
        { params: { brand_id: brandId } },
      );
      message.success(onSale ? '已上架' : '已下架');
      await fetchMenu();
    } catch {
      message.error('操作失败');
    }
  };

  // ── 门店操作 ─────────────────────────────

  const fetchShopInfo = async () => {
    setShopLoading(true);
    try {
      const resp = await apiClient.get<{ success: boolean; shop: ShopInfo }>(
        '/api/v1/eleme/shop',
        { params: { brand_id: brandId } },
      );
      setShopInfo(resp.shop || null);
    } catch {
      message.error('获取门店信息失败');
    } finally {
      setShopLoading(false);
    }
  };

  const handleToggleShopStatus = async (status: number) => {
    setTogglingShop(true);
    try {
      await apiClient.post(
        '/api/v1/eleme/shop/status',
        { status },
        { params: { brand_id: brandId } },
      );
      message.success(status === 1 ? '已开启营业' : '已暂停营业');
      await fetchShopInfo();
    } catch {
      message.error('状态切换失败');
    } finally {
      setTogglingShop(false);
    }
  };

  // ── 配送操作 ─────────────────────────────

  const handleSearchDelivery = async () => {
    if (!deliveryOrderId.trim()) {
      message.warning('请输入订单号');
      return;
    }
    setDeliveryLoading(true);
    try {
      const resp = await apiClient.get<{ success: boolean; delivery: DeliveryInfo }>(
        `/api/v1/eleme/delivery/${deliveryOrderId.trim()}`,
        { params: { brand_id: brandId } },
      );
      setDeliveryInfo(resp.delivery || null);
    } catch {
      message.error('查询配送状态失败');
      setDeliveryInfo(null);
    } finally {
      setDeliveryLoading(false);
    }
  };

  // ── 订单表格列 ─────────────────────────────

  const orderColumns: ColumnsType<ElemeOrder> = [
    {
      title: '订单号',
      dataIndex: 'id',
      key: 'id',
      width: 180,
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
        const info = STATUS_MAP[s] || { label: s, color: 'default' };
        return <Badge status={info.color as any} text={info.label} />;
      },
    },
    {
      title: '金额',
      dataIndex: 'final_amount',
      key: 'final_amount',
      width: 100,
      render: (v: number) => formatYuan(v),
    },
    {
      title: '商品数',
      dataIndex: 'items_count',
      key: 'items_count',
      width: 80,
      align: 'center',
    },
    {
      title: '备注',
      dataIndex: 'notes',
      key: 'notes',
      ellipsis: true,
      render: (n: string | null) => n || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: any, record: ElemeOrder) => (
        <Space size="small">
          {record.status === 'pending' && (
            <>
              <Button
                type="primary"
                size="small"
                icon={<CheckCircleOutlined />}
                onClick={() => handleConfirmOrder(record.id)}
              >
                接单
              </Button>
              <Button
                danger
                size="small"
                icon={<CloseCircleOutlined />}
                onClick={() => handleCancelOrder(record.id)}
              >
                取消
              </Button>
            </>
          )}
          {record.status !== 'pending' && (
            <Tag>{STATUS_MAP[record.status]?.label || record.status}</Tag>
          )}
        </Space>
      ),
    },
  ];

  // ── 菜单表格列 ─────────────────────────────

  const menuColumns: ColumnsType<ElemeFood> = [
    {
      title: '商品名称',
      key: 'name',
      render: (_: any, r: ElemeFood) => r.food_name || r.name || '-',
    },
    {
      title: '分类',
      dataIndex: 'category_name',
      key: 'category_name',
      render: (v: string) => v || '-',
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      width: 100,
      render: (v: number) =>
        v != null ? `\u00A5${(v / 100).toFixed(2)}` : '-',
    },
    {
      title: '库存',
      dataIndex: 'stock',
      key: 'stock',
      width: 80,
      render: (v: number) => (v != null ? v : '-'),
    },
    {
      title: '状态',
      key: 'status',
      width: 80,
      render: (_: any, r: ElemeFood) => {
        const onSale = r.is_on_sale !== false && r.status !== 'sold_out';
        return onSale ? (
          <Tag color="success">在售</Tag>
        ) : (
          <Tag color="error">已下架</Tag>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: any, r: ElemeFood) => {
        const fid = r.food_id || (r as any).id || '';
        const onSale = r.is_on_sale !== false && r.status !== 'sold_out';
        return (
          <Space size="small">
            <Button
              size="small"
              onClick={() => {
                setStockFoodId(fid);
                setStockValue(r.stock ?? 0);
                setStockModalVisible(true);
              }}
            >
              改库存
            </Button>
            <Button
              size="small"
              danger={onSale}
              onClick={() => handleToggleFood(fid, !onSale)}
            >
              {onSale ? '下架' : '上架'}
            </Button>
          </Space>
        );
      },
    },
  ];

  // ── 渲染 ─────────────────────────────────

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            饿了么集成
          </Title>
          <Text type="secondary">管理饿了么外卖平台的订单、菜单、门店与配送</Text>
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
          <Card size="small">
            <Statistic
              title="今日订单"
              value={orderStats.todayCount}
              suffix="单"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="今日营收"
              value={orderStats.todayRevenue / 100}
              precision={2}
              prefix={'\u00A5'}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="待确认"
              value={orderStats.pendingCount}
              valueStyle={
                orderStats.pendingCount > 0
                  ? { color: '#faad14' }
                  : undefined
              }
              suffix="单"
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
            label: '订单管理',
            children: (
              <div>
                <div className={styles.toolbar}>
                  <Space wrap>
                    <Select
                      placeholder="状态筛选"
                      allowClear
                      style={{ width: 120 }}
                      value={statusFilter}
                      onChange={(v) => {
                        setStatusFilter(v);
                        setOrderPage(1);
                      }}
                      options={[
                        { value: 'pending', label: '待确认' },
                        { value: 'confirmed', label: '已接单' },
                        { value: 'delivering', label: '配送中' },
                        { value: 'completed', label: '已完成' },
                        { value: 'cancelled', label: '已取消' },
                      ]}
                    />
                    <Input
                      type="date"
                      style={{ width: 160 }}
                      value={dateFilter}
                      onChange={(e) => {
                        setDateFilter(e.target.value || undefined);
                        setOrderPage(1);
                      }}
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
                  locale={{ emptyText: <Empty description="暂无饿了么订单" /> }}
                />
              </div>
            ),
          },
          {
            key: 'menu',
            label: '菜单同步',
            children: (
              <div>
                <div className={styles.toolbar}>
                  <Text type="secondary">
                    共 {foods.length} 个商品
                  </Text>
                  <Button
                    type="primary"
                    icon={<ReloadOutlined />}
                    loading={menuLoading}
                    onClick={fetchMenu}
                  >
                    加载菜单
                  </Button>
                </div>
                <Table
                  columns={menuColumns}
                  dataSource={foods}
                  rowKey={(r) => r.food_id || (r as any).id || Math.random().toString()}
                  loading={menuLoading}
                  size="middle"
                  pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 个` }}
                  locale={{ emptyText: <Empty description='点击"加载菜单"从饿了么获取' /> }}
                />
              </div>
            ),
          },
          {
            key: 'shop',
            label: '门店状态',
            children: (
              <div>
                <div className={styles.toolbar}>
                  <Text type="secondary">饿了么门店营业信息</Text>
                  <Button
                    icon={<ShopOutlined />}
                    loading={shopLoading}
                    onClick={fetchShopInfo}
                  >
                    刷新门店信息
                  </Button>
                </div>
                {shopLoading ? (
                  <Spin className={styles.spinCenter} />
                ) : shopInfo ? (
                  <Card>
                    <Descriptions
                      title={shopInfo.shop_name || shopInfo.name || '门店信息'}
                      bordered
                      column={2}
                    >
                      <Descriptions.Item label="门店ID">
                        {shopInfo.shop_id || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="营业状态">
                        <Badge
                          status={
                            (shopInfo.status === 1 || shopInfo.business_status === 1)
                              ? 'success'
                              : 'error'
                          }
                          text={
                            (shopInfo.status === 1 || shopInfo.business_status === 1)
                              ? '营业中'
                              : '休息中'
                          }
                        />
                      </Descriptions.Item>
                      <Descriptions.Item label="地址" span={2}>
                        {shopInfo.address || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="电话">
                        {shopInfo.phone || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="营业时间">
                        {shopInfo.open_time && shopInfo.close_time
                          ? `${shopInfo.open_time} - ${shopInfo.close_time}`
                          : '-'}
                      </Descriptions.Item>
                    </Descriptions>
                    <div className={styles.shopActions}>
                      <Space>
                        <Button
                          type="primary"
                          loading={togglingShop}
                          onClick={() => handleToggleShopStatus(1)}
                          disabled={shopInfo.status === 1 || shopInfo.business_status === 1}
                        >
                          开启营业
                        </Button>
                        <Button
                          danger
                          loading={togglingShop}
                          onClick={() => handleToggleShopStatus(0)}
                          disabled={shopInfo.status === 0 || shopInfo.business_status === 0}
                        >
                          暂停营业
                        </Button>
                      </Space>
                    </div>
                  </Card>
                ) : (
                  <Empty description='点击"刷新门店信息"加载' />
                )}
              </div>
            ),
          },
          {
            key: 'delivery',
            label: '配送追踪',
            children: (
              <div>
                <div className={styles.toolbar}>
                  <Space>
                    <Input
                      placeholder="输入饿了么订单号"
                      prefix={<CarOutlined />}
                      value={deliveryOrderId}
                      onChange={(e) => setDeliveryOrderId(e.target.value)}
                      onPressEnter={handleSearchDelivery}
                      style={{ width: 280 }}
                    />
                    <Button
                      type="primary"
                      icon={<SearchOutlined />}
                      loading={deliveryLoading}
                      onClick={handleSearchDelivery}
                    >
                      查询
                    </Button>
                  </Space>
                </div>
                {deliveryLoading ? (
                  <Spin className={styles.spinCenter} />
                ) : deliveryInfo ? (
                  <Card title="配送信息">
                    <Descriptions bordered column={2}>
                      <Descriptions.Item label="订单号">
                        {deliveryInfo.order_id || deliveryOrderId}
                      </Descriptions.Item>
                      <Descriptions.Item label="配送状态">
                        {(() => {
                          const s = deliveryInfo.status || '';
                          const info = DELIVERY_STATUS_MAP[s] || { label: s || '-', color: 'default' };
                          return <Badge status={info.color as any} text={info.label} />;
                        })()}
                      </Descriptions.Item>
                      <Descriptions.Item label="骑手姓名">
                        {deliveryInfo.rider_name || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="骑手电话">
                        {deliveryInfo.rider_phone || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="预计送达">
                        {deliveryInfo.estimated_time || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="距离">
                        {deliveryInfo.distance != null
                          ? `${deliveryInfo.distance}m`
                          : '-'}
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                ) : (
                  <Empty description="输入订单号查询配送状态" />
                )}
              </div>
            ),
          },
        ]}
      />

      {/* 库存修改弹窗 */}
      <Modal
        title="修改库存"
        open={stockModalVisible}
        onOk={handleUpdateStock}
        onCancel={() => setStockModalVisible(false)}
        okText="确认"
        cancelText="取消"
      >
        <div className={styles.stockModal}>
          <Text>商品ID: {stockFoodId}</Text>
          <div className={styles.stockInput}>
            <Text>库存数量:</Text>
            <InputNumber
              min={0}
              value={stockValue}
              onChange={(v) => setStockValue(v ?? 0)}
              style={{ width: '100%' }}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ElemePage;
