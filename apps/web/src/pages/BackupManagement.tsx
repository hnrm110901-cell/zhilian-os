import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Table, Button, Modal, Form, DatePicker, Space,
  Popconfirm, Row, Col, Statistic, Tag, Progress,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, DownloadOutlined, DeleteOutlined,
  CloudUploadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { showSuccess, handleApiError, showLoading } from '../utils/message';

interface BackupJob {
  job_id: string;
  backup_type: 'full' | 'incremental';
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress?: number;
  size?: number;
  checksum?: string;
  created_at?: string;
  completed_at?: string;
}

const statusColorMap: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
};

const statusTextMap: Record<string, string> = {
  pending: '等待中',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
};

const BackupManagement: React.FC = () => {
  const [backups, setBackups] = useState<BackupJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [incrementalModalVisible, setIncrementalModalVisible] = useState(false);
  const [form] = Form.useForm();
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadBackups = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiClient.get('/api/v1/backups/');
      setBackups(res.data?.data || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载备份列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const pollRunningJobs = useCallback(async (currentBackups: BackupJob[]) => {
    const running = currentBackups.filter(j => j.status === 'running' || j.status === 'pending');
    if (running.length === 0) return;
    const updated = await Promise.all(
      running.map(async (j) => {
        try {
          const res = await apiClient.get(`/api/v1/backups/${j.job_id}`);
          return res.data?.data || res.data;
        } catch {
          return j;
        }
      })
    );
    setBackups(prev => prev.map(b => {
      const u = updated.find((u: any) => u?.job_id === b.job_id);
      return u || b;
    }));
  }, []);

  useEffect(() => {
    loadBackups();
  }, [loadBackups]);

  useEffect(() => {
    const hasRunning = backups.some(b => b.status === 'running' || b.status === 'pending');
    if (hasRunning && !pollingRef.current) {
      pollingRef.current = setInterval(() => pollRunningJobs(backups), 5000);
    } else if (!hasRunning && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [backups, pollRunningJobs]);

  const triggerBackup = async (backup_type: 'full' | 'incremental', since_timestamp?: string) => {
    const hide = showLoading(`触发${backup_type === 'full' ? '全量' : '增量'}备份中...`);
    try {
      const body: any = { backup_type };
      if (since_timestamp) body.since_timestamp = since_timestamp;
      await apiClient.post('/api/v1/backups/', body);
      hide();
      showSuccess('备份任务已提交');
      loadBackups();
    } catch (err: any) {
      hide();
      handleApiError(err, '触发备份失败');
    }
  };

  const handleIncrementalOk = async () => {
    try {
      const values = await form.validateFields();
      const since = values.since_timestamp ? values.since_timestamp.toISOString() : undefined;
      setIncrementalModalVisible(false);
      form.resetFields();
      await triggerBackup('incremental', since);
    } catch (_) {}
  };

  const handleDownload = (job_id: string) => {
    const link = document.createElement('a');
    link.href = `/api/v1/backups/${job_id}/download`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const handleDelete = async (job_id: string) => {
    const hide = showLoading('删除中...');
    try {
      await apiClient.delete(`/api/v1/backups/${job_id}`);
      hide();
      showSuccess('删除成功');
      loadBackups();
    } catch (err: any) {
      hide();
      handleApiError(err, '删除失败');
    }
  };

  const formatSize = (bytes?: number) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  const columns: ColumnsType<BackupJob> = [
    {
      title: '类型', dataIndex: 'backup_type', key: 'backup_type',
      render: (v) => <Tag color={v === 'full' ? 'blue' : 'cyan'}>{v === 'full' ? '全量' : '增量'}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v) => <Tag color={statusColorMap[v]}>{statusTextMap[v] || v}</Tag>,
    },
    {
      title: '进度', dataIndex: 'progress', key: 'progress',
      render: (v, record) => record.status === 'running'
        ? <Progress percent={v ?? 0} size="small" style={{ width: 100 }} />
        : record.status === 'completed' ? <Progress percent={100} size="small" style={{ width: 100 }} /> : '-',
    },
    { title: '大小', dataIndex: 'size', key: 'size', render: formatSize },
    { title: '校验和', dataIndex: 'checksum', key: 'checksum', ellipsis: true, render: (v) => v || '-' },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at',
      render: (v) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '操作', key: 'action',
      render: (_, record) => (
        <Space>
          {record.status === 'completed' && (
            <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(record.job_id)}>下载</Button>
          )}
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.job_id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const completedBackups = backups.filter(b => b.status === 'completed');
  const lastBackup = completedBackups.sort((a, b) =>
    dayjs(b.completed_at || b.created_at || 0).diff(dayjs(a.completed_at || a.created_at || 0))
  )[0];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="总备份数" value={backups.length} suffix="个" />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="最近备份时间"
              value={lastBackup?.completed_at
                ? dayjs(lastBackup.completed_at).format('MM-DD HH:mm')
                : '暂无'}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <div style={{ marginBottom: 16 }}>
          <Space>
            <Button type="primary" icon={<CloudUploadOutlined />} onClick={() => triggerBackup('full')}>
              触发全量备份
            </Button>
            <Button icon={<PlusOutlined />} onClick={() => setIncrementalModalVisible(true)}>
              触发增量备份
            </Button>
            <Button icon={<ReloadOutlined />} onClick={loadBackups}>刷新</Button>
          </Space>
        </div>
        <Table columns={columns} dataSource={backups} rowKey="job_id" loading={loading} />
      </Card>

      <Modal
        title="触发增量备份"
        open={incrementalModalVisible}
        onOk={handleIncrementalOk}
        onCancel={() => { setIncrementalModalVisible(false); form.resetFields(); }}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="since_timestamp" label="起始时间（可选）"
            extra="不填则从上次备份时间开始">
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default BackupManagement;
