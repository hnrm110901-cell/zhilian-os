import React, { useState, useCallback } from 'react';
import {
  Card, Col, Row, Input, Select, Button, Tabs, Statistic, Table, Tag,
  Timeline, Descriptions, Space, Avatar, Progress, List, Empty,
} from 'antd';
import {
  SearchOutlined, UserOutlined, ShoppingOutlined,
  CalendarOutlined, CreditCardOutlined, StarOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;

const tierColor: Record<string, string> = {
  VIP: 'gold', '高价值': 'blue', '中价值': 'green', '低价值': 'orange', '流失风险': 'red',
};
const eventIcon: Record<string, React.ReactNode> = {
  order: <ShoppingOutlined style={{ color: '#1890ff' }} />,
  reservation: <CalendarOutlined style={{ color: '#52c41a' }} />,
  pos_transaction: <CreditCardOutlined style={{ color: '#722ed1' }} />,
};
const eventColor: Record<string, string> = {
  order: 'blue', reservation: 'green', pos_transaction: 'purple',
};

const Customer360Page: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [identifierType, setIdentifierType] = useState('phone');
  const [storeId, setStoreId] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);

  const searchCustomers = useCallback(async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await apiClient.get('/api/v1/customer360/search', {
        params: { query: searchQuery, store_id: storeId || undefined, limit: 20 },
      });
      setSearchResults(res.data?.data?.results || []);
    } catch (err: any) { handleApiError(err, '搜索客户失败'); }
    finally { setSearching(false); }
  }, [searchQuery, storeId]);

  const loadProfile = useCallback(async (identifier: string, type: string = identifierType) => {
    setLoading(true);
    setProfile(null);
    try {
      const res = await apiClient.get('/api/v1/customer360/profile', {
        params: { customer_identifier: identifier, identifier_type: type, store_id: storeId || undefined },
      });
      setProfile(res.data?.data || res.data);
    } catch (err: any) { handleApiError(err, '加载客户画像失败'); }
    finally { setLoading(false); }
  }, [identifierType, storeId]);

  const searchColumns: ColumnsType<any> = [
    { title: '姓名', dataIndex: 'name', key: 'name', render: (v: string) => v || '-' },
    { title: '手机号', dataIndex: 'phone', key: 'phone' },
    { title: '订单数', dataIndex: 'order_count', key: 'order_count' },
    { title: '总消费', dataIndex: 'total_spend', key: 'total_spend', render: (v: number) => `¥${v?.toFixed(2)}` },
    { title: '最近到访', dataIndex: 'last_visit', key: 'last_visit', render: (v: string) => v?.slice(0, 10) || '-' },
    {
      title: '操作', key: 'action',
      render: (_: any, r: any) => (
        <Button size="small" type="link" onClick={() => loadProfile(r.phone, 'phone')}>查看画像</Button>
      ),
    },
  ];

  const orderColumns: ColumnsType<any> = [
    { title: '订单号', dataIndex: 'order_number', key: 'order_number', ellipsis: true },
    { title: '类型', dataIndex: 'order_type', key: 'order_type' },
    { title: '金额', dataIndex: 'total', key: 'total', render: (v: number) => `¥${v}` },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag>{v}</Tag> },
    { title: '时间', dataIndex: 'order_time', key: 'order_time', render: (v: string) => v?.slice(0, 16) },
  ];

  const cv = profile?.customer_value || {};
  const stats = profile?.statistics || {};
  const tier = cv.customer_tier;

  const tabItems = profile ? [
    {
      key: 'overview', label: '画像概览',
      children: (
        <Row gutter={16}>
          <Col span={8}>
            <Card size="small" title="基础信息">
              <div style={{ textAlign: 'center', marginBottom: 16 }}>
                <Avatar size={64} icon={<UserOutlined />} style={{ backgroundColor: '#1890ff' }} />
                <div style={{ marginTop: 8, fontWeight: 600, fontSize: 16 }}>
                  {profile.member_info?.name || profile.customer_identifier}
                </div>
                {tier && <Tag color={tierColor[tier] || 'default'} style={{ marginTop: 4 }}>{tier}</Tag>}
              </div>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="标识">{profile.customer_identifier}</Descriptions.Item>
                <Descriptions.Item label="类型">{profile.identifier_type}</Descriptions.Item>
                {profile.member_info?.mobile && <Descriptions.Item label="手机">{profile.member_info.mobile}</Descriptions.Item>}
                {profile.member_info?.level && <Descriptions.Item label="会员等级">Lv.{profile.member_info.level}</Descriptions.Item>}
                {profile.member_info?.points != null && <Descriptions.Item label="积分">{profile.member_info.points}</Descriptions.Item>}
                {profile.member_info?.balance != null && <Descriptions.Item label="余额">¥{(profile.member_info.balance / 100).toFixed(2)}</Descriptions.Item>}
              </Descriptions>
            </Card>
            <Card size="small" title="客户标签" style={{ marginTop: 12 }}>
              <Space wrap>
                {(profile.customer_tags || []).map((t: string) => (
                  <Tag key={t} color="blue">{t}</Tag>
                ))}
                {(!profile.customer_tags?.length) && <span style={{ color: '#999' }}>暂无标签</span>}
              </Space>
            </Card>
          </Col>
          <Col span={16}>
            <Row gutter={12} style={{ marginBottom: 12 }}>
              <Col span={8}><Card size="small"><Statistic title="总消费" value={(cv.total_spent / 100 || cv.total_spent || 0).toFixed(2)} prefix="¥" /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="订单数" value={cv.total_orders ?? stats.total_orders ?? '--'} /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="均单价" value={(cv.avg_order_value / 100 || cv.avg_order_value || 0).toFixed(2)} prefix="¥" /></Card></Col>
              <Col span={8} style={{ marginTop: 12 }}><Card size="small"><Statistic title="月均频次" value={cv.order_frequency_per_month ?? '--'} suffix="次" /></Card></Col>
              <Col span={8} style={{ marginTop: 12 }}><Card size="small"><Statistic title="生命周期" value={cv.customer_lifetime_days ?? '--'} suffix="天" /></Card></Col>
              <Col span={8} style={{ marginTop: 12 }}><Card size="small"><Statistic title="预订次数" value={stats.total_reservations ?? '--'} /></Card></Col>
            </Row>
            <Card size="small" title={`RFM评分 ${cv.rfm_score ?? '--'}`}>
              <Progress
                percent={Math.round(cv.rfm_score || 0)}
                strokeColor={{ '0%': '#ff4d4f', '50%': '#faad14', '100%': '#52c41a' }}
                status="active"
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#999', marginTop: 4 }}>
                <span>流失风险</span><span>低价值</span><span>中价值</span><span>高价值</span><span>VIP</span>
              </div>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'timeline', label: `时间线 (${profile.timeline?.length ?? 0})`,
      children: (
        <div style={{ maxHeight: 500, overflowY: 'auto', padding: '8px 0' }}>
          {profile.timeline?.length ? (
            <Timeline
              items={(profile.timeline || []).map((e: any) => ({
                dot: eventIcon[e.event_type],
                color: eventColor[e.event_type] || 'gray',
                children: (
                  <div>
                    <div style={{ fontWeight: 500 }}>{e.title}</div>
                    <div style={{ color: '#666', fontSize: 12 }}>{e.description}</div>
                    <div style={{ color: '#999', fontSize: 11 }}>{e.event_time?.slice(0, 16)}</div>
                  </div>
                ),
              }))}
            />
          ) : <Empty description="暂无活动记录" />}
        </div>
      ),
    },
    {
      key: 'orders', label: `近期订单 (${profile.recent_orders?.length ?? 0})`,
      children: <Table columns={orderColumns} dataSource={profile.recent_orders || []} rowKey={(r, i) => `${r.order_number || i}`} size="small" />,
    },
    {
      key: 'reservations', label: `预订记录 (${profile.recent_reservations?.length ?? 0})`,
      children: (
        <List
          dataSource={profile.recent_reservations || []}
          renderItem={(r: any) => (
            <List.Item>
              <List.Item.Meta
                avatar={<CalendarOutlined style={{ fontSize: 20, color: '#52c41a' }} />}
                title={`${r.reservation_date?.slice(0, 10)} — ${r.party_size}人`}
                description={`状态: ${r.status}${r.special_requests ? ` | 备注: ${r.special_requests}` : ''}`}
              />
            </List.Item>
          )}
          locale={{ emptyText: '暂无预订记录' }}
        />
      ),
    },
  ] : [];

  return (
    <div>
      <Card title="客户搜索" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select value={identifierType} onChange={setIdentifierType} style={{ width: 120 }}>
            <Option value="phone">手机号</Option>
            <Option value="member_id">会员ID</Option>
            <Option value="email">邮箱</Option>
          </Select>
          <Input
            placeholder="输入姓名或手机号搜索"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onPressEnter={searchCustomers}
            style={{ width: 240 }}
          />
          <Input placeholder="门店ID（可选）" value={storeId} onChange={e => setStoreId(e.target.value)} style={{ width: 140 }} />
          <Button type="primary" icon={<SearchOutlined />} onClick={searchCustomers} loading={searching}>搜索</Button>
          {searchQuery && (
            <Button onClick={() => loadProfile(searchQuery)}>直接查询画像</Button>
          )}
        </Space>

        {searchResults.length > 0 && (
          <Table
            columns={searchColumns}
            dataSource={searchResults}
            rowKey="phone"
            size="small"
            style={{ marginTop: 12 }}
            pagination={false}
          />
        )}
      </Card>

      {loading && <Card loading style={{ marginBottom: 16 }} />}

      {profile && !loading && (
        <Card
          title={
            <Space>
              <StarOutlined style={{ color: tierColor[tier] || '#999' }} />
              客户360画像 — {profile.customer_identifier}
              {tier && <Tag color={tierColor[tier]}>{tier}</Tag>}
            </Space>
          }
        >
          <Tabs items={tabItems} />
        </Card>
      )}
    </div>
  );
};

export default Customer360Page;
