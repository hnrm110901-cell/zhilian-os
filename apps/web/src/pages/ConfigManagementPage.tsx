import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Tree, Tabs, Button, Modal, Form, Input, InputNumber,
  Select, Space, Row, Col, message, Popconfirm, Spin, Tooltip,
  Typography, Tag, Divider, Empty,
} from 'antd';
import {
  ReloadOutlined, EditOutlined, DeleteOutlined, CopyOutlined,
  ApartmentOutlined, SettingOutlined,
} from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import { apiClient } from '../utils/apiClient';
import styles from './ConfigManagementPage.module.css';

const { Text, Title } = Typography;

// ── 配置分组 ──────────────────────────────────────────────────────────────────

interface ConfigKeyDef {
  key: string;
  label: string;
  type: 'float' | 'int' | 'string' | 'bool' | 'json';
  unit?: string;
}

interface ConfigTabDef {
  key: string;
  label: string;
  keys: ConfigKeyDef[];
}

const CONFIG_TABS: ConfigTabDef[] = [
  {
    key: 'kpi',
    label: 'KPI目标',
    keys: [
      { key: 'food_cost_ratio_target', label: '食材成本率目标', type: 'float', unit: '%' },
      { key: 'labor_cost_ratio_target', label: '人力成本率目标', type: 'float', unit: '%' },
      { key: 'csat_target', label: '客户满意度目标', type: 'float' },
      { key: 'revenue_growth_target', label: '营收增长目标', type: 'float', unit: '%' },
      { key: 'baseline_table_turnover', label: '翻台率基准', type: 'float', unit: '次/天' },
    ],
  },
  {
    key: 'schedule',
    label: '排班规则',
    keys: [
      { key: 'shift_morning_start', label: '早班开始', type: 'string' },
      { key: 'shift_morning_end', label: '早班结束', type: 'string' },
      { key: 'shift_afternoon_start', label: '中班开始', type: 'string' },
      { key: 'shift_afternoon_end', label: '中班结束', type: 'string' },
      { key: 'shift_evening_start', label: '晚班开始', type: 'string' },
      { key: 'shift_evening_end', label: '晚班结束', type: 'string' },
      { key: 'schedule_min_shift_hours', label: '最短班次时长(h)', type: 'int' },
      { key: 'schedule_max_shift_hours', label: '最长班次时长(h)', type: 'int' },
      { key: 'schedule_max_weekly_hours', label: '周最大工时(h)', type: 'int' },
      { key: 'max_consecutive_work_days', label: '最大连续工作天数', type: 'int' },
    ],
  },
  {
    key: 'member',
    label: '会员体系',
    keys: [
      { key: 'member_discount_rate', label: '会员折扣率', type: 'float', unit: '%' },
      { key: 'coupon_discount_amount', label: '优惠券面额(元)', type: 'float' },
      { key: 'member_first_spend_threshold', label: '首消触发金额(元)', type: 'float' },
      { key: 'member_consecutive_months', label: '连续消费月数阈值', type: 'int' },
      { key: 'points_expiring_alert_days', label: '积分过期预警天数', type: 'int' },
    ],
  },
  {
    key: 'alert',
    label: '告警阈值',
    keys: [
      { key: 'food_cost_alert_threshold', label: '食材成本率告警线', type: 'float', unit: '%' },
      { key: 'labor_cost_alert_threshold', label: '人力成本率告警线', type: 'float', unit: '%' },
      { key: 'labor_cost_warning_threshold', label: '人力成本率预警线', type: 'float', unit: '%' },
      { key: 'dish_return_rate_alert', label: '退菜率告警线', type: 'float', unit: '%' },
      { key: 'inventory_low_stock_ratio', label: '库存低位告警比例', type: 'float' },
      { key: 'inventory_expiring_days', label: '库存过期预警天数', type: 'int' },
    ],
  },
  {
    key: 'marketing',
    label: '营销规则',
    keys: [
      { key: 'referral_family_min_party', label: '家宴触发最小人数', type: 'int' },
      { key: 'referral_business_min_party', label: '商务宴触发最小人数', type: 'int' },
      { key: 'referral_super_fan_frequency', label: '超级粉丝频率(30天)', type: 'int' },
      { key: 'holiday_promotion_advance_days', label: '节假日提前推送天数', type: 'int' },
    ],
  },
];

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface OrgNode {
  node_id: string;
  name: string;
  node_type: 'group' | 'brand' | 'region' | 'store';
  parent_id: string | null;
  children?: OrgNode[];
}

interface ConfigEntry {
  key: string;
  value: unknown;
  source_node_id: string;
  source_node_name: string;
  is_inherited: boolean;
}

