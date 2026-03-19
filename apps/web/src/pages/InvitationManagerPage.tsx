/**
 * AI邀请函管理页 — 列表+创建+AI生成+发布
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Select, DatePicker, Space,
  Tag, message, Descriptions, Statistic, Row, Col, Typography, Divider,
} from 'antd';
import {
  PlusOutlined, RobotOutlined, ShareAltOutlined, CopyOutlined,
  EyeOutlined, TeamOutlined,
} from '@ant-design/icons';
import { apiClient } from '../utils/apiClient';
import { useAuthStore } from '../stores/authStore';
import styles from './InvitationManagerPage.module.css';

const { TextArea } = Input;
const { Text } = Typography;

interface InvitationItem {
  id: string;
  store_id: string;
  host_name: string;
  event_type: string;
  event_title: string;
  event_date: string;
  venue_name: string;
  template: string;
  ai_generated_message: string;
  share_token: string;
  view_count: number;
  rsvp_count: number;
  is_published: boolean;
  created_at: string;
}

const EVENT_TYPES = [
  '商务宴请', '朋友聚会', '宝宝宴', '普通宴请',
  '生日宴', '婚宴', '中秋节', '国庆节', '家宴',
  '寿宴', '升学宴', '谢师宴', '满月宴', '订婚宴',
];

const TEMPLATES = [
  { value: 'wedding_red', label: '婚宴红金' },
  { value: 'birthday_gold', label: '寿宴暖金' },
  { value: 'corporate_blue', label: '商务深蓝' },
  { value: 'full_moon_pink', label: '满月粉色' },
  { value: 'graduation_green', label: '升学翠绿' },
];

const GENRES = ['藏头诗', '现代诗', '对联', '文言文', '古诗', '口号'];
const MOODS = ['简约', '豪放', '正式'];
const EMOTIONS = ['庆祝', '感恩', '回忆', '庄重', '鼓励'];

const InvitationManagerPage: React.FC = () => {
  const [items, setItems] = useState<InvitationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [createVisible, setCreateVisible] = useState(false);
  const [aiVisible, setAiVisible] = useState(false);
  const [rsvpVisible, setRsvpVisible] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const [generatedText, setGeneratedText] = useState('');
  const [generating, setGenerating] = useState(false);
  const [rsvpData, setRsvpData] = useState<any>(null);
  const [form] = Form.useForm();
  const [aiForm] = Form.useForm();
  const user = useAuthStore((s) => s.user);
  const storeId = user?.store_id || '';

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<InvitationItem[]>(`/api/v1/invitations?store_id=${storeId}`);
      setItems(data);
    } catch {
      message.error('加载失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadItems(); }, [loadItems]);

  const handleCreate = async (values: any) => {
    try {
      await apiClient.post('/api/v1/invitations', {
        ...values,
        store_id: storeId,
        event_date: values.event_date?.toISOString(),
      });
      message.success('创建成功');
      setCreateVisible(false);
      form.resetFields();
      loadItems();
    } catch {
      message.error('创建失败');
    }
  };

  const handleGenerate = async () => {
    const values = aiForm.getFieldsValue();
    setGenerating(true);
    try {
      const data = await apiClient.post<{ text: string }>(
        `/api/v1/invitations/${selectedId}/generate-text`,
        values
      );
      setGeneratedText(data.text);
      loadItems();
    } catch {
      message.error('生成失败');
    } finally {
      setGenerating(false);
    }
  };

  const handlePublish = async (id: string) => {
    try {
      const data = await apiClient.post<{ share_url: string }>(`/api/v1/invitations/${id}/publish`);
      message.success('已发布');
      navigator.clipboard?.writeText(data.share_url);
      message.info('分享链接已复制');
      loadItems();
    } catch {
      message.error('发布失败');
    }
  };

  const viewRsvps = async (id: string) => {
    try {
      const data = await apiClient.get(`/api/v1/invitations/${id}/rsvps`);
      setRsvpData(data);
      setRsvpVisible(true);
    } catch {
      message.error('加载回执失败');
    }
  };

  const columns = [
    { title: '标题', dataIndex: 'event_title', width: 200 },
    { title: '类型', dataIndex: 'event_type', width: 100 },
    { title: '主人', dataIndex: 'host_name', width: 100 },
    {
      title: '状态',
      dataIndex: 'is_published',
      width: 80,
      render: (v: boolean) => v ? <Tag color="green">已发布</Tag> : <Tag>草稿</Tag>,
    },
    {
      title: '浏览/回执',
      width: 120,
      render: (_: any, r: InvitationItem) => (
        <Space>
          <span><EyeOutlined /> {r.view_count}</span>
          <span><TeamOutlined /> {r.rsvp_count}</span>
        </Space>
      ),
    },
    {
      title: '操作',
      width: 280,
      render: (_: any, r: InvitationItem) => (
        <Space>
          <Button
            size="small"
            icon={<RobotOutlined />}
            onClick={() => { setSelectedId(r.id); setGeneratedText(r.ai_generated_message || ''); setAiVisible(true); }}
          >
            AI生成
          </Button>
          {!r.is_published && (
            <Button size="small" icon={<ShareAltOutlined />} type="primary" onClick={() => handlePublish(r.id)}>
              发布
            </Button>
          )}
          {r.is_published && (
            <Button
              size="small"
              icon={<CopyOutlined />}
              onClick={() => {
                navigator.clipboard?.writeText(`https://zlsjos.cn/invitation/${r.share_token}`);
                message.success('链接已复制');
              }}
            >
              复制链接
            </Button>
          )}
          <Button size="small" onClick={() => viewRsvps(r.id)}>回执</Button>
        </Space>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <Card
        title="AI邀请函管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateVisible(true)}>
            新建邀请函
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 900 }}
        />
      </Card>

      {/* Create Modal */}
      <Modal
        title="新建邀请函"
        open={createVisible}
        onCancel={() => setCreateVisible(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="host_name" label="主人姓名" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="host_phone" label="联系电话" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="event_type" label="宴会类型" rules={[{ required: true }]}>
                <Select options={EVENT_TYPES.map(t => ({ value: t, label: t }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="template" label="模板主题" initialValue="corporate_blue">
                <Select options={TEMPLATES} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="event_title" label="宴会标题" rules={[{ required: true }]}>
            <Input placeholder="如：张先生寿宴" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="event_date" label="日期" rules={[{ required: true }]}>
                <DatePicker showTime style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="venue_name" label="场所" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="venue_address" label="地址">
            <Input />
          </Form.Item>
          <Form.Item name="custom_message" label="自定义要求">
            <TextArea rows={3} placeholder="AI生成文案时会参考此要求" />
          </Form.Item>
        </Form>
      </Modal>

      {/* AI Generate Modal */}
      <Modal
        title="AI生成邀请语"
        open={aiVisible}
        onCancel={() => setAiVisible(false)}
        footer={null}
        width={600}
      >
        <Form form={aiForm} layout="vertical">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="genre" label="体裁" initialValue="现代诗">
                <Select options={GENRES.map(g => ({ value: g, label: g }))} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="mood" label="语气" initialValue="正式">
                <Select options={MOODS.map(m => ({ value: m, label: m }))} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="emotion" label="情感" initialValue="庆祝">
                <Select options={EMOTIONS.map(e => ({ value: e, label: e }))} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="guest_name" label="宾客姓名（选填，用于藏头诗）">
            <Input placeholder="输入姓名生成专属请柬" />
          </Form.Item>
        </Form>
        <Button type="primary" icon={<RobotOutlined />} loading={generating} onClick={handleGenerate} block>
          {generating ? '生成中...' : '立即生成'}
        </Button>
        {generatedText && (
          <Card size="small" style={{ marginTop: 16, background: '#fafafa' }}>
            <pre style={{ whiteSpace: 'pre-wrap', margin: 0, lineHeight: 1.8 }}>{generatedText}</pre>
          </Card>
        )}
      </Modal>

      {/* RSVP Stats Modal */}
      <Modal
        title="回执统计"
        open={rsvpVisible}
        onCancel={() => setRsvpVisible(false)}
        footer={null}
        width={600}
      >
        {rsvpData && (
          <>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={8}><Statistic title="总回执" value={rsvpData.total} /></Col>
              <Col span={8}><Statistic title="确认出席" value={rsvpData.attending} valueStyle={{ color: '#52c41a' }} /></Col>
              <Col span={8}><Statistic title="出席人数" value={rsvpData.attending_guests} suffix="人" /></Col>
            </Row>
            <Divider />
            <Table
              size="small"
              dataSource={rsvpData.rsvps}
              rowKey="guest_name"
              pagination={false}
              columns={[
                { title: '姓名', dataIndex: 'guest_name' },
                { title: '人数', dataIndex: 'party_size' },
                { title: '状态', dataIndex: 'status', render: (v: string) => v === 'attending' ? <Tag color="green">出席</Tag> : <Tag color="red">谢绝</Tag> },
                { title: '祝福语', dataIndex: 'message' },
              ]}
            />
          </>
        )}
      </Modal>
    </div>
  );
};

export default InvitationManagerPage;
