import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card,
  Button,
  Upload,
  message,
  Space,
  Tabs,
  Alert,
  Table,
  Modal,
  Form,
  Select,
  Tag,
  Progress,
  Popconfirm,
} from 'antd';
import {
  UploadOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import type { UploadProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { showSuccess, showError, handleApiError, showLoading } from '../utils/message';

interface ExportJob {
  job_id: string;
  job_type: string;
  format: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress?: number;
  file_size?: number;
  created_at?: string;
}

const exportStatusColorMap: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
};

const exportStatusTextMap: Record<string, string> = {
  pending: '等待中',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
};

const { TabPane } = Tabs;

const DataImportExportPage: React.FC = () => {
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [exportJobs, setExportJobs] = useState<ExportJob[]>([]);
  const [exportJobsLoading, setExportJobsLoading] = useState(false);
  const [exportModalVisible, setExportModalVisible] = useState(false);
  const [exportForm] = Form.useForm();
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadExportJobs = useCallback(async () => {
    try {
      setExportJobsLoading(true);
      const res = await apiClient.get('/api/v1/export-jobs/');
      setExportJobs(res.data?.data || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载导出任务失败');
    } finally {
      setExportJobsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadExportJobs();
  }, [loadExportJobs]);

  useEffect(() => {
    const hasRunning = exportJobs.some(j => j.status === 'running' || j.status === 'pending');
    if (hasRunning && !pollingRef.current) {
      pollingRef.current = setInterval(loadExportJobs, 5000);
    } else if (!hasRunning && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    return () => {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    };
  }, [exportJobs, loadExportJobs]);

  const handleSubmitExportJob = async () => {
    try {
      const values = await exportForm.validateFields();
      const hide = showLoading('提交导出任务中...');
      try {
        await apiClient.post('/api/v1/export-jobs/', values);
        hide();
        showSuccess('导出任务已提交');
        setExportModalVisible(false);
        exportForm.resetFields();
        loadExportJobs();
      } catch (err: any) {
        hide();
        handleApiError(err, '提交任务失败');
      }
    } catch (_) {}
  };

  const handleDownloadExportJob = (job_id: string) => {
    const link = document.createElement('a');
    link.href = `/api/v1/export-jobs/${job_id}/download`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const handleDeleteExportJob = async (job_id: string) => {
    const hide = showLoading('删除中...');
    try {
      await apiClient.delete(`/api/v1/export-jobs/${job_id}`);
      hide();
      showSuccess('删除成功');
      loadExportJobs();
    } catch (err: any) {
      hide();
      handleApiError(err, '删除失败');
    }
  };

  const exportJobColumns: ColumnsType<ExportJob> = [
    { title: '任务类型', dataIndex: 'job_type', key: 'job_type' },
    { title: '格式', dataIndex: 'format', key: 'format', render: (v) => <Tag>{v?.toUpperCase()}</Tag> },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v) => <Tag color={exportStatusColorMap[v]}>{exportStatusTextMap[v] || v}</Tag>,
    },
    {
      title: '进度', dataIndex: 'progress', key: 'progress',
      render: (v, record) => record.status === 'running'
        ? <Progress percent={v ?? 0} size="small" style={{ width: 100 }} />
        : record.status === 'completed' ? <Progress percent={100} size="small" style={{ width: 100 }} /> : '-',
    },
    {
      title: '文件大小', dataIndex: 'file_size', key: 'file_size',
      render: (v) => {
        if (!v) return '-';
        if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
        return `${(v / 1024 / 1024).toFixed(1)} MB`;
      },
    },
    {
      title: '操作', key: 'action',
      render: (_, record) => (
        <Space>
          {record.status === 'completed' && (
            <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownloadExportJob(record.job_id)}>下载</Button>
          )}
          <Popconfirm title="确认删除？" onConfirm={() => handleDeleteExportJob(record.job_id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const handleExportUsers = async () => {
    try {
      message.loading({ content: '正在导出用户数据...', key: 'export' });

      const response = await apiClient.get('/data/export/users', {
        responseType: 'blob',
      });

      // 创建下载链接
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'users_export.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      message.success({ content: '用户数据导出成功', key: 'export' });
    } catch (err: any) {
      message.error({ content: '导出失败', key: 'export' });
      handleApiError(err, '导出用户数据失败');
    }
  };

  const handleExportInventory = async () => {
    try {
      message.loading({ content: '正在导出库存数据...', key: 'export' });

      const response = await apiClient.get('/data/export/inventory', {
        responseType: 'blob',
      });

      // 创建下载链接
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'inventory_export.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      message.success({ content: '库存数据导出成功', key: 'export' });
    } catch (err: any) {
      message.error({ content: '导出失败', key: 'export' });
      handleApiError(err, '导出库存数据失败');
    }
  };

  const handleDownloadUserTemplate = async () => {
    try {
      const response = await apiClient.get('/data/templates/users', {
        responseType: 'blob',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'user_import_template.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      showSuccess('模板下载成功');
    } catch (err: any) {
      handleApiError(err, '下载模板失败');
    }
  };

  const handleDownloadInventoryTemplate = async () => {
    try {
      const response = await apiClient.get('/data/templates/inventory', {
        responseType: 'blob',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'inventory_import_template.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      showSuccess('模板下载成功');
    } catch (err: any) {
      handleApiError(err, '下载模板失败');
    }
  };

  const userUploadProps: UploadProps = {
    name: 'file',
    accept: '.csv',
    showUploadList: false,
    beforeUpload: (file) => {
      const isCSV = file.name.endsWith('.csv');
      if (!isCSV) {
        message.error('只能上传CSV文件!');
      }
      return isCSV || Upload.LIST_IGNORE;
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        setImporting(true);
        setImportResult(null);

        const formData = new FormData();
        formData.append('file', file);

        const response = await apiClient.post('/data/import/users', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        });

        setImportResult(response.data);

        if (response.data.success) {
          showSuccess(`成功导入 ${response.data.imported_count} 个用户`);
          onSuccess?.(response.data);
        } else {
          showError('导入失败，请查看错误详情');
          onError?.(new Error('Import failed'));
        }
      } catch (err: any) {
        handleApiError(err, '导入用户数据失败');
        onError?.(err);
      } finally {
        setImporting(false);
      }
    },
  };

  const inventoryUploadProps: UploadProps = {
    name: 'file',
    accept: '.csv',
    showUploadList: false,
    beforeUpload: (file) => {
      const isCSV = file.name.endsWith('.csv');
      if (!isCSV) {
        message.error('只能上传CSV文件!');
      }
      return isCSV || Upload.LIST_IGNORE;
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        setImporting(true);
        setImportResult(null);

        const formData = new FormData();
        formData.append('file', file);

        const response = await apiClient.post('/data/import/inventory', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        });

        setImportResult(response.data);

        if (response.data.success) {
          showSuccess(`成功导入 ${response.data.imported_count} 个库存项`);
          onSuccess?.(response.data);
        } else {
          showError('导入失败，请查看错误详情');
          onError?.(new Error('Import failed'));
        }
      } catch (err: any) {
        handleApiError(err, '导入库存数据失败');
        onError?.(err);
      } finally {
        setImporting(false);
      }
    },
  };

  return (
    <div>
      <h1 style={{ marginBottom: '24px' }}>
        <FileExcelOutlined /> 数据导入导出
      </h1>

      <Alert
        message="使用说明"
        description={
          <div>
            <p>1. 导出：将系统数据导出为CSV文件，可用于数据备份或分析</p>
            <p>2. 导入：从CSV文件批量导入数据，请先下载模板了解格式要求</p>
            <p>3. 注意：导入前请确保数据格式正确，避免导入失败</p>
          </div>
        }
        type="info"
        showIcon
        style={{ marginBottom: '24px' }}
      />

      <Card>
        <Tabs defaultActiveKey="users">
          <TabPane tab="用户数据" key="users">
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              {/* 导出 */}
              <Card title="导出用户数据" size="small">
                <p>导出所有用户数据为CSV文件</p>
                <Button
                  type="primary"
                  icon={<DownloadOutlined />}
                  onClick={handleExportUsers}
                >
                  导出用户数据
                </Button>
              </Card>

              {/* 导入 */}
              <Card title="导入用户数据" size="small">
                <Space direction="vertical" style={{ width: '100%' }}>
                  <div>
                    <p>从CSV文件批量导入用户数据</p>
                    <p style={{ color: '#999', fontSize: '12px' }}>
                      必需列: username, email, role | 可选列: store_id, is_active
                    </p>
                  </div>

                  <Space>
                    <Button
                      icon={<DownloadOutlined />}
                      onClick={handleDownloadUserTemplate}
                    >
                      下载导入模板
                    </Button>

                    <Upload {...userUploadProps}>
                      <Button
                        type="primary"
                        icon={<UploadOutlined />}
                        loading={importing}
                      >
                        上传CSV文件
                      </Button>
                    </Upload>
                  </Space>

                  {/* 导入结果 */}
                  {importResult && (
                    <Alert
                      message={
                        importResult.success ? (
                          <span>
                            <CheckCircleOutlined style={{ color: '#52c41a' }} />{' '}
                            导入成功
                          </span>
                        ) : (
                          <span>
                            <CloseCircleOutlined style={{ color: '#ff4d4f' }} />{' '}
                            导入失败
                          </span>
                        )
                      }
                      description={
                        <div>
                          <p>成功导入: {importResult.imported_count} 条</p>
                          {importResult.errors && importResult.errors.length > 0 && (
                            <div>
                              <p style={{ color: '#ff4d4f', fontWeight: 'bold' }}>
                                错误信息:
                              </p>
                              <ul style={{ maxHeight: '200px', overflow: 'auto' }}>
                                {importResult.errors.map((error: string, index: number) => (
                                  <li key={index}>{error}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      }
                      type={importResult.success ? 'success' : 'error'}
                      showIcon
                    />
                  )}
                </Space>
              </Card>
            </Space>
          </TabPane>

          <TabPane tab="库存数据" key="inventory">
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              {/* 导出 */}
              <Card title="导出库存数据" size="small">
                <p>导出所有库存数据为CSV文件</p>
                <Button
                  type="primary"
                  icon={<DownloadOutlined />}
                  onClick={handleExportInventory}
                >
                  导出库存数据
                </Button>
              </Card>

              {/* 导入 */}
              <Card title="导入库存数据" size="small">
                <Space direction="vertical" style={{ width: '100%' }}>
                  <div>
                    <p>从CSV文件批量导入库存数据</p>
                    <p style={{ color: '#999', fontSize: '12px' }}>
                      必需列: name, category, quantity, unit | 可选列: min_quantity,
                      max_quantity, unit_price, supplier, store_id
                    </p>
                  </div>

                  <Space>
                    <Button
                      icon={<DownloadOutlined />}
                      onClick={handleDownloadInventoryTemplate}
                    >
                      下载导入模板
                    </Button>

                    <Upload {...inventoryUploadProps}>
                      <Button
                        type="primary"
                        icon={<UploadOutlined />}
                        loading={importing}
                      >
                        上传CSV文件
                      </Button>
                    </Upload>
                  </Space>

                  {/* 导入结果 */}
                  {importResult && (
                    <Alert
                      message={
                        importResult.success ? (
                          <span>
                            <CheckCircleOutlined style={{ color: '#52c41a' }} />{' '}
                            导入成功
                          </span>
                        ) : (
                          <span>
                            <CloseCircleOutlined style={{ color: '#ff4d4f' }} />{' '}
                            导入失败
                          </span>
                        )
                      }
                      description={
                        <div>
                          <p>成功导入: {importResult.imported_count} 条</p>
                          {importResult.errors && importResult.errors.length > 0 && (
                            <div>
                              <p style={{ color: '#ff4d4f', fontWeight: 'bold' }}>
                                错误信息:
                              </p>
                              <ul style={{ maxHeight: '200px', overflow: 'auto' }}>
                                {importResult.errors.map((error: string, index: number) => (
                                  <li key={index}>{error}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      }
                      type={importResult.success ? 'success' : 'error'}
                      showIcon
                    />
                  )}
                </Space>
              </Card>
            </Space>
          </TabPane>

          <TabPane tab="异步导出任务" key="async-export">
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setExportModalVisible(true)}>
                  提交导出任务
                </Button>
                <Button icon={<ReloadOutlined />} onClick={loadExportJobs}>刷新</Button>
              </Space>
            </div>
            <Table
              columns={exportJobColumns}
              dataSource={exportJobs}
              rowKey="job_id"
              loading={exportJobsLoading}
            />
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title="提交异步导出任务"
        open={exportModalVisible}
        onOk={handleSubmitExportJob}
        onCancel={() => { setExportModalVisible(false); exportForm.resetFields(); }}
        destroyOnClose
      >
        <Form form={exportForm} layout="vertical">
          <Form.Item name="job_type" label="任务类型" rules={[{ required: true, message: '请选择任务类型' }]}>
            <Select options={[
              { label: '交易记录', value: 'transactions' },
              { label: '审计日志', value: 'audit_logs' },
              { label: '订单数据', value: 'orders' },
            ]} />
          </Form.Item>
          <Form.Item name="format" label="导出格式" rules={[{ required: true, message: '请选择格式' }]}>
            <Select options={[
              { label: 'CSV', value: 'csv' },
              { label: 'Excel (xlsx)', value: 'xlsx' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DataImportExportPage;