interface NodeConfig {
  node_id: string;
  node_name: string;
  configs: ConfigEntry[];
}

// ── 辅助函数 ──────────────────────────────────────────────────────────────────

function buildTreeData(nodes: OrgNode[]): DataNode[] {
  return nodes.map((n) => ({
    key: n.node_id,
    title: n.name,
    icon: <ApartmentOutlined />,
    children: n.children ? buildTreeData(n.children) : undefined,
  }));
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

// ── 编辑对话框 ────────────────────────────────────────────────────────────────

interface EditModalProps {
  open: boolean;
  configKey: ConfigKeyDef | null;
  currentValue: unknown;
  nodeId: string | null;
  onClose: () => void;
  onSaved: () => void;
}

const EditModal: React.FC<EditModalProps> = ({
  open, configKey, currentValue, nodeId, onClose, onSaved,
}) => {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && configKey) {
      form.setFieldsValue({ value: currentValue });
    }
  }, [open, configKey, currentValue, form]);

  const handleSave = async () => {
    if (!nodeId || !configKey) return;
    try {
      const values = await form.validateFields();
      setSaving(true);
      await apiClient.post(`/api/v1/org/nodes/${nodeId}/config`, {
        key: configKey.key,
        value: values.value,
      });
      message.success('配置已保存');
      onSaved();
      onClose();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) return; // 表单验证失败
      message.error('保存失败，请重试');
    } finally {
      setSaving(false);
    }
  };

  const renderInput = (def: ConfigKeyDef) => {
    switch (def.type) {
      case 'float':
        return (
          <InputNumber
            style={{ width: '100%' }}
            step={0.01}
            precision={4}
            addonAfter={def.unit}
            placeholder={`请输入${def.label}`}
          />
        );
      case 'int':
        return (
          <InputNumber
            style={{ width: '100%' }}
            precision={0}
            addonAfter={def.unit}
            placeholder={`请输入${def.label}`}
          />
        );
      case 'bool':
        return (
          <Select style={{ width: '100%' }} placeholder="请选择">
            <Select.Option value={true}>是</Select.Option>
            <Select.Option value={false}>否</Select.Option>
          </Select>
        );
      case 'json':
        return (
          <Input.TextArea
            rows={4}
            placeholder={`请输入 JSON（${def.label}）`}
          />
        );
      default:
        return (
          <Input
            addonAfter={def.unit}
            placeholder={`请输入${def.label}`}
          />
        );
    }
  };

  return (
    <Modal
      title={`编辑配置：${configKey?.label ?? ''}`}
      open={open}
      onOk={handleSave}
      onCancel={onClose}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      destroyOnClose
    >
      {configKey && (
        <Form form={form} layout="vertical">
          <Form.Item
            label={configKey.label}
            name="value"
            rules={[{ required: true, message: '请输入配置值' }]}
          >
            {renderInput(configKey)}
          </Form.Item>
          <Text type="secondary" style={{ fontSize: 12 }}>
            配置项：<code>{configKey.key}</code>（类型：{configKey.type}
            {configKey.unit ? `，单位：${configKey.unit}` : ''}）
          </Text>
        </Form>
      )}
    </Modal>
  );
};

// ── 批量复制对话框 ──────────────────────────────────────────────────────────────

interface CopyModalProps {
  open: boolean;
  nodeId: string | null;
  onClose: () => void;
  onCopied: () => void;
}

