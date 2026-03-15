/**
 * 审批管理页面
 * 路由: /approval-management
 * 功能: 待审批列表 + 审批模板管理 + 审批/驳回操作
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Card, Table, Tag, Button, Tabs, Modal, Form, Input, Space,
  message, Typography, Spin, Select,
} from 'antd';
import {
  CheckCircleOutlined, CloseCircleOutlined, PlusOutlined,
  AuditOutlined,
} from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { ApprovalInstanceItem, ApprovalTemplateItem } from '../../services/hrService';

const { Title } = Typography;
const { TextArea } = Input;

const BRAND_ID = localStorage.getItem('brand_id') || 'BRAND_001';
const CURRENT_USER_ID = localStorage.getItem('user_id') || 'current_user';
const CURRENT_USER_NAME = localStorage.getItem('user_name') || '当前用户';

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待审批', color: 'processing' },
  approved: { label: '已通过', color: 'success' },
  rejected: { label: '已驳回', color: 'error' },
  cancelled: { label: '已取消', color: 'default' },
};

const BIZ_TYPE_LABELS: Record<string, string> = {
  leave_request: '请假', salary_adjust: '调薪', resign: '离职',
  reward_penalty: '奖惩', contract: '合同', other: '其他',
};

const ApprovalManagementPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('pending');
  const [pendingList, setPendingList] = useState<ApprovalInstanceItem[]>([]);
  const [templates, setTemplates] = useState<ApprovalTemplateItem[]>([]);
  const [loading, setLoading] = useState(true);

  // 审批 modal
  const [actionModal, setActionModal] = useState<{ visible: boolean; type: 'approve' | 'reject'; instanceId: string }>({
    visible: false, type: 'approve', instanceId: '',
  });
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // 模板创建 modal
  const [templateModal, setTemplateModal] = useState(false);
  const [templateForm] = Form.useForm();

  const loadPending = useCallback(async () => {
    setLoading(true);
    try {
      const res = await hrService.getPendingApprovals(CURRENT_USER_ID, BRAND_ID);
      setPendingList(res.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const res = await hrService.getApprovalTemplates(BRAND_ID);
      setTemplates(res.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (activeTab === 'pending') loadPending();
    else loadTemplates();
  }, [activeTab, loadPending, loadTemplates]);

  const handleAction = async () => {
    setSubmitting(true);
    try {
      if (actionModal.type === 'approve') {
        await hrService.approveInstance(actionModal.instanceId, CURRENT_USER_ID, CURRENT_USER_NAME, comment);
        message.success('审批通过');
      } else {
        if (!comment.trim()) {
          message.warning('请输入驳回理由');
          setSubmitting(false);
          return;
        }
        await hrService.rejectInstance(actionModal.instanceId, CURRENT_USER_ID, CURRENT_USER_NAME, comment);
        message.success('已驳回');
      }
      setActionModal({ visible: false, type: 'approve', instanceId: '' });
      setComment('');
      loadPending();
    } catch {
      message.error('操作失败');
    }
    setSubmitting(false);
  };

  const handleCreateTemplate = async () => {
    try {
      const values = await templateForm.validateFields();
      const chainStr = values.approval_chain || '[]';
      let chain: unknown[];
      try {
        chain = JSON.parse(chainStr);
      } catch {
        message.error('审批链路格式错误，请输入合法JSON');
        return;
      }
      await hrService.createApprovalTemplate({
        brand_id: BRAND_ID,
        template_code: values.template_code,
        template_name: values.template_name,
        approval_chain: chain,
        description: values.description,
      });
      message.success('模板创建成功');
      setTemplateModal(false);
      templateForm.resetFields();
      loadTemplates();
    } catch {
      message.error('创建失败');
    }
  };

  const pendingColumns = [
    {
      title: '申请人', dataIndex: 'applicant_name', key: 'applicant_name', width: 100,
    },
    {
      title: '业务类型', dataIndex: 'business_type', key: 'business_type', width: 100,
      render: (v: string) => BIZ_TYPE_LABELS[v] || v,
    },
    {
      title: '摘要', dataIndex: 'summary', key: 'summary', ellipsis: true,
    },
    {
      title: '金额',
      dataIndex: 'amount_fen',
      key: 'amount_fen',
      width: 120,
      render: (v: number | null) => v != null ? `¥${(v / 100).toFixed(2)}` : '-',
    },
    {
      title: '当前层级', dataIndex: 'current_level', key: 'current_level', width: 90,
      render: (v: number) => `第${v}级`,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => {
        const s = STATUS_MAP[v] || STATUS_MAP.pending;
        return <Tag color={s.color}>{s.label}</Tag>;
      },
    },
    {
      title: '发起时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string | null) => v ? v.replace('T', ' ').slice(0, 16) : '-',
    },
    {
      title: '操作', key: 'actions', width: 160,
      render: (_: unknown, record: ApprovalInstanceItem) => (
        record.status === 'pending' ? (
          <Space>
            <Button
              type="primary"
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => setActionModal({ visible: true, type: 'approve', instanceId: record.id })}
            >
              通过
            </Button>
            <Button
              danger
              size="small"
              icon={<CloseCircleOutlined />}
              onClick={() => setActionModal({ visible: true, type: 'reject', instanceId: record.id })}
            >
              驳回
            </Button>
          </Space>
        ) : null
      ),
    },
  ];

  const templateColumns = [
    { title: '模板名称', dataIndex: 'template_name', key: 'template_name' },
    { title: '模板编码', dataIndex: 'template_code', key: 'template_code', width: 150 },
    {
      title: '审批链', dataIndex: 'approval_chain', key: 'approval_chain',
      render: (v: unknown[]) => `${(v || []).length}级审批`,
    },
    { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <AuditOutlined style={{ marginRight: 8 }} />
        审批管理
      </Title>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'pending',
            label: `待审批 (${pendingList.length})`,
            children: (
              <Card bordered={false}>
                <Table
                  rowKey="id"
                  columns={pendingColumns}
                  dataSource={pendingList}
                  loading={loading}
                  pagination={{ pageSize: 10 }}
                  locale={{ emptyText: '暂无待审批事项' }}
                />
              </Card>
            ),
          },
          {
            key: 'templates',
            label: '审批模板',
            children: (
              <Card
                bordered={false}
                extra={
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => setTemplateModal(true)}>
                    新建模板
                  </Button>
                }
              >
                <Table
                  rowKey="id"
                  columns={templateColumns}
                  dataSource={templates}
                  loading={loading}
                  pagination={false}
                  locale={{ emptyText: '暂无审批模板' }}
                />
              </Card>
            ),
          },
        ]}
      />

      {/* 审批/驳回 Modal */}
      <Modal
        title={actionModal.type === 'approve' ? '审批通过' : '驳回审批'}
        open={actionModal.visible}
        onOk={handleAction}
        onCancel={() => { setActionModal({ visible: false, type: 'approve', instanceId: '' }); setComment(''); }}
        confirmLoading={submitting}
        okText={actionModal.type === 'approve' ? '确认通过' : '确认驳回'}
        okButtonProps={actionModal.type === 'reject' ? { danger: true } : undefined}
      >
        <TextArea
          rows={3}
          value={comment}
          onChange={e => setComment(e.target.value)}
          placeholder={actionModal.type === 'approve' ? '审批意见（选填）' : '请输入驳回理由（必填）'}
        />
      </Modal>

      {/* 创建模板 Modal */}
      <Modal
        title="新建审批模板"
        open={templateModal}
        onOk={handleCreateTemplate}
        onCancel={() => { setTemplateModal(false); templateForm.resetFields(); }}
        okText="创建"
        width={560}
      >
        <Form form={templateForm} layout="vertical">
          <Form.Item name="template_name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="如：请假审批" />
          </Form.Item>
          <Form.Item name="template_code" label="模板编码" rules={[{ required: true, message: '请输入模板编码' }]}>
            <Input placeholder="如：leave" />
          </Form.Item>
          <Form.Item name="approval_chain" label="审批链路 (JSON)" rules={[{ required: true, message: '请输入审批链路' }]}>
            <TextArea
              rows={4}
              placeholder='[{"level":1,"role":"store_manager","name":"店长"},{"level":2,"role":"area_manager","name":"区域经理"}]'
            />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input placeholder="模板用途说明" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ApprovalManagementPage;
