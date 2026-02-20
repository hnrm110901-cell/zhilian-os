import React, { ReactNode } from 'react';
import { Empty, Button } from 'antd';
import { InboxOutlined } from '@ant-design/icons';

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: ReactNode;
  action?: {
    text: string;
    onClick: () => void;
  };
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = '暂无数据',
  description,
  icon,
  action,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
        minHeight: 300,
      }}
    >
      <Empty
        image={icon || <InboxOutlined style={{ fontSize: 64, color: 'var(--text-tertiary)' }} />}
        imageStyle={{ height: 80 }}
        description={
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 16, fontWeight: 500, color: 'var(--text-primary)' }}>
              {title}
            </div>
            {description && (
              <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 8 }}>
                {description}
              </div>
            )}
          </div>
        }
      >
        {action && (
          <Button type="primary" onClick={action.onClick} style={{ marginTop: 16 }}>
            {action.text}
          </Button>
        )}
      </Empty>
    </div>
  );
};
