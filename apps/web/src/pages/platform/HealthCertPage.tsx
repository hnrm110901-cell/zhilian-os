/**
 * HealthCertPage — /platform/health-certs
 *
 * 健康证管理：录入/查询/到期预警/批量状态更新
 * 后端 API:
 *   GET    /api/v1/health-certs            — 健康证列表
 *   GET    /api/v1/health-certs/stats      — 统计概览
 *   GET    /api/v1/health-certs/expiring   — 即将到期
 *   GET    /api/v1/health-certs/expired    — 已过期
 *   POST   /api/v1/health-certs            — 录入
 *   PUT    /api/v1/health-certs/{id}       — 更新
 *   DELETE /api/v1/health-certs/{id}       — 删除
 *   POST   /api/v1/health-certs/auto-update — 批量状态更新
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Alert, message } from 'antd';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton, ZModal,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './HealthCertPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface HealthCert {
  id: string;
  brand_id: string;
  store_id: string;
  employee_id: string;
  employee_name: string;
  certificate_number?: string;
  issue_date?: string;
  expiry_date?: string;
  issuing_authority?: string;
  certificate_image_url?: string;
  status: string;
  days_remaining: number;
  physical_exam_date?: string;
  physical_exam_result?: string;
  notes?: string;
  created_at?: string;
}

interface CertListResponse {
  items: HealthCert[];
  total: number;
  page: number;
  page_size: number;
}

interface CertStats {
  valid: number;
  expiring_soon: number;
  expired: number;
  revoked: number;
  total: number;
  compliance_rate: number;
}

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function fmtDate(iso?: string): string {
  if (!iso) return '\u2014';
  try {
    return new Date(iso).toLocaleDateString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
    });
  } catch { return iso; }
}

function getDaysClass(days: number): string {
  if (days > 60) return styles.daysGreen;
  if (days >= 30) return styles.daysOrange;
  return styles.daysRed;
}

const STATUS_MAP: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'error' }> = {
  valid:         { label: '有效',     variant: 'success' },
  expiring_soon: { label: '即将到期', variant: 'warning' },
  expired:       { label: '已过期',   variant: 'error' },
  revoked:       { label: '已撤销',   variant: 'default' },
};

const EXAM_LABELS: Record<string, string> = {
  passed: '合格',
  failed: '不合格',
};

// ── 组件 ─────────────────────────────────────────────────────────────────────

const HealthCertPage: React.FC = () => {
  const [certs, setCerts] = useState<HealthCert[]>([]);
  const [stats, setStats] = useState<CertStats | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // 筛选
  const [filterStore, setFilterStore] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [searchText, setSearchText] = useState('');
  const [storeList, setStoreList] = useState<any[]>([]);
  useEffect(() => {
    apiClient.get('/api/v1/stores').then((res: any) => {
      setStoreList(res.stores || res || []);
    }).catch(() => {});
  }, []);

  // 创建/编辑 Modal
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [modalErr, setModalErr] = useState('');

  // 表单字段
  const [formEmployeeId, setFormEmployeeId] = useState('');
  const [formEmployeeName, setFormEmployeeName] = useState('');
  const [formStoreId, setFormStoreId] = useState('');
  const [formCertNumber, setFormCertNumber] = useState('');
  const [formIssueDate, setFormIssueDate] = useState('');
  const [formExpiryDate, setFormExpiryDate] = useState('');
  const [formAuthority, setFormAuthority] = useState('');
  const [formImageUrl, setFormImageUrl] = useState('');
  const [formExamDate, setFormExamDate] = useState('');
  const [formExamResult, setFormExamResult] = useState('');
  const [formNotes, setFormNotes] = useState('');

  const brandId = 'default';

  // ── 数据加载 ────────────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { brand_id: brandId, page, page_size: pageSize };
      if (filterStore) params.store_id = filterStore;
      if (filterStatus) params.status = filterStatus;
      if (searchText.trim()) params.employee_name = searchText.trim();

      const [listRes, statsRes] = await Promise.all([
        apiClient.get<CertListResponse>('/api/v1/health-certs', { params }),
        apiClient.get<CertStats>('/api/v1/health-certs/stats', {
          params: { brand_id: brandId },
        }),
      ]);
      setCerts(listRes.items);
      setTotal(listRes.total);
      setStats(statsRes);
    } catch (err) {
      message.error('加载健康证数据失败');
    } finally {
      setLoading(false);
    }
  }, [brandId, page, filterStore, filterStatus, searchText]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── 批量更新状态 ──────────────────────────────────────────────────────────

  const handleAutoUpdate = async () => {
    try {
      await apiClient.post('/api/v1/health-certs/auto-update', null, {
        params: { brand_id: brandId },
      });
      fetchData();
    } catch (err) {
      message.error('批量更新失败');
    }
  };

  // ── 删除 ──────────────────────────────────────────────────────────────────

  const handleDelete = async (id: string) => {
    try {
      await apiClient.delete(`/api/v1/health-certs/${id}`);
      fetchData();
    } catch (err) {
      message.error('删除失败');
    }
  };

  // ── 查看图片 ──────────────────────────────────────────────────────────────

  const handleViewImage = (url?: string) => {
    if (url) window.open(url, '_blank');
  };

  // ── 表单操作 ──────────────────────────────────────────────────────────────

  const resetForm = () => {
    setEditingId(null);
    setFormEmployeeId(''); setFormEmployeeName(''); setFormStoreId('');
    setFormCertNumber(''); setFormIssueDate(''); setFormExpiryDate('');
    setFormAuthority(''); setFormImageUrl('');
    setFormExamDate(''); setFormExamResult(''); setFormNotes('');
    setModalErr('');
  };

  const openCreate = () => {
    resetForm();
    setShowModal(true);
  };

  const openEdit = (cert: HealthCert) => {
    resetForm();
    setEditingId(cert.id);
    setFormEmployeeId(cert.employee_id);
    setFormEmployeeName(cert.employee_name);
    setFormStoreId(cert.store_id);
    setFormCertNumber(cert.certificate_number || '');
    setFormIssueDate(cert.issue_date || '');
    setFormExpiryDate(cert.expiry_date || '');
    setFormAuthority(cert.issuing_authority || '');
    setFormImageUrl(cert.certificate_image_url || '');
    setFormExamDate(cert.physical_exam_date || '');
    setFormExamResult(cert.physical_exam_result || '');
    setFormNotes(cert.notes || '');
    setShowModal(true);
  };

  const handleSubmit = async () => {
    if (!formEmployeeName.trim() || !formIssueDate || !formExpiryDate) {
      setModalErr('请填写必填字段：员工姓名、发证日期、到期日期');
      return;
    }
    if (!editingId && (!formEmployeeId.trim() || !formStoreId.trim())) {
      setModalErr('请填写必填字段：员工ID、门店ID');
      return;
    }

    setSubmitting(true);
    setModalErr('');
    try {
      if (editingId) {
        // 更新
        const data: Record<string, string | undefined> = {
          employee_name: formEmployeeName.trim(),
          store_id: formStoreId.trim() || undefined,
          certificate_number: formCertNumber.trim() || undefined,
          issue_date: formIssueDate || undefined,
          expiry_date: formExpiryDate || undefined,
          issuing_authority: formAuthority.trim() || undefined,
          certificate_image_url: formImageUrl.trim() || undefined,
          physical_exam_date: formExamDate || undefined,
          physical_exam_result: formExamResult || undefined,
          notes: formNotes.trim() || undefined,
        };
        // 过滤 undefined
        const filtered = Object.fromEntries(
          Object.entries(data).filter(([, v]) => v !== undefined)
        );
        await apiClient.put(`/api/v1/health-certs/${editingId}`, filtered);
      } else {
        // 创建
        await apiClient.post('/api/v1/health-certs', {
          brand_id: brandId,
          store_id: formStoreId.trim(),
          employee_id: formEmployeeId.trim(),
          employee_name: formEmployeeName.trim(),
          certificate_number: formCertNumber.trim() || undefined,
          issue_date: formIssueDate,
          expiry_date: formExpiryDate,
          issuing_authority: formAuthority.trim() || undefined,
          certificate_image_url: formImageUrl.trim() || undefined,
          physical_exam_date: formExamDate || undefined,
          physical_exam_result: formExamResult || undefined,
          notes: formNotes.trim() || undefined,
        });
      }
      setShowModal(false);
      resetForm();
      fetchData();
    } catch (err: any) {
      setModalErr(err?.message || (editingId ? '更新失败' : '创建失败'));
    } finally {
      setSubmitting(false);
    }
  };

  // ── 统计数据 ──────────────────────────────────────────────────────────────

  const validCount = stats?.valid ?? 0;
  const expiringCount = stats?.expiring_soon ?? 0;
  const expiredCount = stats?.expired ?? 0;
  const complianceRate = stats?.compliance_rate ?? 100;

  // ── 表格列 ────────────────────────────────────────────────────────────────

  const columns: ZTableColumn<HealthCert>[] = [
    {
      key: 'employee',
      title: '员工',
      render: (cert) => (
        <div className={styles.employeeCell}>
          <span className={styles.employeeName}>{cert.employee_name}</span>
          <span className={styles.employeeId}>{cert.employee_id}</span>
        </div>
      ),
    },
    {
      key: 'store_id',
      title: '门店',
      render: (cert) => cert.store_id,
    },
    {
      key: 'certificate_number',
      title: '证件编号',
      render: (cert) => cert.certificate_number
        ? <span className={styles.certNo}>{cert.certificate_number}</span>
        : <span className={styles.dateCell}>{'\u2014'}</span>,
    },
    {
      key: 'issue_date',
      title: '发证日期',
      render: (cert) => <span className={styles.dateCell}>{fmtDate(cert.issue_date)}</span>,
    },
    {
      key: 'expiry_date',
      title: '到期日期',
      render: (cert) => <span className={styles.dateCell}>{fmtDate(cert.expiry_date)}</span>,
    },
    {
      key: 'days_remaining',
      title: '剩余天数',
      render: (cert) => (
        <span className={`${styles.daysCell} ${getDaysClass(cert.days_remaining)}`}>
          {cert.days_remaining > 0 ? `${cert.days_remaining}天` : `已过期${Math.abs(cert.days_remaining)}天`}
        </span>
      ),
    },
    {
      key: 'status',
      title: '状态',
      render: (cert) => {
        const s = STATUS_MAP[cert.status] || { label: cert.status, variant: 'default' as const };
        return <ZBadge type={s.variant} text={s.label} />;
      },
    },
    {
      key: 'exam_result',
      title: '体检结果',
      render: (cert) => cert.physical_exam_result
        ? EXAM_LABELS[cert.physical_exam_result] || cert.physical_exam_result
        : '\u2014',
    },
    {
      key: 'actions',
      title: '',
      render: (cert) => (
        <div className={styles.actionGroup}>
          <ZButton size="sm" variant="ghost" onClick={() => openEdit(cert)}>编辑</ZButton>
          {cert.certificate_image_url && (
            <ZButton size="sm" variant="ghost" onClick={() => handleViewImage(cert.certificate_image_url)}>
              查看
            </ZButton>
          )}
          <ZButton size="sm" variant="danger" onClick={() => handleDelete(cert.id)}>删除</ZButton>
        </div>
      ),
    },
  ];

  // ── 分页 ──────────────────────────────────────────────────────────────────

  const totalPages = Math.ceil(total / pageSize);

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>健康证管理</h1>
          <p className={styles.pageSubtitle}>员工健康证录入、到期预警、合规追踪</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={openCreate}>录入健康证</ZButton>
          <ZButton variant="ghost" onClick={handleAutoUpdate}>批量更新状态</ZButton>
          <ZButton variant="ghost" onClick={fetchData}>刷新</ZButton>
        </div>
      </div>

      {/* 统计卡片 */}
      {loading ? (
        <ZSkeleton height={90} />
      ) : (
        <div className={styles.statsRow}>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statGreen}`}>{validCount}</div>
            <div className={styles.statLabel}>有效</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statOrange}`}>{expiringCount}</div>
            <div className={styles.statLabel}>即将到期</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statRed}`}>{expiredCount}</div>
            <div className={styles.statLabel}>已过期</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statBlue}`}>{complianceRate}%</div>
            <div className={styles.statLabel}>合规率</div>
          </ZCard>
        </div>
      )}

      {/* 过期预警 */}
      {!loading && expiredCount > 0 && (
        <div className={styles.alertBanner}>
          <Alert type="error" message={`有 ${expiredCount} 名员工健康证已过期，请尽快安排续办！`} />
        </div>
      )}

      {/* 筛选工具栏 */}
      <div className={styles.toolbar}>
        <select
          className={styles.filterSelect}
          value={filterStore}
          onChange={e => { setFilterStore(e.target.value); setPage(1); }}
        >
          <option value="">全部门店</option>
          {storeList.map((s: any) => (
            <option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</option>
          ))}
        </select>
        <select
          className={styles.filterSelect}
          value={filterStatus}
          onChange={e => { setFilterStatus(e.target.value); setPage(1); }}
        >
          <option value="">全部状态</option>
          <option value="valid">有效</option>
          <option value="expiring_soon">即将到期</option>
          <option value="expired">已过期</option>
          <option value="revoked">已撤销</option>
        </select>
        <input
          className={styles.searchInput}
          placeholder="搜索员工姓名"
          value={searchText}
          onChange={e => { setSearchText(e.target.value); setPage(1); }}
        />
        <div className={styles.toolbarSpacer} />
        {totalPages > 1 && (
          <div style={{ display: 'flex', gap: 4, alignItems: 'center', fontSize: 13 }}>
            <ZButton size="sm" variant="ghost" disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}>上一页</ZButton>
            <span>{page} / {totalPages}</span>
            <ZButton size="sm" variant="ghost" disabled={page >= totalPages}
              onClick={() => setPage(p => p + 1)}>下一页</ZButton>
          </div>
        )}
      </div>

      {/* 健康证表格 */}
      <ZCard className={styles.tableCard}>
        {loading ? (
          <ZSkeleton rows={6} />
        ) : certs.length === 0 ? (
          <ZEmpty description="暂无健康证记录" />
        ) : (
          <ZTable<HealthCert> columns={columns} data={certs} rowKey="id" />
        )}
      </ZCard>

      {/* 录入/编辑 Modal */}
      <ZModal
        open={showModal}
        title={editingId ? '编辑健康证' : '录入健康证'}
        onClose={() => setShowModal(false)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setShowModal(false)}>取消</ZButton>
            <ZButton onClick={handleSubmit} disabled={submitting}>
              {submitting ? '提交中...' : (editingId ? '保存' : '录入')}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          {modalErr && <Alert type="error" message={modalErr} className={styles.modalErr} />}

          {/* 员工信息 */}
          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                员工姓名<span className={styles.fieldRequired}>*</span>
              </label>
              <input className={styles.fieldInput} value={formEmployeeName}
                onChange={e => setFormEmployeeName(e.target.value)} placeholder="员工姓名" />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                员工ID{!editingId && <span className={styles.fieldRequired}>*</span>}
              </label>
              <input className={styles.fieldInput} value={formEmployeeId}
                onChange={e => setFormEmployeeId(e.target.value)} placeholder="员工编号"
                disabled={!!editingId} />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                门店ID{!editingId && <span className={styles.fieldRequired}>*</span>}
              </label>
              <select className={styles.fieldInput} value={formStoreId}
                onChange={e => setFormStoreId(e.target.value)}>
                <option value="">选择门店</option>
                {storeList.map((s: any) => (
                  <option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</option>
                ))}
              </select>
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>证件编号</label>
              <input className={styles.fieldInput} value={formCertNumber}
                onChange={e => setFormCertNumber(e.target.value)} placeholder="健康证编号" />
            </div>
          </div>

          {/* 日期信息 */}
          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                发证日期<span className={styles.fieldRequired}>*</span>
              </label>
              <input className={styles.fieldInput} type="date" value={formIssueDate}
                onChange={e => setFormIssueDate(e.target.value)} />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                到期日期<span className={styles.fieldRequired}>*</span>
              </label>
              <input className={styles.fieldInput} type="date" value={formExpiryDate}
                onChange={e => setFormExpiryDate(e.target.value)} />
            </div>
          </div>

          {/* 发证机构 */}
          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>发证机构</label>
            <input className={styles.fieldInput} value={formAuthority}
              onChange={e => setFormAuthority(e.target.value)} placeholder="如：XX区疾控中心" />
          </div>

          {/* 体检信息 */}
          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>体检日期</label>
              <input className={styles.fieldInput} type="date" value={formExamDate}
                onChange={e => setFormExamDate(e.target.value)} />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>体检结果</label>
              <select className={styles.filterSelect} value={formExamResult}
                onChange={e => setFormExamResult(e.target.value)} style={{ width: '100%' }}>
                <option value="">请选择</option>
                <option value="passed">合格</option>
                <option value="failed">不合格</option>
              </select>
            </div>
          </div>

          {/* 证件照片URL */}
          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>证件照片URL</label>
            <input className={styles.fieldInput} value={formImageUrl}
              onChange={e => setFormImageUrl(e.target.value)} placeholder="照片链接（可选）" />
          </div>

          {/* 备注 */}
          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>备注</label>
            <textarea className={styles.fieldTextarea} value={formNotes}
              onChange={e => setFormNotes(e.target.value)} placeholder="可选备注信息" />
          </div>
        </div>
      </ZModal>
    </div>
  );
};

export default HealthCertPage;
