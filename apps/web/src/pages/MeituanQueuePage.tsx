import React, { useState, useCallback, useEffect } from 'react';
import { Card, Button, Space, Statistic, Row, Col, Form, Input, InputNumber, Table, Alert } from 'antd';
import { SyncOutlined, SettingOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const MeituanQueuePage: React.FC = () => {
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [syncLoading, setSyncLoading] = useState<Record<string, boolean>>({});
  const [tableTypeForm] = Form.useForm();

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/meituan/queue/config');
      setConfig(res.data);
    } catch (err: any) {
      handleApiError(err, '加载美团配置失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadConfig(); }, [loadConfig]);

  const syncTableTypes = async (values: any) => {
    setSyncLoading(prev => ({ ...prev, tableTypes: true }));
    try {
      const tableTypes = (values.table_types || '').split('\n').filter(Boolean).map((line: string) => {
        const [id, name, capacity] = line.split(',');
        return { id: id?.trim(), name: name?.trim(), capacity: parseInt(capacity?.trim() || '4') };
      });
      await apiClient.post('/meituan/queue/sync/table-types', {
        store_id: values.store_id,
        app_auth_token: values.app_auth_token,
        table_types: tableTypes,
      });
      showSuccess('桌型同步成功');
    } catch (err: any) {
      handleApiError(err, '同步失败');
    } finally {
      setSyncLoading(prev => ({ ...prev, tableTypes: false }));
    }
  };

  const syncWaitingInfo = async () => {
    setSyncLoading(prev => ({ ...prev, waiting: true }));
    try {
      await apiClient.post('/meituan/queue/sync/waiting-info', {
        store_id: config?.store_id || 'STORE001',
        app_auth_token: config?.app_auth_token || '',
      });
      showSuccess('等待信息同步成功');
    } catch (err: any) {
      handleApiError(err, '同步失败');
    } finally {
      setSyncLoading(prev => ({ ...prev, waiting: false }));
    }
  };

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}><Card loading={loading}><Statistic title="门店ID" value={config?.store_id || '-'} /></Card></Col>
        <Col span={8}><Card loading={loading}><Statistic title="集成状态" value={config?.enabled ? '已启用' : '未启用'} /></Card></Col>
        <Col span={8}><Card loading={loading}><Statistic title="桌型数量" value={config?.table_types?.length ?? 0} /></Card></Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Card
            title="桌型配置同步"
            extra={<Button icon={<SyncOutlined />} loading={syncLoading.tableTypes} onClick={() => tableTypeForm.submit()}>同步到美团</Button>}
          >
            <Alert message="每行格式：桌型ID,桌型名称,容纳人数（如：1,双人桌,2）" type="info" style={{ marginBottom: 12 }} />
            <Form form={tableTypeForm} layout="vertical" onFinish={syncTableTypes}>
              <Form.Item name="store_id" label="门店ID" initialValue={config?.store_id || 'STORE001'} rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="app_auth_token" label="App Auth Token" rules={[{ required: true }]}>
                <Input.Password />
              </Form.Item>
              <Form.Item name="table_types" label="桌型列表（每行一条）">
                <Input.TextArea rows={5} placeholder="1,双人桌,2&#10;2,四人桌,4&#10;3,大桌,8" />
              </Form.Item>
            </Form>
          </Card>
        </Col>

        <Col span={12}>
          <Card
            title="等待信息同步"
            extra={<Button icon={<SyncOutlined />} loading={syncLoading.waiting} onClick={syncWaitingInfo}>立即同步</Button>}
          >
            <p>将当前门店的排队等待信息同步到美团/大众点评平台，让顾客在 App 上实时查看等待状态。</p>
            {config?.table_types && (
              <Table
                size="small"
                dataSource={config.table_types}
                rowKey={(r, i) => r.id || String(i)}
                columns={[
                  { title: '桌型ID', dataIndex: 'id', key: 'id' },
                  { title: '名称', dataIndex: 'name', key: 'name' },
                  { title: '容纳人数', dataIndex: 'capacity', key: 'capacity' },
                ]}
                pagination={false}
              />
            )}
          </Card>

          <Card title="配置信息" style={{ marginTop: 16 }} loading={loading} extra={<Button icon={<SettingOutlined />} onClick={loadConfig}>刷新</Button>}>
            {config && (
              <div>
                <p><strong>门店ID：</strong>{config.store_id}</p>
                <p><strong>Webhook URL：</strong>{config.webhook_url || '-'}</p>
                <p><strong>最后同步：</strong>{config.last_sync || '-'}</p>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default MeituanQueuePage;
