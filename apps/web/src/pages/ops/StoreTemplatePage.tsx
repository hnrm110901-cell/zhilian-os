import React, { useState } from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './StoreTemplatePage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Template {
  id: string;
  name: string;
  bizType: string;
  moduleCount: number;
  appliedStores: number;
  createdAt: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_TEMPLATES: Template[] = [
  { id: 'TPL001', name: '标准快餐模板', bizType: '快餐', moduleCount: 12, appliedStores: 18, createdAt: '2026-01-10' },
  { id: 'TPL002', name: '正餐连锁模板', bizType: '正餐', moduleCount: 15, appliedStores: 8, createdAt: '2026-01-15' },
  { id: 'TPL003', name: '火锅专用模板', bizType: '火锅', moduleCount: 14, appliedStores: 5, createdAt: '2026-02-01' },
  { id: 'TPL004', name: '茶饮轻食模板', bizType: '茶饮', moduleCount: 9, appliedStores: 22, createdAt: '2026-02-20' },
  { id: 'TPL005', name: '宴会酒楼模板', bizType: '宴会', moduleCount: 18, appliedStores: 3, createdAt: '2026-03-05' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const StoreTemplatePage: React.FC = () => {
  const [search, setSearch] = useState('');

  const filtered = MOCK_TEMPLATES.filter(
    (t) => t.name.includes(search) || t.bizType.includes(search),
  );

  const columns: ZTableColumn<Template>[] = [
    { key: 'name', dataIndex: 'name', title: '模板名称' },
    { key: 'bizType', dataIndex: 'bizType', title: '适用业态',
      render: (v: string) => <ZBadge type="info" text={v} />,
    },
    { key: 'moduleCount', dataIndex: 'moduleCount', title: '包含模块数', align: 'center' },
    { key: 'appliedStores', dataIndex: 'appliedStores', title: '已应用门店数', align: 'center' },
    { key: 'createdAt', dataIndex: 'createdAt', title: '创建时间' },
    {
      key: 'actions', title: '操作', align: 'center',
      render: () => (
        <div className={styles.actionGroup}>
          <button className={styles.actionBtn}>查看</button>
          <button className={styles.actionBtn}>编辑</button>
          <button className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}>下发</button>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2>门店配置模板</h2>
          <p>管理标准化门店配置模板，快速复制到新门店</p>
        </div>
        <div className={styles.headerActions}>
          <input
            className={styles.searchInput}
            placeholder="搜索模板名称/业态..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className={styles.createBtn}>+ 新建模板</button>
        </div>
      </div>

      <div className={styles.section}>
        <ZCard noPadding>
          <ZTable<Template>
            columns={columns}
            dataSource={filtered}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default StoreTemplatePage;
