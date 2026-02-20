import React, { useState, useEffect, useRef } from 'react';
import { Modal, Input, List, Tag, Space, Empty } from 'antd';
import {
  SearchOutlined,
  DashboardOutlined,
  ScheduleOutlined,
  ShoppingCartOutlined,
  InboxOutlined,
  CustomerServiceOutlined,
  ReadOutlined,
  BarChartOutlined,
  CalendarOutlined,
  TeamOutlined,
  ApiOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

interface SearchResult {
  id: string;
  title: string;
  description: string;
  path: string;
  icon: React.ReactNode;
  category: string;
}

const searchData: SearchResult[] = [
  {
    id: '1',
    title: '控制台',
    description: '查看系统概览和关键指标',
    path: '/',
    icon: <DashboardOutlined />,
    category: '导航',
  },
  {
    id: '2',
    title: '智能排班',
    description: 'AI驱动的员工排班管理',
    path: '/schedule',
    icon: <ScheduleOutlined />,
    category: 'Agent系统',
  },
  {
    id: '3',
    title: '订单协同',
    description: '订单管理和协同处理',
    path: '/order',
    icon: <ShoppingCartOutlined />,
    category: 'Agent系统',
  },
  {
    id: '4',
    title: '库存预警',
    description: '智能库存监控和预警',
    path: '/inventory',
    icon: <InboxOutlined />,
    category: 'Agent系统',
  },
  {
    id: '5',
    title: '服务质量',
    description: '服务质量监控和分析',
    path: '/service',
    icon: <CustomerServiceOutlined />,
    category: 'Agent系统',
  },
  {
    id: '6',
    title: '培训辅导',
    description: '员工培训和技能提升',
    path: '/training',
    icon: <ReadOutlined />,
    category: 'Agent系统',
  },
  {
    id: '7',
    title: '决策支持',
    description: '数据驱动的决策建议',
    path: '/decision',
    icon: <BarChartOutlined />,
    category: 'Agent系统',
  },
  {
    id: '8',
    title: '预定宴会',
    description: '宴会预定和管理',
    path: '/reservation',
    icon: <CalendarOutlined />,
    category: 'Agent系统',
  },
  {
    id: '9',
    title: '用户管理',
    description: '系统用户和权限管理',
    path: '/users',
    icon: <TeamOutlined />,
    category: '系统管理',
  },
  {
    id: '10',
    title: '企业集成',
    description: '第三方系统集成配置',
    path: '/enterprise',
    icon: <ApiOutlined />,
    category: '系统管理',
  },
  {
    id: '11',
    title: '审计日志',
    description: '系统操作审计记录',
    path: '/audit',
    icon: <FileTextOutlined />,
    category: '系统管理',
  },
];

interface GlobalSearchProps {
  visible: boolean;
  onClose: () => void;
}

export const GlobalSearch: React.FC<GlobalSearchProps> = ({ visible, onClose }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const inputRef = useRef<any>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (visible) {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
    } else {
      setSearchQuery('');
      setResults([]);
    }
  }, [visible]);

  useEffect(() => {
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      const filtered = searchData.filter(
        (item) =>
          item.title.toLowerCase().includes(query) ||
          item.description.toLowerCase().includes(query) ||
          item.category.toLowerCase().includes(query)
      );
      setResults(filtered);
    } else {
      setResults(searchData.slice(0, 8));
    }
  }, [searchQuery]);

  const handleSelect = (path: string) => {
    navigate(path);
    onClose();
  };

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      footer={null}
      width={600}
      style={{ top: 100 }}
      bodyStyle={{ padding: 0 }}
      closeIcon={null}
    >
      <div style={{ padding: '16px 16px 0' }}>
        <Input
          ref={inputRef}
          size="large"
          placeholder="搜索页面、功能... (Ctrl+K)"
          prefix={<SearchOutlined style={{ color: 'var(--text-tertiary)' }} />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ borderRadius: 'var(--radius-md)' }}
          allowClear
        />
      </div>

      <div style={{ maxHeight: 400, overflowY: 'auto', padding: '8px 0' }}>
        {results.length > 0 ? (
          <List
            dataSource={results}
            renderItem={(item) => (
              <List.Item
                onClick={() => handleSelect(item.path)}
                style={{
                  padding: '12px 16px',
                  cursor: 'pointer',
                  transition: 'background var(--transition-fast)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--bg-secondary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                }}
              >
                <List.Item.Meta
                  avatar={
                    <div
                      style={{
                        width: 40,
                        height: 40,
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--bg-secondary)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 18,
                        color: 'var(--primary-color)',
                      }}
                    >
                      {item.icon}
                    </div>
                  }
                  title={
                    <Space>
                      <span style={{ fontWeight: 500 }}>{item.title}</span>
                      <Tag style={{ fontSize: 11 }}>{item.category}</Tag>
                    </Space>
                  }
                  description={
                    <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      {item.description}
                    </span>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="未找到相关结果"
            style={{ padding: '32px 0' }}
          />
        )}
      </div>

      <div
        style={{
          padding: '12px 16px',
          borderTop: '1px solid var(--border-light)',
          background: 'var(--bg-secondary)',
          fontSize: 12,
          color: 'var(--text-tertiary)',
        }}
      >
        <Space size={16}>
          <span>↑↓ 导航</span>
          <span>Enter 选择</span>
          <span>Esc 关闭</span>
        </Space>
      </div>
    </Modal>
  );
};
