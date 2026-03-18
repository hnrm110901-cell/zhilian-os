/**
 * 桌台平面图 — 交互式SVG渲染
 * 颜色编码: 绿=空闲, 黄=已订, 红=在座, 灰=维护
 * 支持: 编辑模式拖拽 + 楼层切换 + 30s自动刷新 + 点击弹窗
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Button, Tabs, Tag, Modal, Space, Tooltip, Switch, Select, InputNumber, Input, message } from 'antd';
import {
  EditOutlined, SaveOutlined, PlusOutlined, DeleteOutlined,
  ReloadOutlined, EnvironmentOutlined, UserOutlined,
} from '@ant-design/icons';
import { apiClient } from '../utils/apiClient';
import styles from './FloorPlanPage.module.css';

interface TableData {
  id: string;
  store_id: string;
  table_number: string;
  table_type: string;
  min_capacity: number;
  max_capacity: number;
  pos_x: number;
  pos_y: number;
  width: number;
  height: number;
  rotation: number;
  shape: string;
  floor: number;
  area_name: string;
  status: string;
  is_active: boolean;
  current_reservation?: {
    id: string;
    customer_name: string;
    party_size: number;
    time: string;
    status: string;
  } | null;
  realtime_status?: string;
}

const STATUS_COLORS: Record<string, string> = {
  available: '#4CAF50',
  reserved: '#FF9800',
  occupied: '#F44336',
  maintenance: '#9E9E9E',
};

const STATUS_LABELS: Record<string, string> = {
  available: '空闲',
  reserved: '已订',
  occupied: '在座',
  maintenance: '维护',
};

const FloorPlanPage: React.FC = () => {
  const [tables, setTables] = useState<TableData[]>([]);
  const [loading, setLoading] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [selectedTable, setSelectedTable] = useState<TableData | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [activeFloor, setActiveFloor] = useState(1);
  const [storeId, setStoreId] = useState(localStorage.getItem('store_id') || ''); // default
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragTable, setDragTable] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  const loadTables = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<TableData[]>(
        `/api/v1/floor-plan/${storeId}/tables/realtime?floor=${activeFloor}`
      );
      setTables(data);
    } catch {
      message.error('加载桌台数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, activeFloor]);

  useEffect(() => {
    loadTables();
  }, [loadTables]);

  // 30s auto refresh
  useEffect(() => {
    if (editMode) return;
    const timer = setInterval(loadTables, 30000);
    return () => clearInterval(timer);
  }, [loadTables, editMode]);

  const saveBatchLayout = async () => {
    try {
      await apiClient.put(`/api/v1/floor-plan/${storeId}/tables/batch`, {
        tables: tables.map(t => ({
          id: t.id,
          table_number: t.table_number,
          table_type: t.table_type,
          min_capacity: t.min_capacity,
          max_capacity: t.max_capacity,
          pos_x: t.pos_x,
          pos_y: t.pos_y,
          width: t.width,
          height: t.height,
          rotation: t.rotation,
          shape: t.shape,
          floor: t.floor,
          area_name: t.area_name,
          is_active: t.is_active,
        })),
        deleted_ids: [],
      });
      message.success('布局保存成功');
      setEditMode(false);
      loadTables();
    } catch {
      message.error('保存失败');
    }
  };

  const addTable = () => {
    const newTable: TableData = {
      id: '',
      store_id: storeId,
      table_number: `桌${tables.length + 1}`,
      table_type: '大厅',
      min_capacity: 2,
      max_capacity: 4,
      pos_x: 50,
      pos_y: 50,
      width: 8,
      height: 8,
      rotation: 0,
      shape: 'rect',
      floor: activeFloor,
      area_name: '',
      status: 'available',
      is_active: true,
    };
    setTables([...tables, newTable]);
  };

  // SVG coordinate conversion
  const getSvgPoint = (e: React.MouseEvent) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * 100,
      y: ((e.clientY - rect.top) / rect.height) * 100,
    };
  };

  const handleMouseDown = (e: React.MouseEvent, table: TableData) => {
    if (!editMode) return;
    e.preventDefault();
    const pt = getSvgPoint(e);
    setDragTable(table.id || table.table_number);
    setDragOffset({ x: pt.x - table.pos_x, y: pt.y - table.pos_y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragTable) return;
    const pt = getSvgPoint(e);
    setTables(prev => prev.map(t => {
      if ((t.id || t.table_number) === dragTable) {
        return { ...t, pos_x: pt.x - dragOffset.x, pos_y: pt.y - dragOffset.y };
      }
      return t;
    }));
  };

  const handleMouseUp = () => {
    setDragTable(null);
  };

  const handleTableClick = (table: TableData) => {
    if (editMode) return;
    setSelectedTable(table);
    setDetailVisible(true);
  };

  return (
    <div className={styles.container}>
      {/* Toolbar */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space style={{ width: '100%', justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <Space>
            <Tabs
              activeKey={String(activeFloor)}
              onChange={k => setActiveFloor(Number(k))}
              items={[
                { key: '1', label: '1层' },
                { key: '2', label: '2层' },
                { key: '3', label: '3层' },
              ]}
              size="small"
            />
          </Space>
          <Space>
            {/* Legend */}
            {Object.entries(STATUS_LABELS).map(([k, v]) => (
              <Tag key={k} color={STATUS_COLORS[k]}>{v}</Tag>
            ))}
            <Button icon={<ReloadOutlined />} onClick={loadTables} loading={loading} size="small">
              刷新
            </Button>
            {editMode ? (
              <>
                <Button icon={<PlusOutlined />} onClick={addTable} size="small">添加桌台</Button>
                <Button icon={<SaveOutlined />} type="primary" onClick={saveBatchLayout} size="small">
                  保存布局
                </Button>
                <Button onClick={() => { setEditMode(false); loadTables(); }} size="small">取消</Button>
              </>
            ) : (
              <Button icon={<EditOutlined />} onClick={() => setEditMode(true)} size="small">
                编辑布局
              </Button>
            )}
          </Space>
        </Space>
      </Card>

      {/* SVG Floor Plan */}
      <Card bodyStyle={{ padding: 0, position: 'relative' }}>
        <svg
          ref={svgRef}
          viewBox="0 0 100 100"
          className={styles.floorSvg}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          {/* Grid */}
          <defs>
            <pattern id="grid" width="5" height="5" patternUnits="userSpaceOnUse">
              <path d="M 5 0 L 0 0 0 5" fill="none" stroke="#f0f0f0" strokeWidth="0.1" />
            </pattern>
          </defs>
          <rect width="100" height="100" fill="url(#grid)" />

          {/* Tables */}
          {tables.map(table => {
            const color = STATUS_COLORS[table.realtime_status || table.status] || '#4CAF50';
            const key = table.id || table.table_number;

            return (
              <g
                key={key}
                transform={`translate(${table.pos_x}, ${table.pos_y}) rotate(${table.rotation})`}
                style={{ cursor: editMode ? 'move' : 'pointer' }}
                onMouseDown={e => handleMouseDown(e, table)}
                onClick={() => handleTableClick(table)}
              >
                {table.shape === 'circle' ? (
                  <circle
                    cx={0} cy={0}
                    r={table.width / 2}
                    fill={color}
                    opacity={0.85}
                    stroke="#fff"
                    strokeWidth="0.3"
                  />
                ) : (
                  <rect
                    x={-table.width / 2}
                    y={-table.height / 2}
                    width={table.width}
                    height={table.height}
                    rx={0.8}
                    fill={color}
                    opacity={0.85}
                    stroke="#fff"
                    strokeWidth="0.3"
                  />
                )}
                {/* Table number */}
                <text
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#fff"
                  fontSize="1.6"
                  fontWeight="600"
                >
                  {table.table_number}
                </text>
                {/* Guest info */}
                {table.current_reservation && (
                  <text
                    textAnchor="middle"
                    y={table.height / 2 + 1.8}
                    fill="#666"
                    fontSize="1.2"
                  >
                    {table.current_reservation.customer_name} {table.current_reservation.party_size}人
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </Card>

      {/* Table Detail Modal */}
      <Modal
        title={selectedTable ? `${selectedTable.table_number} - ${STATUS_LABELS[selectedTable.realtime_status || selectedTable.status] || ''}` : ''}
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={null}
        width={400}
      >
        {selectedTable && (
          <div>
            <p><strong>桌号:</strong> {selectedTable.table_number}</p>
            <p><strong>类型:</strong> {selectedTable.table_type}</p>
            <p><strong>容量:</strong> {selectedTable.min_capacity}-{selectedTable.max_capacity}人</p>
            <p><strong>区域:</strong> {selectedTable.area_name || '-'}</p>
            <p>
              <strong>状态:</strong>{' '}
              <Tag color={STATUS_COLORS[selectedTable.realtime_status || selectedTable.status]}>
                {STATUS_LABELS[selectedTable.realtime_status || selectedTable.status]}
              </Tag>
            </p>
            {selectedTable.current_reservation && (
              <Card size="small" title="当前预订" style={{ marginTop: 12 }}>
                <p><UserOutlined /> {selectedTable.current_reservation.customer_name}</p>
                <p>人数: {selectedTable.current_reservation.party_size}人</p>
                <p>时间: {selectedTable.current_reservation.time}</p>
                <p>预订号: {selectedTable.current_reservation.id}</p>
              </Card>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default FloorPlanPage;
