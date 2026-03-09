/**
 * AI Assistant Drawer — 右侧常驻 AI 协作栏
 * 调用 /api/v1/decisions/top3 获取今日 Top3 建议
 * 功能：今日建议 · 一键派发 · 场景识别 · 快捷追问
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Drawer, Space, Button, Tag, Typography, Spin,
  Tooltip, Divider, Badge, message,
  Input, Avatar, Empty, Alert,
} from 'antd';
import {
  RobotOutlined,
  CloseOutlined,
  ReloadOutlined,
  SendOutlined,
  EnvironmentOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import AISuggestionCard from '../design-system/components/AISuggestionCard';

const { Text, Paragraph } = Typography;

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface DecisionItem {
  rank: number;
  title: string;
  action: string;
  source: string;
  expected_saving_yuan: number;
  net_benefit_yuan: number;
  confidence_pct: number;
  urgency_hours: number;
  execution_difficulty: string;
  decision_window_label: string;
  priority_score: number;
}

interface ScenarioInfo {
  scenario_type: string;
  scenario_label: string;
  metrics: Record<string, number | string>;
}

interface ChatMsg {
  role: 'user' | 'assistant';
  text: string;
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const QUICK_QUESTIONS = [
  '为什么今天利润低？',
  '哪个设备能耗异常？',
  '今日需要优先处理什么？',
  '上周同期对比如何？',
];

// ── 主组件 ───────────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onClose: () => void;
  storeId?: string;
}

const AIAssistantDrawer: React.FC<Props> = ({ open, onClose, storeId = 'store_001' }) => {
  const [decisions, setDecisions]       = useState<DecisionItem[]>([]);
  const [scenario, setScenario]         = useState<ScenarioInfo | null>(null);
  const [loading, setLoading]           = useState(false);
  const [chatMsgs, setChatMsgs]         = useState<ChatMsg[]>([]);
  const [inputText, setInputText]       = useState('');
  const [chatLoading, setChatLoading]   = useState(false);
  const [activeTab, setActiveTab]       = useState<'decisions' | 'chat'>('decisions');

  const load = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    try {
      const [decResp, scenResp] = await Promise.allSettled([
        apiClient.get('/api/v1/decisions/top3', { params: { store_id: storeId, monthly_revenue_yuan: 0 } }),
        apiClient.get('/api/v1/decisions/scenario', { params: { store_id: storeId } }),
      ]);

      if (decResp.status === 'fulfilled') {
        setDecisions(decResp.value.data.decisions ?? []);
      }
      if (scenResp.status === 'fulfilled') {
        setScenario(scenResp.value.data);
      }
    } catch {
      // 静默降级，不显示错误（网络不可用时不打断用户）
    } finally {
      setLoading(false);
    }
  }, [open, storeId]);

  useEffect(() => { load(); }, [load]);

  // 派发任务（创建为普通任务，链接到决策）
  const dispatchTask = async (d: DecisionItem) => {
    try {
      await apiClient.post('/api/v1/tasks', {
        title:       d.title,
        description: d.action,
        priority:    d.rank === 1 ? 'high' : 'medium',
        store_id:    storeId,
      });
      message.success('任务已派发');
    } catch {
      message.warning('任务派发需连接后端，当前仅演示');
    }
  };

  // 简易追问（调用 LLM 接口，降级为本地模板回答）
  const askQuestion = async (q: string) => {
    const text = q || inputText.trim();
    if (!text) return;
    setInputText('');
    setChatMsgs(prev => [...prev, { role: 'user', text }]);
    setChatLoading(true);

    try {
      const resp = await apiClient.post('/api/v1/llm/chat', {
        message: text,
        context: `门店ID: ${storeId}，当前场景: ${scenario?.scenario_label ?? '未知'}`,
      });
      const reply = resp.data?.reply ?? resp.data?.content ?? '收到，正在分析...';
      setChatMsgs(prev => [...prev, { role: 'assistant', text: reply }]);
    } catch {
      // 降级：本地模板答复
      const fallback = getFallbackReply(text);
      setChatMsgs(prev => [...prev, { role: 'assistant', text: fallback }]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <Drawer
      title={
        <Space>
          <Avatar
            icon={<RobotOutlined />}
            size={28}
            style={{ backgroundColor: '#1677ff' }}
          />
          <span style={{ fontWeight: 600 }}>AI 经营助手</span>
          {scenario && (
            <Tag color="blue" style={{ fontSize: 11 }}>
              <EnvironmentOutlined /> {scenario.scenario_label}
            </Tag>
          )}
        </Space>
      }
      placement="right"
      width={380}
      open={open}
      onClose={onClose}
      closable={false}
      mask={false}
      style={{ boxShadow: '-4px 0 12px rgba(0,0,0,0.08)' }}
      styles={{ body: { padding: '12px 16px', display: 'flex', flexDirection: 'column', height: '100%' } }}
      extra={
        <Space size={4}>
          <Tooltip title="刷新建议">
            <Button size="small" type="text" icon={<ReloadOutlined />} onClick={load} loading={loading} />
          </Tooltip>
          <Button size="small" type="text" icon={<CloseOutlined />} onClick={onClose} />
        </Space>
      }
    >
      {/* ── Tab 切换 ─────────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <Button
          size="small"
          type={activeTab === 'decisions' ? 'primary' : 'default'}
          onClick={() => setActiveTab('decisions')}
          style={{ flex: 1 }}
        >
          今日建议
        </Button>
        <Button
          size="small"
          type={activeTab === 'chat' ? 'primary' : 'default'}
          onClick={() => setActiveTab('chat')}
          style={{ flex: 1 }}
        >
          追问 AI
        </Button>
      </div>

      {/* ── 今日建议 Tab ─────────────────────────────────────────────────────── */}
      {activeTab === 'decisions' && (
        <div style={{ flex: 1, overflow: 'auto' }}>
          {loading ? (
            <Spin style={{ display: 'block', margin: '40px auto' }} />
          ) : decisions.length === 0 ? (
            <Empty description="暂无建议（门店数据不足）" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            decisions.map((d) => (
              <AISuggestionCard
                key={d.rank}
                rank={d.rank}
                title={d.title}
                action={d.action}
                savingYuan={d.expected_saving_yuan}
                confidencePct={d.confidence_pct}
                difficulty={d.execution_difficulty as any}
                windowLabel={d.decision_window_label}
                source={d.source}
                dispatchLabel="派发给店长执行"
                onDispatch={() => dispatchTask(d)}
              />
            ))
          )}

          {decisions.length > 0 && (
            <>
              <Divider style={{ margin: '8px 0', fontSize: 12 }}>快捷追问</Divider>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {QUICK_QUESTIONS.map(q => (
                  <Button
                    key={q}
                    size="small"
                    style={{ fontSize: 11 }}
                    onClick={() => { setActiveTab('chat'); askQuestion(q); }}
                  >
                    {q}
                  </Button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── 追问 AI Tab ──────────────────────────────────────────────────────── */}
      {activeTab === 'chat' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* 快捷问题 */}
          {chatMsgs.length === 0 && (
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                快捷追问：
              </Text>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {QUICK_QUESTIONS.map(q => (
                  <Button key={q} size="small" style={{ fontSize: 11 }} onClick={() => askQuestion(q)}>
                    {q}
                  </Button>
                ))}
              </div>
              <Divider style={{ margin: '12px 0' }} />
            </div>
          )}

          {/* 消息列表 */}
          <div style={{ flex: 1, overflow: 'auto', marginBottom: 12 }}>
            {chatMsgs.map((m, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                  marginBottom: 10,
                }}
              >
                {m.role === 'assistant' && (
                  <Avatar
                    icon={<RobotOutlined />}
                    size={24}
                    style={{ backgroundColor: '#1677ff', marginRight: 8, flexShrink: 0 }}
                  />
                )}
                <div
                  style={{
                    maxWidth: '80%',
                    padding: '8px 12px',
                    borderRadius: m.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                    background: m.role === 'user' ? '#1677ff' : '#f5f5f5',
                    color: m.role === 'user' ? 'white' : '#333',
                    fontSize: 13,
                    lineHeight: '1.5',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Avatar
                  icon={<RobotOutlined />}
                  size={24}
                  style={{ backgroundColor: '#1677ff' }}
                />
                <Spin size="small" />
                <Text type="secondary" style={{ fontSize: 12 }}>AI 正在思考...</Text>
              </div>
            )}
          </div>

          {/* 输入框 */}
          <div style={{ display: 'flex', gap: 8 }}>
            <Input
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              onPressEnter={() => askQuestion('')}
              placeholder="追问 AI（如：为什么今天利润低？）"
              size="small"
              style={{ flex: 1 }}
            />
            <Button
              type="primary"
              size="small"
              icon={<SendOutlined />}
              onClick={() => askQuestion('')}
              disabled={!inputText.trim()}
            />
          </div>
        </div>
      )}
    </Drawer>
  );
};

// ── 本地降级回答 ──────────────────────────────────────────────────────────────

function getFallbackReply(q: string): string {
  const lower = q.toLowerCase();
  if (lower.includes('利润') || lower.includes('亏')) {
    return '影响今日利润的常见因素：①食材损耗率偏高（建议核查当日BOM出品差异）②人工成本超排（对比客流与在岗人数）③非营业时段能耗（建议查看能耗Agent异常中心）。';
  }
  if (lower.includes('能耗') || lower.includes('用电') || lower.includes('电费')) {
    return '请前往「智能体中心 > 能耗Agent > 异常中心」查看当前未处理能耗异常，或触发今日日期的异常扫描，系统将自动分析5类规则。';
  }
  if (lower.includes('库存') || lower.includes('备货')) {
    return '库存建议：①查看库存预警列表，重点关注剩余量<安全库存50%的食材②核对今日预计客流量，提前备货高频消耗品③与供应商确认明日配送窗口。';
  }
  if (lower.includes('员工') || lower.includes('排班')) {
    return '今日人力建议：①对比历史同周期客流，确认当前在岗人数是否匹配②检查是否存在未到岗/迟到记录③高峰时段（12:00-13:00 / 18:00-20:00）确保核心岗位有人。';
  }
  return `关于"${q}"：请确认后端 LLM 服务已配置，当前为离线降级模式。如需精准分析，请连接 /api/v1/llm/chat 接口并配置 ANTHROPIC_API_KEY 或 OPENAI_API_KEY。`;
}

export default AIAssistantDrawer;
