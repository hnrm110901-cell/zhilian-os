import React, { useState } from 'react';
import { ZCard, ZBadge, ZButton } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './StoreTemplatePage.module.css';

// TODO: GET /api/v1/ops/store-templates

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Template {
  id: string;
  name: string;
  description: string;
  bizType: string;
  moduleCount: number;
  appliedStores: number;
  createdAt: string;
  deployStatus: 'published' | 'draft' | 'deploying';
}

interface DeployRecord {
  id: string;
  templateName: string;
  store: string;
  operator: string;
  deployedAt: string;
  status: 'success' | 'failed' | 'in_progress';
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_TEMPLATES: Template[] = [
  {
    id: 'TPL001',
    name: '基础模板',
    description: '适合3～10家门店的初创连锁，包含基础排班、库存、订单模块',
    bizType: '通用',
    moduleCount: 8,
    appliedStores: 24,
    createdAt: '2026-01-10',
    deployStatus: 'published',
  },
  {
    id: 'TPL002',
    name: '高端模板',
    description: '面向精品餐厅，集成宴会管理、VIP会员、食材溯源与高级报表',
    bizType: '正餐/宴会',
    moduleCount: 18,
    appliedStores: 6,
    createdAt: '2026-01-15',
    deployStatus: 'published',
  },
  {
    id: 'TPL003',
    name: '快餐模板',
    description: '高翻台率场景，强化收银集成、聚合外卖、快速排班',
    bizType: '快餐/茶饮',
    moduleCount: 11,
    appliedStores: 31,
    createdAt: '2026-02-01',
    deployStatus: 'published',
  },
  {
    id: 'TPL004',
    name: '火锅专用模板',
    description: '食材损耗追踪、锅底BOM管理、翻台时长分析',
    bizType: '火锅',
    moduleCount: 14,
    appliedStores: 8,
    createdAt: '2026-02-20',
    deployStatus: 'published',
  },
  {
    id: 'TPL005',
    name: '宴会酒楼模板',
    description: '大型宴会场地调度、桌位预订、礼宾服务全链路管理',
    bizType: '宴会',
    moduleCount: 20,
    appliedStores: 3,
    createdAt: '2026-03-05',
    deployStatus: 'draft',
  },
];

const MOCK_DEPLOY_RECORDS: DeployRecord[] = [
  { id: 'DR001', templateName: '快餐模板', store: '尝在一起·五一店', operator: '系统自动', deployedAt: '2026-03-16 14:30', status: 'success' },
  { id: 'DR002', templateName: '基础模板', store: '徐记海鲜·解放西店', operator: '王管理', deployedAt: '2026-03-15 10:00', status: 'success' },
  { id: 'DR003', templateName: '高端模板', store: '尚宫厨·梅溪湖店', operator: '李运维', deployedAt: '2026-03-14 16:20', status: 'failed' },
  { id: 'DR004', templateName: '宴会酒楼模板', store: '最黔线·五一广场店', operator: '张管理', deployedAt: '2026-03-17 09:15', status: 'in_progress' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const deployStatusLabel: Record<Template['deployStatus'], string> = {
  published: '已发布',
  draft: '草稿',
  deploying: '下发中',
};

const deployStatusType: Record<Template['deployStatus'], 'success' | 'default' | 'warning'> = {
  published: 'success',
  draft: 'default',
  deploying: 'warning',
};

const recordStatusType: Record<DeployRecord['status'], 'success' | 'error' | 'warning'> = {
  success: 'success',
  failed: 'error',
  in_progress: 'warning',
};

const recordStatusLabel: Record<DeployRecord['status'], string> = {
  success: '成功',
  failed: '失败',
  in_progress: '下发中',
};

const StoreTemplatePage: React.FC = () => {
  const [search, setSearch] = useState('');
  const [view, setView] = useState<'card' | 'table'>('card');

  const filtered = MOCK_TEMPLATES.filter(
    (t) => t.name.includes(search) || t.bizType.includes(search) || t.description.includes(search),
  );

  const tableColumns: ZTableColumn<Template>[] = [
    { key: 'name', dataIndex: 'name', title: '模板名称' },
    { key: 'bizType', dataIndex: 'bizType', title: '适用业态',
      render: (v: string) => <ZBadge type="info" text={v} />,
    },
    { key: 'moduleCount', dataIndex: 'moduleCount', title: '包含模块数', align: 'center' },
    { key: 'appliedStores', dataIndex: 'appliedStores', title: '已应用门店', align: 'center' },
    { key: 'createdAt', dataIndex: 'createdAt', title: '创建时间' },
    { key: 'deployStatus', dataIndex: 'deployStatus', title: '状态',
      render: (v: Template['deployStatus']) => (
        <ZBadge type={deployStatusType[v]} text={deployStatusLabel[v]} />
      ),
    },
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

  const deployColumns: ZTableColumn<DeployRecord>[] = [
    { key: 'templateName', dataIndex: 'templateName', title: '模板' },
    { key: 'store', dataIndex: 'store', title: '目标门店' },
    { key: 'operator', dataIndex: 'operator', title: '操作人' },
    { key: 'deployedAt', dataIndex: 'deployedAt', title: '下发时间' },
    { key: 'status', dataIndex: 'status', title: '结果',
      render: (v: DeployRecord['status']) => (
        <ZBadge type={recordStatusType[v]} text={recordStatusLabel[v]} />
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
          <div className={styles.viewToggle}>
            <button
              className={`${styles.viewBtn} ${view === 'card' ? styles.viewBtnActive : ''}`}
              onClick={() => setView('card')}
            >
              卡片
            </button>
            <button
              className={`${styles.viewBtn} ${view === 'table' ? styles.viewBtnActive : ''}`}
              onClick={() => setView('table')}
            >
              列表
            </button>
          </div>
          <button className={styles.createBtn}>+ 新建模板</button>
        </div>
      </div>

      {/* 模板展示 */}
      <div className={styles.section}>
        {view === 'card' ? (
          <div className={styles.cardGrid}>
            {filtered.map((tpl) => (
              <ZCard key={tpl.id} className={styles.templateCard}>
                <div className={styles.cardHeader}>
                  <div className={styles.cardTitle}>{tpl.name}</div>
                  <ZBadge type={deployStatusType[tpl.deployStatus]} text={deployStatusLabel[tpl.deployStatus]} />
                </div>
                <p className={styles.cardDesc}>{tpl.description}</p>
                <div className={styles.cardMeta}>
                  <ZBadge type="info" text={tpl.bizType} />
                  <span className={styles.metaText}>{tpl.moduleCount} 个模块</span>
                  <span className={styles.metaText}>{tpl.appliedStores} 家门店在用</span>
                </div>
                <div className={styles.cardFooter}>
                  <span className={styles.cardDate}>创建于 {tpl.createdAt}</span>
                  <div className={styles.cardActions}>
                    <button className={styles.actionBtn}>编辑</button>
                    <button className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}>下发</button>
                  </div>
                </div>
              </ZCard>
            ))}
          </div>
        ) : (
          <ZCard noPadding>
            <ZTable<Template>
              columns={tableColumns}
              dataSource={filtered}
              rowKey="id"
            />
          </ZCard>
        )}
      </div>

      {/* 下发记录 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>近期下发记录</div>
        <ZCard noPadding>
          <ZTable<DeployRecord>
            columns={deployColumns}
            dataSource={MOCK_DEPLOY_RECORDS}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default StoreTemplatePage;
