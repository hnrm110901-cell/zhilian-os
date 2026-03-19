/**
 * 花名册导入页面 — Excel上传 → 列映射预览 → 确认导入
 */
import React, { useState } from 'react';
import { Card, Upload, Button, Table, message, Alert, Steps, Space, Tag, Typography } from 'antd';
import { UploadOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { ImportPreviewResult, ImportConfirmResult } from '../../services/hrService';
import { useAuthStore } from '../../stores/authStore';

const { Title } = Typography;

const RosterImportPage: React.FC = () => {
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResult | null>(null);
  const [result, setResult] = useState<ImportConfirmResult | null>(null);
  const [loading, setLoading] = useState(false);
  const user = useAuthStore((s) => s.user);
  const brandId = user?.brand_id || '';

  const handleUpload = async (uploadFile: File) => {
    setFile(uploadFile);
    setLoading(true);
    try {
      const res = await hrService.previewRosterImport(brandId, uploadFile);
      setPreview(res);
      setStep(1);
    } catch (e: unknown) {
      message.error('文件解析失败');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const res = await hrService.confirmRosterImport(brandId, file);
      setResult(res);
      setStep(2);
      message.success(`导入完成：新增${res.created}人，更新${res.updated}人`);
    } catch (e: unknown) {
      message.error('导入失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>花名册导入</Title>
      <Steps current={step} style={{ marginBottom: 24 }}>
        <Steps.Step title="上传文件" />
        <Steps.Step title="预览确认" />
        <Steps.Step title="导入完成" />
      </Steps>

      {step === 0 && (
        <Card>
          <Alert
            message="支持从乐才HR、钉钉、企业微信导出的花名册Excel文件（.xlsx）"
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <Upload
            accept=".xlsx,.xls"
            showUploadList={false}
            beforeUpload={(f) => { handleUpload(f); return false; }}
          >
            <Button icon={<UploadOutlined />} loading={loading} type="primary" size="large">
              选择花名册文件
            </Button>
          </Upload>
        </Card>
      )}

      {step === 1 && preview && (
        <Card>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Alert
              message={`检测到 ${preview.total_rows} 条数据，匹配 ${preview.matched_columns} 列`}
              type="success"
              showIcon
            />
            {preview.unmatched_columns.length > 0 && (
              <Alert
                message={`未匹配的列：${preview.unmatched_columns.join('、')}`}
                type="warning"
                showIcon
              />
            )}
            <Title level={5}>数据预览（前10行）</Title>
            <Table
              dataSource={preview.preview.map((r, i) => ({ key: i, ...r }))}
              columns={Object.keys(preview.preview[0] || {}).filter(k => k !== 'key').map(k => ({
                title: k,
                dataIndex: k,
                key: k,
                width: 120,
                ellipsis: true,
              }))}
              scroll={{ x: 'max-content' }}
              pagination={false}
              size="small"
            />
            <Space>
              <Button onClick={() => setStep(0)}>重新上传</Button>
              <Button type="primary" loading={loading} onClick={handleConfirm}>
                确认导入 {preview.total_rows} 条数据
              </Button>
            </Space>
          </Space>
        </Card>
      )}

      {step === 2 && result && (
        <Card>
          <Alert
            message="导入完成"
            description={
              <div>
                <p>新增：<Tag color="green">{result.created}人</Tag></p>
                <p>更新：<Tag color="blue">{result.updated}人</Tag></p>
                <p>跳过：<Tag>{result.skipped}人</Tag></p>
                {result.errors.length > 0 && (
                  <p>错误：<Tag color="red">{result.errors.length}条</Tag></p>
                )}
              </div>
            }
            type="success"
            showIcon
            icon={<CheckCircleOutlined />}
          />
          <Button onClick={() => { setStep(0); setFile(null); setPreview(null); setResult(null); }} style={{ marginTop: 16 }}>
            继续导入
          </Button>
        </Card>
      )}
    </div>
  );
};

export default RosterImportPage;
