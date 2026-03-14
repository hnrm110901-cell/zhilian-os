/**
 * PlatformDataSovereigntyPage — /platform/data-sovereignty
 *
 * 数据主权管理：控制餐饮客户数据的加密导出与断开权，满足 GDPR / 个保法合规要求
 * 后端 API:
 *   GET  /api/v1/ontology/data-sovereignty/config            — 功能开关 + 密钥状态
 *   GET  /api/v1/ontology/data-sovereignty/audit-logs        — 操作审计日志
 *   POST /api/v1/ontology/data-sovereignty/export-encrypted  — 发起加密导出
 *   POST /api/v1/ontology/data-sovereignty/disconnect        — 执行断开权
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZAlert, ZSkeleton, ZModal,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './PlatformDataSovereigntyPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface SovereigntyConfig {
  enabled: boolean;
  key_configured: boolean;
}

interface SovereigntyLog {
  id: string;
  created_at: string;
  action: string;
  username?: string;
  user_id?: string;
  description?: string;
  status: 'success' | 'failure';
}

// ── 工具 ─────────────────────────────────────────────────────────────────────

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return iso; }
}

const ACTION_LABEL: Record<string, string> = {
  data_sovereignty_export: '加密导出',
  data_sovereignty_disconnect: '断开权',
};

// ── 配置信息行 ───────────────────────────────────────────────────────────────

function ConfigRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.configRow}>
      <span className={styles.configLabel}>{label}</span>
      <span className={styles.configVal}>{children}</span>
    </div>
  );
}

// ── 表单 —— 加密导出 ─────────────────────────────────────────────────────────

function ExportForm({
  open, onClose, onSuccess,
}: { open: boolean; onClose: () => void; onSuccess: () => void }) {
  const [tenantId, setTenantId] = useState('');
  const [storeIds, setStoreIds] = useState('');
  const [customerKey, setCustomerKey] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!tenantId.trim()) { setErr('请填写租户 ID'); return; }
    setSubmitting(true);
    setErr(null);
    try {
      const storeList = storeIds
        ? storeIds.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean)
        : undefined;
      await apiClient.post('/api/v1/ontology/data-sovereignty/export-encrypted', {
        tenant_id: tenantId.trim(),
        store_ids: storeList?.length ? storeList : undefined,
        customer_key: customerKey.trim() || undefined,
      });
      onSuccess();
      onClose();
      setTenantId(''); setStoreIds(''); setCustomerKey('');
    } catch (e: any) {
      setErr(e?.message ?? '导出请求失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ZModal
      open={open}
      title="加密数据导出"
      onClose={onClose}
      width={480}
      footer={
        <div className={styles.modalFooter}>
          <ZButton variant="ghost" onClick={onClose}>取消</ZButton>
          <ZButton variant="primary" onClick={handleSubmit}>
            {submitting ? '处理中…' : '确认导出'}
          </ZButton>
        </div>
      }
    >
      <div className={styles.modalBody}>
        <div className={styles.modalTip}>
          <ZAlert
            variant="info"
            title="导出的数据将使用客户密钥加密，仅限合规归档用途"
          />
        </div>
        {err && (
          <div className={styles.modalErr}>
            <ZAlert variant="error" title={err} />
          </div>
        )}
        <div className={styles.fieldRow}>
          <label className={styles.fieldLabel}>租户 ID <span className={styles.req}>*</span></label>
          <input
            className={styles.fieldInput}
            placeholder="如：tenant_徐记海鲜"
            value={tenantId}
            onChange={e => setTenantId(e.target.value)}
          />
        </div>
        <div className={styles.fieldRow}>
          <label className={styles.fieldLabel}>门店 ID（可选，逗号分隔）</label>
          <input
            className={styles.fieldInput}
            placeholder="留空则导出全部门店"
            value={storeIds}
            onChange={e => setStoreIds(e.target.value)}
          />
        </div>
        <div className={styles.fieldRow}>
          <label className={styles.fieldLabel}>客户密钥（可选）</label>
          <input
            className={styles.fieldInput}
            type="password"
            placeholder="留空使用系统默认密钥"
            value={customerKey}
            onChange={e => setCustomerKey(e.target.value)}
          />
          <span className={styles.fieldHint}>客户自持密钥可实现端对端加密，屯象无法解密</span>
        </div>
      </div>
    </ZModal>
  );
}

// ── 表单 —— 断开权 ───────────────────────────────────────────────────────────

function DisconnectForm({
  open, onClose, onSuccess,
}: { open: boolean; onClose: () => void; onSuccess: () => void }) {
  const [tenantId, setTenantId] = useState('');
  const [storeIds, setStoreIds] = useState('');
  const [customerKey, setCustomerKey] = useState('');
  const [exportFirst, setExportFirst] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!tenantId.trim()) { setErr('请填写租户 ID'); return; }
    const storeList = storeIds
      ? storeIds.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean)
      : [];
    if (!storeList.length) { setErr('请至少填写一个门店 ID'); return; }
    setSubmitting(true);
    setErr(null);
    try {
      await apiClient.post('/api/v1/ontology/data-sovereignty/disconnect', {
        tenant_id: tenantId.trim(),
        store_ids: storeList,
        export_first: exportFirst,
        customer_key: customerKey.trim() || undefined,
      });
      onSuccess();
      onClose();
      setTenantId(''); setStoreIds(''); setCustomerKey(''); setExportFirst(true);
    } catch (e: any) {
      setErr(e?.message ?? '断开权执行失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ZModal
      open={open}
      title="执行断开权"
      onClose={onClose}
      width={480}
      footer={
        <div className={styles.modalFooter}>
          <ZButton variant="ghost" onClick={onClose}>取消</ZButton>
          <ZButton variant="primary" onClick={handleSubmit}>
            {submitting ? '执行中…' : '确认断开'}
          </ZButton>
        </div>
      }
    >
      <div className={styles.modalBody}>
        <div className={styles.modalTip}>
          <ZAlert
            variant="warning"
            title="此操作将从本体图谱中删除指定租户/门店的全部数据，不可撤销"
          />
        </div>
        {err && (
          <div className={styles.modalErr}>
            <ZAlert variant="error" title={err} />
          </div>
        )}
        <div className={styles.fieldRow}>
          <label className={styles.fieldLabel}>租户 ID <span className={styles.req}>*</span></label>
          <input
            className={styles.fieldInput}
            placeholder="如：tenant_徐记海鲜"
            value={tenantId}
            onChange={e => setTenantId(e.target.value)}
          />
        </div>
        <div className={styles.fieldRow}>
          <label className={styles.fieldLabel}>门店 ID（必填，逗号分隔）<span className={styles.req}>*</span></label>
          <input
            className={styles.fieldInput}
            placeholder="如：store_001, store_002"
            value={storeIds}
            onChange={e => setStoreIds(e.target.value)}
          />
        </div>
        <div className={styles.fieldRow}>
          <label className={styles.fieldLabel}>客户密钥（可选）</label>
          <input
            className={styles.fieldInput}
            type="password"
            placeholder="用于断开前的加密备份"
            value={customerKey}
            onChange={e => setCustomerKey(e.target.value)}
          />
        </div>
        <div className={styles.checkRow}>
          <label className={styles.checkLabel}>
            <input
              type="checkbox"
              checked={exportFirst}
              onChange={e => setExportFirst(e.target.checked)}
              className={styles.checkbox}
            />
            断开前先执行加密导出备份
          </label>
        </div>
      </div>
    </ZModal>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

export default function PlatformDataSovereigntyPage() {
  const [config, setConfig] = useState<SovereigntyConfig | null>(null);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [logs, setLogs] = useState<SovereigntyLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loadingLogs, setLoadingLogs] = useState(true);
  const [exportOpen, setExportOpen] = useState(false);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // ── 加载配置 ──
  const loadConfig = useCallback(async () => {
    setLoadingConfig(true);
    try {
      const res = await apiClient.get('/api/v1/ontology/data-sovereignty/config');
      setConfig(res ?? null);
    } catch { setConfig(null); } finally { setLoadingConfig(false); }
  }, []);

  // ── 加载日志 ──
  const loadLogs = useCallback(async (pg = 0) => {
    setLoadingLogs(true);
    try {
      const res = await apiClient.get('/api/v1/ontology/data-sovereignty/audit-logs', {
        params: { skip: pg * PAGE_SIZE, limit: PAGE_SIZE },
      });
      setLogs(res?.logs ?? []);
      setTotal(res?.total ?? 0);
      setPage(pg);
    } catch { setLogs([]); } finally { setLoadingLogs(false); }
  }, []);

  useEffect(() => { loadConfig(); loadLogs(0); }, [loadConfig, loadLogs]);

  const handleSuccess = (msg: string) => {
    setSuccessMsg(msg);
    loadLogs(0);
    setTimeout(() => setSuccessMsg(null), 5000);
  };

  const columns: ZTableColumn<SovereigntyLog>[] = [
    {
      key: 'created_at',
      title: '时间',
      width: 180,
      render: (_, row) => <span className={styles.timeCell}>{fmtTime(row.created_at)}</span>,
    },
    {
      key: 'action',
      title: '操作类型',
      width: 130,
      render: (_, row) => (
        <ZBadge
          type={row.action === 'data_sovereignty_disconnect' ? 'error' : 'warning'}
          text={ACTION_LABEL[row.action] ?? row.action}
        />
      ),
    },
    {
      key: 'user',
      title: '操作用户',
      width: 130,
      render: (_, row) => (
        <span className={styles.userCell}>{row.username || row.user_id || '—'}</span>
      ),
    },
    {
      key: 'description',
      title: '描述',
      render: (_, row) => <span className={styles.descCell}>{row.description ?? '—'}</span>,
    },
    {
      key: 'status',
      title: '状态',
      width: 90,
      align: 'center',
      render: (_, row) => (
        <ZBadge
          type={row.status === 'success' ? 'success' : 'error'}
          text={row.status === 'success' ? '成功' : '失败'}
        />
      ),
    },
  ];

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>数据主权</h1>
          <p className={styles.pageSubtitle}>
            管理餐饮客户数据的加密导出与断开权，确保合规与数据安全
          </p>
        </div>
        <ZButton size="sm" variant="ghost" onClick={() => { loadConfig(); loadLogs(0); }}>
          刷新
        </ZButton>
      </div>

      {successMsg && (
        <div className={styles.alertRow}>
          <ZAlert variant="success" title={successMsg} />
        </div>
      )}

      {/* 功能状态卡 */}
      <ZCard className={styles.configCard}>
        <div className={styles.configCardTitle}>🔐 功能状态 & 密钥配置</div>
        {loadingConfig ? (
          <ZSkeleton rows={3} />
        ) : config ? (
          <>
            <ConfigRow label="数据主权功能">
              <ZBadge
                type={config.enabled ? 'success' : 'default'}
                text={config.enabled ? '已启用' : '已停用'}
              />
            </ConfigRow>
            <ConfigRow label="密钥配置">
              <ZBadge
                type={config.key_configured ? 'success' : 'warning'}
                text={config.key_configured ? '已配置' : '未配置（使用系统默认）'}
              />
            </ConfigRow>
            <div className={styles.actionRow}>
              <ZButton
                size="sm"
                variant="secondary"
                onClick={() => setExportOpen(true)}
              >
                🔒 发起加密导出
              </ZButton>
              <ZButton
                size="sm"
                variant="ghost"
                onClick={() => setDisconnectOpen(true)}
              >
                ⚡ 执行断开权
              </ZButton>
            </div>
          </>
        ) : (
          <ZAlert
            variant="warning"
            title="无法加载配置，后端 API 可能暂不可用"
          />
        )}
      </ZCard>

      {/* 审计日志表 */}
      <div className={styles.logSection}>
        <div className={styles.logHeader}>
          <div>
            <h2 className={styles.logTitle}>操作审计日志</h2>
            <p className={styles.logSubtitle}>共 <strong>{total}</strong> 条操作记录</p>
          </div>
          {total > 0 && (
            <div className={styles.pagination}>
              <ZButton
                size="sm"
                variant="ghost"
                onClick={() => loadLogs(page - 1)}
              >
                ‹
              </ZButton>
              <span className={styles.pageInfo}>
                {page + 1} / {Math.max(1, totalPages)}
              </span>
              <ZButton
                size="sm"
                variant="ghost"
                onClick={() => loadLogs(page + 1)}
              >
                ›
              </ZButton>
            </div>
          )}
        </div>

        {loadingLogs ? (
          <ZCard><ZSkeleton rows={6} /></ZCard>
        ) : logs.length === 0 ? (
          <ZCard><ZEmpty text="暂无操作记录" /></ZCard>
        ) : (
          <ZCard className={styles.tableCard}>
            <ZTable<SovereigntyLog>
              columns={columns}
              data={logs}
              rowKey="id"
            />
          </ZCard>
        )}
      </div>

      {/* 加密导出 Modal */}
      <ExportForm
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onSuccess={() => handleSuccess('导出请求已处理，请查看返回数据并妥善保存')}
      />

      {/* 断开权 Modal */}
      <DisconnectForm
        open={disconnectOpen}
        onClose={() => setDisconnectOpen(false)}
        onSuccess={() => handleSuccess('断开权已执行，图谱中该租户/门店数据已删除')}
      />
    </div>
  );
}
