import React, { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Descriptions,
  Modal,
  Form,
  Input,
  Switch,
  message,
  Typography,
} from 'antd';
import {
  SafetyCertificateOutlined,
  ReloadOutlined,
  ExportOutlined,
  DisconnectOutlined,
  KeyOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { showSuccess, handleApiError } from '../utils/message';
import dayjs from 'dayjs';

const { Text } = Typography;

const DataSovereigntyPage: React.FC = () => {
  const [config, setConfig] = useState<{ enabled: boolean; key_configured: boolean } | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exportModalVisible, setExportModalVisible] = useState(false);
  const [disconnectModalVisible, setDisconnectModalVisible] = useState(false);
  const [exportForm] = Form.useForm();
  const [disconnectForm] = Form.useForm();
  const [auditPage, setAuditPage] = useState(1);
  const auditPageSize = 50;

  const loadConfig = async () => {
    try {
      const res = await apiClient.get('/api/v1/ontology/data-sovereignty/config');
      setConfig(res.data || null);
    } catch (err: any) {
      handleApiError(err, '加载配置失败');
    }
  };

  const loadAuditLogs = async (skip = 0, limit = 50) => {
    try {
      setLoading(true);
      const res = await apiClient.get('/api/v1/ontology/data-sovereignty/audit-logs', {
        params: { skip, limit },
      });
      setLogs(res.data?.logs || []);
      setTotal(res.data?.total ?? 0);
    } catch (err: any) {
      handleApiError(err, '加载审计日志失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);
  useEffect(() => {
    loadAuditLogs((auditPage - 1) * auditPageSize, auditPageSize);
  }, [auditPage]);

  const handleExportOk = async () => {
    try {
      const values = await exportForm.validateFields();
      const storeIds = values.store_ids
        ? String(values.store_ids).split(/[,，\s]+/).map((s: string) => s.trim()).filter(Boolean)
        : undefined;
      await apiClient.post('/api/v1/ontology/data-sovereignty/export-encrypted', {
        tenant_id: values.tenant_id || '',
        store_ids: storeIds && storeIds.length ? storeIds : undefined,
        customer_key: values.customer_key || undefined,
      });
      showSuccess('导出请求已处理，请查看返回的密文或明文导出数据并妥善保存');
      setExportModalVisible(false);
      exportForm.resetFields();
      setAuditPage(1);
      loadAuditLogs(0, auditPageSize);
    } catch (err: any) {
      if (err?.errorFields) return;
      handleApiError(err, '加密导出失败');
    }
  };

  const handleDisconnectOk = async () => {
    try {
      const values = await disconnectForm.validateFields();
      const storeIds = String(values.store_ids || '').split(/[,，\s]+/).map((s: string) => s.trim()).filter(Boolean);
      if (!storeIds.length) {
        message.warning('请至少填写一个门店 ID');
        return;
      }
      await apiClient.post('/api/v1/ontology/data-sovereignty/disconnect', {
        tenant_id: values.tenant_id || '',
        store_ids: storeIds,
        export_first: values.export_first !== false,
        customer_key: values.customer_key || undefined,
      });
      showSuccess('断开权已执行，图谱中该租户/门店数据已删除，请妥善保管导出文件');
      setDisconnectModalVisible(false);
      disconnectForm.resetFields();
      setAuditPage(1);
      loadAuditLogs(0, auditPageSize);
    } catch (err: any) {
      if (err?.errorFields) return;
      handleApiError(err, '断开权执行失败');
    }
  };

  const actionText: Record<string, string> = {
    data_sovereignty_export: '加密导出',
    data_sovereignty_disconnect: '断开权',
  };

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      render: (a: string) => actionText[a] || a,
    },
    {
      title: '用户',
      dataIndex: 'username',
      key: 'username',
      render: (u: string, r: any) => u || r.user_id || '-',
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (
        <Tag color={s === 'success' ? 'green' : 'red'}>{s === 'success' ? '成功' : '失败'}</Tag>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Card
        title={
          <Space>
            <SafetyCertificateOutlined />
            数据主权与密钥
          </Space>
        }
        extra={
          <Button type="primary" icon={<ReloadOutlined />} onClick={() => { loadConfig(); loadAuditLogs(); }}>
            刷新
          </Button>
        }
      >
        <Descriptions bordered size="small" column={1}>
          <Descriptions.Item label="功能开关">
            {config ? (
              config.enabled ? (
                <Tag color="green">已启用</Tag>
              ) : (
                <Tag color="default">未启用（需配置 DATA_SOVEREIGNTY_ENABLED）</Tag>
              )
            ) : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="客户密钥">
            {config ? (
              config.key_configured ? (
                <Tag color="blue" icon={<KeyOutlined />}>已配置（密钥不展示，客户自持）</Tag>
              ) : (
                <Text type="secondary">未配置（可通过环境变量 CUSTOMER_ENCRYPTION_KEY 或导出/断开时传入）</Text>
              )
            ) : '-'}
          </Descriptions.Item>
        </Descriptions>
        <div style={{ marginTop: 16 }}>
          <Space>
            <Button
              type="primary"
              icon={<ExportOutlined />}
              onClick={() => setExportModalVisible(true)}
              disabled={!config?.enabled}
            >
              加密导出
            </Button>
            <Button
              danger
              icon={<DisconnectOutlined />}
              onClick={() => setDisconnectModalVisible(true)}
              disabled={!config?.enabled}
            >
              断开权
            </Button>
          </Space>
        </div>
      </Card>

      <Card title="数据主权审计日志" style={{ marginTop: 24 }}>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={logs}
          pagination={{
            current: auditPage,
            total,
            pageSize: auditPageSize,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p) => setAuditPage(p),
          }}
          scroll={{ x: 800 }}
        />
      </Card>

      <Modal
        title="加密导出"
        open={exportModalVisible}
        onOk={handleExportOk}
        onCancel={() => { setExportModalVisible(false); exportForm.resetFields(); }}
        okText="导出"
        width={520}
      >
        <Form form={exportForm} layout="vertical">
          <Form.Item name="tenant_id" label="租户 ID">
            <Input placeholder="可选，留空表示当前租户" />
          </Form.Item>
          <Form.Item name="store_ids" label="门店 ID（多个用逗号分隔，留空表示全部）">
            <Input placeholder="例如: store1, store2" />
          </Form.Item>
          <Form.Item name="customer_key" label="客户密钥（可选，留空则使用系统配置）">
            <Input.Password placeholder="用于 AES-256 加密，客户自持则屯象无法解密" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="断开权"
        open={disconnectModalVisible}
        onOk={handleDisconnectOk}
        onCancel={() => { setDisconnectModalVisible(false); disconnectForm.resetFields(); }}
        okText="确认执行"
        okButtonProps={{ danger: true }}
        width={520}
      >
        <Typography.Paragraph type="danger">
          执行后将先导出数据（可选加密），再删除图谱中该租户/门店数据。请务必先保存导出文件。
        </Typography.Paragraph>
        <Form form={disconnectForm} layout="vertical" initialValues={{ export_first: true }}>
          <Form.Item name="tenant_id" label="租户 ID" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="要断开数据的租户" />
          </Form.Item>
          <Form.Item name="store_ids" label="门店 ID（多个用逗号分隔）" rules={[{ required: true, message: '至少填一个门店 ID' }]}>
            <Input placeholder="例如: store1, store2" />
          </Form.Item>
          <Form.Item name="export_first" valuePropName="checked" label="执行前先导出">
            <Switch />
          </Form.Item>
          <Form.Item name="customer_key" label="导出时使用的客户密钥（可选）">
            <Input.Password placeholder="若先导出且需加密可填写" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DataSovereigntyPage;
