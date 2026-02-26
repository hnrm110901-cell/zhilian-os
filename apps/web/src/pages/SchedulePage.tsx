import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Form, Input, Button, DatePicker, Table, Space, Tag, Tabs,
  Modal, Select, Row, Col, Statistic, Popconfirm, Alert, Badge,
  Tooltip, Drawer, InputNumber,
} from 'antd';
import {
  PlusOutlined, UserOutlined, CalendarOutlined, ReloadOutlined,
  ThunderboltOutlined, CheckCircleOutlined, SendOutlined,
  BarChartOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs, { Dayjs } from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

dayjs.extend(isoWeek);

const { Option } = Select;

const SKILL_OPTIONS = [
  { value: 'waiter',   label: '服务员', color: 'blue' },
  { value: 'cashier',  label: '收银员', color: 'green' },
  { value: 'chef',     label: '厨师',   color: 'orange' },
  { value: 'manager',  label: '经理',   color: 'purple' },
  { value: 'cleaner',  label: '清洁员', color: 'cyan' },
];

const SHIFT_COLOR: Record<string, string> = {
  morning: 'green', afternoon: 'orange', evening: 'purple',
};
const SHIFT_LABEL: Record<string, string> = {
  morning: '早班', afternoon: '午班', evening: '晚班',
};

const SchedulePage: React.FC = () => {
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [weekView, setWeekView] = useState<any>(null);
  const [stats, setStats] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [empLoading, setEmpLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('week');

  const [empModalVisible, setEmpModalVisible] = useState(false);
  const [editingEmp, setEditingEmp] = useState<any>(null);
  const [empForm] = Form.useForm();

  const [autoGenDrawer, setAutoGenDrawer] = useState(false);
  const [autoGenForm] = Form.useForm();
  const [autoGenLoading, setAutoGenLoading] = useState(false);

  const [manualDrawer, setManualDrawer] = useState(false);
  const [manualForm] = Form.useForm();

  const [weekDate, setWeekDate] = useState<Dayjs>(dayjs().startOf('isoWeek'));
  const [statsRange, setStatsRange] = useState<[Dayjs, Dayjs]>([dayjs().subtract(7, 'day'), dayjs()]);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadEmployees = useCallback(async () => {
    try {
      setEmpLoading(true);
      const res = await apiClient.get(`/api/v1/employees?store_id=${storeId}`);
      setEmployees(res.data || []);
    } catch (err: any) { handleApiError(err, '加载员工失败'); }
    finally { setEmpLoading(false); }
  }, [storeId]);

  const loadWeekView = useCallback(async () => {
    try {
      setLoading(true);
      const weekStart = weekDate.format('YYYY-MM-DD');
      const res = await apiClient.get(`/api/v1/schedules/week-view?store_id=${storeId}&week_start=${weekStart}`);
      setWeekView(res.data);
    } catch (err: any) { handleApiError(err, '加载周视图失败'); }
    finally { setLoading(false); }
  }, [storeId, weekDate]);

  const loadSchedules = useCallback(async () => {
    try {
      setLoading(true);
      const start = dayjs().subtract(7, 'day').format('YYYY-MM-DD');
      const end = dayjs().add(14, 'day').format('YYYY-MM-DD');
      const res = await apiClient.get(`/api/v1/schedules?store_id=${storeId}&start_date=${start}&end_date=${end}`);
      setSchedules(res.data || []);
    } catch (err: any) { handleApiError(err, '加载排班失败'); }
    finally { setLoading(false); }
  }, [storeId]);

  const loadStats = useCallback(async () => {
    try {
      const start = statsRange[0].format('YYYY-MM-DD');
      const end = statsRange[1].format('YYYY-MM-DD');
      const res = await apiClient.get(`/api/v1/schedules/stats?store_id=${storeId}&start_date=${start}&end_date=${end}`);
      setStats(res.data?.stats || []);
    } catch (err: any) { handleApiError(err, '加载统计失败'); }
  }, [storeId, statsRange]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadEmployees(); }, [loadEmployees]);
  useEffect(() => {
    if (activeTab === 'week') loadWeekView();
    else if (activeTab === 'list') loadSchedules();
    else if (activeTab === 'stats') loadStats();
  }, [activeTab, loadWeekView, loadSchedules, loadStats]);

  // ── Employee CRUD ──
  const handleSaveEmployee = async (values: any) => {
    try {
      if (editingEmp) {
        await apiClient.patch(`/api/v1/employees/${editingEmp.id}`, values);
        showSuccess('员工信息已更新');
      } else {
        await apiClient.post('/api/v1/employees', {
          id: `EMP_${Date.now()}`,
          store_id: storeId,
          ...values,
        });
        showSuccess('员工已添加');
      }
      setEmpModalVisible(false);
      empForm.resetFields();
      loadEmployees();
    } catch (err: any) { handleApiError(err, '保存失败'); }
  };

  const handleDeactivateEmployee = async (empId: string) => {
    try {
      await apiClient.delete(`/api/v1/employees/${empId}`);
      showSuccess('员工已停用');
      loadEmployees();
    } catch (err: any) { handleApiError(err, '操作失败'); }
  };

  // ── Auto Generate ──
  const handleAutoGenerate = async (values: any) => {
    try {
      setAutoGenLoading(true);
      await apiClient.post('/api/v1/schedules/auto-generate', {
        store_id: storeId,
        schedule_date: values.schedule_date.format('YYYY-MM-DD'),
      });
      showSuccess('智能排班已生成');
      setAutoGenDrawer(false);
      autoGenForm.resetFields();
      loadWeekView();
      loadSchedules();
    } catch (err: any) { handleApiError(err, '生成失败'); }
    finally { setAutoGenLoading(false); }
  };

  // ── Manual Create ──
  const handleManualCreate = async (values: any) => {
    try {
      const shifts = (values.shifts || []).map((s: any) => ({
        employee_id: s.employee_id,
        shift_type: s.shift_type,
        start_time: s.start_time,
        end_time: s.end_time,
        position: s.position,
      }));
      await apiClient.post('/api/v1/schedules', {
        store_id: storeId,
        schedule_date: values.schedule_date.format('YYYY-MM-DD'),
        shifts,
      });
      showSuccess('排班已创建');
      setManualDrawer(false);
      manualForm.resetFields();
      loadWeekView();
      loadSchedules();
    } catch (err: any) { handleApiError(err, '创建失败'); }
  };

  // ── Publish ──
  const handlePublish = async (scheduleId: string) => {
    try {
      await apiClient.post(`/api/v1/schedules/${scheduleId}/publish`);
      showSuccess('排班已发布');
      loadWeekView();
      loadSchedules();
    } catch (err: any) { handleApiError(err, '发布失败'); }
  };

  // ── Confirm Shift ──
  const handleConfirmShift = async (scheduleId: string, shiftId: string) => {
    try {
      await apiClient.patch(`/api/v1/schedules/${scheduleId}/shifts/${shiftId}/confirm`, {});
      showSuccess('班次已确认');
      loadWeekView();
    } catch (err: any) { handleApiError(err, '确认失败'); }
  };

  // ── Columns ──
  const empColumns: ColumnsType<any> = [
    { title: '员工ID', dataIndex: 'id', key: 'id', width: 130, ellipsis: true },
    { title: '姓名', dataIndex: 'name', key: 'name', width: 90 },
    { title: '职位', dataIndex: 'position', key: 'position', width: 90, render: (v: string) => v || '-' },
    {
      title: '技能', dataIndex: 'skills', key: 'skills',
      render: (skills: string[]) => (skills || []).map(s => {
        const opt = SKILL_OPTIONS.find(o => o.value === s);
        return <Tag key={s} color={opt?.color || 'default'}>{opt?.label || s}</Tag>;
      }),
    },
    { title: '状态', dataIndex: 'is_active', key: 'is_active', width: 70, render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '在职' : '离职'}</Tag> },
    {
      title: '操作', key: 'action', width: 130,
      render: (_: any, record: any) => (
        <Space>
          <Button type="link" size="small" onClick={() => { setEditingEmp(record); empForm.setFieldsValue(record); setEmpModalVisible(true); }}>编辑</Button>
          {record.is_active && (
            <Popconfirm title="确认停用该员工？" onConfirm={() => handleDeactivateEmployee(record.id)} okText="确认" cancelText="取消">
              <Button type="link" danger size="small">停用</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const scheduleColumns: ColumnsType<any> = [
    { title: '日期', dataIndex: 'schedule_date', key: 'schedule_date', width: 120 },
    { title: '员工数', dataIndex: 'total_employees', key: 'total_employees', width: 80 },
    { title: '班次数', key: 'shifts_count', width: 80, render: (_: any, r: any) => r.shifts?.length || 0 },
    { title: '状态', dataIndex: 'is_published', key: 'is_published', width: 90, render: (v: boolean) => <Tag color={v ? 'green' : 'orange'}>{v ? '已发布' : '草稿'}</Tag> },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: any, record: any) => !record.is_published && (
        <Popconfirm title="发布后员工可见，确认发布？" onConfirm={() => handlePublish(record.id)} okText="发布" cancelText="取消">
          <Button size="small" type="primary" icon={<SendOutlined />}>发布</Button>
        </Popconfirm>
      ),
    },
  ];

  const statsColumns: ColumnsType<any> = [
    { title: '员工', dataIndex: 'employee_name', key: 'employee_name', width: 100 },
    { title: '总班次', dataIndex: 'total_shifts', key: 'total_shifts', width: 80, sorter: (a: any, b: any) => a.total_shifts - b.total_shifts },
    { title: '总工时(h)', dataIndex: 'total_hours', key: 'total_hours', width: 100, sorter: (a: any, b: any) => a.total_hours - b.total_hours },
    {
      title: '班次分布', dataIndex: 'shift_breakdown', key: 'shift_breakdown',
      render: (v: Record<string, number>) => Object.entries(v || {}).map(([k, n]) => (
        <Tag key={k} color={SHIFT_COLOR[k]}>{SHIFT_LABEL[k] || k}: {n}</Tag>
      )),
    },
  ];

  // ── Week View Render ──
  const renderWeekView = () => {
    if (!weekView) return <Alert message="暂无排班数据" type="info" showIcon />;
    return (
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {weekView.days?.map((day: any) => (
                <th key={day.date} style={{ padding: '8px 4px', textAlign: 'center', background: '#fafafa', border: '1px solid #f0f0f0', minWidth: 120 }}>
                  <div style={{ fontWeight: 600 }}>{dayjs(day.date).format('MM/DD')}</div>
                  <div style={{ fontSize: 12, color: '#999' }}>{['一','二','三','四','五','六','日'][dayjs(day.date).isoWeekday() - 1]}</div>
                  {day.is_published
                    ? <Tag color="green" style={{ fontSize: 10 }}>已发布</Tag>
                    : day.schedule_id
                      ? <Tag color="orange" style={{ fontSize: 10 }}>草稿</Tag>
                      : <Tag color="default" style={{ fontSize: 10 }}>未排班</Tag>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {weekView.days?.map((day: any) => (
                <td key={day.date} style={{ padding: 4, verticalAlign: 'top', border: '1px solid #f0f0f0' }}>
                  {day.shifts.length === 0
                    ? <div style={{ color: '#ccc', textAlign: 'center', padding: 8 }}>-</div>
                    : day.shifts.map((sh: any) => (
                      <div key={sh.shift_id} style={{ marginBottom: 4, padding: '4px 6px', background: sh.is_confirmed ? '#f6ffed' : '#fff7e6', borderRadius: 4, border: `1px solid ${sh.is_confirmed ? '#b7eb8f' : '#ffd591'}`, fontSize: 12 }}>
                        <div><Tag color={SHIFT_COLOR[sh.shift_type]} style={{ fontSize: 10, padding: '0 4px' }}>{SHIFT_LABEL[sh.shift_type]}</Tag></div>
                        <div style={{ fontWeight: 500 }}>{sh.employee_name}</div>
                        <div style={{ color: '#666' }}>{sh.start_time}–{sh.end_time}</div>
                        {sh.position && <div style={{ color: '#999' }}>{SKILL_OPTIONS.find(o => o.value === sh.position)?.label || sh.position}</div>}
                        {!sh.is_confirmed && day.schedule_id && (
                          <Button size="small" type="link" style={{ padding: 0, fontSize: 11 }}
                            onClick={() => handleConfirmShift(day.schedule_id, sh.shift_id)}>
                            确认
                          </Button>
                        )}
                        {sh.is_confirmed && <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 11 }} />}
                      </div>
                    ))
                  }
                  {day.schedule_id && !day.is_published && (
                    <Popconfirm title="发布后员工可见，确认？" onConfirm={() => handlePublish(day.schedule_id)} okText="发布" cancelText="取消">
                      <Button size="small" block icon={<SendOutlined />} style={{ marginTop: 4, fontSize: 11 }}>发布</Button>
                    </Popconfirm>
                  )}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    );
  };

  const activeCount = employees.filter(e => e.is_active).length;
  const skillCount = new Set(employees.flatMap(e => e.skills || [])).size;
  const publishedCount = schedules.filter(s => s.is_published).length;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>智能排班Agent</h1>
        <Space>
          <Select value={storeId} onChange={v => { setStoreId(v); }} style={{ width: 160 }}>
            {stores.length > 0 ? stores.map((s: any) => (
              <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
            )) : <Option value="STORE001">STORE001</Option>}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={() => { loadEmployees(); if (activeTab === 'week') loadWeekView(); else if (activeTab === 'list') loadSchedules(); else loadStats(); }}>刷新</Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}><Card size="small"><Statistic title="在职员工" value={activeCount} prefix={<UserOutlined />} valueStyle={{ color: '#1890ff' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="技能类型" value={skillCount} valueStyle={{ color: '#faad14' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已发布排班" value={publishedCount} prefix={<CalendarOutlined />} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="本周班次" value={weekView?.days?.reduce((acc: number, d: any) => acc + d.shifts.length, 0) ?? '--'} prefix={<ClockCircleOutlined />} valueStyle={{ color: '#722ed1' }} /></Card></Col>
      </Row>

      <Tabs activeKey={activeTab} onChange={setActiveTab}
        tabBarExtraContent={
          <Space>
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => setAutoGenDrawer(true)}>AI智能排班</Button>
            <Button icon={<PlusOutlined />} onClick={() => setManualDrawer(true)}>手动创建</Button>
          </Space>
        }
      >
        <Tabs.TabPane tab="周视图" key="week">
          <Card size="small" style={{ marginBottom: 12 }}
            extra={
              <Space>
                <Button size="small" onClick={() => setWeekDate(d => d.subtract(1, 'week'))}>上一周</Button>
                <span style={{ fontWeight: 600 }}>{weekDate.format('YYYY/MM/DD')} – {weekDate.add(6, 'day').format('MM/DD')}</span>
                <Button size="small" onClick={() => setWeekDate(d => d.add(1, 'week'))}>下一周</Button>
                <Button size="small" onClick={() => setWeekDate(dayjs().startOf('isoWeek'))}>本周</Button>
              </Space>
            }
          >
            {loading ? <div style={{ textAlign: 'center', padding: 40 }}>加载中...</div> : renderWeekView()}
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab="排班列表" key="list">
          <Card size="small">
            <Table dataSource={schedules} columns={scheduleColumns} rowKey="id" loading={loading}
              expandable={{
                expandedRowRender: (record: any) => (
                  <Table
                    dataSource={record.shifts || []}
                    rowKey="id"
                    pagination={false}
                    size="small"
                    columns={[
                      { title: '员工ID', dataIndex: 'employee_id', key: 'employee_id', width: 130 },
                      { title: '班次', dataIndex: 'shift_type', key: 'shift_type', width: 80, render: (v: string) => <Tag color={SHIFT_COLOR[v]}>{SHIFT_LABEL[v] || v}</Tag> },
                      { title: '开始', dataIndex: 'start_time', key: 'start_time', width: 80 },
                      { title: '结束', dataIndex: 'end_time', key: 'end_time', width: 80 },
                      { title: '职位', dataIndex: 'position', key: 'position', width: 90 },
                      { title: '已确认', dataIndex: 'is_confirmed', key: 'is_confirmed', width: 80, render: (v: boolean) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : '-' },
                    ]}
                  />
                ),
              }}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab={<span><UserOutlined /> 员工管理</span>} key="employees">
          <Card size="small"
            extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingEmp(null); empForm.resetFields(); setEmpModalVisible(true); }}>添加员工</Button>}
          >
            <Table dataSource={employees} columns={empColumns} rowKey="id" loading={empLoading}
              locale={{ emptyText: '暂无员工，请先添加' }} />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab={<span><BarChartOutlined /> 工时统计</span>} key="stats">
          <Card size="small" style={{ marginBottom: 12 }}
            extra={
              <Space>
                <DatePicker.RangePicker
                  value={statsRange}
                  onChange={v => v && setStatsRange(v as [Dayjs, Dayjs])}
                  size="small"
                />
                <Button size="small" type="primary" onClick={loadStats}>查询</Button>
              </Space>
            }
          >
            <Table dataSource={stats} columns={statsColumns} rowKey="employee_id" size="small"
              locale={{ emptyText: '暂无统计数据' }} />
          </Card>
        </Tabs.TabPane>
      </Tabs>

      {/* 员工 Modal */}
      <Modal title={editingEmp ? '编辑员工' : '添加员工'} open={empModalVisible}
        onCancel={() => { setEmpModalVisible(false); empForm.resetFields(); }} footer={null} width={480}>
        <Form form={empForm} layout="vertical" onFinish={handleSaveEmployee}>
          <Form.Item label="姓名" name="name" rules={[{ required: true, min: 2 }]}>
            <Input placeholder="员工姓名" />
          </Form.Item>
          <Form.Item label="职位" name="position">
            <Input placeholder="例如：服务员" />
          </Form.Item>
          <Form.Item label="技能" name="skills" rules={[{ required: true, message: '请选择至少一项技能' }]}>
            <Select mode="multiple" placeholder="选择技能">
              {SKILL_OPTIONS.map(o => <Option key={o.value} value={o.value}><Tag color={o.color}>{o.label}</Tag></Option>)}
            </Select>
          </Form.Item>
          <Form.Item label="联系电话" name="phone">
            <Input placeholder="选填" />
          </Form.Item>
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => { setEmpModalVisible(false); empForm.resetFields(); }}>取消</Button>
              <Button type="primary" htmlType="submit">{editingEmp ? '保存' : '添加'}</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* AI智能排班 Drawer */}
      <Drawer title="AI智能排班" open={autoGenDrawer} onClose={() => setAutoGenDrawer(false)} width={400}>
        <Alert message="系统将根据员工技能自动分配早/午/晚三个班次，确保每班次关键岗位有人覆盖。" type="info" showIcon style={{ marginBottom: 16 }} />
        <Form form={autoGenForm} layout="vertical" onFinish={handleAutoGenerate}>
          <Form.Item label="排班日期" name="schedule_date" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={autoGenLoading} block icon={<ThunderboltOutlined />}>
              生成排班
            </Button>
          </Form.Item>
        </Form>
        <div style={{ marginTop: 16, color: '#666', fontSize: 12 }}>
          <div>班次规则：</div>
          <div>• 早班 08:00–14:00（服务员/收银员/厨师）</div>
          <div>• 午班 14:00–20:00（服务员/收银员/厨师）</div>
          <div>• 晚班 20:00–23:00（服务员/经理）</div>
        </div>
      </Drawer>

      {/* 手动创建排班 Drawer */}
      <Drawer title="手动创建排班" open={manualDrawer} onClose={() => setManualDrawer(false)} width={520}>
        <Form form={manualForm} layout="vertical" onFinish={handleManualCreate}>
          <Form.Item label="排班日期" name="schedule_date" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.List name="shifts" initialValue={[{}]}>
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name }) => (
                  <Card key={key} size="small" style={{ marginBottom: 8 }}
                    extra={fields.length > 1 && <Button type="link" danger size="small" onClick={() => remove(name)}>删除</Button>}>
                    <Row gutter={8}>
                      <Col span={12}>
                        <Form.Item name={[name, 'employee_id']} label="员工" rules={[{ required: true }]}>
                          <Select placeholder="选择员工">
                            {employees.filter(e => e.is_active).map(e => (
                              <Option key={e.id} value={e.id}>{e.name}</Option>
                            ))}
                          </Select>
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item name={[name, 'shift_type']} label="班次" rules={[{ required: true }]}>
                          <Select placeholder="选择班次">
                            <Option value="morning">早班</Option>
                            <Option value="afternoon">午班</Option>
                            <Option value="evening">晚班</Option>
                          </Select>
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item name={[name, 'start_time']} label="开始时间" rules={[{ required: true }]}>
                          <Input placeholder="08:00" />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item name={[name, 'end_time']} label="结束时间" rules={[{ required: true }]}>
                          <Input placeholder="14:00" />
                        </Form.Item>
                      </Col>
                    </Row>
                  </Card>
                ))}
                <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>添加班次</Button>
              </>
            )}
          </Form.List>
          <Form.Item style={{ marginTop: 16 }}>
            <Button type="primary" htmlType="submit" block>创建排班</Button>
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default SchedulePage;
