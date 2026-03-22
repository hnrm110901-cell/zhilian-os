import React, { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../../services/api';
import styles from './HRPages.module.css';

interface EmployeeItem {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  position: string | null;
  hire_date: string | null;
  is_active: boolean;
  performance_score: string | null;
  skills: string[];
  employment_type: string | null;
  health_cert_expiry: string | null;
  emergency_contact: string | null;
  emergency_phone: string | null;
  emergency_relation: string | null;
  bank_name: string | null;
  bank_account: string | null;
  education: string | null;
  gender: string | null;
  seniority_months: number | null;
}

const POSITION_OPTIONS = ['全部', '服务员', '厨师', '收银', '店长', '厨师长', '保洁'];

const EMP_TYPE_MAP: Record<string, string> = {
  regular: '正式', part_time: '半日工', intern: '实习', trainee: '见习',
  rehire: '返聘', temp: '灵活用工', outsource: '业务外包', outsource_flex: '勤工俭学',
};

const DetailTab: React.FC<{ label: string; active: boolean; onClick: () => void }> = ({ label, active, onClick }) => (
  <button
    onClick={onClick}
    style={{
      padding: '6px 16px', fontSize: 13, border: 'none', cursor: 'pointer',
      background: active ? 'rgba(255,107,44,0.15)' : 'transparent',
      color: active ? '#FF6B2C' : 'rgba(255,255,255,0.6)',
      borderBottom: active ? '2px solid #FF6B2C' : '2px solid transparent',
    }}
  >{label}</button>
);

const DetailRow: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div style={{ display: 'flex', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
    <div style={{ width: 100, color: 'rgba(255,255,255,0.45)', fontSize: 13, flexShrink: 0 }}>{label}</div>
    <div style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13 }}>{value || '-'}</div>
  </div>
);

