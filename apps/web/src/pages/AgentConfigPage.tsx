import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, InputNumber, Select,
  Switch, Tag, Space, Row, Col, message, Descriptions, Tooltip,
  Checkbox,
} from 'antd';
import {
  RobotOutlined, SettingOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined,
  BellOutlined, AlertOutlined, AuditOutlined,
  UserSwitchOutlined, LineChartOutlined, ExperimentOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../utils/apiClient';
import styles from './AgentConfigPage.module.css';

// ── Constants ────────────────────────────────────────────────────────────────

const AGENT_TYPE_META: Record<string, { label: string; icon: React.ReactNode; color: string; desc: string }> = {
  daily_report: {
    label: '经营日报',
    icon: <BellOutlined />,
    color: '#1677ff',
    desc: '每日推送经营简报（营收/客流/成本率/异常），支持企微/短信通道',
  },
  inventory_alert: {
    label: '库存预警',
    icon: <AlertOutlined />,
    color: '#fa8c16',
    desc: '低库存和临期自动预警，推送至厨师长/店长企微',
  },
  reconciliation: {
    label: '三源对账',
    icon: <AuditOutlined />,
    color: '#52c41a',
    desc: 'POS(品智) vs 库存消耗 vs 采购单三角对账，差异超阈值自动标红告警',
  },
  member_lifecycle: {
    label: '会员生命周期',
    icon: <UserSwitchOutlined />,
    color: '#722ed1',
    desc: '流失预警、生日关怀、RFM分层，自动触发召回任务',
  },
  revenue_anomaly: {
    label: '营收异常检测',
    icon: <LineChartOutlined />,
    color: '#ff4d4f',
    desc: '每15分钟检测营收偏差（>2σ），异常自动推送企微群',
  },
  prep_suggestion: {
    label: '智能备料建议',
    icon: <ExperimentOutlined />,
    color: '#FF6B2C',
    desc: '基于预订+历史+库存生成次日备料量，一键生成采购单',
  },
};

const CHANNEL_OPTIONS = [
  { value: 'wechat', label: '企业微信' },
  { value: 'sms', label: '短信' },
  { value: 'email', label: '邮件' },
  { value: 'in_app', label: '站内通知' },
];

// ── Types ────────────────────────────────────────────────────────────────────

interface AgentConfigItem {
  id: string;
  brand_id: string;
  agent_type: string;
  agent_label: string;
  is_enabled: boolean;
  config: Record<string, unknown>;
  description: string;
  created_at: string | null;
  updated_at: string | null;
}

interface Props {
  brandId: string;
  brandName?: string;
}

// ── Component ────────────────────────────────────────────────────────────────

const AgentConfigPage: React.FC<Props> = ({ brandId, brandName }) => {
  const [agents, setAgents] = useState<AgentConfigItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [editVisible, setEditVisible] = useState(false);
  const [editAgent, setEditAgent] = useState<AgentConfigItem | null>(null);
  const [editForm] = Form.useForm();

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<AgentConfigItem[]>(`/api/v1/agent-configs/${brandId}`);
      setAgents(data);
    } catch {
      message.error('加载 Agent 配置失败');
    } finally {
      setLoading(false);
    }
  }, [brandId]);

  useEffect(() => { fetchAgents(); }, [fetchAgents]);

  const handleToggle = async (agentType: string) => {
    try {
      await apiClient.post(`/api/v1/agent-configs/${brandId}/${agentType}/toggle`, {});
      message.success('状态已切换');
      fetchAgents();
    } catch {
      message.error('操作失败');
    }
  };

  const openEdit = (agent: AgentConfigItem) => {
    setEditAgent(agent);
    editForm.setFieldsValue(agent.config);
    setEditVisible(true);
  };

  const handleSave = async () => {
    if (!editAgent) return;
    try {
      const values = await editForm.validateFields();
      await apiClient.put(`/api/v1/agent-configs/${brandId}/${editAgent.agent_type}`, {
        config: values,
      });
      message.success('配置已保存');
      setEditVisible(false);
      fetchAgents();
    } catch {
      message.error('保存失败');
    }
  };

  // ── Render config form fields based on agent_type ──────────────────────────

  const renderConfigForm = (agentType: string) => {
    switch (agentType) {
      case 'daily_report':
        return (
          <>
            <Form.Item name="push_time" label="推送时间">
              <Input placeholder="07:30" />
            </Form.Item>
            <Form.Item name="channels" label="推送通道">
              <Checkbox.Group options={CHANNEL_OPTIONS} />
            </Form.Item>
            <Form.Item name="include_sections" label="报告模块">
              <Checkbox.Group options={[
                { value: 'revenue', label: '营收' },
                { value: 'traffic', label: '客流' },
                { value: 'food_cost', label: '食材成本率' },
                { value: 'anomalies', label: '关键异常' },
                { value: 'ranking', label: '门店排名' },
              ]} />
            </Form.Item>
          </>
        );

      case 'inventory_alert':
        return (
          <>
            <Form.Item name="low_stock_threshold_pct" label="低库存阈值(%)">
              <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="expiry_days_before" label="临期提前天数">
              <InputNumber min={1} max={30} addonAfter="天" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="check_time" label="检查时间">
              <Input placeholder="10:00" />
            </Form.Item>
            <Form.Item name="channels" label="告警通道">
              <Checkbox.Group options={CHANNEL_OPTIONS} />
            </Form.Item>
          </>
        );

      case 'reconciliation':
        return (
          <>
            <Form.Item name="threshold_pct" label="差异阈值(%)">
              <InputNumber min={0} max={20} step={0.5} addonAfter="%" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="schedule" label="对账频率">
              <Select options={[
                { value: 'daily', label: '每日' },
                { value: 'weekly', label: '每周' },
              ]} />
            </Form.Item>
            <Form.Item name="run_time" label="执行时间">
              <Input placeholder="03:00" />
            </Form.Item>
            <Form.Item name="sources" label="数据源">
              <Checkbox.Group options={[
                { value: 'pos', label: 'POS (品智/天财)' },
                { value: 'inventory', label: '库存消耗' },
                { value: 'procurement', label: '采购单' },
              ]} />
            </Form.Item>
            <Form.Item name="auto_alert" label="自动告警" valuePropName="checked">
              <Switch />
            </Form.Item>
          </>
        );

      case 'member_lifecycle':
        return (
          <>
            <Form.Item name="churn_days" label="流失天数阈值">
              <InputNumber min={30} max={365} addonAfter="天" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="birthday_days_before" label="生日提醒提前">
              <InputNumber min={1} max={14} addonAfter="天" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="rfm_enabled" label="RFM分层" valuePropName="checked">
              <Switch />
            </Form.Item>
          </>
        );

      case 'revenue_anomaly':
        return (
          <>
            <Form.Item name="check_interval_minutes" label="检测频率(分钟)">
              <InputNumber min={5} max={60} addonAfter="分钟" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="threshold_std" label="标准差阈值(σ)">
              <InputNumber min={1} max={5} step={0.5} addonAfter="σ" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="channels" label="告警通道">
              <Checkbox.Group options={CHANNEL_OPTIONS} />
            </Form.Item>
          </>
        );

      case 'prep_suggestion':
        return (
          <>
            <Form.Item name="generate_time" label="生成时间">
              <Input placeholder="16:00" />
            </Form.Item>
            <Form.Item name="safety_factor" label="安全系数">
              <InputNumber min={1.0} max={2.0} step={0.05} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="auto_push" label="自动推送" valuePropName="checked">
              <Switch />
            </Form.Item>
          </>
        );

      default:
        return <div>未知的 Agent 类型</div>;
    }
  };

  // ── Table columns ──────────────────────────────────────────────────────────

  const columns: ColumnsType<AgentConfigItem> = [
    {
      title: 'Agent', dataIndex: 'agent_type', key: 'agent_type', width: 220,
      render: (type: string) => {
        const meta = AGENT_TYPE_META[type];
        if (!meta) return type;
        return (
          <div className={styles.agentCell}>
            <span className={styles.agentIcon} style={{ color: meta.color }}>{meta.icon}</span>
            <div>
              <div className={styles.agentLabel}>{meta.label}</div>
              <div className={styles.agentDesc}>{meta.desc}</div>
            </div>
          </div>
        );
      },
    },
    {
      title: '状态', dataIndex: 'is_enabled', key: 'is_enabled', width: 100,
      render: (enabled: boolean, record: AgentConfigItem) => (
        <Switch
          checked={enabled}
          onChange={() => handleToggle(record.agent_type)}
          checkedChildren="运行中"
          unCheckedChildren="已停用"
        />
      ),
    },
    {
      title: '配置摘要', key: 'summary', width: 260,
      render: (_: unknown, r: AgentConfigItem) => {
        const cfg = r.config;
        const items: string[] = [];
        if (cfg.push_time) items.push(`推送 ${cfg.push_time}`);
        if (cfg.check_time) items.push(`检查 ${cfg.check_time}`);
        if (cfg.run_time) items.push(`执行 ${cfg.run_time}`);
        if (cfg.generate_time) items.push(`生成 ${cfg.generate_time}`);
        if (cfg.threshold_pct) items.push(`阈值 ${cfg.threshold_pct}%`);
        if (cfg.low_stock_threshold_pct) items.push(`低库存 ${cfg.low_stock_threshold_pct}%`);
        if (cfg.churn_days) items.push(`流失 ${cfg.churn_days}天`);
        if (cfg.channels && Array.isArray(cfg.channels)) {
          const labels = (cfg.channels as string[]).map(c =>
            c === 'wechat' ? '企微' : c === 'sms' ? '短信' : c
          );
          items.push(labels.join('+'));
        }
        return <span className={styles.configSummary}>{items.join(' · ') || '默认配置'}</span>;
      },
    },
    {
      title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 120,
      render: (v: string | null) => v ? new Date(v).toLocaleDateString('zh-CN') : '-',
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: unknown, r: AgentConfigItem) => (
        <Button type="link" size="small" icon={<SettingOutlined />} onClick={() => openEdit(r)}>
          配置
        </Button>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <Card
        title={
          <span className={styles.cardTitle}>
            <RobotOutlined className={styles.cardTitleIcon} />
            {brandName ? `${brandName} — Agent 配置` : 'Agent 配置管理'}
          </span>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={fetchAgents}>刷新</Button>
        }
      >
        <div className={styles.statsBar}>
          <Tag icon={<CheckCircleOutlined />} color="success">
            运行中 {agents.filter(a => a.is_enabled).length}
          </Tag>
          <Tag icon={<CloseCircleOutlined />} color="default">
            已停用 {agents.filter(a => !a.is_enabled).length}
          </Tag>
        </div>
        <Table<AgentConfigItem>
          rowKey="id"
          columns={columns}
          dataSource={agents}
          loading={loading}
          pagination={false}
          size="middle"
        />
      </Card>

      {/* Edit Modal */}
      <Modal
        title={editAgent ? `配置 — ${AGENT_TYPE_META[editAgent.agent_type]?.label || editAgent.agent_type}` : '编辑配置'}
        open={editVisible}
        onCancel={() => setEditVisible(false)}
        onOk={handleSave}
        width={520}
        destroyOnClose
      >
        <div className={styles.editDesc}>
          {editAgent && AGENT_TYPE_META[editAgent.agent_type]?.desc}
        </div>
        <Form form={editForm} layout="vertical" preserve={false}>
          {editAgent && renderConfigForm(editAgent.agent_type)}
        </Form>
      </Modal>
    </div>
  );
};

export default AgentConfigPage;
