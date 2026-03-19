import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZTable } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRTeam.module.css';

interface PersonRow {
  id: string;
  name: string;
  phone: string | null;
  job_title: string | null;
  employment_type: string;
  start_date: string | null;
  risk_score: number | null;
  achieved_count: number;
}

interface ListResp {
  store_id: string;
  total: number;
  items: PersonRow[];
}

const EMP_TYPE_LABELS: Record<string, string> = {
  full_time: '全职',
  hourly: '小时工',
  outsourced: '外包',
  dispatched: '派遣',
  partner: '合伙人',
};

function riskBadge(score: number | null): React.ReactNode {
  if (score == null) return <ZBadge type="info" text="未评估" />;
  if (score >= 0.7) return <ZBadge type="critical" text={`${Math.round(score * 100)}%`} />;
  if (score >= 0.4) return <ZBadge type="warning" text={`${Math.round(score * 100)}%`} />;
  return <ZBadge type="success" text={`${Math.round(score * 100)}%`} />;
}

export default function SMHRTeam() {
  const [data, setData] = useState<ListResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const storeId = localStorage.getItem('store_id') || 'STORE001';
  const navigate = useNavigate();

  const load = useCallback(async (q?: string) => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { store_id: storeId, limit: 100 };
      if (q) params.search = q;
      const resp = await apiClient.get('/api/v1/hr/persons', { params });
      setData(resp as ListResp);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  const handleSearch = () => load(search || undefined);

  const columns: ZTableColumn<PersonRow>[] = [
    {
      key: 'name',
      title: '姓名',
      render: (r) => (
        <button
          className={styles.nameLink}
          onClick={() => navigate(`/sm/hr/person/${r.id}`)}
        >
          {r.name}
        </button>
      ),
    },
    {
      key: 'job_title',
      title: '岗位',
      render: (r) => r.job_title || '—',
    },
    {
      key: 'employment_type',
      title: '用工类型',
      render: (r) => (
        <ZBadge type="info" text={EMP_TYPE_LABELS[r.employment_type] || r.employment_type} />
      ),
    },
    {
      key: 'achieved_count',
      title: '技能认证',
      render: (r) => `${r.achieved_count} 项`,
    },
    {
      key: 'risk_score',
      title: '离职风险',
      render: (r) => riskBadge(r.risk_score),
    },
    {
      key: 'start_date',
      title: '入职日期',
      render: (r) =>
        r.start_date ? new Date(r.start_date).toLocaleDateString('zh-CN') : '—',
    },
  ];

  const items = data?.items ?? [];
  const highRiskCount = items.filter((r) => (r.risk_score ?? 0) >= 0.7).length;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>团队成员</h2>
        <ZButton variant="ghost" size="sm" onClick={() => load()}>
          刷新
        </ZButton>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={5} /></div>
      ) : (
        <div className={styles.body}>
          {/* 搜索栏 */}
          <div className={styles.searchRow}>
            <input
              className={styles.searchInput}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="搜索姓名…"
            />
            <ZButton variant="ghost" size="sm" onClick={handleSearch}>搜索</ZButton>
          </div>

          {/* 汇总行 */}
          {data && (
            <div className={styles.summaryRow}>
              <span className={styles.summaryItem}>共 <b>{data.total}</b> 人</span>
              {highRiskCount > 0 && (
                <ZBadge type="critical" text={`${highRiskCount}人高风险`} />
              )}
            </div>
          )}

          {/* 员工表格 */}
          <ZCard title="员工列表">
            {items.length === 0 ? (
              <ZEmpty title="暂无员工" description="当前门店暂无活跃员工记录" />
            ) : (
              <ZTable data={items} columns={columns} rowKey="id" />
            )}
          </ZCard>
        </div>
      )}
    </div>
  );
}
