/**
 * 门店全天业务流程节点管理 — 店长工作台
 * 路由: /sm/daily-flow
 *
 * 功能：
 * 1. 全天节点时间轴（当前节点高亮）
 * 2. 当前节点任务列表（可提交/可拍照）
 * 3. 进度概览（完成率/超时数/异常数）
 * 4. 快速操作（完成节点/上报异常/跳过节点）
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Card, Progress, Tag, Button, List, Space, Badge, message, Modal, Input, Timeline, Descriptions, Empty, Spin } from 'antd';
import {
  CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined,
  PlayCircleOutlined, StopOutlined, WarningOutlined,
  RightOutlined, CameraOutlined, FormOutlined
} from '@ant-design/icons';
import apiClient from '../../services/api';

const { TextArea } = Input;

interface NodeData {
  id: string;
  node_code: string;
  node_name: string;
  node_order: number;
  status: string;
  scheduled_start: string;
  scheduled_end: string;
  actual_start?: string;
  actual_end?: string;
  total_tasks: number;
  completed_tasks: number;
  is_optional: boolean;
}

interface TaskData {
  id: string;
  task_code: string;
  task_name: string;
  task_order: number;
  is_required: boolean;
  status: string;
  proof_type: string;
  assignee_role: string;
  submitted_at?: string;
  remark?: string;
}

interface ProgressData {
  total_nodes: number;
  completed_nodes: number;
  progress_pct: number;
  current_node?: NodeData;
  overdue_nodes: string[];
  status: string;
}

const STATUS_MAP: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  pending:     { color: 'default',    icon: <ClockCircleOutlined />,         label: '待开始' },
  in_progress: { color: 'processing', icon: <PlayCircleOutlined />,          label: '进行中' },
  completed:   { color: 'success',    icon: <CheckCircleOutlined />,         label: '已完成' },
  overdue:     { color: 'error',      icon: <ExclamationCircleOutlined />,   label: '已超时' },
  skipped:     { color: 'warning',    icon: <StopOutlined />,                label: '已跳过' },
};

const TASK_STATUS: Record<string, { color: string; label: string }> = {
  todo: { color: 'default', label: '待处理' },
  doing: { color: 'processing', label: '处理中' },
  done: { color: 'success', label: '已完成' },
  overtime: { color: 'error', label: '已超时' },
};

const DailyFlow: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [selectedNode, setSelectedNode] = useState<NodeData | null>(null);
  const [tasks, setTasks] = useState<TaskData[]>([]);
  const [canComplete, setCanComplete] = useState(false);
  const [blockingReasons, setBlockingReasons] = useState<string[]>([]);
  const [incidentModalOpen, setIncidentModalOpen] = useState(false);
  const [incidentTitle, setIncidentTitle] = useState('');

  const storeId = localStorage.getItem('store_id') || 'CZYZ-2461';
  const brandId = localStorage.getItem('brand_id') || 'BRD_CZYZ0001';
  const today = new Date().toISOString().slice(0, 10);

  const loadFlow = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.post('/api/v1/daily-flow/mobile/init-flow', {
        store_id: storeId,
        brand_id: brandId,
        biz_date: today,
        business_mode: 'lunch_dinner',
      });
      const data = resp.data;
      setProgress(data.progress);
      setNodes(data.nodes || []);

      // 自动选中当前节点
      if (data.progress?.current_node) {
        const cur = (data.nodes || []).find(
          (n: NodeData) => n.id === data.progress.current_node?.id
        ) || data.nodes?.[0];
        if (cur) loadNodeDetail(cur);
      }
    } catch {
      message.error('加载流程失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, brandId, today]);

  const loadNodeDetail = async (node: NodeData) => {
    setSelectedNode(node);
    try {
      const resp = await apiClient.get(`/api/v1/daily-flow/mobile/node/${node.id}`);
      setTasks(resp.data.tasks || []);
      setCanComplete(resp.data.can_complete);
      setBlockingReasons(resp.data.blocking_reasons || []);
    } catch {
      setTasks([]);
    }
  };

  const submitTask = async (taskId: string) => {
    try {
      await apiClient.post('/api/v1/daily-flow/mobile/task/submit', {
        task_instance_id: taskId,
        submitted_by: 'current_user',
      });
      message.success('任务已提交');
      if (selectedNode) loadNodeDetail(selectedNode);
      loadFlow();
    } catch {
      message.error('提交失败');
    }
  };

  const completeNode = async () => {
    if (!selectedNode) return;
    try {
      await apiClient.post('/api/v1/daily-flow/mobile/node/complete', {
        node_instance_id: selectedNode.id,
        completed_by: 'current_user',
      });
      message.success(`${selectedNode.node_name} 已完成`);
      loadFlow();
    } catch (e: any) {
      message.error(e.response?.data?.detail || '完成失败');
    }
  };

  const reportIncident = async () => {
    if (!incidentTitle.trim()) return;
    try {
      await apiClient.post('/api/v1/daily-flow/mobile/incident/create', {
        store_id: storeId,
        brand_id: brandId,
        biz_date: today,
        incident_type: 'general',
        severity: 'medium',
        title: incidentTitle,
        reporter_id: 'current_user',
      });
      message.success('异常已上报');
      setIncidentModalOpen(false);
      setIncidentTitle('');
    } catch {
      message.error('上报失败');
    }
  };

  useEffect(() => { loadFlow(); }, [loadFlow]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  const timeStr = (iso: string) => {
    if (!iso) return '--';
    return iso.includes('T') ? iso.split('T')[1]?.slice(0, 5) : iso.slice(11, 16);
  };

  return (
    <div style={{ padding: 16, maxWidth: 800, margin: '0 auto' }}>
      {/* 进度概览 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 600 }}>今日流程</div>
            <div style={{ color: '#999', fontSize: 12 }}>{today}</div>
          </div>
          <Progress
            type="circle"
            percent={progress?.progress_pct || 0}
            size={64}
            format={(pct) => `${pct}%`}
          />
        </div>
        <div style={{ display: 'flex', gap: 16, marginTop: 12 }}>
          <Tag color="green">{progress?.completed_nodes || 0} 完成</Tag>
          <Tag color="blue">{(progress?.total_nodes || 0) - (progress?.completed_nodes || 0)} 剩余</Tag>
          {(progress?.overdue_nodes?.length || 0) > 0 && (
            <Tag color="red">{progress?.overdue_nodes?.length} 超时</Tag>
          )}
        </div>
      </Card>

      {/* 节点时间轴 */}
      <Card title="节点时间轴" size="small" style={{ marginBottom: 16 }}
            extra={
              <Button size="small" danger icon={<WarningOutlined />}
                      onClick={() => setIncidentModalOpen(true)}>
                上报异常
              </Button>
            }>
        <Timeline>
          {nodes.map((node) => {
            const st = STATUS_MAP[node.status] || STATUS_MAP.pending;
            const isCurrent = selectedNode?.id === node.id;
            return (
              <Timeline.Item
                key={node.id}
                color={st.color === 'default' ? 'gray' : st.color === 'processing' ? 'blue' : st.color === 'success' ? 'green' : st.color === 'error' ? 'red' : 'gray'}
              >
                <div
                  onClick={() => loadNodeDetail(node)}
                  style={{
                    cursor: 'pointer',
                    padding: '8px 12px',
                    borderRadius: 8,
                    background: isCurrent ? '#e6f4ff' : 'transparent',
                    border: isCurrent ? '1px solid #91caff' : '1px solid transparent',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Space>
                      {st.icon}
                      <span style={{ fontWeight: isCurrent ? 600 : 400 }}>{node.node_name}</span>
                      <Tag color={st.color}>{st.label}</Tag>
                    </Space>
                    <span style={{ color: '#999', fontSize: 12 }}>
                      {timeStr(node.scheduled_start)}-{timeStr(node.scheduled_end)}
                    </span>
                  </div>
                  {node.total_tasks > 0 && (
                    <Progress
                      percent={Math.round((node.completed_tasks / node.total_tasks) * 100)}
                      size="small"
                      style={{ marginTop: 4 }}
                    />
                  )}
                </div>
              </Timeline.Item>
            );
          })}
        </Timeline>
      </Card>

      {/* 当前节点任务 */}
      {selectedNode && (
        <Card
          title={`${selectedNode.node_name} — 任务列表`}
          size="small"
          extra={
            selectedNode.status === 'in_progress' && (
              <Button
                type="primary"
                disabled={!canComplete}
                onClick={completeNode}
                icon={<CheckCircleOutlined />}
              >
                完成节点
              </Button>
            )
          }
        >
          {blockingReasons.length > 0 && (
            <div style={{ marginBottom: 12, padding: 8, background: '#fff7e6', borderRadius: 4 }}>
              {blockingReasons.map((r, i) => (
                <div key={i} style={{ color: '#d48806' }}>
                  <ExclamationCircleOutlined /> {r}
                </div>
              ))}
            </div>
          )}

          {tasks.length === 0 ? (
            <Empty description="该节点无任务" />
          ) : (
            <List
              dataSource={tasks}
              renderItem={(task) => {
                const ts = TASK_STATUS[task.status] || TASK_STATUS.todo;
                return (
                  <List.Item
                    actions={
                      task.status === 'todo' || task.status === 'doing'
                        ? [
                            <Button
                              key="submit"
                              type="primary"
                              size="small"
                              icon={task.proof_type === 'photo' ? <CameraOutlined /> : <FormOutlined />}
                              onClick={() => submitTask(task.id)}
                            >
                              提交
                            </Button>,
                          ]
                        : []
                    }
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <span>{task.task_name}</span>
                          {task.is_required && <Tag color="red">必需</Tag>}
                          <Tag color={ts.color}>{ts.label}</Tag>
                        </Space>
                      }
                      description={task.submitted_at ? `提交于 ${task.submitted_at.slice(11, 16)}` : task.assignee_role}
                    />
                  </List.Item>
                );
              }}
            />
          )}
        </Card>
      )}

      {/* 上报异常弹窗 */}
      <Modal
        title="上报异常"
        open={incidentModalOpen}
        onOk={reportIncident}
        onCancel={() => setIncidentModalOpen(false)}
        okText="提交"
      >
        <TextArea
          rows={3}
          placeholder="请描述异常情况..."
          value={incidentTitle}
          onChange={(e) => setIncidentTitle(e.target.value)}
        />
      </Modal>
    </div>
  );
};

export default DailyFlow;
