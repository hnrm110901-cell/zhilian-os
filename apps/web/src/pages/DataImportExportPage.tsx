import React, { useState } from 'react';
import {
  Card,
  Button,
  Upload,
  message,
  Space,
  Tabs,
  Alert,
} from 'antd';
import {
  UploadOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { apiClient } from '../services/api';
import { showSuccess, showError, handleApiError } from '../utils/message';

const { TabPane } = Tabs;

const DataImportExportPage: React.FC = () => {
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);

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
        </Tabs>
      </Card>
    </div>
  );
};

export default DataImportExportPage;
