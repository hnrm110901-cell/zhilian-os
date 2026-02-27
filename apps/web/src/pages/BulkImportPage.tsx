import React, { useState } from 'react';
import {
  Card, Select, Upload, Button, Table, Alert, Space, Typography, Tabs, Tag,
} from 'antd';
import { UploadOutlined, DownloadOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { Text } = Typography;

type Entity = 'employees' | 'inventory' | 'orders';

const ENTITY_LABELS: Record<Entity, string> = {
  employees: '员工',
  inventory: '库存',
  orders: '订单',
};

const BulkImportPage: React.FC = () => {
  const [storeId, setStoreId] = useState('STORE001');
  const [entity, setEntity] = useState<Entity>('inventory');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ success: number; failed: number; errors: string[] } | null>(null);

  const handleDownloadTemplate = async () => {
    try {
      const res = await apiClient.get(`/api/v1/bulk-import/template/${entity}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `import_template_${entity}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      handleApiError(err, '下载模板失败');
    }
  };

  const handleUpload = async () => {
    if (!fileList.length) return;
    setLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append('file', fileList[0] as any);
      const res = await apiClient.post(
        `/api/v1/bulk-import/${entity}/${storeId}`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      setResult(res.data);
      if (res.data.failed === 0) showSuccess(`导入完成，共 ${res.data.success} 条`);
    } catch (err: any) {
      handleApiError(err, '导入失败');
    } finally {
      setLoading(false);
    }
  };

  const errorColumns = [
    { title: '错误信息', dataIndex: 'msg', key: 'msg' },
  ];

  const tabItems = (Object.keys(ENTITY_LABELS) as Entity[]).map((e) => ({
    key: e,
    label: `导入${ENTITY_LABELS[e]}`,
    children: null,
  }));

  return (
    <div>
      <Card title="数据批量导入" style={{ marginBottom: 16 }}>
        <Space wrap style={{ marginBottom: 16 }}>
          <Select value={storeId} onChange={setStoreId} style={{ width: 160 }} placeholder="选择门店">
            <Option value="STORE001">STORE001</Option>
          </Select>
          <Tabs
            activeKey={entity}
            onChange={(k) => { setEntity(k as Entity); setFileList([]); setResult(null); }}
            items={tabItems}
            style={{ marginBottom: 0 }}
          />
        </Space>

        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Button icon={<DownloadOutlined />} onClick={handleDownloadTemplate}>
              下载{ENTITY_LABELS[entity]}导入模板
            </Button>
            <Text type="secondary" style={{ fontSize: 12 }}>
              请按模板格式填写后上传，支持 .xlsx / .xls，单次最多 5000 行
            </Text>
          </Space>

          <Upload
            accept=".xlsx,.xls"
            maxCount={1}
            fileList={fileList}
            beforeUpload={(file) => { setFileList([file]); return false; }}
            onRemove={() => setFileList([])}
          >
            <Button icon={<UploadOutlined />}>选择 Excel 文件</Button>
          </Upload>

          <Button
            type="primary"
            onClick={handleUpload}
            loading={loading}
            disabled={!fileList.length}
          >
            开始导入
          </Button>
        </Space>
      </Card>

      {result && (
        <Card title="导入结果">
          <Space style={{ marginBottom: 12 }}>
            <Tag icon={<CheckCircleOutlined />} color="success">成功 {result.success} 条</Tag>
            {result.failed > 0 && (
              <Tag icon={<CloseCircleOutlined />} color="error">失败 {result.failed} 条</Tag>
            )}
          </Space>
          {result.errors.length > 0 && (
            <Alert
              type="warning"
              message="部分行导入失败"
              description={
                <Table
                  dataSource={result.errors.map((msg, i) => ({ key: i, msg }))}
                  columns={errorColumns}
                  size="small"
                  pagination={false}
                  scroll={{ y: 200 }}
                />
              }
            />
          )}
        </Card>
      )}
    </div>
  );
};

export default BulkImportPage;
