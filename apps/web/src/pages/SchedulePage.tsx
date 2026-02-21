import React, { useState } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  DatePicker,
  Table,
  message,
  Space,
  Tag,
  Tabs,
  Modal,
  Select,
  Row,
  Col,
  Statistic,
} from 'antd';
import {
  PlusOutlined,
  UserOutlined,
  CalendarOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import type { ScheduleRequest } from '../types/api';

const { TabPane } = Tabs;
const { Option } = Select;

interface Employee {
  id: string;
  name: string;
  skills: string[];
}

const skillOptions = [
  { value: 'waiter', label: '服务员', color: 'blue' },
  { value: 'cashier', label: '收银员', color: 'green' },
  { value: 'chef', label: '厨师', color: 'orange' },
  { value: 'manager', label: '经理', color: 'purple' },
  { value: 'cleaner', label: '清洁员', color: 'cyan' },
];

const SchedulePage: React.FC = () => {
  const [form] = Form.useForm();
  const [employeeForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [employees, setEmployees] = useState<Employee[]>([
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
  ]);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null);

  // 添加或编辑员工
  const handleAddEmployee = () => {
    setEditingEmployee(null);
    employeeForm.resetFields();
    setModalVisible(true);
  };

  const handleEditEmployee = (employee: Employee) => {
    setEditingEmployee(employee);
    employeeForm.setFieldsValue(employee);
    setModalVisible(true);
  };

  const handleSaveEmployee = async (values: any) => {
    if (editingEmployee) {
      // 编辑现有员工
      setEmployees(
        employees.map((emp) =>
          emp.id === editingEmployee.id ? { ...emp, ...values } : emp
        )
      );
      message.success('员工信息已更新');
    } else {
      // 添加新员工
      const newEmployee: Employee = {
        id: `emp_${Date.now()}`,
        name: values.name,
        skills: values.skills,
      };
      setEmployees([...employees, newEmployee]);
      message.success('员工已添加');
    }
    setModalVisible(false);
    employeeForm.resetFields();
  };

  const handleDeleteEmployee = (employeeId: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个员工吗？',
      onOk: () => {
        setEmployees(employees.filter((emp) => emp.id !== employeeId));
        message.success('员工已删除');
      },
    });
  };

  const handleSubmit = async (values: any) => {
    if (employees.length === 0) {
      message.warning('请先添加员工');
      return;
    }

    try {
      setLoading(true);

      const request: ScheduleRequest = {
        action: 'run',
        store_id: values.store_id,
        date: values.date.format('YYYY-MM-DD'),
        employees: employees,
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

  // 员工列表表格列
  const employeeColumns = [
    {
      title: '员工ID',
      dataIndex: 'id',
      key: 'id',
      width: 150,
    },
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '技能',
      dataIndex: 'skills',
      key: 'skills',
      render: (skills: string[]) => (
        <>
          {skills.map((skill) => {
            const skillOption = skillOptions.find((opt) => opt.value === skill);
            return (
              <Tag key={skill} color={skillOption?.color || 'default'}>
                {skillOption?.label || skill}
              </Tag>
            );
          })}
        </>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: any, record: Employee) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => handleEditEmployee(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            danger
            size="small"
            onClick={() => handleDeleteEmployee(record.id)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  // 排班结果表格列
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

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="员工总数"
              value={employees.length}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="已排班"
              value={result ? result.schedule?.length || 0 : 0}
              prefix={<CalendarOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="技能类型"
              value={new Set(employees.flatMap((e) => e.skills)).size}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      <Tabs defaultActiveKey="employees">
        <TabPane tab="员工管理" key="employees">
          <Card
            title="员工列表"
            extra={
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleAddEmployee}
              >
                添加员工
              </Button>
            }
          >
            <Table
              dataSource={employees}
              columns={employeeColumns}
              rowKey="id"
              pagination={false}
              locale={{ emptyText: '暂无员工，请先添加员工' }}
            />
          </Card>
        </TabPane>

        <TabPane tab="生成排班" key="schedule">
          <Card title="排班设置">
            <Form form={form} layout="vertical" onFinish={handleSubmit}>
              <Form.Item
                label="门店ID"
                name="store_id"
                rules={[{ required: true, message: '请输入门店ID' }]}
                tooltip="请输入需要排班的门店ID"
              >
                <Input placeholder="例如: store_001" />
              </Form.Item>

              <Form.Item
                label="排班日期"
                name="date"
                rules={[{ required: true, message: '请选择日期' }]}
                tooltip="选择需要生成排班表的日期"
              >
                <DatePicker style={{ width: '100%' }} placeholder="选择日期" />
              </Form.Item>

              <Form.Item>
                <Space>
                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={loading}
                    icon={<CalendarOutlined />}
                    disabled={employees.length === 0}
                  >
                    生成排班
                  </Button>
                  <Button onClick={() => form.resetFields()}>重置</Button>
                  {employees.length === 0 && (
                    <span style={{ color: '#ff4d4f', marginLeft: 8 }}>
                      请先在"员工管理"中添加员工
                    </span>
                  )}
                </Space>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>

        {result && (
          <TabPane tab="排班结果" key="result">
            {result.success ? (
              <>
                <Card title="排班表" style={{ marginBottom: 24 }}>
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
          </TabPane>
        )}
      </Tabs>

      {/* 员工编辑Modal */}
      <Modal
        title={editingEmployee ? '编辑员工' : '添加员工'}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          employeeForm.resetFields();
        }}
        footer={null}
        width={500}
      >
        <Form
          form={employeeForm}
          layout="vertical"
          onFinish={handleSaveEmployee}
        >
          <Form.Item
            label="员工姓名"
            name="name"
            rules={[
              { required: true, message: '请输入员工姓名' },
              { min: 2, max: 20, message: '姓名长度应在2-20个字符之间' },
            ]}
          >
            <Input placeholder="请输入员工姓名" />
          </Form.Item>

          <Form.Item
            label="技能"
            name="skills"
            rules={[
              { required: true, message: '请选择至少一项技能' },
              {
                type: 'array',
                min: 1,
                message: '请选择至少一项技能',
              },
            ]}
            tooltip="员工可以拥有多项技能"
          >
            <Select
              mode="multiple"
              placeholder="请选择员工技能"
              style={{ width: '100%' }}
            >
              {skillOptions.map((option) => (
                <Option key={option.value} value={option.value}>
                  <Tag color={option.color}>{option.label}</Tag>
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button
                onClick={() => {
                  setModalVisible(false);
                  employeeForm.resetFields();
                }}
              >
                取消
              </Button>
              <Button type="primary" htmlType="submit">
                {editingEmployee ? '保存' : '添加'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SchedulePage;
