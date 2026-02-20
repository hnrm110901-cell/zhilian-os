import React from 'react';
import { Skeleton, Card, Space } from 'antd';

interface LoadingSkeletonProps {
  type?: 'card' | 'list' | 'table' | 'form';
  rows?: number;
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({ type = 'card', rows = 3 }) => {
  if (type === 'card') {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
        {Array.from({ length: rows }).map((_, index) => (
          <Card key={index}>
            <Skeleton active paragraph={{ rows: 2 }} />
          </Card>
        ))}
      </div>
    );
  }

  if (type === 'list') {
    return (
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {Array.from({ length: rows }).map((_, index) => (
          <Card key={index}>
            <Skeleton active avatar paragraph={{ rows: 1 }} />
          </Card>
        ))}
      </Space>
    );
  }

  if (type === 'table') {
    return (
      <Card>
        <Skeleton active paragraph={{ rows: rows }} />
      </Card>
    );
  }

  if (type === 'form') {
    return (
      <Card>
        <Space direction="vertical" size={24} style={{ width: '100%' }}>
          {Array.from({ length: rows }).map((_, index) => (
            <Skeleton.Input key={index} active block />
          ))}
        </Space>
      </Card>
    );
  }

  return <Skeleton active />;
};
