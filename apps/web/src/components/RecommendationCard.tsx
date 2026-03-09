import React, { useEffect, useState, useCallback } from 'react';
import { Card, Tag, List, Typography, Spin, Button, Tooltip } from 'antd';
import {
  RiseOutlined, FallOutlined, ClockCircleOutlined,
  ThunderboltOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';

const { Text } = Typography;

interface Recommendation {
  dish_id: string;
  dish_name: string;
  action: 'promote' | 'bundle' | 'discount' | 'reduce' | 'retire';
  reason: string;
  expected_revenue_impact: number;
  confidence: number;
  priority: number;
  tags: string[];
}

const ACTION_CONFIG: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  promote:  { icon: <RiseOutlined />,         color: 'success', label: '重点推广' },
  bundle:   { icon: <ThunderboltOutlined />,   color: 'blue',    label: '搭配套餐' },
  discount: { icon: <ClockCircleOutlined />,   color: 'orange',  label: '限时折扣' },
  reduce:   { icon: <FallOutlined />,          color: 'warning', label: '减少产量' },
  retire:   { icon: <FallOutlined />,          color: 'error',   label: '建议下架' },
};

interface Props {
  storeId: string;
  compact?: boolean;
  maxItems?: number;
}

export default function RecommendationCard({ storeId, compact = false, maxItems = 5 }: Props) {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const resp = await apiClient.get<{ recommendations: Recommendation[] }>(
        `/api/v1/recommendations/${storeId}`
      );
      setRecs((resp.recommendations ?? []).slice(0, maxItems));
    } catch {
      // fail silently
    } finally {
      setLoading(false);
    }
  }, [storeId, maxItems]);

  useEffect(() => { fetch(); }, [fetch]);

  const impactColor = (v: number) => v >= 0 ? '#52c41a' : '#f5222d';
  const impactLabel = (v: number) => `${v >= 0 ? '+' : ''}¥${Math.abs(v).toFixed(0)}`;

  return (
    <Card
      title={compact ? undefined : '🤖 AI 经营推荐'}
      size={compact ? 'small' : 'default'}
      extra={
        <Tooltip title="刷新推荐">
          <Button type="text" size="small" icon={<ReloadOutlined />} onClick={fetch} loading={loading} />
        </Tooltip>
      }
    >
      {loading ? (
        <Spin style={{ display: 'block', textAlign: 'center', padding: 16 }} />
      ) : (
        <List
          dataSource={recs}
          locale={{ emptyText: '暂无推荐' }}
          renderItem={(rec) => {
            const cfg = ACTION_CONFIG[rec.action] ?? ACTION_CONFIG.promote;
            return (
              <List.Item style={{ padding: '8px 0' }}>
                <List.Item.Meta
                  title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>
                      <Text strong style={{ fontSize: 13 }}>{rec.dish_name}</Text>
                      {rec.tags.map((t) => (
                        <Tag key={t} bordered={false} style={{ fontSize: 11 }}>{t}</Tag>
                      ))}
                    </div>
                  }
                  description={
                    <div style={{ fontSize: 12 }}>
                      <Text type="secondary">{rec.reason}</Text>
                      <span style={{ marginLeft: 8, color: impactColor(rec.expected_revenue_impact), fontWeight: 600 }}>
                        预期 {impactLabel(rec.expected_revenue_impact)}
                      </span>
                      <Text type="secondary" style={{ marginLeft: 8 }}>
                        置信度 {(rec.confidence * 100).toFixed(0)}%
                      </Text>
                    </div>
                  }
                />
              </List.Item>
            );
          }}
        />
      )}
    </Card>
  );
}
