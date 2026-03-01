import React, { useState, useCallback } from 'react';
import {
  Card, Form, Input, Button, Row, Col, Typography,
  Tag, Space, Spin, Alert, Descriptions, Drawer, Switch,
} from 'antd';
import { ApartmentOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Paragraph, Text } = Typography;

// 节点类型颜色配置（基础模式 5 类 + 全图模式 3 类）
const NODE_STYLE: Record<string, { color: string; size: number; label: string }> = {
  Store:             { color: '#1890ff', size: 28, label: '门店' },
  Dish:              { color: '#52c41a', size: 20, label: '菜品' },
  BOM:               { color: '#faad14', size: 16, label: 'BOM' },
  Ingredient:        { color: '#f5222d', size: 18, label: '食材' },
  InventorySnapshot: { color: '#722ed1', size: 12, label: '库存快照' },
  Staff:             { color: '#13c2c2', size: 20, label: '员工' },
  WasteEvent:        { color: '#cf1322', size: 16, label: '损耗事件' },
  TrainingModule:    { color: '#d46b08', size: 18, label: '培训模块' },
};

// 关系类型标签映射
const REL_LABEL: Record<string, string> = {
  similar_to:          'SIMILAR_TO',
  belongs_to:          'BELONGS_TO',
  triggered_by:        'TRIGGERED_BY',
  needs_training:      'NEEDS_TRAINING',
  completed_training:  'COMPLETED_TRAINING',
};

interface GraphNode {
  id: string;
  name: string;
  type: string;
  category: number;
  symbolSize: number;
  itemStyle: { color: string };
  meta: Record<string, any>;
}

interface GraphEdge {
  source: string;
  target: string;
  label: string;
}

const OntologyGraphPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [fullMode, setFullMode] = useState(false);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const buildGraph = useCallback((data: any, isFullMode: boolean) => {
    const ns: GraphNode[] = [];
    const es: GraphEdge[] = [];
    const seen = new Set<string>();
    const nodeTypes = Object.keys(NODE_STYLE);

    const addNode = (id: string, name: string, type: string, meta: Record<string, any>) => {
      if (seen.has(id)) return;
      seen.add(id);
      const style = NODE_STYLE[type] || { color: '#aaa', size: 14, label: type };
      ns.push({
        id, name, type,
        category: nodeTypes.indexOf(type),
        symbolSize: style.size,
        itemStyle: { color: style.color },
        meta,
      });
    };

    const addEdge = (source: string, target: string, label: string) => {
      es.push({ source, target, label });
    };

    // === 基础节点（两种模式都有）===

    // Store 节点
    (data.stores || []).forEach((s: any) => addNode(
      `Store:${s.store_id}`, s.name || s.store_id, 'Store', s,
    ));

    // Dish 节点 + Store→Dish 边
    (data.dishes || []).forEach((d: any) => {
      addNode(`Dish:${d.dish_id}`, d.name || d.dish_id, 'Dish', d);
      if (d.store_id) addEdge(`Store:${d.store_id}`, `Dish:${d.dish_id}`, 'HAS_DISH');
    });

    // BOM 节点 + Dish→BOM 边
    (data.boms || []).forEach((b: any) => {
      addNode(`BOM:${b.bom_id}`, `BOM v${b.version || '?'}`, 'BOM', b);
      if (b.dish_id) addEdge(`Dish:${b.dish_id}`, `BOM:${b.bom_id}`, 'HAS_BOM');
    });

    // Ingredient 节点
    const ingMap: Record<string, any> = {};
    (data.ingredients || []).forEach((i: any) => {
      ingMap[i.ing_id] = i;
      addNode(`Ing:${i.ing_id}`, i.name || i.ing_id, 'Ingredient', i);
    });

    // InventorySnapshot 节点 + 关联边
    (data.inventory_snapshots || []).forEach((sn: any) => {
      addNode(
        `Snap:${sn.snapshot_id}`,
        `库存 ${sn.qty ?? '?'} ${ingMap[sn.ing_id]?.unit || ''}`,
        'InventorySnapshot', sn,
      );
      if (sn.ing_id) {
        addEdge(`Ing:${sn.ing_id}`, `Snap:${sn.snapshot_id}`, 'LOCATED_AT');
        if (sn.store_id && !es.find(e => e.source === `Store:${sn.store_id}` && e.target === `Ing:${sn.ing_id}`)) {
          addEdge(`Store:${sn.store_id}`, `Ing:${sn.ing_id}`, 'HAS_INGREDIENT');
        }
      }
    });

    // === 全图模式额外节点与关系 ===
    if (isFullMode) {
      // Staff 节点
      (data.staff || []).forEach((s: any) => addNode(
        `Staff:${s.staff_id}`, s.name || s.staff_id, 'Staff', s,
      ));

      // WasteEvent 节点
      (data.waste_events || []).forEach((w: any) => addNode(
        `WasteEvent:${w.event_id}`, `损耗:${w.event_type || w.event_id}`, 'WasteEvent', w,
      ));

      // TrainingModule 节点
      (data.training_modules || []).forEach((m: any) => addNode(
        `TM:${m.module_id}`, m.name || m.module_id, 'TrainingModule', m,
      ));

      const rels = data.relations || {};

      // Store -SIMILAR_TO-> Store
      (rels.similar_to || []).forEach((r: any) => {
        addEdge(`Store:${r.from_id}`, `Store:${r.to_id}`, `SIMILAR_TO(${r.score ?? ''})`);
      });

      // Staff -BELONGS_TO-> Store
      (rels.belongs_to || []).forEach((r: any) => {
        addEdge(`Staff:${r.from_id}`, `Store:${r.to_id}`, 'BELONGS_TO');
      });

      // WasteEvent -TRIGGERED_BY-> Staff
      (rels.triggered_by || []).forEach((r: any) => {
        addEdge(`WasteEvent:${r.from_id}`, `Staff:${r.to_id}`, 'TRIGGERED_BY');
      });

      // Staff -NEEDS_TRAINING-> TrainingModule
      (rels.needs_training || []).forEach((r: any) => {
        addEdge(`Staff:${r.from_id}`, `TM:${r.to_id}`, `NEEDS(${r.urgency || ''})`);
      });

      // Staff -COMPLETED_TRAINING-> TrainingModule
      (rels.completed_training || []).forEach((r: any) => {
        addEdge(`Staff:${r.from_id}`, `TM:${r.to_id}`, `COMPLETED(${r.score ?? ''})`);
      });
    }

    // 过滤掉指向不存在节点的边
    const validEdges = es.filter(e => seen.has(e.source) && seen.has(e.target));
    setNodes(ns);
    setEdges(validEdges);
  }, []);

  const handleLoad = async (values: any) => {
    setLoading(true);
    try {
      const params: any = { tenant_id: values.tenant_id || '' };
      if (values.store_id) params.store_id = values.store_id;
      const endpoint = fullMode ? '/api/v1/ontology/graph-full' : '/api/v1/ontology/export';
      const res = await apiClient.get(endpoint, { params });
      buildGraph(res as any, fullMode);
    } catch (err: any) {
      handleApiError(err, '图谱加载失败');
    } finally {
      setLoading(false);
    }
  };

  // 当前显示的节点类型（基础/全图模式不同）
  const activeNodeTypes = fullMode
    ? Object.keys(NODE_STYLE)
    : Object.keys(NODE_STYLE).slice(0, 5);

  const option = {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => p.data?.name || p.name,
    },
    legend: {
      data: activeNodeTypes.map(k => ({
        name: NODE_STYLE[k].label,
        icon: 'circle',
        textStyle: { color: NODE_STYLE[k].color },
      })),
      bottom: 0,
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        force: { repulsion: fullMode ? 300 : 220, edgeLength: [60, 200], gravity: 0.1 },
        label: { show: true, position: 'right', fontSize: 11 },
        edgeLabel: { show: false },
        lineStyle: { color: '#aaa', curveness: 0.15, width: 1.2 },
        emphasis: { focus: 'adjacency' },
        categories: activeNodeTypes.map(k => ({
          name: NODE_STYLE[k].label,
          itemStyle: { color: NODE_STYLE[k].color },
        })),
        data: nodes.map(n => ({
          id: n.id, name: n.name, category: activeNodeTypes.indexOf(n.type),
          symbolSize: n.symbolSize, itemStyle: n.itemStyle,
          _meta: n.meta, _type: n.type,
        })),
        links: edges.map(e => ({ source: e.source, target: e.target, name: e.label })),
      },
    ],
  };

  const handleChartClick = (params: any) => {
    if (params.dataType === 'node') {
      const node = nodes.find(n => n.id === params.data?.id);
      if (node) { setSelected(node); setDrawerOpen(true); }
    }
  };

  const total = nodes.length;
  const totalEdges = edges.length;

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 0' }}>
      <Title level={3}>
        <ApartmentOutlined style={{ marginRight: 8 }} />
        本体图谱可视化
      </Title>
      <Paragraph type="secondary">
        {fullMode
          ? '全图模式：包含 Staff / WasteEvent / TrainingModule 节点及五类运营关系，呈现完整知识飞轮。'
          : '基础模式：可视化 Store / Dish / BOM / Ingredient / InventorySnapshot 结构节点。'}
        点击节点查看详细属性，支持拖拽和缩放。
      </Paragraph>

      <Card style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" onFinish={handleLoad}>
          <Form.Item name="tenant_id" label="租户 ID">
            <Input placeholder="留空查全部" style={{ width: 140 }} allowClear />
          </Form.Item>
          <Form.Item name="store_id" label="门店 ID">
            <Input placeholder="留空查全部门店" style={{ width: 160 }} allowClear />
          </Form.Item>
          <Form.Item label="全图模式">
            <Switch
              checked={fullMode}
              onChange={v => { setFullMode(v); setNodes([]); setEdges([]); }}
              checkedChildren="全图"
              unCheckedChildren="基础"
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} icon={<ReloadOutlined />}>
              加载图谱
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {total > 0 && (
        <Card
          title={
            <Space wrap>
              <Text strong>图谱概览</Text>
              <Tag color="blue">{total} 节点</Tag>
              <Tag color="geekblue">{totalEdges} 关系</Tag>
              {activeNodeTypes.map(k => {
                const cnt = nodes.filter(n => n.type === k).length;
                return cnt > 0
                  ? <Tag key={k} color={NODE_STYLE[k].color}>{NODE_STYLE[k].label} {cnt}</Tag>
                  : null;
              })}
            </Space>
          }
          style={{ marginBottom: 0 }}
          bodyStyle={{ padding: 0 }}
        >
          <Spin spinning={loading}>
            <ReactECharts
              option={option}
              style={{ height: 620 }}
              onEvents={{ click: handleChartClick }}
            />
          </Spin>
        </Card>
      )}

      {total === 0 && !loading && (
        <Alert
          type="info"
          message={`点击「加载图谱」获取 Neo4j 数据（当前：${fullMode ? '全图模式' : '基础模式'}）`}
          description={
            fullMode
              ? '全图模式需要 Neo4j 中存在 Staff、WasteEvent、TrainingModule 节点，请先完成损耗推理和培训闭环数据写入。'
              : '需要先完成 PG → 图谱同步（POST /ontology/sync-from-pg 或等待每日自动同步）。'
          }
          showIcon
        />
      )}

      <Drawer
        title={selected ? `${NODE_STYLE[selected.type]?.label || selected.type}：${selected.name}` : ''}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={380}
      >
        {selected && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="类型">
              <Tag color={NODE_STYLE[selected.type]?.color || 'default'}>{selected.type}</Tag>
            </Descriptions.Item>
            {Object.entries(selected.meta)
              .filter(([, v]) => v !== null && v !== undefined && v !== '')
              .map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>
                  <Text style={{ fontSize: 12, wordBreak: 'break-all' }}>
                    {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                  </Text>
                </Descriptions.Item>
              ))}
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
};

export default OntologyGraphPage;
