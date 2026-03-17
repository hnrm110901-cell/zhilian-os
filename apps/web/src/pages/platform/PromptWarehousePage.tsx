import React, { useState } from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './PromptWarehousePage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface PromptItem {
  id: string;
  name: string;
  agent: string;
  version: string;
  score: number;
  usageCount: number;
  updatedAt: string;
  status: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const TABS = ['全部', '生产中', '测试中', '已归档'];

const MOCK_PROMPTS: PromptItem[] = [
  { id: 'P001', name: '排班优化提示词', agent: 'ScheduleAgent', version: 'v3.2', score: 92, usageCount: 1580, updatedAt: '2026-03-15', status: '生产中' },
  { id: 'P002', name: '库存预测提示词', agent: 'InventoryAgent', version: 'v2.8', score: 89, usageCount: 2340, updatedAt: '2026-03-14', status: '生产中' },
  { id: 'P003', name: '订单异常检测', agent: 'OrderAgent', version: 'v2.1', score: 94, usageCount: 3200, updatedAt: '2026-03-16', status: '生产中' },
  { id: 'P004', name: '决策建议生成', agent: 'DecisionAgent', version: 'v1.5', score: 86, usageCount: 890, updatedAt: '2026-03-12', status: '生产中' },
  { id: 'P005', name: '服务评价分析', agent: 'ServiceAgent', version: 'v2.0', score: 91, usageCount: 1120, updatedAt: '2026-03-10', status: '生产中' },
  { id: 'P006', name: '会员流失预警', agent: 'PrivateDomainAgent', version: 'v1.3', score: 78, usageCount: 450, updatedAt: '2026-03-17', status: '测试中' },
  { id: 'P007', name: '菜品推荐话术', agent: 'ServiceAgent', version: 'v1.0', score: 72, usageCount: 200, updatedAt: '2026-03-08', status: '测试中' },
  { id: 'P008', name: '旧版排班提示词', agent: 'ScheduleAgent', version: 'v2.0', score: 85, usageCount: 5600, updatedAt: '2025-12-20', status: '已归档' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const PromptWarehousePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('全部');
  const [search, setSearch] = useState('');

  const filtered = MOCK_PROMPTS.filter((p) => {
    if (activeTab !== '全部' && p.status !== activeTab) return false;
    if (search && !p.name.includes(search) && !p.agent.includes(search)) return false;
    return true;
  });

  const columns: ZTableColumn<PromptItem>[] = [
    { key: 'name', dataIndex: 'name', title: '名称' },
    { key: 'agent', dataIndex: 'agent', title: '关联Agent' },
    { key: 'version', dataIndex: 'version', title: '版本号' },
    { key: 'score', dataIndex: 'score', title: '效果评分', align: 'center',
      render: (v: number) => {
        const cls = v >= 90 ? styles.scoreHigh : v >= 80 ? styles.scoreMid : styles.scoreLow;
        return <span className={`${styles.scoreCell} ${cls}`}>{v}</span>;
      },
    },
    { key: 'usageCount', dataIndex: 'usageCount', title: '使用次数', align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    { key: 'updatedAt', dataIndex: 'updatedAt', title: '更新时间' },
    { key: 'actions', title: '操作',
      render: () => (
        <div className={styles.actionGroup}>
          <button className={styles.actionBtn}>编辑</button>
          <button className={styles.actionBtn}>复制</button>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2>提示词仓库</h2>
          <p>Agent 提示词模板管理，版本控制与效果评估</p>
        </div>
        <div className={styles.headerActions}>
          <input
            className={styles.searchInput}
            placeholder="搜索提示词/Agent..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className={styles.createBtn}>+ 新建</button>
        </div>
      </div>

      {/* Tab 切换 */}
      <div className={styles.tabBar}>
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`${styles.tabBtn} ${activeTab === tab ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className={styles.section}>
        <ZCard noPadding>
          <ZTable<PromptItem>
            columns={columns}
            dataSource={filtered}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default PromptWarehousePage;
