/**
 * 动态定价策略查询页
 * Dynamic Pricing Strategy — Agent-14
 *
 * 输入会员 ID → 实时查询该会员的个性化定价推荐
 * 结果展示：马斯洛层级、优惠类型、折扣、策略说明、置信度
 */
import React, { useState } from 'react';
import {
  Card, Row, Col, Select, Input, Button, Typography, Space,
  Tag, Progress, Alert, Divider, Tooltip, Badge,
} from 'antd';
import {
  SearchOutlined, ThunderboltOutlined, StarOutlined,
  GiftOutlined, TeamOutlined, ExperimentOutlined, SafetyCertificateOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import apiClient from '../services/api';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

// ── Types ─────────────────────────────────────────────────────────────────────

interface PricingOffer {
  offer_type: string;
  title: string;
  description: string;
  discount_pct: number;
  maslow_level: number;
  strategy_note: string;
  is_peak_hour: boolean;
  confidence: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STORE_OPTIONS = ['S001', 'S002', 'S003'];

const MASLOW_COLORS: Record<number, string> = {
  1: '#bfbfbf',
  2: '#91d5ff',
  3: '#52c41a',
  4: '#1890ff',
  5: '#722ed1',
};

const MASLOW_LABELS: Record<number, string> = {
  1: 'L1 · 初次接触',
  2: 'L2 · 初步信任',
  3: 'L3 · 社交习惯',
  4: 'L4 · 高频忠实',
  5: 'L5 · 深度忠诚',
};

const OFFER_TYPE_ICONS: Record<string, React.ReactNode> = {
  quality_story:    <SafetyCertificateOutlined style={{ fontSize: 32 }} />,
  discount_coupon:  <GiftOutlined style={{ fontSize: 32 }} />,
  group_bundle:     <TeamOutlined style={{ fontSize: 32 }} />,
  exclusive_access: <StarOutlined style={{ fontSize: 32 }} />,
  experience:       <ExperimentOutlined style={{ fontSize: 32 }} />,
};

const OFFER_TYPE_LABELS: Record<string, string> = {
  quality_story:    '品质故事',
  discount_coupon:  '折扣券',
  group_bundle:     '聚餐套餐',
  exclusive_access: '专属礼遇',
  experience:       '主厨体验',
};

// ── Main Component ────────────────────────────────────────────────────────────

const DynamicPricingPage: React.FC = () => {
  const [storeId, setStoreId] = useState('S001');
  const [customerId, setCustomerId] = useState('');
  const [loading, setLoading] = useState(false);
  const [offer, setOffer] = useState<PricingOffer | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!customerId.trim()) {
      setError('请输入会员 ID');
      return;
    }
    setLoading(true);
    setError(null);
    setOffer(null);
    try {
      const data = await apiClient.get<PricingOffer>(
        `/api/v1/private-domain/dynamic-pricing/${storeId}?customer_id=${encodeURIComponent(customerId.trim())}`
      );
      setOffer(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? '查询失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const levelColor = offer ? MASLOW_COLORS[offer.maslow_level] : '#bfbfbf';

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: '0 auto' }}>
      {/* Header */}
      <Row align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            <ThunderboltOutlined style={{ marginRight: 8, color: '#faad14' }} />
            动态定价策略
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Agent-14 · 基于马斯洛层级 + 时段的个性化定价推荐
          </Text>
        </Col>
      </Row>

      {/* 查询区 */}
      <Card bordered={false} style={{ marginBottom: 24, background: '#fafafa' }}>
        <Row gutter={12} align="middle">
          <Col>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>门店</Text>
            <Select
              value={storeId}
              onChange={setStoreId}
              style={{ width: 110 }}
            >
              {STORE_OPTIONS.map(s => <Option key={s} value={s}>{s}</Option>)}
            </Select>
          </Col>
          <Col flex={1}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>会员 ID</Text>
            <Input
              placeholder="输入会员 ID，如 C001"
              value={customerId}
              onChange={e => setCustomerId(e.target.value)}
              onPressEnter={handleSearch}
              allowClear
            />
          </Col>
          <Col>
            <div style={{ marginBottom: 4, visibility: 'hidden', fontSize: 12 }}>占位</div>
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={loading}
              onClick={handleSearch}
            >
              查询定价策略
            </Button>
          </Col>
        </Row>
      </Card>

      {error && (
        <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />
      )}

      {/* 结果展示 */}
      {offer && (
        <Card
          bordered={false}
          style={{ borderTop: `4px solid ${levelColor}` }}
        >
          <Row gutter={[24, 16]}>
            {/* 左：层级 + 图标 */}
            <Col xs={24} sm={6} style={{ textAlign: 'center' }}>
              <div
                style={{
                  width: 72, height: 72,
                  borderRadius: '50%',
                  background: levelColor,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#fff',
                  margin: '0 auto 12px',
                }}
              >
                {OFFER_TYPE_ICONS[offer.offer_type] ?? <GiftOutlined style={{ fontSize: 32 }} />}
              </div>
              <Tag
                style={{
                  background: levelColor,
                  color: '#fff',
                  border: 'none',
                  fontWeight: 'bold',
                  fontSize: 13,
                  padding: '2px 12px',
                }}
              >
                {MASLOW_LABELS[offer.maslow_level]}
              </Tag>
              <div style={{ marginTop: 8 }}>
                <Tag color={offer.is_peak_hour ? 'red' : 'default'}>
                  <ClockCircleOutlined style={{ marginRight: 4 }} />
                  {offer.is_peak_hour ? '高峰时段' : '平峰时段'}
                </Tag>
              </div>
            </Col>

            {/* 右：详情 */}
            <Col xs={24} sm={18}>
              <Space style={{ marginBottom: 8 }} align="center">
                <Title level={4} style={{ margin: 0 }}>{offer.title}</Title>
                <Tag color="blue">{OFFER_TYPE_LABELS[offer.offer_type] ?? offer.offer_type}</Tag>
                {offer.discount_pct > 0 ? (
                  <Tag color="red" style={{ fontSize: 14, fontWeight: 'bold' }}>
                    {offer.discount_pct} 折
                  </Tag>
                ) : (
                  <Tag color="purple">无折扣 · 礼遇优先</Tag>
                )}
              </Space>

              <Paragraph style={{ color: '#595959', marginBottom: 16 }}>
                {offer.description}
              </Paragraph>

              <Divider style={{ margin: '12px 0' }} />

              <Row gutter={16}>
                <Col span={24}>
                  <Text type="secondary" style={{ fontSize: 12 }}>运营策略依据</Text>
                  <div style={{ marginTop: 4 }}>
                    <Text style={{ fontSize: 13 }}>{offer.strategy_note}</Text>
                  </div>
                </Col>
              </Row>

              <div style={{ marginTop: 16 }}>
                <Row align="middle" gutter={8}>
                  <Col>
                    <Tooltip title="基于会员历史消费次数，消费越多越可信">
                      <Text type="secondary" style={{ fontSize: 12 }}>置信度</Text>
                    </Tooltip>
                  </Col>
                  <Col flex={1}>
                    <Progress
                      percent={Math.round(offer.confidence * 100)}
                      size="small"
                      strokeColor={levelColor}
                      format={p => <Text style={{ fontSize: 12 }}>{p}%</Text>}
                    />
                  </Col>
                </Row>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* 空状态提示 */}
      {!offer && !loading && !error && (
        <Card bordered={false} style={{ textAlign: 'center', padding: '40px 0' }}>
          <GiftOutlined style={{ fontSize: 48, color: '#d9d9d9', marginBottom: 16 }} />
          <div>
            <Text type="secondary">输入会员 ID 查询个性化定价策略</Text>
          </div>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              系统将根据消费频次自动判断马斯洛层级，给出最匹配的定价建议
            </Text>
          </div>
        </Card>
      )}

      {/* 层级说明 */}
      <Card
        title="各层级定价逻辑"
        bordered={false}
        size="small"
        style={{ marginTop: 24 }}
      >
        <Row gutter={[8, 8]}>
          {[1, 2, 3, 4, 5].map(level => (
            <Col key={level} xs={24} sm={12} md={8} lg={4} xl={4}>
              <div
                style={{
                  padding: '8px 12px',
                  borderRadius: 8,
                  background: `${MASLOW_COLORS[level]}18`,
                  borderLeft: `3px solid ${MASLOW_COLORS[level]}`,
                  height: '100%',
                }}
              >
                <Text strong style={{ color: MASLOW_COLORS[level], fontSize: 13 }}>
                  {MASLOW_LABELS[level]}
                </Text>
                <div style={{ fontSize: 11, color: '#595959', marginTop: 4 }}>
                  {level === 1 && '品质口碑，无折扣'}
                  {level === 2 && '88折，降低门槛'}
                  {level === 3 && '78折，聚餐套餐'}
                  {level === 4 && '专属席位，无折扣'}
                  {level === 5 && '主厨体验，无折扣'}
                </div>
                <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 2 }}>
                  {level === 1 && '频次 = 0'}
                  {level === 2 && '频次 = 1'}
                  {level === 3 && '频次 2-5'}
                  {level === 4 && '频次 ≥ 6，< ¥500'}
                  {level === 5 && '频次 ≥ 6，≥ ¥500'}
                </div>
              </div>
            </Col>
          ))}
        </Row>
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>
            平峰时段（13:00-17:00 / 20:00+）L2/L3 额外让利 1 折，提升非高峰客流
          </Text>
        </div>
      </Card>
    </div>
  );
};

export default DynamicPricingPage;
