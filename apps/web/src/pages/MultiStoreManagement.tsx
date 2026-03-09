import React, { useEffect, useState, useCallback } from 'react';
import {
  Card,
  Col,
  Row,
  Table,
  Statistic,
  Spin,
  Select,
  Tag,
  Space,
  Empty,
  Form,
  Input,
  InputNumber,
  Button,
  Modal,
  message,
} from 'antd';
import {
  ShopOutlined,
  RiseOutlined,
  FallOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import {
  inventoryDataService,
  type InventoryItem,
  type TransferRequestRecord,
} from '../services/inventoryData';
import { handleApiError } from '../utils/message';

interface StoreItem {
  id: string;
  name: string;
  region: string;
}

interface ComparisonMetrics {
  revenue: number;
  orders: number;
  customers: number;
  avg_order_value: number;
}

interface ComparisonStore {
  id: string;
  name: string;
  metrics: ComparisonMetrics;
}

interface ComparisonResponse {
  stores: ComparisonStore[];
}

interface RegionalSummaryItem {
  region: string;
  total_revenue: number;
  store_count: number;
  total_orders: number;
  total_customers: number;
}

interface PerformanceRankingItem {
  rank: number;
  store_id: string;
  store_name: string;
  region: string;
  value: number;
  growth_rate: number;
}

type TransferActionType = 'approve' | 'reject';

const MultiStoreManagement: React.FC = () => {
  const [transferForm] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [stores, setStores] = useState<StoreItem[]>([]);
  const [selectedStores, setSelectedStores] = useState<string[]>([]);
  const [comparisonData, setComparisonData] = useState<ComparisonResponse | null>(null);
  const [regionalSummary, setRegionalSummary] = useState<RegionalSummaryItem[]>([]);
  const [performanceRanking, setPerformanceRanking] = useState<PerformanceRankingItem[]>([]);
  const [sourceInventoryItems, setSourceInventoryItems] = useState<InventoryItem[]>([]);
  const [targetInventoryItems, setTargetInventoryItems] = useState<InventoryItem[]>([]);
  const [transferRequests, setTransferRequests] = useState<TransferRequestRecord[]>([]);
  const [transferSubmitting, setTransferSubmitting] = useState(false);
  const [transferActionLoadingId, setTransferActionLoadingId] = useState<string | null>(null);
  const [transferFilterStoreId, setTransferFilterStoreId] = useState<string | undefined>(undefined);
  const [transferFilterStatus, setTransferFilterStatus] = useState<import('../services/inventoryData').TransferRequestQueryStatus | undefined>(undefined);
  const [transferActionModalVisible, setTransferActionModalVisible] = useState(false);
  const [pendingActionDecisionId, setPendingActionDecisionId] = useState<string | null>(null);
  const [pendingActionType, setPendingActionType] = useState<TransferActionType>('approve');
  const [transferFeedbackInput, setTransferFeedbackInput] = useState('');

  const loadComparisonData = useCallback(async (storeIds: string[]) => {
    if (storeIds.length < 2) {
      setComparisonData(null);
      return;
    }

    try {
      const response = await apiClient.post('/api/v1/multi-store/compare', {
        store_ids: storeIds,
        start_date: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        end_date: new Date().toISOString().split('T')[0],
      }) as ComparisonResponse;
      setComparisonData(response);
    } catch (err: unknown) {
      handleApiError(err, '加载对比数据失败');
    }
  }, []);

  const loadStores = useCallback(async () => {
    try {
      const response = await apiClient.get('/api/v1/multi-store/stores') as { stores?: StoreItem[] };
      const storeList = response.stores || [];
      setStores(storeList);

      if (storeList.length >= 2) {
        const defaults = [storeList[0].id, storeList[1].id];
        setSelectedStores(defaults);
        await loadComparisonData(defaults);
        transferForm.setFieldsValue({
          source_store_id: storeList[0].id,
          target_store_id: storeList[1].id,
        });
      }
    } catch (err: unknown) {
      handleApiError(err, '加载门店列表失败');
    }
  }, [loadComparisonData, transferForm]);

  const loadStoreInventory = useCallback(async (storeId: string, setter: (items: InventoryItem[]) => void) => {
    if (!storeId) {
      setter([]);
      return;
    }
    try {
      const response = await inventoryDataService.getAll(storeId);
      setter(response);
    } catch (err: unknown) {
      setter([]);
      handleApiError(err, `加载门店 ${storeId} 库存失败`);
    }
  }, []);

  const loadTransferRequests = useCallback(async () => {
    try {
      const response = await inventoryDataService.listTransferRequests({
        storeId: transferFilterStoreId,
        status: transferFilterStatus,
        limit: 30,
      });
      setTransferRequests(response.items || []);
    } catch (err: unknown) {
      handleApiError(err, '加载调货申请失败');
    }
  }, [transferFilterStatus, transferFilterStoreId]);

  const handleCreateTransferRequest = useCallback(async (values: {
    source_store_id: string;
    target_store_id: string;
    source_item_id: string;
    target_item_id?: string;
    quantity: number;
    reason?: string;
    }) => {
    if (values.source_store_id === values.target_store_id) {
      message.warning('目标门店不能与来源门店相同');
      return;
    }
    try {
      setTransferSubmitting(true);
      await inventoryDataService.createTransferRequest(values.source_store_id, {
        source_item_id: values.source_item_id,
        target_store_id: values.target_store_id,
        target_item_id: values.target_item_id || undefined,
        quantity: values.quantity,
        reason: values.reason,
      });
      message.success('调货申请已提交，等待审批');
      await loadTransferRequests();
    } catch (err: unknown) {
      handleApiError(err, '提交调货申请失败');
    } finally {
      setTransferSubmitting(false);
    }
  }, [loadTransferRequests]);

  const handleApproveTransfer = useCallback(async (decisionId: string, managerFeedback?: string) => {
    try {
      setTransferActionLoadingId(decisionId);
      await inventoryDataService.approveTransferRequest(decisionId, managerFeedback || '同意调货');
      message.success('已批准并执行调货');
      await loadTransferRequests();
    } catch (err: unknown) {
      handleApiError(err, '批准调货失败');
    } finally {
      setTransferActionLoadingId(null);
    }
  }, [loadTransferRequests]);

  const handleRejectTransfer = useCallback(async (decisionId: string, managerFeedback: string) => {
    try {
      setTransferActionLoadingId(decisionId);
      await inventoryDataService.rejectTransferRequest(decisionId, managerFeedback);
      message.success('已驳回调货申请');
      await loadTransferRequests();
    } catch (err: unknown) {
      handleApiError(err, '驳回调货失败');
    } finally {
      setTransferActionLoadingId(null);
    }
  }, [loadTransferRequests]);

  const openTransferActionModal = useCallback((decisionId: string, action: TransferActionType) => {
    setPendingActionDecisionId(decisionId);
    setPendingActionType(action);
    setTransferFeedbackInput(action === 'approve' ? '同意调货' : '');
    setTransferActionModalVisible(true);
  }, []);

  const closeTransferActionModal = useCallback(() => {
    setTransferActionModalVisible(false);
    setPendingActionDecisionId(null);
    setTransferFeedbackInput('');
  }, []);

  const confirmTransferAction = useCallback(async () => {
    if (!pendingActionDecisionId) return;

    const feedback = transferFeedbackInput.trim();
    if (pendingActionType === 'reject' && !feedback) {
      message.warning('驳回时请填写审批意见');
      return;
    }

    if (pendingActionType === 'approve') {
      await handleApproveTransfer(pendingActionDecisionId, feedback);
    } else {
      await handleRejectTransfer(pendingActionDecisionId, feedback);
    }
    closeTransferActionModal();
  }, [
    closeTransferActionModal,
    handleApproveTransfer,
    handleRejectTransfer,
    pendingActionDecisionId,
    pendingActionType,
    transferFeedbackInput,
  ]);

  const loadRegionalSummary = useCallback(async () => {
    try {
      const response = await apiClient.get('/api/v1/multi-store/regional-summary') as { regions?: RegionalSummaryItem[] };
      setRegionalSummary(response.regions || []);
    } catch (err: unknown) {
      handleApiError(err, '加载区域汇总失败');
    }
  }, []);

  const loadPerformanceRanking = useCallback(async () => {
    try {
      const response = await apiClient.get('/api/v1/multi-store/performance-ranking?metric=revenue&limit=10') as {
        ranking?: PerformanceRankingItem[];
      };
      setPerformanceRanking(response.ranking || []);
    } catch (err: unknown) {
      handleApiError(err, '加载绩效排名失败');
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        loadStores(),
        loadRegionalSummary(),
        loadPerformanceRanking(),
      ]);
      setLoading(false);
    };

    loadData();
  }, [loadStores, loadRegionalSummary, loadPerformanceRanking]);

  useEffect(() => {
    loadTransferRequests();
  }, [loadTransferRequests]);

  const sourceStoreId = Form.useWatch('source_store_id', transferForm);
  const targetStoreId = Form.useWatch('target_store_id', transferForm);

  useEffect(() => {
    if (sourceStoreId) {
      loadStoreInventory(sourceStoreId, setSourceInventoryItems);
    } else {
      setSourceInventoryItems([]);
    }
  }, [sourceStoreId, loadStoreInventory]);

  useEffect(() => {
    if (targetStoreId) {
      loadStoreInventory(targetStoreId, setTargetInventoryItems);
    } else {
      setTargetInventoryItems([]);
    }
  }, [targetStoreId, loadStoreInventory]);

  useEffect(() => {
    if (!sourceStoreId || !targetStoreId) return;
    if (sourceStoreId !== targetStoreId) return;
    transferForm.setFieldValue('target_store_id', undefined);
    setTargetInventoryItems([]);
    message.warning('目标门店不能与来源门店相同，请重新选择');
  }, [sourceStoreId, targetStoreId, transferForm]);

  const handleStoreSelectionChange = async (values: string[]) => {
    setSelectedStores(values);
    await loadComparisonData(values);
  };

  const comparisonChartOption = {
    title: { text: '门店对比分析', left: 'center' },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    legend: {
      data: comparisonData?.stores?.map((s) => s.name) || [],
      bottom: 10,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: ['营收', '订单数', '客流量', '客单价'],
    },
    yAxis: { type: 'value' },
    series: comparisonData?.stores?.map((store) => ({
      name: store.name,
      type: 'bar',
      data: [
        store.metrics.revenue / 100,
        store.metrics.orders,
        store.metrics.customers,
        store.metrics.avg_order_value / 100,
      ],
    })) || [],
  };

  const regionalChartOption = {
    title: {
      text: '区域营收分布',
      left: 'center',
    },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: ¥{c} ({d}%)',
    },
    legend: {
      orient: 'vertical',
      left: 'left',
    },
    series: [
      {
        name: '区域营收',
        type: 'pie',
        radius: '50%',
        data: regionalSummary.map((region) => ({
          value: region.total_revenue / 100,
          name: region.region,
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
  };

  const rankingColumns = [
    {
      title: '排名',
      dataIndex: 'rank',
      key: 'rank',
      width: 80,
      render: (rank: number) => {
        if (rank === 1) return <Tag color="gold">🥇 {rank}</Tag>;
        if (rank === 2) return <Tag color="silver">🥈 {rank}</Tag>;
        if (rank === 3) return <Tag color="bronze">🥉 {rank}</Tag>;
        return <Tag>{rank}</Tag>;
      },
    },
    {
      title: '门店名称',
      dataIndex: 'store_name',
      key: 'store_name',
    },
    {
      title: '区域',
      dataIndex: 'region',
      key: 'region',
    },
    {
      title: '营收（元）',
      dataIndex: 'value',
      key: 'value',
      render: (value: number) => `¥${(value / 100).toFixed(2)}`,
    },
    {
      title: '环比',
      dataIndex: 'growth_rate',
      key: 'growth_rate',
      render: (rate: number) => {
        const isPositive = rate >= 0;
        return (
          <Tag color={isPositive ? 'green' : 'red'} icon={isPositive ? <RiseOutlined /> : <FallOutlined />}>
            {isPositive ? '+' : ''}{rate.toFixed(1)}%
          </Tag>
        );
      },
    },
  ];

  const transferStatusTag = (status: string) => {
    if (status === 'pending') return <Tag color="processing">待审批</Tag>;
    if (status === 'executed') return <Tag color="success">已执行</Tag>;
    if (status === 'rejected') return <Tag color="error">已驳回</Tag>;
    return <Tag>{status}</Tag>;
  };

  const transferColumns = [
    {
      title: '申请单',
      dataIndex: 'decision_id',
      key: 'decision_id',
      width: 220,
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => transferStatusTag(status),
    },
    {
      title: '调货项',
      dataIndex: 'item_name',
      key: 'item_name',
      render: (_: unknown, row: TransferRequestRecord) => {
        if (!row.item_name || row.quantity === null) return '-';
        return `${row.item_name} ${row.quantity}${row.unit || ''}`;
      },
    },
    {
      title: '来源门店',
      dataIndex: 'source_store_id',
      key: 'source_store_id',
      render: (value: string | null) => value || '-',
    },
    {
      title: '目标门店',
      dataIndex: 'target_store_id',
      key: 'target_store_id',
      render: (value: string | null) => value || '-',
    },
    {
      title: '备注',
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true,
    },
    {
      title: '审批意见',
      dataIndex: 'manager_feedback',
      key: 'manager_feedback',
      ellipsis: true,
      render: (feedback?: string) => feedback || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_: unknown, row: TransferRequestRecord) => {
        const disabled = row.status !== 'pending';
        return (
          <Space>
            <Button
              type="link"
              size="small"
              loading={transferActionLoadingId === row.decision_id}
              disabled={disabled}
              onClick={() => openTransferActionModal(row.decision_id, 'approve')}
            >
              批准
            </Button>
            <Button
              type="link"
              size="small"
              danger
              loading={transferActionLoadingId === row.decision_id}
              disabled={disabled}
              onClick={() => openTransferActionModal(row.decision_id, 'reject')}
            >
              驳回
            </Button>
          </Space>
        );
      },
    },
  ];

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', background: '#f0f2f5', minHeight: '100vh' }}>
      <h1 style={{ marginBottom: '24px' }}>
        <ShopOutlined /> 多门店管理
      </h1>

      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        {regionalSummary.map((region) => (
          <Col xs={24} sm={12} md={6} key={region.region}>
            <Card>
              <Statistic
                title={region.region}
                value={region.total_revenue / 100}
                precision={2}
                prefix="¥"
                suffix={`/ ${region.store_count}店`}
              />
              <div style={{ marginTop: '8px', fontSize: '12px', color: '#666' }}>
                订单: {region.total_orders} | 客流: {region.total_customers}
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Card title="门店对比分析" style={{ marginBottom: '24px' }}>
        <Space style={{ marginBottom: '16px' }}>
          <span>选择门店:</span>
          <Select
            mode="multiple"
            style={{ width: 400 }}
            placeholder="请选择要对比的门店"
            value={selectedStores}
            onChange={handleStoreSelectionChange}
            maxTagCount={2}
            options={stores.map((store) => ({
              label: `${store.name} (${store.region})`,
              value: store.id,
            }))}
          />
        </Space>
        {selectedStores.length < 2 ? (
          <Empty description="请至少选择两个门店进行对比" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : comparisonData ? (
          <ReactECharts option={comparisonChartOption} style={{ height: '400px' }} />
        ) : (
          <Empty description="暂无对比数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="区域营收分布">
            <ReactECharts option={regionalChartOption} style={{ height: '400px' }} />
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="门店绩效排名（按营收）">
            <Table
              columns={rankingColumns}
              dataSource={performanceRanking}
              rowKey="store_id"
              pagination={{ pageSize: 10, showSizeChanger: false }}
              size="small"
            />
          </Card>
        </Col>
      </Row>

      <Card title="跨店调货审批" style={{ marginTop: '24px' }}>
        <Space style={{ marginBottom: '12px', flexWrap: 'wrap' }}>
          <span>列表筛选:</span>
          <Select
            allowClear
            style={{ width: 180 }}
            placeholder="按门店筛选"
            value={transferFilterStoreId}
            onChange={(value) => setTransferFilterStoreId(value)}
            options={stores.map((store) => ({ label: `${store.name} (${store.region})`, value: store.id }))}
          />
          <Select
            allowClear
            style={{ width: 160 }}
            placeholder="按状态筛选"
            value={transferFilterStatus}
            onChange={(value) => setTransferFilterStatus(value)}
            options={[
              { label: '待审批', value: 'pending' },
              { label: '已执行', value: 'executed' },
              { label: '已驳回', value: 'rejected' },
            ]}
          />
          <Button onClick={loadTransferRequests}>刷新列表</Button>
        </Space>

        <Form
          form={transferForm}
          layout="inline"
          onFinish={handleCreateTransferRequest}
          style={{ marginBottom: '16px', rowGap: 12 }}
        >
          <Form.Item
            name="source_store_id"
            rules={[{ required: true, message: '请选择来源门店' }]}
          >
            <Select
              style={{ width: 180 }}
              placeholder="来源门店"
              options={stores.map((store) => ({ label: `${store.name} (${store.region})`, value: store.id }))}
            />
          </Form.Item>
          <Form.Item
            name="target_store_id"
            rules={[
              { required: true, message: '请选择目标门店' },
              () => ({
                validator(_, value) {
                  if (!value || value !== sourceStoreId) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('目标门店不能与来源门店相同'));
                },
              }),
            ]}
          >
            <Select
              style={{ width: 180 }}
              placeholder="目标门店"
              options={stores
                .filter((store) => store.id !== sourceStoreId)
                .map((store) => ({ label: `${store.name} (${store.region})`, value: store.id }))}
            />
          </Form.Item>
          <Form.Item
            name="source_item_id"
            rules={[{ required: true, message: '请选择来源库存项' }]}
          >
            <Select
              showSearch
              style={{ width: 220 }}
              placeholder="来源库存项"
              options={sourceInventoryItems.map((item) => ({
                label: `${item.name}（可用 ${item.current_quantity}${item.unit || ''}）`,
                value: item.id,
              }))}
            />
          </Form.Item>
          <Form.Item name="target_item_id">
            <Select
              allowClear
              showSearch
              style={{ width: 220 }}
              placeholder="目标库存项（可选）"
              options={targetInventoryItems.map((item) => ({
                label: `${item.name}（现有 ${item.current_quantity}${item.unit || ''}）`,
                value: item.id,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="quantity"
            rules={[{ required: true, message: '请输入调货数量' }]}
          >
            <InputNumber min={0.01} precision={2} placeholder="数量" />
          </Form.Item>
          <Form.Item name="reason">
            <Input style={{ width: 220 }} placeholder="调货原因（可选）" maxLength={120} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={transferSubmitting}>
              提交申请
            </Button>
          </Form.Item>
        </Form>

        <Table
          columns={transferColumns}
          dataSource={transferRequests}
          rowKey="decision_id"
          pagination={{ pageSize: 8, showSizeChanger: false }}
          size="small"
          locale={{ emptyText: '暂无调货申请' }}
        />

        <Modal
          open={transferActionModalVisible}
          title={pendingActionType === 'approve' ? '批准调货申请' : '驳回调货申请'}
          okText={pendingActionType === 'approve' ? '确认批准' : '确认驳回'}
          cancelText="取消"
          onCancel={closeTransferActionModal}
          onOk={confirmTransferAction}
          confirmLoading={!!transferActionLoadingId}
          destroyOnClose
        >
          <Input.TextArea
            rows={4}
            maxLength={200}
            value={transferFeedbackInput}
            placeholder={pendingActionType === 'approve' ? '可填写审批意见（选填）' : '请填写驳回原因（必填）'}
            onChange={(e) => setTransferFeedbackInput(e.target.value)}
          />
        </Modal>
      </Card>
    </div>
  );
};

export default MultiStoreManagement;
