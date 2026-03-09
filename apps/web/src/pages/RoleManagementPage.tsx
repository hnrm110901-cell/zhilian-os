import React, { useEffect, useState } from 'react';
import { Table, Tag, Spin, Alert, Typography, Select, Divider, Card, Space } from 'antd';
import { apiClient } from '../services/api';

const { Title, Text } = Typography;

interface RoleInfo {
  value: string;
  label: string;
  permissions: string[];
}

interface Permission {
  group: string;
  value: string;
  label: string;
}

const PRIORITY_COLOR: Record<string, string> = {
  admin: 'red',
  store_manager: 'orange',
  assistant_manager: 'gold',
  floor_manager: 'blue',
  head_chef: 'purple',
  finance: 'green',
};

export default function RoleManagementPage() {
  const [matrix, setMatrix] = useState<Record<string, RoleInfo>>({});
  const [allPerms, setAllPerms] = useState<Permission[]>([]);
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiClient.get<Record<string, RoleInfo>>('/api/v1/roles/matrix'),
      apiClient.get<Permission[]>('/api/v1/roles/permissions'),
    ])
      .then(([m, perms]) => {
        setMatrix(m);
        setAllPerms(perms);
        setSelectedRole(Object.keys(m)[0] ?? null);
      })
      .catch((e) => setError(e?.message ?? '加载失败'))
      .finally(() => setLoading(false));
  }, []);

  const roleOptions = Object.entries(matrix).map(([value, info]) => ({
    value,
    label: info.label,
  }));

  const selectedPerms = selectedRole ? new Set(matrix[selectedRole]?.permissions ?? []) : new Set<string>();

  // Group permissions by group
  const groups = Array.from(new Set(allPerms.map((p) => p.group)));

  const columns = [
    {
      title: '权限',
      dataIndex: 'value',
      key: 'value',
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: '状态',
      key: 'status',
      render: (_: unknown, record: Permission) =>
        selectedPerms.has(record.value)
          ? <Tag color="success">✓ 允许</Tag>
          : <Tag color="default">— 无权限</Tag>,
    },
  ];

  if (loading) return <Spin style={{ marginTop: 40, display: 'block', textAlign: 'center' }} />;
  if (error) return <Alert type="error" message={error} />;

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Title level={3}>角色权限矩阵</Title>
      <Text type="secondary">查看各角色的权限分配情况（权限由系统预设，如需调整请联系管理员）</Text>
      <Divider />

      <Space style={{ marginBottom: 16 }}>
        <Text strong>选择角色：</Text>
        <Select
          style={{ width: 200 }}
          value={selectedRole}
          onChange={setSelectedRole}
          options={roleOptions}
          optionRender={(opt) => (
            <span>
              <Tag color={PRIORITY_COLOR[opt.value as string] ?? 'default'} style={{ marginRight: 4 }}>
                {opt.value}
              </Tag>
              {opt.label}
            </span>
          )}
        />
        {selectedRole && (
          <Tag color={PRIORITY_COLOR[selectedRole] ?? 'default'} style={{ fontSize: 13 }}>
            {matrix[selectedRole]?.permissions?.length ?? 0} 项权限
          </Tag>
        )}
      </Space>

      {groups.map((group) => {
        const groupPerms = allPerms.filter((p) => p.group === group);
        return (
          <Card
            key={group}
            title={group}
            size="small"
            style={{ marginBottom: 12 }}
          >
            <Table
              dataSource={groupPerms}
              columns={columns}
              rowKey="value"
              pagination={false}
              size="small"
              showHeader={false}
              locale={{ emptyText: '无权限项' }}
            />
          </Card>
        );
      })}
    </div>
  );
}