const EmployeeRosterPage: React.FC = () => {
  const [storeId] = useState(localStorage.getItem('store_id') || '');
  const [employees, setEmployees] = useState<EmployeeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [positionFilter, setPositionFilter] = useState('');
  const [page, setPage] = useState(1);
  const [selectedEmp, setSelectedEmp] = useState<EmployeeItem | null>(null);
  const [detailTab, setDetailTab] = useState('basic');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        store_id: storeId,
        page: String(page),
        page_size: '50',
      });
      if (statusFilter) params.append('status', statusFilter);
      if (positionFilter) params.append('position', positionFilter);
      if (keyword) params.append('keyword', keyword);

      const res = await apiClient.get<{
        items: EmployeeItem[];
        total: number;
      }>(`/api/v1/hr/employees?${params}`);
      setEmployees(res.items || []);
      setTotal(res.total || 0);
    } catch { /* silent */ }
    setLoading(false);
  }, [storeId, page, statusFilter, positionFilter, keyword]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>员工花名册</h1>
          <p className={styles.pageDesc}>全员档案管理 — 共 {total} 人</p>
        </div>
        <div className={styles.headerActions}>
          <input
            type="text"
            placeholder="搜索姓名/手机号"
            value={keyword}
            onChange={e => { setKeyword(e.target.value); setPage(1); }}
            className={styles.monthPicker}
            style={{ width: 180 }}
          />
        </div>
      </div>

      {/* 筛选 */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <div className={styles.tabBar}>
          {['active', 'inactive', 'all'].map(s => (
            <button
              key={s}
              className={`${styles.tab} ${statusFilter === s ? styles.tabActive : ''}`}
              onClick={() => { setStatusFilter(s === 'all' ? '' : s); setPage(1); }}
            >
              {s === 'active' ? '在职' : s === 'inactive' ? '离职' : '全部'}
            </button>
          ))}
        </div>
        <div className={styles.tabBar}>
          {POSITION_OPTIONS.map(p => (
            <button
              key={p}
              className={`${styles.tab} ${(p === '全部' ? !positionFilter : positionFilter === p) ? styles.tabActive : ''}`}
              onClick={() => { setPositionFilter(p === '全部' ? '' : p); setPage(1); }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* 表格 */}
      <div className={styles.section}>
        {loading ? (
          <div className={styles.loadingWrap}>加载中...</div>
        ) : employees.length === 0 ? (
          <div className={styles.emptyWrap}>暂无员工数据</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>工号</th>
                  <th>姓名</th>
                  <th>岗位</th>
                  <th>手机</th>
                  <th>入职日期</th>
                  <th>绩效</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {employees.map(e => (
                  <tr key={e.id} onClick={() => { setSelectedEmp(e); setDetailTab('basic'); }} style={{ cursor: 'pointer' }}>
                    <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{e.id}</td>
                    <td className={styles.cellName}>{e.name}</td>
                    <td>{e.position || '-'}</td>
                    <td>{e.phone || '-'}</td>
                    <td>{e.hire_date || '-'}</td>
                    <td>
                      {e.performance_score ? (
                        <span className={styles.badge} style={{
                          color: e.performance_score <= 'B' ? '#27AE60' : '#F2994A',
                          borderColor: e.performance_score <= 'B' ? '#27AE60' : '#F2994A',
                        }}>
                          {e.performance_score}
                        </span>
                      ) : '-'}
                    </td>
                    <td>
                      <span className={styles.badge} style={{
                        color: e.is_active ? '#27AE60' : '#EB5757',
                        borderColor: e.is_active ? '#27AE60' : '#EB5757',
                      }}>
                        {e.is_active ? '在职' : '离职'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 分页 */}
        {total > 50 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 16 }}>
            <button
              className={styles.btnSecondary}
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
            >
              上一页
            </button>
            <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, lineHeight: '36px' }}>
              {page} / {Math.ceil(total / 50)}
            </span>
            <button
              className={styles.btnSecondary}
              disabled={page >= Math.ceil(total / 50)}
              onClick={() => setPage(p => p + 1)}
            >
              下一页
            </button>
          </div>
        )}
      </div>

      {/* 员工详情侧边栏 */}
      {selectedEmp && (
        <div style={{
          position: 'fixed', top: 0, right: 0, width: 400, height: '100vh',
          background: '#0D2029', borderLeft: '1px solid rgba(255,255,255,0.08)',
          zIndex: 1000, overflowY: 'auto', padding: '20px 24px',
          boxShadow: '-4px 0 20px rgba(0,0,0,0.3)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ color: 'rgba(255,255,255,0.92)', margin: 0 }}>{selectedEmp.name}</h3>
            <button onClick={() => setSelectedEmp(null)} style={{
              background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)',
              fontSize: 20, cursor: 'pointer',
            }}>✕</button>
          </div>

          <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid rgba(255,255,255,0.08)', marginBottom: 16 }}>
            {['basic', 'compliance', 'emergency', 'bank'].map(tab => (
              <DetailTab key={tab} label={{ basic: '基本信息', compliance: '合规', emergency: '紧急联系', bank: '银行信息' }[tab]!}
                active={detailTab === tab} onClick={() => setDetailTab(tab)} />
            ))}
          </div>

          {detailTab === 'basic' && (
            <div>
              <DetailRow label="工号" value={selectedEmp.id} />
              <DetailRow label="姓名" value={selectedEmp.name} />
              <DetailRow label="性别" value={selectedEmp.gender} />
              <DetailRow label="岗位" value={selectedEmp.position} />
              <DetailRow label="用工类型" value={selectedEmp.employment_type ? EMP_TYPE_MAP[selectedEmp.employment_type] || selectedEmp.employment_type : null} />
              <DetailRow label="入职日期" value={selectedEmp.hire_date} />
              <DetailRow label="司龄" value={selectedEmp.seniority_months != null ? `${selectedEmp.seniority_months}个月` : null} />
              <DetailRow label="学历" value={selectedEmp.education} />
              <DetailRow label="手机" value={selectedEmp.phone} />
              <DetailRow label="邮箱" value={selectedEmp.email} />
              <DetailRow label="绩效" value={selectedEmp.performance_score} />
              <DetailRow label="状态" value={selectedEmp.is_active ? '在职' : '离职'} />
            </div>
          )}

          {detailTab === 'compliance' && (
            <div>
              <DetailRow label="健康证到期" value={
                selectedEmp.health_cert_expiry ? (
                  <span style={{
                    color: (() => {
                      const expiry = new Date(selectedEmp.health_cert_expiry);
                      const now = new Date();
                      const in30d = new Date(now.getTime() + 30 * 86400000);
                      return expiry < now ? '#EB5757' : expiry < in30d ? '#F2994A' : '#27AE60';
                    })()
                  }}>
                    {selectedEmp.health_cert_expiry}
                  </span>
                ) : null
              } />
            </div>
          )}

          {detailTab === 'emergency' && (
            <div>
              <DetailRow label="联系人" value={selectedEmp.emergency_contact} />
              <DetailRow label="电话" value={selectedEmp.emergency_phone} />
              <DetailRow label="关系" value={selectedEmp.emergency_relation} />
            </div>
          )}

          {detailTab === 'bank' && (
            <div>
              <DetailRow label="银行" value={selectedEmp.bank_name} />
              <DetailRow label="账号" value={selectedEmp.bank_account} />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default EmployeeRosterPage;
