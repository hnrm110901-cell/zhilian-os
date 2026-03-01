import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Tag, Progress, Typography, Space, Select, Button,
  Tooltip, Badge, Statistic, Row, Col, Spin, Alert
} from 'antd';
import {
  RiseOutlined, FallOutlined, StarOutlined, ReloadOutlined, TrophyOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

const { Title, Text } = Typography;

interface DishScore {
  total: number;
  trend: number;
  margin: number;
  stock: number;
  time_slot: number;
  low_refund: number;
}

interface RecommendedDish {
  rank: number;
  dish_id: string;
  dish_name: string;
  category: string | null;
  price: number | null;
  highlight: string | null;
  scores: DishScore;
}

interface RecommendationResponse {
  store_id: string;
  total: number;
  recommendations: RecommendedDish[];
}

const SCORE_FACTORS = [
  { key: 'trend',      label: '趋势',    weight: '30%', color: '#1677ff' },
  { key: 'margin',     label: '毛利',    weight: '25%', color: '#52c41a' },
  { key: 'stock',      label: '库存',    weight: '20%', color: '#faad14' },
  { key: 'time_slot',  label: '时段',    weight: '15%', color: '#722ed1' },
  { key: 'low_refund', label: '低退单',  weight: '10%', color: '#f5222d' },
];

function ScoreBar({ value, color }: { value: number; color: string }) {
  return (
    <Progress
      percent={Math.round(value * 100)}
      size="small"
      strokeColor={color}
      showInfo={false}
      style={{ width: 80, marginBottom: 0 }}
    />
  );
}

function RankBadge({ rank }: { rank: number }) {
  if (rank === 1) return <TrophyOutlined style={{ color: '#ffd700', fontSize: 18 }} />;
  if (rank === 2) return <TrophyOutlined style={{ color: '#c0c0c0', fontSize: 16 }} />;
  if (rank === 3) return <TrophyOutlined style={{ color: '#cd7f32', fontSize: 16 }} />;
  return <Text type="secondary">#{rank}</Text>;
}

const MenuRecommendationPage: React.FC = () => {
  const [storeId, setStoreId] = useState<string>('');
  const [limit, setLimit] = useState<number>(10);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchRecommendations = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(
        `/api/v1/menu/recommendations?store_id=${encodeURIComponent(storeId)}&limit=${limit}`
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json: RecommendationResponse = await resp.json();
      setData(json);
    } catch (e: any) {
      setError(e.message || '获取推荐失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, limit]);

  useEffect(() => {
    if (storeId) fetchRecommendations();
  }, [storeId, limit]);

  const columns: ColumnsType<RecommendedDish> = [
    {
      title: '排名',
      dataIndex: 'rank',
      width: 60,
      render: (rank: number) => <RankBadge rank={rank} />,
    },
    {
      title: '菜品',
      dataIndex: 'dish_name',
      render: (name: string, record) => (
        <Space direction="vertical" size={2}>
          <Text strong>{name}</Text>
          {record.highlight && (
            <Tag color="blue" style={{ fontSize: 11 }}>{record.highlight}</Tag>
          )}
          {record.category && (
            <Text type="secondary" style={{ fontSize: 12 }}>{record.category}</Text>
          )}
        </Space>
      ),
    },
    {
      title: '售价',
      dataIndex: 'price',
      width: 80,
      render: (price: number | null) =>
        price != null ? <Text>¥{price.toFixed(2)}</Text> : <Text type="secondary">-</Text>,
    },
    {
      title: '综合评分',
      dataIndex: 'scores',
      width: 130,
      sorter: (a, b) => a.scores.total - b.scores.total,
      render: (scores: DishScore) => (
        <Space>
          <Progress
            type="circle"
            percent={Math.round(scores.total * 100)}
            size={44}
            strokeColor={scores.total >= 0.7 ? '#52c41a' : scores.total >= 0.5 ? '#faad14' : '#f5222d'}
          />
        </Space>
      ),
    },
    {
      title: '评分因子详情',
      dataIndex: 'scores',
      render: (scores: DishScore) => (
        <Space direction="vertical" size={2} style={{ width: '100%' }}>
          {SCORE_FACTORS.map(f => (
            <Space key={f.key} size={4}>
              <Text style={{ fontSize: 11, width: 32, color: f.color }}>{f.label}</Text>
              <Text style={{ fontSize: 11, width: 24 }}>{f.weight}</Text>
              <ScoreBar value={(scores as any)[f.key]} color={f.color} />
              <Text style={{ fontSize: 11, width: 30 }}>
                {Math.round((scores as any)[f.key] * 100)}
              </Text>
            </Space>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3} style={{ marginBottom: 16 }}>
        <RiseOutlined /> 动态菜单推荐
      </Title>

      {/* 控制栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col>
            <Space>
              <Text>门店：</Text>
              <Select
                placeholder="选择门店"
                style={{ width: 200 }}
                value={storeId || undefined}
                onChange={setStoreId}
                options={[
                  { value: 'STORE_A1', label: '门店A1（示例）' },
                  { value: 'STORE_A2', label: '门店A2（示例）' },
                ]}
                allowClear
              />
            </Space>
          </Col>
          <Col>
            <Space>
              <Text>显示条数：</Text>
              <Select
                value={limit}
                onChange={setLimit}
                options={[5, 10, 20].map(n => ({ value: n, label: `Top ${n}` }))}
                style={{ width: 90 }}
              />
            </Space>
          </Col>
          <Col>
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchRecommendations}
              loading={loading}
              disabled={!storeId}
            >
              刷新
            </Button>
          </Col>
          <Col flex="auto">
            <Text type="secondary" style={{ fontSize: 12 }}>
              缓存 TTL：5分钟 · 目标响应：&lt; 200ms
            </Text>
          </Col>
        </Row>
      </Card>

      {/* 因子说明 */}
      <Card
        size="small"
        title="评分因子权重"
        style={{ marginBottom: 16 }}
      >
        <Space wrap>
          {SCORE_FACTORS.map(f => (
            <Tag key={f.key} color={f.color} style={{ fontSize: 12 }}>
              {f.label} {f.weight}
            </Tag>
          ))}
        </Space>
      </Card>

      {/* 错误提示 */}
      {error && (
        <Alert type="error" message={error} style={{ marginBottom: 16 }} closable />
      )}

      {/* 无门店提示 */}
      {!storeId && !loading && (
        <Alert type="info" message="请先选择门店以获取推荐" style={{ marginBottom: 16 }} />
      )}

      {/* 推荐列表 */}
      {storeId && (
        <Card title={data ? `Top ${data.total} 推荐菜品` : '菜品推荐'}>
          <Spin spinning={loading}>
            <Table
              dataSource={data?.recommendations ?? []}
              columns={columns}
              rowKey="dish_id"
              pagination={false}
              size="middle"
              locale={{ emptyText: '暂无推荐数据' }}
            />
          </Spin>
        </Card>
      )}
    </div>
  );
};

export default MenuRecommendationPage;