const CopyModal: React.FC<CopyModalProps> = ({ open, nodeId, onClose, onCopied }) => {
  const [sourceId, setSourceId] = useState('');
  const [copying, setCopying] = useState(false);

  const handleCopy = async () => {
    if (!nodeId || !sourceId.trim()) {
      message.warning('请输入源节点ID');
      return;
    }
    setCopying(true);
    try {
      await apiClient.post(
        `/api/v1/org/nodes/${nodeId}/config/copy-from/${sourceId.trim()}`,
        {},
      );
      message.success('配置复制成功');
      onCopied();
      onClose();
      setSourceId('');
    } catch {
      message.error('复制失败，请检查源节点ID是否正确');
    } finally {
      setCopying(false);
    }
  };

  return (
    <Modal
      title="批量复制配置"
      open={open}
      onOk={handleCopy}
      onCancel={() => { onClose(); setSourceId(''); }}
      confirmLoading={copying}
      okText="复制"
      cancelText="取消"
      destroyOnClose
    >
      <Form layout="vertical">
        <Form.Item
          label="源节点ID"
          required
          help="将从该节点复制所有本地配置项到当前节点（覆盖同名配置）"
        >
          <Input
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
            placeholder="请输入源节点的 node_id"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};

// ── 配置项列表（单个 Tab 内容） ─────────────────────────────────────────────────

interface ConfigItemRowProps {
  def: ConfigKeyDef;
  entry: ConfigEntry | undefined;
  nodeId: string;
  onEdit: (def: ConfigKeyDef, entry: ConfigEntry | undefined) => void;
  onReset: (key: string) => void;
  resetting: string | null;
}

const ConfigItemRow: React.FC<ConfigItemRowProps> = ({
  def, entry, nodeId: _nodeId, onEdit, onReset, resetting,
}) => {
  const isInherited = entry?.is_inherited ?? true;
  const hasValue = entry !== undefined;

  return (
    <div className={styles.configRow}>
      <div className={styles.configRowMain}>
        <div className={styles.configKey}>
          <span className={styles.configLabel}>{def.label}</span>
          <code className={styles.configKeyCode}>{def.key}</code>
        </div>
        <div className={styles.configValue}>
          {hasValue ? (
            <span className={isInherited ? styles.valueInherited : styles.valueLocal}>
              {formatValue(entry?.value)}
              {def.unit && <span className={styles.valueUnit}> {def.unit}</span>}
            </span>
          ) : (
            <span className={styles.valueEmpty}>未设置</span>
          )}
        </div>
        <div className={styles.configSource}>
          {isInherited && entry ? (
            <Tag color="default" className={styles.inheritTag}>
              继承自：{entry.source_node_name}
            </Tag>
          ) : !isInherited && entry ? (
            <Tag color="blue" className={styles.localTag}>本节点</Tag>
          ) : (
            <Tag color="default">无</Tag>
          )}
        </div>
        <div className={styles.configActions}>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => onEdit(def, entry)}
          >
            编辑
          </Button>
          {!isInherited && entry && (
            <Popconfirm
              title="重置为继承值"
              description="将删除本节点的配置，恢复继承父节点的值。确认操作？"
              onConfirm={() => onReset(def.key)}
              okText="确认"
              cancelText="取消"
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={resetting === def.key}
              >
                重置为继承
              </Button>
            </Popconfirm>
          )}
        </div>
      </div>
    </div>
  );
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

const ConfigManagementPage: React.FC = () => {
  // 组织树
  const [treeData, setTreeData] = useState<DataNode[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);

  // 选中节点
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodeName, setSelectedNodeName] = useState<string>('');

  // 配置数据
  const [nodeConfig, setNodeConfig] = useState<NodeConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(false);

  // Tab
  const [activeTab, setActiveTab] = useState('kpi');

  // 编辑对话框
  const [editOpen, setEditOpen] = useState(false);
  const [editingDef, setEditingDef] = useState<ConfigKeyDef | null>(null);
  const [editingEntry, setEditingEntry] = useState<ConfigEntry | undefined>(undefined);

  // 复制对话框
  const [copyOpen, setCopyOpen] = useState(false);

  // 重置中的 key
  const [resetting, setResetting] = useState<string | null>(null);

  // ── 加载组织树 ────────────────────────────────────────────────────────────

  const fetchTree = useCallback(async () => {
    setTreeLoading(true);
    try {
      // 获取根节点的子树（node_id = root 或平台根）
      const data = await apiClient.get<OrgNode[]>('/api/v1/org/nodes/root/subtree');
      setTreeData(buildTreeData(data));
      // 默认展开第一层
      if (data.length > 0) {
        setExpandedKeys(data.map((n) => n.node_id));
      }
    } catch {
      message.error('加载组织树失败');
    } finally {
      setTreeLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTree();
  }, [fetchTree]);

  // ── 加载节点配置 ──────────────────────────────────────────────────────────

  const fetchNodeConfig = useCallback(async (nodeId: string) => {
    setConfigLoading(true);
    setNodeConfig(null);
    try {
      const data = await apiClient.get<NodeConfig>(`/api/v1/org/nodes/${nodeId}/config`);
      setNodeConfig(data);
    } catch {
      message.error('加载配置失败');
    } finally {
      setConfigLoading(false);
    }
  }, []);

  const handleNodeSelect = (keys: React.Key[], info: { node: DataNode }) => {
    if (keys.length === 0) return;
    const nodeId = String(keys[0]);
    setSelectedNodeId(nodeId);
    setSelectedNodeName(String(info.node.title ?? ''));
    fetchNodeConfig(nodeId);
  };

  // ── 编辑配置 ──────────────────────────────────────────────────────────────

  const handleEdit = (def: ConfigKeyDef, entry: ConfigEntry | undefined) => {
    setEditingDef(def);
    setEditingEntry(entry);
    setEditOpen(true);
  };

  // ── 重置为继承 ────────────────────────────────────────────────────────────

  const handleReset = async (key: string) => {
    if (!selectedNodeId) return;
    setResetting(key);
    try {
      await apiClient.delete(`/api/v1/org/nodes/${selectedNodeId}/config/${key}`);
      message.success('已重置为继承值');
      fetchNodeConfig(selectedNodeId);
    } catch {
      message.error('重置失败，请重试');
    } finally {
      setResetting(null);
    }
  };

  // ── 查找配置项 ────────────────────────────────────────────────────────────

  const getEntry = (key: string): ConfigEntry | undefined =>
    nodeConfig?.configs.find((c) => c.key === key);

  // ── Tab 项 ────────────────────────────────────────────────────────────────

  const tabItems = CONFIG_TABS.map((tab) => ({
    key: tab.key,
    label: tab.label,
    children: (
      <div className={styles.configList}>
        {tab.keys.map((def) => (
          <ConfigItemRow
            key={def.key}
            def={def}
            entry={getEntry(def.key)}
            nodeId={selectedNodeId ?? ''}
            onEdit={handleEdit}
            onReset={handleReset}
            resetting={resetting}
          />
        ))}
      </div>
    ),
  }));

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  return (
    <div className={styles.container}>
      {/* 页面标题栏 */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <Title level={4} style={{ margin: 0 }}>运维配置管理</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            按组织节点管理 KPI 目标、排班规则、会员体系、告警阈值等配置，支持多级继承
          </Text>
        </div>
        <div className={styles.headerActions}>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              fetchTree();
              if (selectedNodeId) fetchNodeConfig(selectedNodeId);
            }}
          >
            刷新
          </Button>
        </div>
      </div>

      {/* 主体：左侧组织树 + 右侧配置面板 */}
      <Row gutter={16} className={styles.mainContent}>
        {/* 左侧：组织树 */}
        <Col flex="280px">
          <Card
            size="small"
            title={
              <Space>
                <ApartmentOutlined />
                <span>组织树</span>
              </Space>
            }
            className={styles.treeCard}
            bodyStyle={{ padding: '12px 8px' }}
          >
            {treeLoading ? (
              <div className={styles.treeLoading}>
                <Spin size="small" />
              </div>
            ) : treeData.length === 0 ? (
              <Empty description="暂无组织数据" imageStyle={{ height: 40 }} />
            ) : (
              <Tree
                showIcon
                expandedKeys={expandedKeys}
                selectedKeys={selectedNodeId ? [selectedNodeId] : []}
                onExpand={(keys) => setExpandedKeys(keys)}
                onSelect={handleNodeSelect}
                treeData={treeData}
                className={styles.orgTree}
              />
            )}
          </Card>
        </Col>

        {/* 右侧：配置详情 */}
        <Col flex="1">
          <Card
            size="small"
            title={
              selectedNodeId ? (
                <Space>
                  <SettingOutlined />
                  <span>配置详情</span>
                  <Divider type="vertical" />
                  <Text strong>{selectedNodeName}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    ({selectedNodeId})
                  </Text>
                </Space>
              ) : (
                <Space>
                  <SettingOutlined />
                  <span>配置详情</span>
                </Space>
              )
            }
            extra={
              selectedNodeId && (
                <Space>
                  <Tooltip title="从另一节点批量复制配置">
                    <Button
                      size="small"
                      icon={<CopyOutlined />}
                      onClick={() => setCopyOpen(true)}
                    >
                      批量复制
                    </Button>
                  </Tooltip>
                </Space>
              )
            }
            className={styles.detailCard}
          >
            {!selectedNodeId ? (
              <Empty
                description="请在左侧选择一个组织节点"
                imageStyle={{ height: 60 }}
                style={{ padding: '40px 0' }}
              />
            ) : configLoading ? (
              <div className={styles.configLoading}>
                <Spin size="default" tip="加载配置中..." />
              </div>
            ) : (
              <Tabs
                activeKey={activeTab}
                onChange={setActiveTab}
                items={tabItems}
                size="small"
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* 编辑对话框 */}
      <EditModal
        open={editOpen}
        configKey={editingDef}
        currentValue={editingEntry?.value}
        nodeId={selectedNodeId}
        onClose={() => setEditOpen(false)}
        onSaved={() => selectedNodeId && fetchNodeConfig(selectedNodeId)}
      />

      {/* 批量复制对话框 */}
      <CopyModal
        open={copyOpen}
        nodeId={selectedNodeId}
        onClose={() => setCopyOpen(false)}
        onCopied={() => selectedNodeId && fetchNodeConfig(selectedNodeId)}
      />
    </div>
  );
};

export default ConfigManagementPage;
