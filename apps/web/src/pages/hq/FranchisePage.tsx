/**
 * 加盟管理页面 — 品牌方视角
 * 路由：/hq/franchise
 */

import React, { useEffect, useState } from "react";
import styles from "./FranchisePage.module.css";
import apiClient from "../../utils/apiClient";

// ================================================================ #
// 类型定义
// ================================================================ #

interface FranchiseeItem {
  id: string;
  company_name: string;
  contact_name?: string;
  contact_phone?: string;
  status: string;
  created_at: string;
}

interface RoyaltySummary {
  monthly_due_yuan: number;
  overdue_total_yuan: number;
  overdue_franchisee_count: number;
}

interface ExpiringContract {
  id: string;
  contract_no: string;
  store_id?: string;
  end_date: string;
  franchisee_id: string;
}

interface FranchiseOverview {
  brand_id: string;
  total_franchisees: number;
  active_franchisees: number;
  monthly_due_yuan: number;
  overdue_total_yuan: number;
  overdue_franchisee_count: number;
  expiring_contracts_90d: ExpiringContract[];
  as_of: string;
}

// ================================================================ #
// 子组件：概览卡片
// ================================================================ #

interface KpiCardProps {
  label: string;
  value: string | number;
  sub?: string;
  highlight?: boolean;
}

const KpiCard: React.FC<KpiCardProps> = ({ label, value, sub, highlight }) => (
  <div className={`${styles.kpiCard} ${highlight ? styles.kpiHighlight : ""}`}>
    <div className={styles.kpiLabel}>{label}</div>
    <div className={styles.kpiValue}>{value}</div>
    {sub && <div className={styles.kpiSub}>{sub}</div>}
  </div>
);

// ================================================================ #
// 主组件
// ================================================================ #

interface FranchisePageProps {
  brandId?: string;
}

const FranchisePage: React.FC<FranchisePageProps> = ({
  brandId = "default",
}) => {
  const [overview, setOverview] = useState<FranchiseOverview | null>(null);
  const [franchisees, setFranchisees] = useState<FranchiseeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [overviewResp, listResp] = await Promise.all([
          apiClient.get(`/api/v1/franchise/overview/${brandId}`),
          apiClient.get(`/api/v1/franchise/franchisees?brand_id=${brandId}&limit=50`),
        ]);
        setOverview(overviewResp.data?.data ?? null);
        setFranchisees(listResp.data?.data?.items ?? []);
      } catch (err: any) {
        setError(err?.message ?? "加载失败，请刷新重试");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [brandId]);

  if (loading) {
    return <div className={styles.loading}>加载中...</div>;
  }

  if (error) {
    return <div className={styles.error}>{error}</div>;
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>加盟管理</h2>
        {overview && (
          <span className={styles.asOf}>
            数据截至 {new Date(overview.as_of).toLocaleString("zh-CN")}
          </span>
        )}
      </div>

      {/* 概览卡片 */}
      {overview && (
        <div className={styles.kpiRow}>
          <KpiCard
            label="加盟商总数"
            value={overview.total_franchisees}
            sub={`活跃 ${overview.active_franchisees} 家`}
          />
          <KpiCard
            label="本月应收提成"
            value={`¥${overview.monthly_due_yuan.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`}
          />
          <KpiCard
            label="逾期未付"
            value={`¥${overview.overdue_total_yuan.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`}
            sub={`${overview.overdue_franchisee_count} 家逾期`}
            highlight={overview.overdue_franchisee_count > 0}
          />
          <KpiCard
            label="合同即将到期"
            value={`${overview.expiring_contracts_90d.length} 份`}
            sub="90天内到期"
            highlight={overview.expiring_contracts_90d.length > 0}
          />
        </div>
      )}

      {/* 合同到期预警 */}
      {overview && overview.expiring_contracts_90d.length > 0 && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>合同到期预警（90天内）</h3>
          <div className={styles.warningList}>
            {overview.expiring_contracts_90d.map((c) => (
              <div key={c.id} className={styles.warningItem}>
                <span className={styles.contractNo}>{c.contract_no}</span>
                <span className={styles.storeId}>
                  门店：{c.store_id ?? "未关联"}
                </span>
                <span className={styles.expiryDate}>
                  到期：{c.end_date}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 加盟商列表 */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>
          加盟商列表（{franchisees.length} 家）
        </h3>
        {franchisees.length === 0 ? (
          <div className={styles.empty}>暂无加盟商数据</div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>公司名</th>
                <th>联系人</th>
                <th>联系电话</th>
                <th>状态</th>
                <th>入盟时间</th>
              </tr>
            </thead>
            <tbody>
              {franchisees.map((f) => (
                <tr key={f.id}>
                  <td>{f.company_name}</td>
                  <td>{f.contact_name ?? "-"}</td>
                  <td>{f.contact_phone ?? "-"}</td>
                  <td>
                    <span
                      className={`${styles.badge} ${
                        f.status === "active"
                          ? styles.badgeActive
                          : f.status === "suspended"
                          ? styles.badgeSuspended
                          : styles.badgeTerminated
                      }`}
                    >
                      {f.status === "active"
                        ? "活跃"
                        : f.status === "suspended"
                        ? "暂停"
                        : "已终止"}
                    </span>
                  </td>
                  <td>
                    {new Date(f.created_at).toLocaleDateString("zh-CN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default FranchisePage;
