import React, { useState } from 'react';
import { ZCard, ZBadge, ZTable, ZButton, ZInput, ZTabs } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './BusinessRulesPage.module.css';

/* ── Mock 数据 ── */

interface Rule {
  id: string;
  name: string;
  trigger: string;
  action: string;
  priority: number;
  enabled: boolean;
  lastTriggered: string;
}

const allRules: Rule[] = [
  { id: 'R001', name: '损耗率超标告警', trigger: '日损耗率 > 3%', action: '推送店长 + 生成改善建议', priority: 1, enabled: true, lastTriggered: '2026-03-17 13:20' },
  { id: 'R002', name: '库存不足预警', trigger: '任一食材库存 < 安全库存', action: '自动生成采购单草稿', priority: 1, enabled: true, lastTriggered: '2026-03-17 09:00' },
  { id: 'R003', name: '营收目标未达', trigger: '当日营收 < 目标 80%（截止14:00）', action: '推送店长促销建议', priority: 2, enabled: true, lastTriggered: '2026-03-16 14:05' },
  { id: 'R004', name: 'POS断连告警', trigger: 'POS连接中断 > 10分钟', action: '推送运维 + 短信通知', priority: 1, enabled: true, lastTriggered: '2026-03-17 12:15' },
  { id: 'R005', name: '差评自动响应', trigger: '渠道评分 < 3星', action: '创建客诉工单 + 推送楼面经理', priority: 2, enabled: true, lastTriggered: '2026-03-16 18:30' },
  { id: 'R006', name: '人力成本预警', trigger: '月人力成本占比 > 28%', action: '推送总部 + 排班优化建议', priority: 3, enabled: false, lastTriggered: '2026-03-10 08:00' },
  { id: 'R007', name: '菜品售罄通知', trigger: '菜品库存为0', action: '自动标记售罄 + 推送前厅', priority: 2, enabled: true, lastTriggered: '2026-03-17 11:45' },
  { id: 'R008', name: '会员流失预警', trigger: 'RFM评分下降至流失区', action: '触发挽回优惠券 + 推送门店', priority: 3, enabled: false, lastTriggered: '2026-03-05 10:00' },
];

/* ── 列定义 ── */

const ruleColumns: ZTableColumn<Rule>[] = [
  { key: 'name', dataIndex: 'name', title: '规则名' },
  { key: 'trigger', dataIndex: 'trigger', title: '触发条件' },
  { key: 'action', dataIndex: 'action', title: '动作' },
  {
    key: 'priority', dataIndex: 'priority', title: '优先级', width: 80, align: 'center',
    render: (v: number) => {
      const t = v === 1 ? 'critical' : v === 2 ? 'warning' : 'default';
      const label = v === 1 ? 'P1' : v === 2 ? 'P2' : 'P3';
      return <ZBadge type={t} text={label} />;
    },
  },
  {
    key: 'enabled', dataIndex: 'enabled', title: '状态', width: 80, align: 'center',
    render: (v: boolean) => (
      <span className={v ? styles.toggleOn : styles.toggleOff}>
        {v ? '启用' : '停用'}
      </span>
    ),
  },
  { key: 'lastTriggered', dataIndex: 'lastTriggered', title: '最后触发', width: 150 },
];

/* ── 页面组件 ── */

const BusinessRulesPage: React.FC = () => {
  const [search, setSearch] = useState('');

  const enabledRules = allRules.filter(r => r.enabled);
  const disabledRules = allRules.filter(r => !r.enabled);

  const filterRules = (rules: Rule[]) => {
    if (!search) return rules;
    const q = search.toLowerCase();
    return rules.filter(r => r.name.toLowerCase().includes(q) || r.trigger.toLowerCase().includes(q));
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>业务规则引擎</h1>
          <p className={styles.subtitle}>配置损耗阈值、告警条件与自动化策略</p>
        </div>
        <div className={styles.headerActions}>
          <ZInput placeholder="搜索规则..." value={search} onChange={setSearch} onClear={() => setSearch('')} />
          <ZButton variant="primary">创建规则</ZButton>
        </div>
      </div>

      <ZTabs
        items={[
          {
            key: 'all',
            label: '全部',
            badge: allRules.length,
            children: (
              <ZCard>
                {/* GET /api/v1/ops/business-rules */}
                <ZTable<Rule> columns={ruleColumns} data={filterRules(allRules)} rowKey="id" />
              </ZCard>
            ),
          },
          {
            key: 'enabled',
            label: '已启用',
            badge: enabledRules.length,
            children: (
              <ZCard>
                <ZTable<Rule> columns={ruleColumns} data={filterRules(enabledRules)} rowKey="id" />
              </ZCard>
            ),
          },
          {
            key: 'disabled',
            label: '已停用',
            badge: disabledRules.length,
            children: (
              <ZCard>
                <ZTable<Rule> columns={ruleColumns} data={filterRules(disabledRules)} rowKey="id" />
              </ZCard>
            ),
          },
        ]}
        defaultKey="all"
      />
    </div>
  );
};

export default BusinessRulesPage;
