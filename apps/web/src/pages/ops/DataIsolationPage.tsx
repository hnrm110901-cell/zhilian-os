import React from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './DataIsolationPage.module.css';

// TODO: GET /api/v1/ops/data-isolation/rules
// TODO: GET /api/v1/ops/data-isolation/audit-log

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface IsolationRule {
  id: string;
  name: string;
  type: string;
  scope: string;
  createdAt: string;
  status: string;
}

interface AuditLog {
  id: string;
  time: string;
  operator: string;
  dataAccessed: string;
  sourceIp: string;
  result: string;
}

interface PermissionMatrixRow {
  dataType: string;
  brand1: boolean;
  brand2: boolean;
  brand3: boolean;
  platform: boolean;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_RULES: IsolationRule[] = [
  { id: 'R001', name: '订单数据隔离', type: '行级隔离', scope: '全部商户', createdAt: '2026-01-05', status: '已启用' },
  { id: 'R002', name: '财务数据隔离', type: '库级隔离', scope: '全部商户', createdAt: '2026-01-05', status: '已启用' },
  { id: 'R003', name: '员工信息隔离', type: '行级隔离', scope: '全部商户', createdAt: '2026-01-10', status: '已启用' },
  { id: 'R004', name: '菜品配方隔离', type: '字段级隔离', scope: '品牌间', createdAt: '2026-02-01', status: '已启用' },
  { id: 'R005', name: '会员数据隔离', type: '行级隔离', scope: '全部商户', createdAt: '2026-02-15', status: '已启用' },
  { id: 'R006', name: '训练数据隔离', type: '逻辑隔离', scope: 'AI模块', createdAt: '2026-03-01', status: '测试中' },
];

const MOCK_AUDIT: AuditLog[] = [
  { id: 'A001', time: '2026-03-17 09:15:02', operator: '张运维', dataAccessed: '订单表(尝在一起)', sourceIp: '10.0.1.22', result: '允许' },
  { id: 'A002', time: '2026-03-17 09:12:30', operator: 'API网关', dataAccessed: '库存表(徐记海鲜)', sourceIp: '10.0.1.5', result: '允许' },
  { id: 'A003', time: '2026-03-17 08:55:18', operator: '李测试', dataAccessed: '财务表(最黔线)', sourceIp: '192.168.1.100', result: '拒绝' },
  { id: 'A004', time: '2026-03-17 08:40:05', operator: 'ScheduleAgent', dataAccessed: '排班表(尝在一起)', sourceIp: '10.0.1.5', result: '允许' },
  { id: 'A005', time: '2026-03-17 08:22:11', operator: '王管理', dataAccessed: '菜品配方(尝在一起)', sourceIp: '10.0.2.15', result: '允许' },
  { id: 'A006', time: '2026-03-17 07:50:33', operator: 'InventoryAgent', dataAccessed: '库存表(尝在一起)', sourceIp: '10.0.1.5', result: '允许' },
  { id: 'A007', time: '2026-03-17 07:30:00', operator: '系统备份', dataAccessed: '全量快照', sourceIp: '10.0.1.1', result: '允许' },
  { id: 'A008', time: '2026-03-16 23:55:12', operator: '未知来源', dataAccessed: '会员表(徐记海鲜)', sourceIp: '203.0.113.50', result: '拒绝' },
];

const PERMISSION_MATRIX: PermissionMatrixRow[] = [
  { dataType: '订单数据', brand1: true, brand2: true, brand3: true, platform: true },
  { dataType: '财务报表', brand1: true, brand2: true, brand3: true, platform: true },
  { dataType: '员工信息', brand1: true, brand2: false, brand3: false, platform: true },
  { dataType: '菜品配方', brand1: true, brand2: false, brand3: false, platform: false },
  { dataType: '会员数据', brand1: true, brand2: true, brand3: false, platform: false },
  { dataType: '库存记录', brand1: true, brand2: true, brand3: true, platform: true },
  { dataType: 'AI训练样本', brand1: false, brand2: false, brand3: false, platform: true },
];

const BRAND_COLS = [
  { key: 'brand1', label: '尝在一起' },
  { key: 'brand2', label: '徐记海鲜' },
  { key: 'brand3', label: '最黔线' },
  { key: 'platform', label: '平台（屯象）' },
] as const;

// ── 组件 ─────────────────────────────────────────────────────────────────────

const DataIsolationPage: React.FC = () => {
  const ruleColumns: ZTableColumn<IsolationRule>[] = [
    { key: 'name', dataIndex: 'name', title: '规则名称' },
    { key: 'type', dataIndex: 'type', title: '类型',
      render: (v: string) => <ZBadge type="info" text={v} />,
    },
    { key: 'scope', dataIndex: 'scope', title: '适用范围' },
    { key: 'createdAt', dataIndex: 'createdAt', title: '创建时间' },
    { key: 'status', dataIndex: 'status', title: '状态',
      render: (v: string) => (
        <ZBadge type={v === '已启用' ? 'success' : 'warning'} text={v} />
      ),
    },
  ];

  const auditColumns: ZTableColumn<AuditLog>[] = [
    { key: 'time', dataIndex: 'time', title: '时间' },
    { key: 'operator', dataIndex: 'operator', title: '操作人' },
    { key: 'dataAccessed', dataIndex: 'dataAccessed', title: '访问数据' },
    { key: 'sourceIp', dataIndex: 'sourceIp', title: '来源IP' },
    { key: 'result', dataIndex: 'result', title: '结果',
      render: (v: string) => (
        <ZBadge type={v === '允许' ? 'success' : 'error'} text={v} />
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h2>数据隔离策略</h2>
          <p>多租户数据隔离管理，确保商户数据安全与访问控制</p>
        </div>
      </div>

      {/* 隔离规则 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>隔离规则</div>
        <ZCard noPadding>
          <ZTable<IsolationRule>
            columns={ruleColumns}
            dataSource={MOCK_RULES}
            rowKey="id"
          />
        </ZCard>
      </div>

      {/* 门店数据权限矩阵 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>品牌数据访问权限矩阵</div>
        <ZCard noPadding>
          <div className={styles.matrixWrapper}>
            <table className={styles.matrix}>
              <thead>
                <tr>
                  <th className={styles.matrixHeader}>数据类型</th>
                  {BRAND_COLS.map((col) => (
                    <th key={col.key} className={styles.matrixHeader}>{col.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {PERMISSION_MATRIX.map((row) => (
                  <tr key={row.dataType} className={styles.matrixRow}>
                    <td className={styles.matrixDataType}>{row.dataType}</td>
                    {BRAND_COLS.map((col) => (
                      <td key={col.key} className={styles.matrixCell}>
                        {row[col.key] ? (
                          <span className={styles.checkYes}>✓</span>
                        ) : (
                          <span className={styles.checkNo}>✗</span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ZCard>
      </div>

      {/* 数据访问审计日志 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>数据访问审计日志</div>
        <ZCard noPadding>
          <ZTable<AuditLog>
            columns={auditColumns}
            dataSource={MOCK_AUDIT}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default DataIsolationPage;
