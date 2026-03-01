/**
 * 数据安全管理页面（AES-256-GCM 客户密钥管理）
 *
 * 功能：
 *   - 门店密钥列表：版本号、算法、状态、创建时间、轮换时间
 *   - 创建密钥
 *   - 密钥轮换（安全替换，旧密钥归档）
 *   - 密钥吊销（危险操作，双重确认）
 *   - 加密覆盖率统计（按表/字段）
 */
import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Table, Button, Tag, Space, Select, Popconfirm,
  Row, Col, Statistic, Modal, Alert, Progress, Descriptions,
  Badge, Divider, Input,
} from 'antd';
import {
  ReloadOutlined, PlusOutlined, SafetyOutlined,
  LockOutlined, UnlockOutlined, WarningOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface CustomerKey {
  id: string;
  store_id: string;
  key_version: number;
  key_alias: string;
  algorithm: string;
  status: string;
  is_active: boolean;
  purpose: string;
  created_at: string;
  rotated_at: string | null;
  rotated_by: string | null;
}

interface CoverageRecord {
  table: string;
  field: string;
  count: number;
}

// ── 配置映射 ──────────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  active:   { color: 'success',  label: '激活' },
  rotating: { color: 'processing', label: '轮换中' },
  retired:  { color: 'default',  label: '已退役' },
  revoked:  { color: 'error',    label: '已吊销' },
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

const DataSecurityPage: React.FC = () => {
  const [storeId, setStoreId] = useState('STORE001');
  const [keys, setKeys] = useState<CustomerKey[]>([]);
  const [loading, setLoading] = useState(false);

  // 加密覆盖率
  const [coverage, setCoverage] = useState<{
    total_records: number;
    tables: Record<string, CoverageRecord>;
    coverage_pct: number;
  } | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(false);

  // 吊销确认输入
  const [revokeId, setRevokeId] = useState<string | null>(null);
  const [revokeConfirmText, setRevokeConfirmText] = useState('');
  const [revokeModalVisible, setRevokeModalVisible] = useState(false);
  const [revokeLoading, setRevokeLoading] = useState(false);

  // ── 数据加载 ──────────────────────────────────────────────────────────────

  const loadKeys = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/security/keys/${storeId}`);
      setKeys(res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载密钥列表失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  const loadCoverage = useCallback(async () => {
    setCoverageLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/security/keys/${storeId}/coverage`);
      setCoverage(res.data);
    } catch (err: any) {
      handleApiError(err, '加载覆盖率失败');
    } finally {
      setCoverageLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    loadKeys();
    loadCoverage();
  }, [loadKeys, loadCoverage]);

  // ── 创建密钥 ──────────────────────────────────────────────────────────────

  const createKey = async () => {
    try {
      await apiClient.post(`/api/v1/security/keys/${storeId}`);
      showSuccess('密钥已创建');
      loadKeys();
    } catch (err: any) {
      handleApiError(err, '创建失败');
    }
  };

  // ── 密钥轮换 ──────────────────────────────────────────────────────────────

  const rotateKey = async () => {
    try {
      await apiClient.post(`/api/v1/security/keys/${storeId}/rotate`);
      showSuccess('密钥轮换完成，旧密钥已退役');
      loadKeys();
    } catch (err: any) {
      handleApiError(err, '轮换失败');
    }
  };

  // ── 密钥吊销 ──────────────────────────────────────────────────────────────

  const openRevoke = (keyId: string) => {
    setRevokeId(keyId);
    setRevokeConfirmText('');
    setRevokeModalVisible(true);
  };

  const confirmRevoke = async () => {
    if (revokeConfirmText !== 'REVOKE' || !revokeId) return;
    setRevokeLoading(true);
    try {
      await apiClient.delete(`/api/v1/security/keys/${revokeId}`);
      showSuccess('密钥已吊销（加密数据将无法恢复）');
      setRevokeModalVisible(false);
      loadKeys();
    } catch (err: any) {
      handleApiError(err, '吊销失败');
    } finally {
      setRevokeLoading(false);
    }
  };

  // ── 统计 ──────────────────────────────────────────────────────────────────

  const activeKey = keys.find(k => k.is_active);
  const totalVersions = keys.length;
  const retiredCount = keys.filter(k => k.status === 'retired').length;

  // ── 密钥列表列定义 ────────────────────────────────────────────────────────

  const keyColumns: ColumnsType<CustomerKey> = [
    {
      title: '版本',
      dataIndex: 'key_version',
      width: 70,
      render: (v, rec) => (
        <Space>
          <Tag color={rec.is_active ? 'green' : 'default'}>v{v}</Tag>
          {rec.is_active && <Badge status="processing" />}
        </Space>
      ),
    },
    {
      title: '别名',
      dataIndex: 'key_alias',
      width: 130,
      render: (v) => <code style={{ fontSize: 11 }}>{v}</code>,
    },
    {
      title: '算法',
      dataIndex: 'algorithm',
      width: 130,
      render: (v) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (v) => {
        const cfg = STATUS_CONFIG[v] || { color: 'default', label: v };
        return <Badge status={cfg.color as any} text={cfg.label} />;
      },
    },
    {
      title: '用途',
      dataIndex: 'purpose',
      width: 120,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 140,
      render: (v) => v?.slice(0, 16).replace('T', ' '),
    },
    {
      title: '轮换时间',
      dataIndex: 'rotated_at',
      width: 140,
      render: (v) => v ? v.slice(0, 16).replace('T', ' ') : '—',
    },
    {
      title: '操作',
      width: 100,
      fixed: 'right',
      render: (_, rec) =>
        rec.status === 'active' ? (
          <Button
            size="small"
            danger
            icon={<UnlockOutlined />}
            onClick={() => openRevoke(rec.id)}
          >
            吊销
          </Button>
        ) : null,
    },
  ];

  // ── 覆盖率表格列 ──────────────────────────────────────────────────────────

  const coverageData = coverage
    ? Object.values(coverage.tables).map(t => ({
        key: `${t.table}.${t.field}`,
        table: t.table,
        field: t.field,
        count: t.count,
      }))
    : [];

  const coverageColumns: ColumnsType<any> = [
    { title: '表名', dataIndex: 'table', width: 180 },
    { title: '字段', dataIndex: 'field', width: 150 },
    { title: '已加密记录数', dataIndex: 'count', width: 130 },
  ];

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: 24 }}>
      {/* 页头 */}
      <Row gutter={16} align="middle" style={{ marginBottom: 16 }}>
        <Col flex="1">
          <h2 style={{ margin: 0 }}>
            <SafetyOutlined style={{ marginRight: 8 }} />
            数据安全管理
          </h2>
          <p style={{ color: '#888', margin: 0, fontSize: 13 }}>
            AES-256-GCM 字段级加密密钥管理与覆盖率审计
          </p>
        </Col>
        <Col>
          <Space>
            <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
              <Option value="STORE001">北京旗舰店</Option>
              <Option value="STORE002">上海直营店</Option>
              <Option value="STORE003">广州加盟店</Option>
            </Select>
            <Button icon={<ReloadOutlined />} onClick={() => { loadKeys(); loadCoverage(); }} loading={loading} />
          </Space>
        </Col>
      </Row>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="密钥版本总数" value={totalVersions} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="当前激活版本"
              value={activeKey ? `v${activeKey.key_version}` : '未创建'}
              valueStyle={{ color: activeKey ? '#52c41a' : '#faad14' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="已退役版本" value={retiredCount} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="加密覆盖率"
              value={coverage?.coverage_pct ?? 0}
              suffix="%"
              valueStyle={{ color: (coverage?.coverage_pct ?? 0) >= 100 ? '#52c41a' : '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 当前密钥状态提示 */}
      {!activeKey && (
        <Alert
          type="warning"
          message="当前门店尚未创建加密密钥，敏感字段将以明文存储"
          showIcon
          action={
            <Button size="small" type="primary" onClick={createKey}>
              立即创建密钥
            </Button>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      {activeKey && (
        <Alert
          type="success"
          message={
            <Space>
              当前激活密钥：<code>{activeKey.key_alias}</code>
              （{activeKey.algorithm}）
            </Space>
          }
          showIcon
          action={
            <Popconfirm
              title="密钥轮换将生成新版本并退役当前密钥，确认？"
              onConfirm={rotateKey}
            >
              <Button size="small" icon={<SyncOutlined />}>轮换密钥</Button>
            </Popconfirm>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      {/* 密钥列表 */}
      <Card
        title="密钥版本历史"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={createKey}
            disabled={!!activeKey}
          >
            创建密钥
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <Table
          rowKey="id"
          columns={keyColumns}
          dataSource={keys}
          loading={loading}
          scroll={{ x: 900 }}
          pagination={false}
          size="small"
          rowClassName={(rec) => rec.is_active ? 'ant-table-row-selected' : ''}
          onRow={(rec) => ({
            style: rec.is_active ? { background: '#f6ffed' } : {},
          })}
        />
      </Card>

      {/* 加密覆盖率 */}
      <Card
        title="加密字段覆盖率"
        loading={coverageLoading}
        extra={<Button icon={<ReloadOutlined />} size="small" onClick={loadCoverage} />}
      >
        {coverage && (
          <>
            <Row gutter={24} align="middle" style={{ marginBottom: 16 }}>
              <Col span={8}>
                <div style={{ fontSize: 13, color: '#666', marginBottom: 4 }}>总加密记录数</div>
                <div style={{ fontSize: 24, fontWeight: 600 }}>{coverage.total_records}</div>
              </Col>
              <Col span={16}>
                <div style={{ fontSize: 13, color: '#666', marginBottom: 4 }}>覆盖率</div>
                <Progress
                  percent={coverage.coverage_pct}
                  strokeColor={coverage.coverage_pct >= 100 ? '#52c41a' : '#faad14'}
                  format={(pct) => `${pct}%`}
                />
              </Col>
            </Row>

            {coverageData.length > 0 ? (
              <Table
                rowKey="key"
                columns={coverageColumns}
                dataSource={coverageData}
                pagination={false}
                size="small"
              />
            ) : (
              <Alert type="info" message="尚无已加密字段的记录" showIcon />
            )}
          </>
        )}
      </Card>

      {/* ── 吊销确认 Modal ─────────────────────────────────────────────────── */}
      <Modal
        title={
          <Space>
            <WarningOutlined style={{ color: '#f5222d' }} />
            <span style={{ color: '#f5222d' }}>危险操作：吊销密钥</span>
          </Space>
        }
        open={revokeModalVisible}
        onCancel={() => setRevokeModalVisible(false)}
        onOk={confirmRevoke}
        okButtonProps={{
          danger: true,
          disabled: revokeConfirmText !== 'REVOKE',
          loading: revokeLoading,
        }}
        okText="确认吊销"
      >
        <Alert
          type="error"
          message="吊销密钥后，所有使用该密钥加密的数据将永久无法解密。此操作不可撤销。"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <p>如确认吊销，请在下方输入 <code>REVOKE</code>：</p>
        <Input
          value={revokeConfirmText}
          onChange={(e) => setRevokeConfirmText(e.target.value)}
          placeholder="输入 REVOKE 以确认"
          status={revokeConfirmText && revokeConfirmText !== 'REVOKE' ? 'error' : undefined}
        />
      </Modal>
    </div>
  );
};

export default DataSecurityPage;
