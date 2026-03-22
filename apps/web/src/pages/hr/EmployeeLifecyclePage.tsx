import React, { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../../services/api';
import styles from './HRPages.module.css';

interface ChangeItem {
  id: string;
  employee_id: string;
  employee_name: string;
  change_type: string;
  effective_date: string;
  from_position: string | null;
  to_position: string | null;
  from_store_id: string | null;
  to_store_id: string | null;
  resign_reason: string | null;
  remark: string | null;
}

const CHANGE_TYPE_LABELS: Record<string, string> = {
  onboard: '入职',
  probation: '转正',
  transfer: '调岗/调店',
  promotion: '晋升',
  demotion: '降级',
  salary_adj: '薪资调整',
  resign: '主动离职',
  dismiss: '辞退',
  retire: '退休',
};

const CHANGE_TYPE_COLORS: Record<string, string> = {
  onboard: '#27AE60',
  probation: '#2D9CDB',
  transfer: '#F2994A',
  promotion: '#FF6B2C',
  demotion: '#EB5757',
  salary_adj: '#9B59B6',
  resign: '#EB5757',
  dismiss: '#EB5757',
  retire: 'rgba(255,255,255,0.38)',
};

const EmployeeLifecyclePage: React.FC = () => {
  const [storeId] = useState(localStorage.getItem('store_id') || '');
  const [changes, setChanges] = useState<ChangeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState('');
  const [showOnboardForm, setShowOnboardForm] = useState(false);
  const [showResignForm, setShowResignForm] = useState(false);

  // 入职表单
  const [onboardForm, setOnboardForm] = useState({
    employee_id: '', name: '', phone: '', position: '', hire_date: '',
  });
  // 离职表单
  const [resignForm, setResignForm] = useState({
    employee_id: '', resign_reason: '', last_work_date: '', change_type: 'resign',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ store_id: storeId, limit: '50' });
      if (typeFilter) params.append('change_type', typeFilter);
      const res = await apiClient.get<{ items: ChangeItem[] }>(
        `/api/v1/hr/employee-changes?${params}`
      );
      setChanges(res.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [storeId, typeFilter]);

  useEffect(() => { load(); }, [load]);

  const handleOnboard = async () => {
    try {
      await apiClient.post('/api/v1/hr/onboard', {
        store_id: storeId,
        ...onboardForm,
      });
      setShowOnboardForm(false);
      setOnboardForm({ employee_id: '', name: '', phone: '', position: '', hire_date: '' });
      load();
    } catch (err) {
      alert('入职登记失败');
    }
  };

  const handleResign = async () => {
    try {
      await apiClient.post('/api/v1/hr/resign', {
        store_id: storeId,
        ...resignForm,
      });
      setShowResignForm(false);
      setResignForm({ employee_id: '', resign_reason: '', last_work_date: '', change_type: 'resign' });
      load();
    } catch (err) {
      alert('离职登记失败');
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>入离职管理</h1>
          <p className={styles.pageDesc}>员工入职、离职、调岗、晋升等全生命周期记录</p>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.btnPrimary} onClick={() => setShowOnboardForm(true)}>
            + 入职登记
          </button>
          <button className={styles.btnSecondary} onClick={() => setShowResignForm(true)}>
            离职登记
          </button>
        </div>
      </div>

      {/* 类型筛选 */}
      <div className={styles.tabBar}>
        <button
          className={`${styles.tab} ${!typeFilter ? styles.tabActive : ''}`}
          onClick={() => setTypeFilter('')}
        >
          全部
        </button>
        {Object.entries(CHANGE_TYPE_LABELS).map(([key, label]) => (
          <button
            key={key}
            className={`${styles.tab} ${typeFilter === key ? styles.tabActive : ''}`}
            onClick={() => setTypeFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 入职表单 */}
      {showOnboardForm && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>新员工入职</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
            <input
              className={styles.monthPicker}
              placeholder="工号 (如 EMP042)"
              value={onboardForm.employee_id}
              onChange={e => setOnboardForm(f => ({ ...f, employee_id: e.target.value }))}
            />
            <input
              className={styles.monthPicker}
              placeholder="姓名"
              value={onboardForm.name}
              onChange={e => setOnboardForm(f => ({ ...f, name: e.target.value }))}
            />
            <input
              className={styles.monthPicker}
              placeholder="手机号"
              value={onboardForm.phone}
              onChange={e => setOnboardForm(f => ({ ...f, phone: e.target.value }))}
            />
            <input
              className={styles.monthPicker}
              placeholder="岗位"
              value={onboardForm.position}
              onChange={e => setOnboardForm(f => ({ ...f, position: e.target.value }))}
            />
            <input
              className={styles.monthPicker}
              type="date"
              value={onboardForm.hire_date}
              onChange={e => setOnboardForm(f => ({ ...f, hire_date: e.target.value }))}
            />
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button className={styles.btnPrimary} onClick={handleOnboard}
              disabled={!onboardForm.employee_id || !onboardForm.name || !onboardForm.position || !onboardForm.hire_date}>
              确认入职
            </button>
            <button className={styles.btnSecondary} onClick={() => setShowOnboardForm(false)}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* 离职表单 */}
      {showResignForm && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>员工离职</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
            <input
              className={styles.monthPicker}
              placeholder="员工工号"
              value={resignForm.employee_id}
              onChange={e => setResignForm(f => ({ ...f, employee_id: e.target.value }))}
            />
            <select
              className={styles.monthPicker}
              value={resignForm.change_type}
              onChange={e => setResignForm(f => ({ ...f, change_type: e.target.value }))}
            >
              <option value="resign">主动离职</option>
              <option value="dismiss">辞退</option>
            </select>
            <input
              className={styles.monthPicker}
              type="date"
              value={resignForm.last_work_date}
              onChange={e => setResignForm(f => ({ ...f, last_work_date: e.target.value }))}
            />
            <input
              className={styles.monthPicker}
              placeholder="离职原因"
              value={resignForm.resign_reason}
              onChange={e => setResignForm(f => ({ ...f, resign_reason: e.target.value }))}
              style={{ gridColumn: 'span 2' }}
            />
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button className={styles.btnPrimary} onClick={handleResign}
              disabled={!resignForm.employee_id || !resignForm.resign_reason || !resignForm.last_work_date}
              style={{ background: '#EB5757' }}>
              确认离职
            </button>
            <button className={styles.btnSecondary} onClick={() => setShowResignForm(false)}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* 变动记录列表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>变动记录</div>
        {loading ? (
          <div className={styles.loadingWrap}>加载中...</div>
        ) : changes.length === 0 ? (
          <div className={styles.emptyWrap}>暂无变动记录</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>类型</th>
                  <th>员工</th>
                  <th>工号</th>
                  <th>生效日期</th>
                  <th>变动详情</th>
                  <th>备注</th>
                </tr>
              </thead>
              <tbody>
                {changes.map(c => (
                  <tr key={c.id}>
                    <td>
                      <span className={styles.badge} style={{
                        color: CHANGE_TYPE_COLORS[c.change_type] || 'rgba(255,255,255,0.38)',
                        borderColor: CHANGE_TYPE_COLORS[c.change_type] || 'rgba(255,255,255,0.12)',
                      }}>
                        {CHANGE_TYPE_LABELS[c.change_type] || c.change_type}
                      </span>
                    </td>
                    <td className={styles.cellName}>{c.employee_name}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{c.employee_id}</td>
                    <td>{c.effective_date}</td>
                    <td className={styles.cellReason}>
                      {c.from_position && c.to_position
                        ? `${c.from_position} → ${c.to_position}`
                        : c.to_position
                        ? `→ ${c.to_position}`
                        : c.resign_reason || '-'}
                    </td>
                    <td className={styles.cellReason}>{c.remark || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default EmployeeLifecyclePage;
