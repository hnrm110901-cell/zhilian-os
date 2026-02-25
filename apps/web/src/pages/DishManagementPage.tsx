import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, InputNumber, Tag, Space, Tabs, Descriptions } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;

const DishManagementPage: React.FC = () => {
  const [dishes, setDishes] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [dishModal, setDishModal] = useState(false);
  const [catModal, setCatModal] = useState(false);
  const [editingDish, setEditingDish] = useState<any>(null);
  const [costDetail, setCostDetail] = useState<any>(null);
  const [costVisible, setCostVisible] = useState(false);
  const [dishForm] = Form.useForm();
  const [catForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [dishRes, catRes] = await Promise.allSettled([
        apiClient.get('/dishes'),
        apiClient.get('/dishes/categories'),
      ]);
      if (dishRes.status === 'fulfilled') setDishes(dishRes.value.data?.dishes || dishRes.value.data || []);
      if (catRes.status === 'fulfilled') setCategories(catRes.value.data?.categories || catRes.value.data || []);
    } catch (err: any) {
      handleApiError(err, '加载菜品数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const openDishModal = (dish?: any) => {
    setEditingDish(dish || null);
    dishForm.setFieldsValue(dish || {});
    setDishModal(true);
  };

  const saveDish = async (values: any) => {
    try {
      if (editingDish) {
        await apiClient.put(`/dishes/${editingDish.dish_id || editingDish.id}`, values);
        showSuccess('菜品更新成功');
      } else {
        await apiClient.post('/dishes', values);
        showSuccess('菜品创建成功');
      }
      setDishModal(false);
      dishForm.resetFields();
      loadData();
    } catch (err: any) {
      handleApiError(err, '保存失败');
    }
  };

  const deleteDish = async (dish: any) => {
    try {
      await apiClient.delete(`/dishes/${dish.dish_id || dish.id}`);
      showSuccess('菜品已删除');
      loadData();
    } catch (err: any) {
      handleApiError(err, '删除失败');
    }
  };

  const viewCost = async (dish: any) => {
    try {
      const res = await apiClient.get(`/dishes/${dish.dish_id || dish.id}/cost-breakdown`);
      setCostDetail(res.data);
      setCostVisible(true);
    } catch (err: any) {
      handleApiError(err, '获取成本失败');
    }
  };

  const createCategory = async (values: any) => {
    try {
      await apiClient.post('/dishes/categories', values);
      showSuccess('分类创建成功');
      setCatModal(false);
      catForm.resetFields();
      loadData();
    } catch (err: any) {
      handleApiError(err, '创建分类失败');
    }
  };

  const dishColumns: ColumnsType<any> = [
    { title: '菜品名称', dataIndex: 'name', key: 'name' },
    { title: '分类', dataIndex: 'category', key: 'category', render: (v: string) => <Tag>{v || '-'}</Tag> },
    { title: '售价', dataIndex: 'price', key: 'price', render: (v: number) => `¥${(v || 0).toFixed(2)}` },
    { title: '成本', dataIndex: 'cost', key: 'cost', render: (v: number) => `¥${(v || 0).toFixed(2)}` },
    { title: '利润率', dataIndex: 'margin', key: 'margin', render: (v: number) => v != null ? `${(v * 100).toFixed(1)}%` : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'active' ? 'green' : 'red'}>{v === 'active' ? '上架' : '下架'}</Tag> },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openDishModal(record)}>编辑</Button>
          <Button size="small" onClick={() => viewCost(record)}>成本</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteDish(record)}>删除</Button>
        </Space>
      ),
    },
  ];

  const catColumns: ColumnsType<any> = [
    { title: '分类名称', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'desc', ellipsis: true },
    { title: '排序', dataIndex: 'sort_order', key: 'sort' },
  ];

  const tabItems = [
    {
      key: 'dishes',
      label: '菜品列表',
      children: (
        <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openDishModal()}>新增菜品</Button>}>
          <Table columns={dishColumns} dataSource={dishes} rowKey={(r, i) => r.dish_id || r.id || String(i)} loading={loading} />
        </Card>
      ),
    },
    {
      key: 'categories',
      label: '菜品分类',
      children: (
        <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCatModal(true)}>新增分类</Button>}>
          <Table columns={catColumns} dataSource={categories} rowKey={(r, i) => r.category_id || r.id || String(i)} />
        </Card>
      ),
    },
  ];

  return (
    <div>
      <Tabs items={tabItems} />

      <Modal title={editingDish ? '编辑菜品' : '新增菜品'} open={dishModal} onCancel={() => { setDishModal(false); dishForm.resetFields(); }} onOk={() => dishForm.submit()} okText="保存">
        <Form form={dishForm} layout="vertical" onFinish={saveDish}>
          <Form.Item name="name" label="菜品名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="category" label="分类">
            <Select placeholder="选择分类">
              {categories.map((c: any) => <Option key={c.id || c.category_id} value={c.name}>{c.name}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="price" label="售价"><InputNumber prefix="¥" min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="cost" label="成本"><InputNumber prefix="¥" min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="description" label="描述"><TextArea rows={2} /></Form.Item>
          <Form.Item name="status" label="状态" initialValue="active">
            <Select><Option value="active">上架</Option><Option value="inactive">下架</Option></Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="新增分类" open={catModal} onCancel={() => { setCatModal(false); catForm.resetFields(); }} onOk={() => catForm.submit()} okText="创建">
        <Form form={catForm} layout="vertical" onFinish={createCategory}>
          <Form.Item name="name" label="分类名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input /></Form.Item>
          <Form.Item name="sort_order" label="排序" initialValue={0}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="成本明细" open={costVisible} onCancel={() => setCostVisible(false)} footer={null}>
        {costDetail && (
          <Descriptions bordered column={1}>
            <Descriptions.Item label="总成本">¥{(costDetail.total_cost || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="食材成本">¥{(costDetail.ingredient_cost || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="人工成本">¥{(costDetail.labor_cost || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="其他成本">¥{(costDetail.other_cost || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="利润率">{((costDetail.margin || 0) * 100).toFixed(1)}%</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default DishManagementPage;
