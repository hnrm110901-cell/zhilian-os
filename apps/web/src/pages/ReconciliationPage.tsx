import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Statistic, Row, Col, DatePicker, Select, Descriptions, Modal } from 'antd';
import { CheckOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const statusColor: Record<string, string> = { pending: 'orange', confirmed: 'green', discrepancy: 'red' };
const statusLabel: Record<string, string> = { pending: '待确认', confirmed: '已确认', discrepancy: '有差异' };

const ReconciliationPage: React.FC = () => {
  const [records, setRecords] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [performing, setPerforming] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [currentRecord, setCurrentRecord] = useState<any>(null);
  const [selectedDate, setSelectedDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [storeId, setStoreId] = useState('STORE001');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, sumRes] = await Promise.allSettled([
        apiClient.get('/reconciliation/records'),
        apiClient.get('/reconciliation/summary'),
      ]);
      if (recRes.status === 'fulfilled') setRecords(recRes.value.data?.records || recRes.value.data || []);
      if (sumRes.status === 'fulfilled') setSummary(sumRes.value.data);
    } catch (err: any) {
      handleApiError(err, '加载对账数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const performReconciliation = async () => {
    setPerforming(true);
    try {
      await apiClient.post('/reconciliation/perform', { store_id: storeId, reconciliation_date: selectedDate });
      showSuccess('对账执行成功');
      loadData();
    } catch (err: any) {
      handleApiError(err, '对账执行失败');
    } finally {
      setPerforming(false);
    }
  };

  const confirmRecord = async (record: any) => {
    try {
      await apiClient.put(`/reconciliation/records/${record.record_id || record.id}/confirm`);
      showSuccess('已确认');
      loadData();
    } catch (err: any) {
      handleApiError(err, '确认失败');
    }
  };

  const columns: ColumnsType<any> = [
    { title: '对账日期', dataIndex: 'reconciliation_date', key: 'date' },
    { title: '门店', dataIndex: 'store_id', key: 'store' },
    { title: '系统金额', dataIndex: 'system_amount', key: 'sys', render: (v: number) => `¥${(v || 0).toFixed(2)}` },
    { title: '实际金额', dataIndex: 'actual_amount', key: 'actual', render: (v: number) => `¥${(v || 0).toFixed(2)}` },
    { title: '差异', dataIndex: 'difference', key: 'diff', render: (v: number) => <span style={{ color: v !== 0 ? 'red' : 'green' }}>{v > 0 ? '+' : ''}{(v || 0).toFixed(2)}</span> },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => <Tag color={statusColor[v] || 'default'}>{statusLabel[v] || v}</Tag>,
    },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" onClick={() => { setCurrentRecord(record); setDetailVisible(true); }}>详情</Button>
          {record.status === 'pending' && (
            <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => confirmRecord(record)}>确认</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="总对账次数" value={summary?.total_count || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="有差异" value={summary?.discrepancy_count || 0} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="总差异金额" prefix="¥" value={(summary?.total_difference || 0).toFixed(2)} /></Card></Col>
        <Col span={6}><Card><Statistic title="对账率" suffix="%" value={summary?.reconciliation_rate || 0} /></Card></Col>
      </Row>

      <Card
        title="对账管理"
        extra={
          <Space>
            <Select value={storeId} onChange={setStoreId} style={{ width: 120 }}>
              <Option value="STORE001">门店001</Option>
              <Option value="STORE002">门店002</Option>
            </Select>
            <DatePicker value={dayjs(selectedDate)} onChange={d => d && setSelectedDate(d.format('YYYY-MM-DD'))} />
            <Button type="primary" icon={<ReloadOutlined />} loading={performing} onClick={performReconciliation}>执行对账</Button>
          </Space>
        }
      >
        <Table columns={columns} dataSource={records} rowKey={(r, i) => r.record_id || r.id || String(i)} loading={loading} />
      </Card>

      <Modal title="对账详情" open={detailVisible} onCancel={() => setDetailVisible(false)} footer={null} width={600}>
        {currentRecord && (
          <Descriptions bordered column={2}>
            <Descriptions.Item label="对账日期">{currentRecord.reconciliation_date}</Descriptions.Item>
            <Descriptions.Item label="门店">{currentRecord.store_id}</Descriptions.Item>
            <Descriptions.Item label="系统金额">¥{(currentRecord.system_amount || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="实际金额">¥{(currentRecord.actual_amount || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="差异金额">¥{(currentRecord.difference || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={statusColor[currentRecord.status]}>{statusLabel[currentRecord.status]}</Tag></Descriptions.Item>
            <Descriptions.Item label="备注" span={2}>{currentRecord.notes || '-'}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default ReconciliationPage;
