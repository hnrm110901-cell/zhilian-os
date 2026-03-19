/**
 * 组织架构页面 — 树形可视化
 */
import React, { useEffect, useState } from 'react';
import { Card, Tree, Spin, Empty, Tag, Typography } from 'antd';
import { ApartmentOutlined } from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { OrganizationNode } from '../../services/hrService';
import { useAuthStore } from '../../stores/authStore';

const { Title } = Typography;

const LEVEL_LABELS: Record<number, string> = {
  1: '集团', 2: '事业部', 3: '品牌', 4: '区域', 5: '门店', 6: '部门组',
};

const LEVEL_COLORS: Record<number, string> = {
  1: 'red', 2: 'orange', 3: 'gold', 4: 'blue', 5: 'green', 6: 'default',
};

interface TreeNode {
  title: React.ReactNode;
  key: string;
  children: TreeNode[];
}

const OrgStructurePage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [treeData, setTreeData] = useState<TreeNode[]>([]);
  const user = useAuthStore((s) => s.user);
  const brandId = user?.brand_id || '';

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const res = await hrService.getOrganizations(brandId);
      const tree = buildTree(res.items);
      setTreeData(tree);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const buildTree = (nodes: OrganizationNode[]): TreeNode[] => {
    const map: Record<string, TreeNode> = {};
    const roots: TreeNode[] = [];

    for (const node of nodes) {
      map[node.id] = {
        title: (
          <span>
            {node.name}
            <Tag color={LEVEL_COLORS[node.level] || 'default'} style={{ marginLeft: 8 }}>
              {LEVEL_LABELS[node.level] || `L${node.level}`}
            </Tag>
            {node.store_id && <Tag color="cyan">门店</Tag>}
          </span>
        ),
        key: node.id,
        children: [],
      };
    }

    for (const node of nodes) {
      if (node.parent_id && map[node.parent_id]) {
        map[node.parent_id].children.push(map[node.id]);
      } else {
        roots.push(map[node.id]);
      }
    }

    return roots;
  };

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><ApartmentOutlined /> 组织架构</Title>
      <Card>
        {loading ? (
          <Spin />
        ) : treeData.length > 0 ? (
          <Tree
            treeData={treeData}
            defaultExpandAll
            showLine
            showIcon
          />
        ) : (
          <Empty description="暂无组织架构数据，请先导入花名册" />
        )}
      </Card>
    </div>
  );
};

export default OrgStructurePage;
