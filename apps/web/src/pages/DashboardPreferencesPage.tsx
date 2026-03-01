import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, List, Switch, Button, Typography, Space, Spin,
  Tag, Tooltip, Empty,
} from 'antd';
import {
  DragOutlined, EyeOutlined, EyeInvisibleOutlined,
  ReloadOutlined, SaveOutlined, UndoOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Title, Text } = Typography;

interface Widget {
  id: string;
  title: string;
  type: string;
  visible: boolean;
  order: number;
}

const TYPE_LABELS: Record<string, string> = {
  stat: '统计卡片',
  stat_group: '统计组',
  chart: '图表',
  list: '列表',
  summary: '摘要',
};

const DashboardPreferencesPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [widgets, setWidgets] = useState<Widget[]>([]);
  const [isCustom, setIsCustom] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/dashboard/preferences');
      setWidgets(res.data.layout || []);
      setIsCustom(res.data.is_custom || false);
    } catch (err: any) {
      handleApiError(err, '加载看板配置失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleVisible = (id: string) => {
    setWidgets(prev => prev.map(w => w.id === id ? { ...w, visible: !w.visible } : w));
  };

  const moveUp = (index: number) => {
    if (index === 0) return;
    setWidgets(prev => {
      const next = [...prev];
      [next[index - 1], next[index]] = [next[index], next[index - 1]];
      return next.map((w, i) => ({ ...w, order: i }));
    });
  };

  const moveDown = (index: number) => {
    setWidgets(prev => {
      if (index >= prev.length - 1) return prev;
      const next = [...prev];
      [next[index], next[index + 1]] = [next[index + 1], next[index]];
      return next.map((w, i) => ({ ...w, order: i }));
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      await apiClient.put('/api/v1/dashboard/preferences', { widgets });
      showSuccess('看板配置已保存');
      setIsCustom(true);
    } catch (err: any) {
      handleApiError(err, '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    try {
      const res = await apiClient.delete('/api/v1/dashboard/preferences');
      setWidgets(res.data.layout || []);
      setIsCustom(false);
      showSuccess('已重置为默认布局');
    } catch (err: any) {
      handleApiError(err, '重置失败');
    }
  };

  const visibleCount = widgets.filter(w => w.visible).length;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>看板布局配置</Title>
          <Text type="secondary">
            {isCustom ? '当前使用自定义布局' : '当前使用角色默认布局'}
            {' · '}已显示 {visibleCount}/{widgets.length} 个组件
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          {isCustom && (
            <Button icon={<UndoOutlined />} onClick={reset}>重置默认</Button>
          )}
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>
            保存配置
          </Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {widgets.length === 0 ? (
          <Empty description="暂无看板组件" />
        ) : (
          <Card>
            <List
              dataSource={widgets}
              renderItem={(widget, index) => (
                <List.Item
                  style={{
                    opacity: widget.visible ? 1 : 0.45,
                    background: widget.visible ? undefined : '#fafafa',
                    borderRadius: 6,
                    marginBottom: 4,
                    padding: '8px 16px',
                  }}
                  actions={[
                    <Button
                      size="small"
                      disabled={index === 0}
                      onClick={() => moveUp(index)}
                    >↑</Button>,
                    <Button
                      size="small"
                      disabled={index === widgets.length - 1}
                      onClick={() => moveDown(index)}
                    >↓</Button>,
                    <Tooltip title={widget.visible ? '点击隐藏' : '点击显示'}>
                      <Switch
                        size="small"
                        checked={widget.visible}
                        onChange={() => toggleVisible(widget.id)}
                        checkedChildren={<EyeOutlined />}
                        unCheckedChildren={<EyeInvisibleOutlined />}
                      />
                    </Tooltip>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={<DragOutlined style={{ color: '#bbb', fontSize: 16, marginTop: 4 }} />}
                    title={
                      <Space>
                        <Text strong={widget.visible}>{widget.title}</Text>
                        <Tag color="blue" style={{ fontSize: 11 }}>
                          {TYPE_LABELS[widget.type] || widget.type}
                        </Tag>
                        <Text type="secondary" style={{ fontSize: 11 }}>#{widget.id}</Text>
                      </Space>
                    }
                    description={`排序位置：${index + 1}`}
                  />
                </List.Item>
              )}
            />
          </Card>
        )}
      </Spin>
    </div>
  );
};

export default DashboardPreferencesPage;
