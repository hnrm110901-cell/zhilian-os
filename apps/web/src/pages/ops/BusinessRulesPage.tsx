import React, { useState } from 'react';
import { ZCard, ZBadge, ZTable, ZButton, ZInput, ZTabs, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './BusinessRulesPage.module.css';

/* ── Mock 数据 ── TODO: GET /api/v1/ops/business-rules */

type RuleCategory = '损耗' | '库存' | '排班' | '质量' | '营收' | '会员';

interface Rule {
  id: string;
  name: string;
  category: RuleCategory;
  trigger: string;
  action: string;
  priority: number;
  enabled: boolean;
  triggerCount: number;
  lastTriggered: string;
}

const initialRules: Rule[] = [
  { id: 'R001', name: '损耗率超标告警', category: '损耗', trigger: '日损耗率 > 3%', action: '推送店长 + 生成改善建议', priority: 1, enabled: true, triggerCount: 42, lastTriggered: '2026-03-17 13:20' },
  { id: 'R002', name: '库存不足预警', category: '库存', trigger: '任一食材库存 < 安全库存', action: '自动生成采购单草稿', priority: 1, enabled: true, triggerCount: 87, lastTriggered: '2026-03-17 09:00' },
  { id: 'R003', name: '营收目标未达', category: '营收', trigger: '当日营收 < 目标80%（截止14:00）', action: '推送店长促销建议', priority: 2, enabled: true, triggerCount: 18, lastTriggered: '2026-03-16 14:05' },
  { id: 'R004', name: 'POS断连告警', category: '质量', trigger: 'POS连接中断 > 10分钟', action: '推送运维 + 短信通知', priority: 1, enabled: true, triggerCount: 5, lastTriggered: '2026-03-17 12:15' },
  { id: 'R005', name: '差评自动响应', category: '质量', trigger: '渠道评分 < 3星', action: '创建客诉工单 + 推送楼面经理', priority: 2, enabled: true, triggerCount: 23, lastTriggered: '2026-03-16 18:30' },
  { id: 'R006', name: '人力成本预警', category: '排班', trigger: '月人力成本占比 > 28%', action: '推送总部 + 排班优化建议', priority: 3, enabled: false, triggerCount: 3, lastTriggered: '2026-03-10 08:00' },
  { id: 'R007', name: '菜品售罄通知', category: '库存', trigger: '菜品库存为0', action: '自动标记售罄 + 推送前厅', priority: 2, enabled: true, triggerCount: 156, lastTriggered: '2026-03-17 11:45' },
  { id: 'R008', name: '会员流失预警', category: '会员', trigger: 'RFM评分下降至流失区', action: '触发挽回优惠券 + 推送门店', priority: 3, enabled: false, triggerCount: 9, lastTriggered: '2026-03-05 10:00' },
];

const CATEGORY_COLORS: Record<RuleCategory, 'default' | 'info' | 'warning' | 'critical' | 'success'> = {
  损耗: 'critical',
  库存: 'warning',
  排班: 'info',
  质量: 'default',
  营收: 'success',
  会员: 'info',
};

/* ── 列定义 ── */

const buildColumns = (
  onToggle: (id: string) => void
): ZTableColumn<Rule>[] => [
  { key: 'name', dataIndex: 'name', title: '规则名', render: (v: string, row: Rule) => (
    <span className={row.enabled ? styles.ruleNameEnabled : styles.ruleNameDisabled}>{v}</span>
  ) },
  {
    key: 'category', dataIndex: 'category', title: '分类', width: 80,
    render: (v: RuleCategory) => <ZBadge type={CATEGORY_COLORS[v]} text={v} />,
  },
  { key: 'trigger', dataIndex: 'trigger', title: '触发条件' },
  { key: 'action', dataIndex: 'action', title: '执行动作' },
  {
    key: 'priority', dataIndex: 'priority', title: '优先级', width: 80, align: 'center',
    render: (v: number) => {
      const t = v === 1 ? 'critical' : v === 2 ? 'warning' : 'default';
      const label = v === 1 ? 'P1' : v === 2 ? 'P2' : 'P3';
      return <ZBadge type={t} text={label} />;
    },
  },
  {
    key: 'triggerCount', dataIndex: 'triggerCount', title: '触发次数', width: 90, align: 'right',
    render: (v: number) => <span className={styles.triggerCount}>{v}</span>,
  },
  {
    key: 'enabled', dataIndex: 'enabled', title: '状态', width: 90, align: 'center',
    render: (v: boolean, row: Rule) => (
      <button
        className={v ? styles.toggleOn : styles.toggleOff}
        onClick={() => onToggle(row.id)}
        title={v ? '点击停用' : '点击启用'}
      >
        {v ? '启用' : '停用'}
      </button>
    ),
  },
  { key: 'lastTriggered', dataIndex: 'lastTriggered', title: '最后触发', width: 150 },
];

/* ── 页面组件 ── */

const BusinessRulesPage: React.FC = () => {
  const [rules, setRules] = useState<Rule[]>(initialRules);
  const [search, setSearch] = useState('');

  const handleToggle = (id: string) => {
    setRules(prev => prev.map(r => r.id === id ? { ...r, enabled: !r.enabled } : r));
  };

  const columns = buildColumns(handleToggle);

  const enabledRules = rules.filter(r => r.enabled);
  const disabledRules = rules.filter(r => !r.enabled);
  const p1Rules = rules.filter(r => r.priority === 1 && r.enabled);
  const totalTriggers = rules.reduce((s, r) => s + r.triggerCount, 0);

  const filterRules = (ruleList: Rule[]) => {
    if (!search) return ruleList;
    const q = search.toLowerCase();
    return ruleList.filter(r =>
      r.name.toLowerCase().includes(q) ||
      r.trigger.toLowerCase().includes(q) ||
      r.category.toLowerCase().includes(q)
    );
  };

  /* 分类统计 */
  const categoryStats: Partial<Record<RuleCategory, number>> = {};
  rules.forEach(r => { categoryStats[r.category] = (categoryStats[r.category] ?? 0) + 1; });

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>业务规则引擎</h1>
          <p className={styles.subtitle}>配置损耗阈值、告警条件与自动化策略，驱动 Agent 自动决策</p>
        </div>
        <div className={styles.headerActions}>
          <ZInput placeholder="搜索规则名/触发条件/分类..." value={search} onChange={setSearch} onClear={() => setSearch('')} />
          <ZButton variant="primary">创建规则</ZButton>
        </div>
      </div>

      {/* KPI 摘要 */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="规则总数" value={rules.length} changeLabel="条" /></ZCard>
        <ZCard><ZKpi label="已启用" value={enabledRules.length} change={(enabledRules.length / rules.length) * 100} changeLabel="启用率%" /></ZCard>
        <ZCard><ZKpi label="P1规则" value={p1Rules.length} color="var(--red)" changeLabel="条" /></ZCard>
        <ZCard><ZKpi label="累计触发次数" value={totalTriggers} changeLabel="次" /></ZCard>
      </div>

      {/* 分类概览 */}
      <div className={styles.categoryRow}>
        {/* TODO: GET /api/v1/ops/business-rules/categories */}
        {(Object.entries(categoryStats) as [RuleCategory, number][]).map(([cat, count]) => (
          <ZCard key={cat}>
            <div className={styles.categoryCard}>
              <ZBadge type={CATEGORY_COLORS[cat]} text={cat} />
              <span className={styles.categoryCount}>{count}</span>
              <span className={styles.categoryLabel}>条规则</span>
            </div>
          </ZCard>
        ))}
      </div>

      {/* 规则列表 */}
      <ZTabs
        items={[
          {
            key: 'all',
            label: '全部',
            badge: rules.length,
            children: (
              <ZCard>
                {/* TODO: GET /api/v1/ops/business-rules */}
                <ZTable<Rule> columns={columns} data={filterRules(rules)} rowKey="id" />
              </ZCard>
            ),
          },
          {
            key: 'enabled',
            label: '已启用',
            badge: enabledRules.length,
            children: (
              <ZCard>
                <ZTable<Rule> columns={columns} data={filterRules(enabledRules)} rowKey="id" />
              </ZCard>
            ),
          },
          {
            key: 'disabled',
            label: '已停用',
            badge: disabledRules.length,
            children: (
              <ZCard>
                <ZTable<Rule> columns={columns} data={filterRules(disabledRules)} rowKey="id" />
              </ZCard>
            ),
          },
          {
            key: 'p1',
            label: 'P1高优',
            badge: p1Rules.length,
            children: (
              <ZCard>
                <ZTable<Rule> columns={columns} data={filterRules(p1Rules)} rowKey="id" />
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
