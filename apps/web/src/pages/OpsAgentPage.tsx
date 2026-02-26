import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Col, Row, Select, Tabs, Statistic, Button,
  Form, Input, Alert, Space,
} from 'antd';
import {
  ReloadOutlined, HeartOutlined, SafetyOutlined, BulbOutlined, ToolOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;

interface QARecord {
  question: string;
  answer: string;
}

const OpsAgentPage: React.FC = () => {
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [healthResult, setHealthResult] = useState('');
  const [healthLoading, setHealthLoading] = useState(false);
  const [assetAdvice, setAssetAdvice] = useState('');
  const [diagnoseResult, setDiagnoseResult] = useState('');
  const [diagnoseLoading, setDiagnoseLoading] = useState(false);
  const [runbookResult, setRunbookResult] = useState('');
  const [runbookLoading, setRunbookLoading] = useState(false);
  const [maintenanceResult, setMaintenanceResult] = useState('');
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [deviceType, setDeviceType] = useState('');
  const [securityResult, setSecurityResult] = useState('');
  const [securityLoading, setSecurityLoading] = useState(false);
  const [securityFocus, setSecurityFocus] = useState('comprehensive');
  const [queryInput, setQueryInput] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryHistory, setQueryHistory] = useState<QARecord[]>([]);

  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const res = await apiClient.get(`/ops/health/${selectedStore}`);
      setHealthResult(res.data?.data?.check_advice || '');
    } catch (err: any) { handleApiError(err, '健康检查失败'); }
    finally { setHealthLoading(false); }
  }, [selectedStore]);

  const loadAssets = useCallback(async () => {
    try {
      const res = await apiClient.get(`/ops/assets/${selectedStore}`);
      setAssetAdvice(res.data?.data?.asset_advice || '');
    } catch { /* silent */ }
  }, [selectedStore]);

  useEffect(() => {
    loadHealth();
    loadAssets();
  }, [loadHealth, loadAssets]);

  const handleDiagnose = async (values: any) => {
    setDiagnoseLoading(true);
    try {
      const res = await apiClient.post('/ops/diagnose', { store_id: selectedStore, ...values });
      setDiagnoseResult(res.data?.data?.diagnosis || '');
    } catch (err: any) { handleApiError(err, '故障诊断失败'); }
    finally { setDiagnoseLoading(false); }
  };

  const handleRunbook = async (values: any) => {
    setRunbookLoading(true);
    try {
      const res = await apiClient.post('/ops/runbook', { store_id: selectedStore, ...values });
      setRunbookResult(res.data?.data?.runbook || '');
    } catch (err: any) { handleApiError(err, 'Runbook生成失败'); }
    finally { setRunbookLoading(false); }
  };

  const handleMaintenance = async () => {
    setMaintenanceLoading(true);
    try {
      const res = await apiClient.get(`/ops/maintenance/${selectedStore}`, { params: { device_type: deviceType } });
      setMaintenanceResult(res.data?.data?.maintenance_advice || '');
    } catch (err: any) { handleApiError(err, '预测维护查询失败'); }
    finally { setMaintenanceLoading(false); }
  };

  const handleSecurity = async () => {
    setSecurityLoading(true);
    try {
      const res = await apiClient.get(`/ops/security/${selectedStore}`, { params: { focus: securityFocus } });
      setSecurityResult(res.data?.data?.security_advice || '');
    } catch (err: any) { handleApiError(err, '安全建议获取失败'); }
    finally { setSecurityLoading(false); }
  };

  const handleQuery = async () => {
    if (!queryInput.trim()) return;
    setQueryLoading(true);
    try {
      const res = await apiClient.post('/ops/query', { store_id: selectedStore, question: queryInput });
      const answer = res.data?.data?.answer || '';
      setQueryHistory(prev => [{ question: queryInput, answer }, ...prev].slice(0, 5));
      setQueryInput('');
    } catch (err: any) { handleApiError(err, '问答失败'); }
    finally { setQueryLoading(false); }
  };

  const tabItems = [
    {
      key: 'health',
      label: '健康检查',
      children: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Button icon={<ReloadOutlined />} loading={healthLoading} onClick={loadHealth}>刷新</Button>
          {healthResult && <Alert type="info" showIcon message="健康检查结果" description={healthResult} />}
        </Space>
      ),
    },
    {
      key: 'diagnose',
      label: '故障诊断',
      children: (
        <Form layout="vertical" onFinish={handleDiagnose}>
          <Form.Item name="component" label="组件" rules={[{ required: true }]}>
            <Select placeholder="选择组件">
              <Option value="network">网络</Option>
              <Option value="database">数据库</Option>
              <Option value="pos">POS系统</Option>
              <Option value="printer">打印机</Option>
              <Option value="camera">摄像头</Option>
            </Select>
          </Form.Item>
          <Form.Item name="symptom" label="症状描述" rules={[{ required: true }]}>
            <Input placeholder="描述故障症状" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={diagnoseLoading}>开始诊断</Button>
          </Form.Item>
          {diagnoseResult && <Alert type="info" showIcon message="诊断结果" description={diagnoseResult} />}
        </Form>
      ),
    },
    {
      key: 'runbook',
      label: 'Runbook',
      children: (
        <Form layout="vertical" onFinish={handleRunbook}>
          <Form.Item name="fault_type" label="故障类型" rules={[{ required: true }]}>
            <Select placeholder="选择故障类型">
              <Option value="network_outage">网络中断</Option>
              <Option value="db_slow">数据库慢查询</Option>
              <Option value="pos_crash">POS崩溃</Option>
              <Option value="printer_jam">打印机卡纸</Option>
              <Option value="power_failure">电源故障</Option>
            </Select>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={runbookLoading}>生成Runbook</Button>
          </Form.Item>
          {runbookResult && <Alert type="info" showIcon message="处理步骤" description={runbookResult} />}
        </Form>
      ),
    },
    {
      key: 'maintenance',
      label: '预测维护',
      children: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Select value={deviceType} onChange={setDeviceType} placeholder="选择设备类型" style={{ width: 200 }}>
              <Option value="pos">POS终端</Option>
              <Option value="printer">打印机</Option>
              <Option value="camera">摄像头</Option>
              <Option value="router">路由器</Option>
              <Option value="server">服务器</Option>
            </Select>
            <Button type="primary" loading={maintenanceLoading} onClick={handleMaintenance}>查询维护建议</Button>
          </Space>
          {maintenanceResult && <Alert type="info" showIcon message="维护建议" description={maintenanceResult} />}
        </Space>
      ),
    },
    {
      key: 'security',
      label: '安全建议',
      children: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Select value={securityFocus} onChange={setSecurityFocus} style={{ width: 200 }}>
              <Option value="comprehensive">全面检查</Option>
              <Option value="weak_password">弱密码</Option>
              <Option value="unauthorized_device">非授权设备</Option>
              <Option value="firmware">固件更新</Option>
              <Option value="vpn">VPN配置</Option>
            </Select>
            <Button type="primary" loading={securityLoading} onClick={handleSecurity}>获取安全建议</Button>
          </Space>
          {securityResult && <Alert type="info" showIcon message="安全建议" description={securityResult} />}
        </Space>
      ),
    },
    {
      key: 'query',
      label: 'NL问答',
      children: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input.TextArea
            value={queryInput}
            onChange={e => setQueryInput(e.target.value)}
            rows={3}
            placeholder="输入运维问题..."
          />
          <Button type="primary" loading={queryLoading} onClick={handleQuery}>提交问题</Button>
          {queryHistory.map((item, idx) => (
            <Card key={idx} size="small" title={`Q: ${item.question}`}>
              <Alert type="info" showIcon message="回答" description={item.answer} />
            </Card>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }}>
          <Option value="STORE001">STORE001</Option>
          <Option value="STORE002">STORE002</Option>
          <Option value="STORE003">STORE003</Option>
        </Select>
      </Space>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="健康状态" value={healthResult ? '已检查' : '待检查'} prefix={<HeartOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="资产建议" value={assetAdvice ? '有建议' : '暂无'} prefix={<ToolOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="安全风险" value={securityResult ? '已分析' : '待分析'} prefix={<SafetyOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="维护建议" value={maintenanceResult ? '有建议' : '暂无'} prefix={<BulbOutlined />} />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs items={tabItems} />
      </Card>
    </div>
  );
};

export default OpsAgentPage;
