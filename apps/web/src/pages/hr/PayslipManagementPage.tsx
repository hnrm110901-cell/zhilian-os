/**
 * 工资条管理页面
 * 路由: /payslip-management
 * 功能: 工资条推送状态 + 批量推送 + PDF下载
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Card, Table, Tag, Button, Space, DatePicker, message,
  Typography, Tooltip,
} from 'antd';
import {
  SendOutlined, FilePdfOutlined, CheckCircleOutlined,
  ClockCircleOutlined, FileTextOutlined,
} from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import { apiClient } from '../../services/api';
import type { PayslipStatusItem } from '../../services/hrService';
import dayjs from 'dayjs';

const { Title } = Typography;

const STORE_ID = localStorage.getItem('store_id') || '';

const PUSH_STATUS_MAP: Record<string, { label: string; color: string }> = {
  not_pushed: { label: '未推送', color: 'default' },
  pushing: { label: '推送中', color: 'processing' },
  pushed: { label: '已推送', color: 'success' },
  failed: { label: '推送失败', color: 'error' },
};

const PayslipManagementPage: React.FC = () => {
  const [payMonth, setPayMonth] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [items, setItems] = useState<PayslipStatusItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pushing, setPushing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await hrService.getPayslipPushStatus(STORE_ID, payMonth);
      setItems(res.data || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [payMonth]);

  useEffect(() => { load(); }, [load]);

  const handleBatchPush = async () => {
    setPushing(true);
    try {
      await hrService.batchPushPayslips(STORE_ID, payMonth);
      message.success('批量推送已发起');
      setTimeout(() => load(), 2000);
    } catch {
      message.error('批量推送失败');
    }
    setPushing(false);
  };

  const handleSinglePush = async (employeeId: string) => {
    try {
      await hrService.pushPayslip(employeeId, payMonth, STORE_ID);
      message.success('推送成功');
      load();
    } catch {
      message.error('推送失败');
    }
  };

  const handleDownloadPdf = (employeeId: string) => {
    const url = `/api/v1/hr/payslip/${employeeId}/${payMonth}/pdf?store_id=${STORE_ID}`;
    window.open(url, '_blank');
  };

  const columns = [
    { title: '员工', dataIndex: 'employee_name', key: 'employee_name', width: 120 },
    { title: '员工ID', dataIndex: 'employee_id', key: 'employee_id', width: 120 },
    { title: '月份', dataIndex: 'pay_month', key: 'pay_month', width: 100 },
    {
      title: '推送状态', dataIndex: 'push_status', key: 'push_status', width: 110,
      render: (v: string) => {
        const s = PUSH_STATUS_MAP[v] || PUSH_STATUS_MAP.not_pushed;
        return <Tag color={s.color}>{s.label}</Tag>;
      },
    },
    {
      title: '推送时间', dataIndex: 'pushed_at', key: 'pushed_at', width: 160,
      render: (v: string | null) => v ? v.replace('T', ' ').slice(0, 16) : '-',
    },
    {
      title: '员工确认', dataIndex: 'confirmed', key: 'confirmed', width: 100,
      render: (v: boolean) => v
        ? <Tag icon={<CheckCircleOutlined />} color="success">已确认</Tag>
        : <Tag icon={<ClockCircleOutlined />} color="default">未确认</Tag>,
    },
    {
      title: '确认时间', dataIndex: 'confirmed_at', key: 'confirmed_at', width: 160,
      render: (v: string | null) => v ? v.replace('T', ' ').slice(0, 16) : '-',
    },
    {
      title: '操作', key: 'actions', width: 180,
      render: (_: unknown, record: PayslipStatusItem) => (
        <Space>
          <Tooltip title="推送工资条">
            <Button
              size="small"
              icon={<SendOutlined />}
              onClick={() => handleSinglePush(record.employee_id)}
              disabled={record.push_status === 'pushed'}
            >
              推送
            </Button>
          </Tooltip>
          <Tooltip title="下载PDF">
            <Button
              size="small"
              icon={<FilePdfOutlined />}
              onClick={() => handleDownloadPdf(record.employee_id)}
            >
              PDF
            </Button>
          </Tooltip>
        </Space>
      ),
    },
  ];

  const pushedCount = items.filter(i => i.push_status === 'pushed').length;
  const confirmedCount = items.filter(i => i.confirmed).length;

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <FileTextOutlined style={{ marginRight: 8 }} />
        工资条管理
      </Title>

      <Card bordered={false}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Space>
            <DatePicker
              picker="month"
              value={dayjs(payMonth, 'YYYY-MM')}
              onChange={(d) => d && setPayMonth(d.format('YYYY-MM'))}
              allowClear={false}
            />
            <span style={{ color: '#888' }}>
              共 {items.length} 人 | 已推送 {pushedCount} | 已确认 {confirmedCount}
            </span>
          </Space>
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleBatchPush}
            loading={pushing}
          >
            批量推送全店
          </Button>
        </div>

        <Table
          rowKey="employee_id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={{ pageSize: 15 }}
          locale={{ emptyText: '暂无工资条数据，请先在薪酬管理中执行算薪' }}
        />
      </Card>
    </div>
  );
};

export default PayslipManagementPage;
