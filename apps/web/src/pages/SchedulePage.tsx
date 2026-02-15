import React, { useState } from 'react';
import { Card, Form, Input, Button, DatePicker, Table, message, Space, Tag } from 'antd';
import { apiClient } from '../services/api';
import type { ScheduleRequest } from '../types/api';

const SchedulePage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleSubmit = async (values: any) => {
    try {
      setLoading(true);

      const request: ScheduleRequest = {
        action: 'run',
        store_id: values.store_id,
        date: values.date.format('YYYY-MM-DD'),
        employees: [
          {
            id: 'emp_001',
            name: '张三',
            skills: ['waiter', 'cashier'],
          },
          {
            id: 'emp_002',
            name: '李四',
            skills: ['chef'],
          },
          {
            id: 'emp_003',
            name: '王五',
            skills: ['waiter'],
          },
          {
            id: 'emp_004',
            name: '赵六',
            skills: ['chef'],
          },
        ],
      };

      const response = await apiClient.callAgent('schedule', request);
      setResult(response.output_data);
      message.success(`排班完成，耗时 ${response.execution_time.toFixed(2)}秒`);
    } catch (error: any) {
      message.error(error.message || '排班失败');
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    {
      title: '员工ID',
      dataIndex: 'employee_id',
      key: 'employee_id',
    },
    {
      title: '员工姓名',
      dataIndex: 'employee_name',
      key: 'employee_name',
    },
    {
      title: '技能',
      dataIndex: 'skill',
      key: 'skill',
      render: (skill: string) => <Tag color="blue">{skill}</Tag>,
    },
    {
      title: '班次',
      dataIndex: 'shift',
      key: 'shift',
      render: (shift: string) => {
        const colorMap: Record<string, string> = {
          morning: 'green',
          afternoon: 'orange',
          evening: 'purple',
        };
        return <Tag color={colorMap[shift] || 'default'}>{shift}</Tag>;
      },
    },
    {
      title: '开始时间',
      dataIndex: 'start_time',
      key: 'start_time',
    },
    {
      title: '结束时间',
      dataIndex: 'end_time',
      key: 'end_time',
    },
  ];

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>智能排班Agent</h1>

      <Card title="生成排班表" style={{ marginBottom: 24 }}>
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            label="门店ID"
            name="store_id"
            rules={[{ required: true, message: '请输入门店ID' }]}
          >
            <Input placeholder="例如: store_001" />
          </Form.Item>

          <Form.Item
            label="排班日期"
            name="date"
            rules={[{ required: true, message: '请选择日期' }]}
          >
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                生成排班
              </Button>
              <Button onClick={() => form.resetFields()}>重置</Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {result && (
        <>
          {result.success ? (
            <>
              <Card title="排班结果" style={{ marginBottom: 24 }}>
                <Table
                  dataSource={result.schedule}
                  columns={columns}
                  rowKey="employee_id"
                  pagination={false}
                />
              </Card>

              {result.suggestions && result.suggestions.length > 0 && (
                <Card title="优化建议">
                  <ul>
                    {result.suggestions.map((suggestion: string, index: number) => (
                      <li key={index}>{suggestion}</li>
                    ))}
                  </ul>
                </Card>
              )}
            </>
          ) : (
            <Card title="错误">
              <p style={{ color: 'red' }}>{result.error}</p>
            </Card>
          )}
        </>
      )}
    </div>
  );
};

export default SchedulePage;
