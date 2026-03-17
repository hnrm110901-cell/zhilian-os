import React from 'react';
import { ZCard } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './ModuleAuthPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface MerchantModules {
  id: string;
  merchantName: string;
  scheduling: boolean;
  inventory: boolean;
  ordering: boolean;
  analytics: boolean;
  memberCrm: boolean;
  aiAgent: boolean;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_DATA: MerchantModules[] = [
  { id: 'M001', merchantName: '尝在一起', scheduling: true, inventory: true, ordering: true, analytics: true, memberCrm: true, aiAgent: true },
  { id: 'M002', merchantName: '徐记海鲜', scheduling: true, inventory: true, ordering: true, analytics: true, memberCrm: false, aiAgent: true },
  { id: 'M003', merchantName: '最黔线', scheduling: true, inventory: true, ordering: false, analytics: false, memberCrm: false, aiAgent: false },
  { id: 'M004', merchantName: '尚宫厨', scheduling: true, inventory: false, ordering: false, analytics: false, memberCrm: false, aiAgent: false },
  { id: 'M005', merchantName: '湘味轩', scheduling: true, inventory: true, ordering: true, analytics: true, memberCrm: true, aiAgent: false },
];

const MODULE_NAMES = ['排班管理', '库存管理', '订单管理', '经营分析', '会员CRM', 'AI Agent'];
const MODULE_KEYS: (keyof MerchantModules)[] = ['scheduling', 'inventory', 'ordering', 'analytics', 'memberCrm', 'aiAgent'];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const ModuleAuthPage: React.FC = () => {
  const renderCheck = (v: boolean) => (
    v ? <span className={styles.checkMark}>&#10003;</span> : <span className={styles.crossMark}>&#10005;</span>
  );

  const columns: ZTableColumn<MerchantModules>[] = [
    { key: 'merchantName', dataIndex: 'merchantName', title: '商户名' },
    ...MODULE_KEYS.map((key, i) => ({
      key: key as string,
      dataIndex: key as string,
      title: MODULE_NAMES[i],
      align: 'center' as const,
      render: (v: boolean) => renderCheck(v),
    })),
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2>模块授权</h2>
          <p>管理商户可用功能模块，按需开通与关闭业务能力</p>
        </div>
        <button className={styles.batchBtn}>批量授权</button>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>商户 x 模块授权矩阵</div>
        <ZCard noPadding>
          <ZTable<MerchantModules>
            columns={columns}
            dataSource={MOCK_DATA}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default ModuleAuthPage;
