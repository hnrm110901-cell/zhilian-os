import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Select, Modal } from 'antd';
import { ReloadOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const agentColor: Record<string, string> = { decision: 'purple', inventory: 'blue', schedule: 'green', order: 'orange', kpi: 'red' };

const AgentMemoryPage: React.FC = () => {
  const [memories, setMemories] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [agentFilter, setAgentFilter] = useState('');
  const [lastN, setLastN] = useState(20);
  const [clearing, setClearing] = useState(false);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadMemories = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { last_n: lastN };
      if (agentFilter) params.agent = agentFilter;
      const res = await apiClient.get(`/agent-memory/${selectedStore}`, { params });
      setMemories(res.data?.memories || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载智能体记忆失败');
    } finally {
      setLoading(false);
    }
  }, [selectedStore, agentFilter, lastN]);

  useEffect(() => { loadStores(); loadMemories(); }, [loadStores, loadMemories]);

  const clearMemory = () => {
    Modal.confirm({
      title: `确认清除门店 ${selectedStore} 的智能体记忆？`,
      content: '此操作仅用于测试/调试，清除后无法恢复。',
      okType: 'danger',
      onOk: async () => {
        setClearing(true);
        try {
          await apiClient.delete(`/agent-memory/${selectedStore}`);
          showSuccess('记忆已清除');
          loadMemories();
        } catch (err: any) {
          handleApiError(err, '清除失败');
        } finally {
          setClearing(false);
        }
      },
    });
  };

  const columns: ColumnsType<any> = [
    { title: '时间', dataIndex: 'timestamp', key: 'timestamp', width: 180, ellipsis: true },
    { title: '智能体', dataIndex: 'agent', key: 'agent', width: 100, render: (v: string) => <Tag color={agentColor[v] || 'default'}>{v}</Tag> },
    { title: '类型', dataIndex: 'type', key: 'type', width: 100 },
    { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true },
    { title: '置信度', dataIndex: 'confidence', key: 'confidence', width: 90, render: (v: number) => v != null ? `${(v * 100).toFixed(0)}%` : '-' },
  ];

  return (
    <div>
      <Card
        title="智能体共享记忆"
        extra={
          <Space>
            <span>门店：</span>
            <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 140 }}>
              {stores.length > 0 ? stores.map((s: any) => (
                <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
              )) : <Option value="STORE001">STORE001</Option>}
            </Select>
            <span>智能体：</span>
            <Select value={agentFilter} onChange={setAgentFilter} style={{ width: 120 }} allowClear placeholder="全部">
              <Option value="decision">决策</Option>
              <Option value="inventory">库存</Option>
              <Option value="schedule">排班</Option>
              <Option value="order">订单</Option>
              <Option value="kpi">KPI</Option>
            </Select>
            <span>条数：</span>
            <Select value={lastN} onChange={setLastN} style={{ width: 80 }}>
              <Option value={20}>20</Option>
              <Option value={50}>50</Option>
              <Option value={100}>100</Option>
            </Select>
            <Button icon={<ReloadOutlined />} onClick={loadMemories}>刷新</Button>
            <Button danger icon={<DeleteOutlined />} loading={clearing} onClick={clearMemory}>清除记忆</Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={memories}
          rowKey={(r, i) => r.id || String(i)}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
        />
      </Card>
    </div>
  );
};

export default AgentMemoryPage;
