import React, { useState, useEffect, useCallback } from 'react';
import { Card, Table, Tag, DatePicker, Button, Empty, Spin, Typography, Space, Badge } from 'antd';
import { ReloadOutlined, CalendarOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

dayjs.extend(isoWeek);

const { Title, Text } = Typography;

const SHIFT_TYPE_MAP: Record<string, { label: string; color: string }> = {
  morning:   { label: '早班', color: 'gold' },
  afternoon: { label: '午班', color: 'blue' },
  evening:   { label: '晚班', color: 'purple' },
};

const MySchedulePage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [weekStart, setWeekStart] = useState<Dayjs>(dayjs().startOf('isoWeek'));
  const [data, setData] = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/schedules/my-schedule', {
        params: { week_start: weekStart.format('YYYY-MM-DD') },
      });
      setData(res.data);
    } catch (err: any) {
      handleApiError(err, '加载班表失败');
    } finally {
      setLoading(false);
    }
  }, [weekStart]);

  useEffect(() => { load(); }, [load]);

  const columns = [
    {
      title: '日期',
      dataIndex: 'date',
      render: (v: string) => {
        const d = dayjs(v);
        const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
        return <Text strong>{v} <Text type="secondary">({weekdays[d.isoWeekday() - 1]})</Text></Text>;
      },
    },
    {
      title: '班次',
      dataIndex: 'shift_type',
      render: (v: string) => {
        const m = SHIFT_TYPE_MAP[v] || { label: v, color: 'default' };
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    { title: '上班时间', dataIndex: 'start_time' },
    { title: '下班时间', dataIndex: 'end_time' },
    { title: '岗位', dataIndex: 'position', render: (v: string) => v || '-' },
    {
      title: '状态',
      dataIndex: 'is_confirmed',
      render: (v: boolean) => v
        ? <Badge status="success" text="已确认" />
        : <Badge status="processing" text="待确认" />,
    },
  ];

  const shifts = data?.shifts || [];
  const totalHours = shifts.reduce((acc: number, s: any) => {
    const [sh, sm] = s.start_time.split(':').map(Number);
    const [eh, em] = s.end_time.split(':').map(Number);
    return acc + (eh * 60 + em - sh * 60 - sm) / 60;
  }, 0);

  return (
    <div>
      <Title level={4}><CalendarOutlined /> 我的班表</Title>
      <Card
        extra={
          <Space>
            <DatePicker
              picker="week"
              value={weekStart}
              onChange={(v) => v && setWeekStart(v.startOf('isoWeek'))}
              allowClear={false}
            />
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          </Space>
        }
      >
        <Spin spinning={loading}>
          {shifts.length === 0 && !loading ? (
            <Empty description="本周暂无排班" />
          ) : (
            <>
              <Space style={{ marginBottom: 16 }}>
                <Tag color="blue">本周班次：{shifts.length} 次</Tag>
                <Tag color="green">合计工时：{totalHours.toFixed(1)} 小时</Tag>
              </Space>
              <Table
                dataSource={shifts}
                columns={columns}
                rowKey="shift_id"
                pagination={false}
                size="middle"
              />
            </>
          )}
        </Spin>
      </Card>
    </div>
  );
};

export default MySchedulePage;
