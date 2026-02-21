import React, { type CSSProperties, type ReactNode } from 'react';
import { Card, Statistic, Space } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';

interface DataCardProps {
  title: string;
  value: string | number;
  prefix?: ReactNode;
  suffix?: ReactNode;
  trend?: {
    value: number;
    isPositive?: boolean;
  };
  extra?: ReactNode;
  loading?: boolean;
  onClick?: () => void;
  style?: CSSProperties;
}

export const DataCard: React.FC<DataCardProps> = ({
  title,
  value,
  prefix,
  suffix,
  trend,
  extra,
  loading = false,
  onClick,
  style,
}) => {
  const trendColor = trend?.isPositive ? '#52c41a' : '#f5222d';
  const TrendIcon = trend?.isPositive ? ArrowUpOutlined : ArrowDownOutlined;

  return (
    <Card
      loading={loading}
      hoverable={!!onClick}
      onClick={onClick}
      style={{
        cursor: onClick ? 'pointer' : 'default',
        ...style,
      }}
    >
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: 14 }}>{title}</span>
          {extra}
        </div>
        <Statistic
          value={value}
          prefix={prefix}
          suffix={suffix}
          valueStyle={{ fontSize: 28, fontWeight: 600 }}
        />
        {trend && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <TrendIcon style={{ color: trendColor, fontSize: 12 }} />
            <span style={{ color: trendColor, fontSize: 14, fontWeight: 500 }}>
              {Math.abs(trend.value)}%
            </span>
            <span style={{ color: 'var(--text-tertiary)', fontSize: 12, marginLeft: 4 }}>
              较上期
            </span>
          </div>
        )}
      </Space>
    </Card>
  );
};
