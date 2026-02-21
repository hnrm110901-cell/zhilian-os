import React, { useEffect, useState, useCallback } from 'react';
import { Card, Table, Button, Modal, Space, Tag, Popconfirm } from 'antd';
import {
  DatabaseOutlined,
  PlusOutlined,
  ReloadOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { showSuccess, showError, handleApiError, showLoading } from '../utils/message';
import dayjs from 'dayjs';

const BackupManagement: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [backups, setBackups] = useState<any[]>([]);
  const [creating, setCreating] = useState(false);

  const loadBackups = useCallback(async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/backup/list');
      setBackups(response.data.backups || []);
    } catch (err: any) {
      handleApiError(err, '加载备份列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBackups();
  }, [loadBackups]);

  const handleCreateBackup = async () => {
    const hide = showLoading('正在创建备份，请稍候...');
    try {
      setCreating(true);
      await apiClient.post('/backup/create', {
        backup_type: 'manual',
      });
      hide();
      showSuccess('备份创建成功');
      loadBackups();
    } catch (err: any) {
      hide();
      handleApiError(err, '创建备份失败');
    } finally {
      setCreating(false);
    }
  };

  const handleRestoreBackup = async (backupName: string) => {
    Modal.confirm({
      title: '确认恢复备份',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>您确定要恢复此备份吗？</p>
          <p style={{ color: '#ff4d4f', fontWeight: 'bold' }}>
            警告：此操作将覆盖当前数据库中的所有数据！
          </p>
          <p>备份文件：{backupName}</p>
        </div>
      ),
      okText: '确认恢复',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const hide = showLoading('正在恢复备份，请稍候...');
        try {
          await apiClient.post(`/backup/restore/${backupName}`);
          hide();
          showSuccess('备份恢复成功');
          // 刷新页面以重新加载数据
          setTimeout(() => {
            window.location.reload();
          }, 1500);
        } catch (err: any) {
          hide();
          handleApiError(err, '恢复备份失败');
        }
      },
    });
  };

  const handleDeleteBackup = async (backupName: string) => {
    try {
      await apiClient.delete(`/backup/${backupName}`);
      showSuccess('备份删除成功');
      loadBackups();
    } catch (err: any) {
      handleApiError(err, '删除备份失败');
    }
  };

  const handleVerifyBackup = async (backupName: string) => {
    const hide = showLoading('正在验证备份...');
    try {
      const response = await apiClient.get(`/backup/verify/${backupName}`);
      hide();

      if (response.data.valid) {
        showSuccess('备份文件验证通过');
      } else {
        showError('备份文件验证失败：' + (response.data.error || '文件损坏'));
      }
    } catch (err: any) {
      hide();
      handleApiError(err, '验证备份失败');
    }
  };

  const columns = [
    {
      title: '备份名称',
      dataIndex: 'name',
      key: 'name',
      width: 300,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => {
        const typeMap: any = {
          manual: { color: 'blue', text: '手动' },
          scheduled: { color: 'green', text: '定时' },
        };
        const t = typeMap[type] || { color: 'default', text: type };
        return <Tag color={t.color}>{t.text}</Tag>;
      },
    },
    {
      title: '大小',
      dataIndex: 'size_mb',
      key: 'size_mb',
      width: 100,
      render: (size: number) => `${size.toFixed(2)} MB`,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '保存天数',
      dataIndex: 'age_days',
      key: 'age_days',
      width: 100,
      render: (days: number) => {
        let color = 'green';
        if (days > 30) color = 'orange';
        if (days > 60) color = 'red';
        return <Tag color={color}>{days} 天</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 250,
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            type="link"
            onClick={() => handleVerifyBackup(record.name)}
          >
            验证
          </Button>
          <Button
            size="small"
            type="link"
            onClick={() => handleRestoreBackup(record.name)}
            danger
          >
            恢复
          </Button>
          <Popconfirm
            title="确定要删除此备份吗？"
            onConfirm={() => handleDeleteBackup(record.name)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px', background: '#f0f2f5', minHeight: '100vh' }}>
      <h1 style={{ marginBottom: '24px' }}>
        <DatabaseOutlined /> 数据备份管理
      </h1>

      <Card>
        <Space style={{ marginBottom: '16px' }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreateBackup}
            loading={creating}
          >
            创建备份
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={loadBackups}
            loading={loading}
          >
            刷新列表
          </Button>
        </Space>

        <div style={{ marginBottom: '16px', padding: '12px', background: '#e6f7ff', border: '1px solid #91d5ff', borderRadius: '4px' }}>
          <p style={{ margin: 0 }}>
            <CheckCircleOutlined style={{ color: '#1890ff', marginRight: '8px' }} />
            系统会在每天凌晨2点自动创建备份，最多保留30个备份文件。
          </p>
          <p style={{ margin: '8px 0 0 0' }}>
            <ExclamationCircleOutlined style={{ color: '#faad14', marginRight: '8px' }} />
            恢复备份将覆盖当前所有数据，请谨慎操作！
          </p>
        </div>

        <Table
          columns={columns}
          dataSource={backups}
          rowKey="name"
          loading={loading}
          pagination={{
            pageSize: 10,
            showTotal: (total) => `共 ${total} 个备份`,
          }}
        />
      </Card>
    </div>
  );
};

export default BackupManagement;
