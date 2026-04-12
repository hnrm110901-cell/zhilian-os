/**
 * 海鲜档口展示屏 — 鱼缸旁大屏/触摸屏展示
 *
 * 功能：
 *  - 分区展示各鱼缸当前品种、时价、库存量
 *  - 每个品种卡片：品种名 + 图片占位 + 时价¥ + 库存(斤) + 新鲜度标签(A/B/C)
 *  - 时价动态更新高亮（价格变化闪烁动画）
 *  - 顾客可查看溯源信息（供应商/到货时间/产地）
 *  - 暗色主题（与 KDS 大屏风格一致）
 *  - 品牌色 #FF6B2C
 */

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Tag, Typography, Badge, Space, Tooltip, Modal, Descriptions,
  Statistic, Segmented, Empty,
} from 'antd';
import {
  EnvironmentOutlined, ClockCircleOutlined, ShopOutlined,
  InfoCircleOutlined, ArrowUpOutlined, ArrowDownOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;

// ── 品牌色 & 暗色主题常量 ───────────────────────────────────────────────────────

const BRAND_COLOR = '#FF6B2C';
const DARK_BG = '#0B1A20';
const CARD_BG = '#132830';
const CARD_BORDER = '#1E3A44';
const TEXT_PRIMARY = '#E8F0F2';
const TEXT_SECONDARY = '#8BA4AD';

// ── 类型定义 ────────────────────────────────────────────────────────────────────

interface SeafoodItem {
  item_id: string;
  tank_id: string;
  tank_name: string;
  species_name: string;
  image_url?: string;
  price_fen: number;
  prev_price_fen: number;
  stock_jin: number;
  freshness_grade: 'A' | 'B' | 'C';
  origin: string;
  supplier: string;
  arrival_time: string;
  batch_id: string;
  is_available: boolean;
}

interface TankZone {
  tank_id: string;
  tank_name: string;
  zone_label: string;
}

// ── 新鲜度配置 ──────────────────────────────────────────────────────────────────

const FRESHNESS_CONFIG: Record<string, { color: string; label: string; description: string }> = {
  A: { color: '#52c41a', label: 'A 极鲜', description: '到店24小时内，状态极佳' },
  B: { color: BRAND_COLOR, label: 'B 新鲜', description: '到店24-48小时，状态良好' },
  C: { color: '#faad14', label: 'C 一般', description: '到店超48小时，建议尽快售出' },
};

// ── 鱼缸分区配置 ────────────────────────────────────────────────────────────────

const TANK_ZONES: TankZone[] = [
  { tank_id: 'T01', tank_name: '1号缸 · 石斑', zone_label: '贵宾鱼缸' },
  { tank_id: 'T02', tank_name: '2号缸 · 龙虾蟹', zone_label: '甲壳类' },
  { tank_id: 'T03', tank_name: '3号缸 · 贝类', zone_label: '贝类专区' },
  { tank_id: 'T04', tank_name: '4号缸 · 鲜鱼', zone_label: '时令鲜鱼' },
];

// ── 示例数据 ────────────────────────────────────────────────────────────────────

const MOCK_SEAFOOD_ITEMS: SeafoodItem[] = [
  {
    item_id: 'S001', tank_id: 'T01', tank_name: '1号缸 · 石斑',
    species_name: '东星斑', price_fen: 58800, prev_price_fen: 56800,
    stock_jin: 12.5, freshness_grade: 'A', origin: '海南三亚',
    supplier: '南海鲜活水产', arrival_time: '2026-03-26 06:30',
    batch_id: 'B20260326-001', is_available: true,
  },
  {
    item_id: 'S002', tank_id: 'T01', tank_name: '1号缸 · 石斑',
    species_name: '老鼠斑', price_fen: 88800, prev_price_fen: 88800,
    stock_jin: 5.2, freshness_grade: 'A', origin: '南海深海',
    supplier: '南海鲜活水产', arrival_time: '2026-03-26 06:30',
    batch_id: 'B20260326-002', is_available: true,
  },
  {
    item_id: 'S003', tank_id: 'T01', tank_name: '1号缸 · 石斑',
    species_name: '龙趸', price_fen: 128800, prev_price_fen: 138800,
    stock_jin: 8.0, freshness_grade: 'B', origin: '南海',
    supplier: '深海优品', arrival_time: '2026-03-25 07:00',
    batch_id: 'B20260325-003', is_available: true,
  },
  {
    item_id: 'S004', tank_id: 'T02', tank_name: '2号缸 · 龙虾蟹',
    species_name: '波士顿龙虾', price_fen: 38800, prev_price_fen: 39800,
    stock_jin: 20.0, freshness_grade: 'A', origin: '美国波士顿',
    supplier: '环球海鲜进口', arrival_time: '2026-03-26 05:00',
    batch_id: 'B20260326-004', is_available: true,
  },
  {
    item_id: 'S005', tank_id: 'T02', tank_name: '2号缸 · 龙虾蟹',
    species_name: '帝王蟹', price_fen: 68800, prev_price_fen: 68800,
    stock_jin: 15.0, freshness_grade: 'A', origin: '阿拉斯加',
    supplier: '环球海鲜进口', arrival_time: '2026-03-26 05:00',
    batch_id: 'B20260326-005', is_available: true,
  },
  {
    item_id: 'S006', tank_id: 'T02', tank_name: '2号缸 · 龙虾蟹',
    species_name: '面包蟹', price_fen: 16800, prev_price_fen: 15800,
    stock_jin: 18.0, freshness_grade: 'B', origin: '英国苏格兰',
    supplier: '环球海鲜进口', arrival_time: '2026-03-25 06:00',
    batch_id: 'B20260325-006', is_available: true,
  },
  {
    item_id: 'S007', tank_id: 'T03', tank_name: '3号缸 · 贝类',
    species_name: '鲍鱼(8头)', price_fen: 28800, prev_price_fen: 28800,
    stock_jin: 10.0, freshness_grade: 'A', origin: '福建连江',
    supplier: '闽海鲍鱼场', arrival_time: '2026-03-26 07:00',
    batch_id: 'B20260326-007', is_available: true,
  },
  {
    item_id: 'S008', tank_id: 'T03', tank_name: '3号缸 · 贝类',
    species_name: '象拔蚌', price_fen: 48800, prev_price_fen: 52800,
    stock_jin: 6.0, freshness_grade: 'B', origin: '加拿大',
    supplier: '北美海鲜', arrival_time: '2026-03-25 05:30',
    batch_id: 'B20260325-008', is_available: true,
  },
  {
    item_id: 'S009', tank_id: 'T04', tank_name: '4号缸 · 鲜鱼',
    species_name: '多宝鱼', price_fen: 12800, prev_price_fen: 12800,
    stock_jin: 25.0, freshness_grade: 'A', origin: '山东威海',
    supplier: '威海渔港', arrival_time: '2026-03-26 04:00',
    batch_id: 'B20260326-009', is_available: true,
  },
  {
    item_id: 'S010', tank_id: 'T04', tank_name: '4号缸 · 鲜鱼',
    species_name: '桂花鱼', price_fen: 16800, prev_price_fen: 15800,
    stock_jin: 18.0, freshness_grade: 'A', origin: '广东顺德',
    supplier: '顺德水产', arrival_time: '2026-03-26 06:00',
    batch_id: 'B20260326-010', is_available: true,
  },
  {
    item_id: 'S011', tank_id: 'T04', tank_name: '4号缸 · 鲜鱼',
    species_name: '黄花鱼', price_fen: 8800, prev_price_fen: 9800,
    stock_jin: 30.0, freshness_grade: 'C', origin: '浙江舟山',
    supplier: '舟山渔业', arrival_time: '2026-03-24 05:00',
    batch_id: 'B20260324-011', is_available: true,
  },
];

// ── 价格格式化 ──────────────────────────────────────────────────────────────────

function formatPriceFen(fen: number): string {
  return `¥${(fen / 100).toFixed(2)}`;
}

function formatPriceYuan(fen: number): string {
  return (fen / 100).toFixed(0);
}

// ── 品种卡片组件 ────────────────────────────────────────────────────────────────

const SeafoodCard: React.FC<{
  item: SeafoodItem;
  onShowTrace: (item: SeafoodItem) => void;
}> = ({ item, onShowTrace }) => {
  const priceDiff = item.price_fen - item.prev_price_fen;
  const freshness = FRESHNESS_CONFIG[item.freshness_grade];
  const [flash, setFlash] = useState(false);

  // 价格变化闪烁效果
  useEffect(() => {
    if (priceDiff !== 0) {
      setFlash(true);
      const timer = setTimeout(() => setFlash(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [item.price_fen, priceDiff]);

  return (
    <Card
      hoverable
      style={{
        background: CARD_BG,
        borderColor: CARD_BORDER,
        borderRadius: 12,
        overflow: 'hidden',
        opacity: item.is_available ? 1 : 0.5,
      }}
      bodyStyle={{ padding: 0 }}
      onClick={() => onShowTrace(item)}
    >
      {/* 图片占位区域 */}
      <div
        style={{
          height: 140,
          background: `linear-gradient(135deg, ${CARD_BG} 0%, #1a3a42 100%)`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          position: 'relative',
        }}
      >
        {item.image_url ? (
          <img src={item.image_url} alt={item.species_name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <ExperimentOutlined style={{ fontSize: 48, color: TEXT_SECONDARY }} />
        )}

        {/* 新鲜度标签 */}
        <Tag
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            margin: 0,
            background: freshness.color,
            color: '#fff',
            border: 'none',
            fontWeight: 700,
            fontSize: 13,
            borderRadius: 6,
          }}
        >
          {freshness.label}
        </Tag>

        {/* 库存不足警告 */}
        {item.stock_jin < 5 && (
          <Tag
            style={{
              position: 'absolute',
              top: 8,
              left: 8,
              margin: 0,
              background: '#ff4d4f',
              color: '#fff',
              border: 'none',
              fontSize: 11,
            }}
          >
            库存紧张
          </Tag>
        )}

        {!item.is_available && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'rgba(0,0,0,0.6)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Text style={{ color: '#ff4d4f', fontSize: 24, fontWeight: 700 }}>已售罄</Text>
          </div>
        )}
      </div>

      {/* 信息区域 */}
      <div style={{ padding: '12px 14px' }}>
        {/* 品种名 */}
        <Text
          style={{
            color: TEXT_PRIMARY,
            fontSize: 18,
            fontWeight: 700,
            display: 'block',
            marginBottom: 8,
          }}
        >
          {item.species_name}
        </Text>

        {/* 时价 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 6,
            marginBottom: 8,
            animation: flash ? 'priceFlash 0.5s ease-in-out 3' : 'none',
          }}
        >
          <Text
            style={{
              color: BRAND_COLOR,
              fontSize: 28,
              fontWeight: 800,
              lineHeight: 1,
            }}
          >
            ¥{formatPriceYuan(item.price_fen)}
          </Text>
          <Text style={{ color: TEXT_SECONDARY, fontSize: 13 }}>/斤</Text>

          {priceDiff > 0 && (
            <Tag color="red" style={{ margin: 0, fontSize: 11 }}>
              <ArrowUpOutlined /> +{formatPriceFen(priceDiff)}
            </Tag>
          )}
          {priceDiff < 0 && (
            <Tag color="green" style={{ margin: 0, fontSize: 11 }}>
              <ArrowDownOutlined /> {formatPriceFen(priceDiff)}
            </Tag>
          )}
        </div>

        {/* 库存 + 产地 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space size={4}>
            <ShopOutlined style={{ color: TEXT_SECONDARY, fontSize: 13 }} />
            <Text style={{ color: TEXT_SECONDARY, fontSize: 13 }}>
              库存 <Text style={{ color: item.stock_jin < 5 ? '#ff4d4f' : TEXT_PRIMARY, fontWeight: 600 }}>{item.stock_jin}</Text> 斤
            </Text>
          </Space>
          <Space size={4}>
            <EnvironmentOutlined style={{ color: TEXT_SECONDARY, fontSize: 12 }} />
            <Text style={{ color: TEXT_SECONDARY, fontSize: 12 }}>{item.origin}</Text>
          </Space>
        </div>

        {/* 溯源入口提示 */}
        <div style={{ marginTop: 8, textAlign: 'right' }}>
          <Text style={{ color: BRAND_COLOR, fontSize: 11, cursor: 'pointer' }}>
            <InfoCircleOutlined /> 点击查看溯源
          </Text>
        </div>
      </div>
    </Card>
  );
};

// ── 溯源信息弹窗 ────────────────────────────────────────────────────────────────

const TraceModal: React.FC<{
  item: SeafoodItem | null;
  visible: boolean;
  onClose: () => void;
}> = ({ item, visible, onClose }) => {
  if (!item) return null;
  const freshness = FRESHNESS_CONFIG[item.freshness_grade];

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      footer={null}
      title={
        <Text style={{ color: TEXT_PRIMARY, fontSize: 18 }}>
          {item.species_name} — 溯源信息
        </Text>
      }
      width={480}
      styles={{
        content: { background: CARD_BG, borderColor: CARD_BORDER },
        header: { background: CARD_BG, borderBottom: `1px solid ${CARD_BORDER}` },
      }}
    >
      <Descriptions
        column={1}
        labelStyle={{ color: TEXT_SECONDARY, width: 100 }}
        contentStyle={{ color: TEXT_PRIMARY }}
        style={{ marginTop: 8 }}
      >
        <Descriptions.Item label="品种">{item.species_name}</Descriptions.Item>
        <Descriptions.Item label="时价">{formatPriceFen(item.price_fen)}/斤</Descriptions.Item>
        <Descriptions.Item label="库存">{item.stock_jin} 斤</Descriptions.Item>
        <Descriptions.Item label="新鲜度">
          <Tag color={freshness.color}>{freshness.label}</Tag>
          <Text style={{ color: TEXT_SECONDARY, fontSize: 12, marginLeft: 4 }}>{freshness.description}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="产地">
          <EnvironmentOutlined style={{ marginRight: 4 }} />{item.origin}
        </Descriptions.Item>
        <Descriptions.Item label="供应商">
          <ShopOutlined style={{ marginRight: 4 }} />{item.supplier}
        </Descriptions.Item>
        <Descriptions.Item label="到货时间">
          <ClockCircleOutlined style={{ marginRight: 4 }} />{item.arrival_time}
        </Descriptions.Item>
        <Descriptions.Item label="批次号">{item.batch_id}</Descriptions.Item>
        <Descriptions.Item label="所在鱼缸">{item.tank_name}</Descriptions.Item>
      </Descriptions>
    </Modal>
  );
};

// ── 主页面组件 ──────────────────────────────────────────────────────────────────

const SeafoodDisplayPage: React.FC = () => {
  const [items] = useState<SeafoodItem[]>(MOCK_SEAFOOD_ITEMS);
  const [selectedTank, setSelectedTank] = useState<string>('all');
  const [traceItem, setTraceItem] = useState<SeafoodItem | null>(null);
  const [traceVisible, setTraceVisible] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());

  // 时钟更新
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // 按鱼缸过滤
  const filteredItems = useMemo(() => {
    if (selectedTank === 'all') return items.filter((i) => i.is_available);
    return items.filter((i) => i.tank_id === selectedTank && i.is_available);
  }, [items, selectedTank]);

  // 按鱼缸分组
  const groupedByTank = useMemo(() => {
    const groups: Record<string, SeafoodItem[]> = {};
    for (const item of filteredItems) {
      if (!groups[item.tank_id]) groups[item.tank_id] = [];
      groups[item.tank_id].push(item);
    }
    return groups;
  }, [filteredItems]);

  // 统计
  const stats = useMemo(() => {
    const available = items.filter((i) => i.is_available);
    const totalSpecies = available.length;
    const totalStock = available.reduce((sum, i) => sum + i.stock_jin, 0);
    const gradeA = available.filter((i) => i.freshness_grade === 'A').length;
    return { totalSpecies, totalStock, gradeA };
  }, [items]);

  const handleShowTrace = useCallback((item: SeafoodItem) => {
    setTraceItem(item);
    setTraceVisible(true);
  }, []);

  // 鱼缸选项
  const tankOptions = [
    { label: '全部鱼缸', value: 'all' },
    ...TANK_ZONES.map((z) => ({ label: z.tank_name, value: z.tank_id })),
  ];

  return (
    <div
      style={{
        minHeight: '100vh',
        background: DARK_BG,
        padding: '20px 24px',
        fontFamily: "'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif",
      }}
    >
      {/* CSS 动画 */}
      <style>{`
        @keyframes priceFlash {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>

      {/* 顶部标题栏 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 20,
          borderBottom: `2px solid ${BRAND_COLOR}`,
          paddingBottom: 16,
        }}
      >
        <div>
          <Title level={2} style={{ color: TEXT_PRIMARY, margin: 0, fontWeight: 800 }}>
            <span style={{ color: BRAND_COLOR }}>鲜</span>活海鲜 · 时价档口
          </Title>
          <Text style={{ color: TEXT_SECONDARY, fontSize: 13 }}>
            所有海鲜均为活体现杀 · 价格随行就市 · 可扫码查看溯源
          </Text>
        </div>

        <div style={{ textAlign: 'right' }}>
          <Text style={{ color: TEXT_PRIMARY, fontSize: 22, fontWeight: 700 }}>
            {currentTime.toLocaleTimeString('zh-CN', { hour12: false })}
          </Text>
          <br />
          <Text style={{ color: TEXT_SECONDARY, fontSize: 12 }}>
            {currentTime.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}
          </Text>
        </div>
      </div>

      {/* 统计栏 */}
      <Row gutter={16} style={{ marginBottom: 20 }}>
        <Col span={8}>
          <Card style={{ background: CARD_BG, borderColor: CARD_BORDER, borderRadius: 10 }} bodyStyle={{ padding: '12px 16px' }}>
            <Statistic
              title={<Text style={{ color: TEXT_SECONDARY }}>在售品种</Text>}
              value={stats.totalSpecies}
              suffix="种"
              valueStyle={{ color: BRAND_COLOR, fontWeight: 700 }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card style={{ background: CARD_BG, borderColor: CARD_BORDER, borderRadius: 10 }} bodyStyle={{ padding: '12px 16px' }}>
            <Statistic
              title={<Text style={{ color: TEXT_SECONDARY }}>总库存</Text>}
              value={stats.totalStock}
              precision={1}
              suffix="斤"
              valueStyle={{ color: TEXT_PRIMARY, fontWeight: 700 }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card style={{ background: CARD_BG, borderColor: CARD_BORDER, borderRadius: 10 }} bodyStyle={{ padding: '12px 16px' }}>
            <Statistic
              title={<Text style={{ color: TEXT_SECONDARY }}>A级鲜活</Text>}
              value={stats.gradeA}
              suffix={`/ ${stats.totalSpecies}`}
              valueStyle={{ color: '#52c41a', fontWeight: 700 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 鱼缸筛选 */}
      <div style={{ marginBottom: 20 }}>
        <Segmented
          options={tankOptions}
          value={selectedTank}
          onChange={(v) => setSelectedTank(v as string)}
          style={{
            background: CARD_BG,
            padding: 4,
            borderRadius: 8,
          }}
        />
      </div>

      {/* 按鱼缸分区展示 */}
      {selectedTank === 'all' ? (
        Object.entries(groupedByTank).map(([tankId, tankItems]) => {
          const zone = TANK_ZONES.find((z) => z.tank_id === tankId);
          return (
            <div key={tankId} style={{ marginBottom: 28 }}>
              <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 4, height: 20, background: BRAND_COLOR, borderRadius: 2 }} />
                <Text style={{ color: TEXT_PRIMARY, fontSize: 18, fontWeight: 700 }}>
                  {zone?.tank_name || tankId}
                </Text>
                <Badge
                  count={tankItems.length}
                  style={{ backgroundColor: BRAND_COLOR }}
                />
                {zone && (
                  <Tag style={{ background: 'transparent', borderColor: CARD_BORDER, color: TEXT_SECONDARY }}>
                    {zone.zone_label}
                  </Tag>
                )}
              </div>
              <Row gutter={[16, 16]}>
                {tankItems.map((item) => (
                  <Col key={item.item_id} xs={24} sm={12} md={8} lg={6}>
                    <SeafoodCard item={item} onShowTrace={handleShowTrace} />
                  </Col>
                ))}
              </Row>
            </div>
          );
        })
      ) : (
        <Row gutter={[16, 16]}>
          {filteredItems.length > 0 ? (
            filteredItems.map((item) => (
              <Col key={item.item_id} xs={24} sm={12} md={8} lg={6}>
                <SeafoodCard item={item} onShowTrace={handleShowTrace} />
              </Col>
            ))
          ) : (
            <Col span={24}>
              <Empty
                description={<Text style={{ color: TEXT_SECONDARY }}>该鱼缸暂无在售品种</Text>}
                style={{ padding: 60 }}
              />
            </Col>
          )}
        </Row>
      )}

      {/* 底部品牌信息 */}
      <div
        style={{
          marginTop: 40,
          paddingTop: 16,
          borderTop: `1px solid ${CARD_BORDER}`,
          textAlign: 'center',
        }}
      >
        <Text style={{ color: TEXT_SECONDARY, fontSize: 12 }}>
          屯象经营助手 · 海鲜档口展示系统 · 价格实时更新
        </Text>
      </div>

      {/* 溯源弹窗 */}
      <TraceModal
        item={traceItem}
        visible={traceVisible}
        onClose={() => setTraceVisible(false)}
      />
    </div>
  );
};

export default SeafoodDisplayPage;
