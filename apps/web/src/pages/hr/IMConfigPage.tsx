/**
 * 商户IM平台配置 + 通讯录同步页面
 * 路由: /im-config
 * 功能: 配置企微/钉钉 → 测试连接 → 一键同步 → 查看日志
 */
import React, { useCallback, useEffect, useState } from 'react';
import { hrService } from '../../services/hrService';
import type {
  IMConfigResponse,
  IMConfigData,
  IMSyncLogItem,
  IMDepartmentItem,
} from '../../services/hrService';
import styles from './IMConfigPage.module.css';

const BRAND_ID = localStorage.getItem('brand_id') || 'BRD_001';

type TabKey = 'config' | 'mapping' | 'logs';

const STATUS_CLASS: Record<string, string> = {
  success: styles.statusSuccess,
  failed: styles.statusFailed,
  partial: styles.statusPartial,
  running: styles.statusRunning,
};

const TRIGGER_LABELS: Record<string, string> = {
  manual: '手动', scheduled: '定时', callback: '回调',
};

const IMConfigPage: React.FC = () => {
  const [tab, setTab] = useState<TabKey>('config');
  const [loading, setLoading] = useState(true);

  // 配置状态
  const [config, setConfig] = useState<IMConfigResponse | null>(null);
  const [platform, setPlatform] = useState<'wechat_work' | 'dingtalk'>('wechat_work');
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [syncResult, setSyncResult] = useState<string | null>(null);

  // 表单字段
  const [corpId, setCorpId] = useState('');
  const [corpSecret, setCorpSecret] = useState('');
  const [agentId, setAgentId] = useState('');
  const [wxToken, setWxToken] = useState('');
  const [wxAesKey, setWxAesKey] = useState('');
  const [dtAppKey, setDtAppKey] = useState('');
  const [dtAppSecret, setDtAppSecret] = useState('');
  const [dtAgentId, setDtAgentId] = useState('');
  const [dtToken, setDtToken] = useState('');
  const [dtAesKey, setDtAesKey] = useState('');
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [autoCreateUser, setAutoCreateUser] = useState(true);
  const [autoDisableUser, setAutoDisableUser] = useState(true);
  const [defaultStoreId, setDefaultStoreId] = useState('');

  // 部门映射
  const [departments, setDepartments] = useState<IMDepartmentItem[]>([]);
  const [deptMapping, setDeptMapping] = useState<Record<string, string>>({});
  const [savingMapping, setSavingMapping] = useState(false);

  // 日志
  const [logs, setLogs] = useState<IMSyncLogItem[]>([]);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getIMConfig(BRAND_ID);
      setConfig(data);
      if (data.configured && data.im_platform) {
        setPlatform(data.im_platform as 'wechat_work' | 'dingtalk');
        setCorpId(data.wechat_corp_id || '');
        setAgentId(data.wechat_agent_id || '');
        setDtAppKey(data.dingtalk_app_key || '');
        setDtAgentId(data.dingtalk_agent_id || '');
        setSyncEnabled(data.sync_enabled ?? true);
        setAutoCreateUser(data.auto_create_user ?? true);
        setAutoDisableUser(data.auto_disable_user ?? true);
        setDefaultStoreId(data.default_store_id || '');
      }
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  const loadDepartments = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getIMDepartments(BRAND_ID);
      setDepartments(data.departments || []);
      setDeptMapping(data.current_mapping || {});
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getIMSyncLogs(BRAND_ID);
      setLogs(data.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (tab === 'config') loadConfig();
    else if (tab === 'mapping') loadDepartments();
    else loadLogs();
  }, [tab, loadConfig, loadDepartments, loadLogs]);

  const handleSave = async () => {
    setSaving(true);
    setTestResult(null);
    setSyncResult(null);
    try {
      const data: IMConfigData = {
        brand_id: BRAND_ID,
        im_platform: platform,
        wechat_corp_id: corpId || undefined,
        wechat_corp_secret: corpSecret || undefined,
        wechat_agent_id: agentId || undefined,
        wechat_token: wxToken || undefined,
        wechat_encoding_aes_key: wxAesKey || undefined,
        dingtalk_app_key: dtAppKey || undefined,
        dingtalk_app_secret: dtAppSecret || undefined,
        dingtalk_agent_id: dtAgentId || undefined,
        dingtalk_aes_key: dtAesKey || undefined,
        dingtalk_token: dtToken || undefined,
        sync_enabled: syncEnabled,
        auto_create_user: autoCreateUser,
        auto_disable_user: autoDisableUser,
        default_store_id: defaultStoreId || undefined,
      };
      const result = await hrService.saveIMConfig(BRAND_ID, data);
      alert(result.message || '保存成功');
      loadConfig();
    } catch (e: unknown) {
      alert('保存失败: ' + (e instanceof Error ? e.message : '未知错误'));
    }
    setSaving(false);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await hrService.testIMConnection(BRAND_ID);
      setTestResult({ ok: result.connected, msg: result.message });
    } catch (e: unknown) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : '连接失败' });
    }
    setTesting(false);
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await hrService.triggerIMSync(BRAND_ID);
      setSyncResult(result.message);
      loadConfig();
    } catch (e: unknown) {
      setSyncResult('同步失败: ' + (e instanceof Error ? e.message : '未知错误'));
    }
    setSyncing(false);
  };

  const renderConfig = () => (
    <>
      {/* 同步状态卡 */}
      {config?.configured && config.last_sync_at && (
        <div className={styles.statusCard}>
          <div className={styles.statusHeader}>
            <span className={styles.statusTitle}>同步状态</span>
            <span className={`${styles.statusBadge} ${STATUS_CLASS[config.last_sync_status || ''] || ''}`}>
              {config.last_sync_status === 'success' ? '成功' :
               config.last_sync_status === 'failed' ? '失败' :
               config.last_sync_status === 'partial' ? '部分成功' : config.last_sync_status}
            </span>
          </div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginBottom: 10 }}>
            最后同步: {config.last_sync_at} | {config.last_sync_message}
          </div>
          {config.last_sync_stats && (
            <div className={styles.statsGrid}>
              <div className={styles.statItem}>
                <div className={styles.statNum}>{config.last_sync_stats.added ?? 0}</div>
                <div className={styles.statLabel}>新增员工</div>
              </div>
              <div className={styles.statItem}>
                <div className={styles.statNum}>{config.last_sync_stats.updated ?? 0}</div>
                <div className={styles.statLabel}>更新</div>
              </div>
              <div className={styles.statItem}>
                <div className={styles.statNum}>{config.last_sync_stats.disabled ?? 0}</div>
                <div className={styles.statLabel}>停用</div>
              </div>
              <div className={styles.statItem}>
                <div className={styles.statNum}>{config.last_sync_stats.user_created ?? 0}</div>
                <div className={styles.statLabel}>新建账号</div>
              </div>
            </div>
          )}
          <div className={styles.btnRow} style={{ marginTop: 12 }}>
            <button className={`${styles.btn} ${styles.btnSync}`} onClick={handleSync} disabled={syncing}>
              {syncing ? '同步中...' : '立即同步'}
            </button>
          </div>
          {syncResult && <div style={{ marginTop: 8, fontSize: 12, color: '#FF6B2C' }}>{syncResult}</div>}
        </div>
      )}

      {/* 平台选择 */}
      <div className={styles.platformPicker}>
        <div
          className={`${styles.platformCard} ${platform === 'wechat_work' ? styles.platformActive : ''}`}
          onClick={() => setPlatform('wechat_work')}
        >
          <div className={styles.platformIcon}>💬</div>
          <div className={styles.platformName}>企业微信</div>
          <div className={styles.platformDesc}>支持 OAuth + 通讯录 + 消息推送</div>
        </div>
        <div
          className={`${styles.platformCard} ${platform === 'dingtalk' ? styles.platformActive : ''}`}
          onClick={() => setPlatform('dingtalk')}
        >
          <div className={styles.platformIcon}>📌</div>
          <div className={styles.platformName}>钉钉</div>
          <div className={styles.platformDesc}>支持 OAuth + 通讯录 + 消息推送</div>
        </div>
      </div>

      {/* 凭证表单 */}
      <div className={styles.form}>
        {platform === 'wechat_work' ? (
          <>
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>企业ID (Corp ID)</label>
                <input className={styles.formInput} value={corpId} onChange={e => setCorpId(e.target.value)} placeholder="ww1234567890" />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>应用AgentId</label>
                <input className={styles.formInput} value={agentId} onChange={e => setAgentId(e.target.value)} placeholder="1000002" />
              </div>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>应用Secret (Corp Secret)</label>
              <input className={styles.formInput} type="password" value={corpSecret} onChange={e => setCorpSecret(e.target.value)} placeholder={config?.has_wechat_secret ? '已设置(留空不修改)' : '输入Secret'} />
            </div>
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>回调Token (可选)</label>
                <input className={styles.formInput} value={wxToken} onChange={e => setWxToken(e.target.value)} placeholder="用于接收通讯录变更回调" />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>EncodingAESKey (可选)</label>
                <input className={styles.formInput} value={wxAesKey} onChange={e => setWxAesKey(e.target.value)} placeholder="43位字符" />
              </div>
            </div>
          </>
        ) : (
          <>
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>AppKey</label>
                <input className={styles.formInput} value={dtAppKey} onChange={e => setDtAppKey(e.target.value)} placeholder="dingxxx" />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>AgentId</label>
                <input className={styles.formInput} value={dtAgentId} onChange={e => setDtAgentId(e.target.value)} placeholder="应用AgentId" />
              </div>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>AppSecret</label>
              <input className={styles.formInput} type="password" value={dtAppSecret} onChange={e => setDtAppSecret(e.target.value)} placeholder={config?.has_dingtalk_secret ? '已设置(留空不修改)' : '输入Secret'} />
            </div>
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>回调Token (可选)</label>
                <input className={styles.formInput} value={dtToken} onChange={e => setDtToken(e.target.value)} placeholder="用于接收通讯录变更回调" />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>回调AES Key (可选)</label>
                <input className={styles.formInput} value={dtAesKey} onChange={e => setDtAesKey(e.target.value)} placeholder="43位字符" />
              </div>
            </div>
          </>
        )}

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>默认门店ID (新员工入职门店)</label>
          <input className={styles.formInput} value={defaultStoreId} onChange={e => setDefaultStoreId(e.target.value)} placeholder="STORE_001" />
        </div>

        <div className={styles.checkboxRow}>
          <label className={styles.checkboxLabel}>
            <input type="checkbox" checked={syncEnabled} onChange={e => setSyncEnabled(e.target.checked)} />
            启用自动同步
          </label>
          <label className={styles.checkboxLabel}>
            <input type="checkbox" checked={autoCreateUser} onChange={e => setAutoCreateUser(e.target.checked)} />
            自动创建系统账号
          </label>
          <label className={styles.checkboxLabel}>
            <input type="checkbox" checked={autoDisableUser} onChange={e => setAutoDisableUser(e.target.checked)} />
            离职自动禁用账号
          </label>
        </div>

        <div className={styles.btnRow}>
          <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleSave} disabled={saving}>
            {saving ? '保存中...' : '保存配置'}
          </button>
          {config?.configured && (
            <button className={styles.btn} onClick={handleTest} disabled={testing}>
              {testing ? '测试中...' : '测试连接'}
            </button>
          )}
        </div>

        {testResult && (
          <div className={`${styles.testResult} ${testResult.ok ? styles.testOk : styles.testFail}`}>
            {testResult.ok ? '✓ ' : '✗ '}{testResult.msg}
          </div>
        )}
      </div>
    </>
  );

  const handleSaveMapping = async () => {
    setSavingMapping(true);
    try {
      const result = await hrService.updateDeptStoreMapping(BRAND_ID, deptMapping);
      alert(result.message || '映射保存成功');
    } catch (e: unknown) {
      alert('保存失败: ' + (e instanceof Error ? e.message : '未知错误'));
    }
    setSavingMapping(false);
  };

  const renderMapping = () => (
    <>
      {!config?.configured ? (
        <div className={styles.empty}>请先完成平台配置</div>
      ) : departments.length === 0 ? (
        <div className={styles.empty}>未获取到部门，请先测试连接</div>
      ) : (
        <>
          <div className={styles.statusCard}>
            <div className={styles.statusTitle}>部门 → 门店映射</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginBottom: 12 }}>
              将 IM 平台的部门关联到屯象OS门店，同步时新员工按部门自动分配到对应门店。
              未映射的部门将使用默认门店。
            </div>
          </div>
          <div className={styles.form}>
            {departments.map(dept => (
              <div key={dept.id} className={styles.formRow}>
                <div className={styles.formGroup} style={{ flex: 2 }}>
                  <label className={styles.formLabel}>{dept.name}</label>
                </div>
                <div className={styles.formGroup} style={{ flex: 3 }}>
                  <input
                    className={styles.formInput}
                    value={deptMapping[dept.name] || ''}
                    onChange={e => {
                      const v = e.target.value;
                      setDeptMapping(prev => {
                        const next = { ...prev };
                        if (v) next[dept.name] = v;
                        else delete next[dept.name];
                        return next;
                      });
                    }}
                    placeholder="门店ID（留空使用默认门店）"
                  />
                </div>
              </div>
            ))}
            <div className={styles.btnRow}>
              <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleSaveMapping} disabled={savingMapping}>
                {savingMapping ? '保存中...' : '保存映射'}
              </button>
              <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
                已映射 {Object.keys(deptMapping).length} / {departments.length} 个部门
              </span>
            </div>
          </div>
        </>
      )}
    </>
  );

  const renderLogs = () => (
    <>
      {logs.length === 0 ? (
        <div className={styles.empty}>暂无同步日志</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>时间</th>
                <th>触发方式</th>
                <th>状态</th>
                <th>平台人数</th>
                <th>新增</th>
                <th>更新</th>
                <th>停用</th>
                <th>建账号</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.id}>
                  <td>{log.started_at?.replace('T', ' ').slice(0, 16) || '-'}</td>
                  <td>{TRIGGER_LABELS[log.trigger] || log.trigger}</td>
                  <td>
                    <span className={`${styles.statusBadge} ${STATUS_CLASS[log.status] || ''}`}>
                      {log.status}
                    </span>
                  </td>
                  <td>{log.total_platform_members}</td>
                  <td style={{ color: log.added_count > 0 ? '#4CAF50' : undefined }}>{log.added_count}</td>
                  <td>{log.updated_count}</td>
                  <td style={{ color: log.disabled_count > 0 ? '#FF6B6B' : undefined }}>{log.disabled_count}</td>
                  <td>{log.user_created_count}</td>
                  <td style={{ color: log.error_count > 0 ? '#FF6B6B' : undefined }}>{log.error_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>IM平台 · 通讯录同步</h1>
        <div className={styles.tabs}>
          <button className={`${styles.tab} ${tab === 'config' ? styles.tabActive : ''}`} onClick={() => setTab('config')}>
            平台配置
          </button>
          <button className={`${styles.tab} ${tab === 'mapping' ? styles.tabActive : ''}`} onClick={() => setTab('mapping')}>
            部门映射
          </button>
          <button className={`${styles.tab} ${tab === 'logs' ? styles.tabActive : ''}`} onClick={() => setTab('logs')}>
            同步日志
          </button>
        </div>
      </div>
      {loading ? <div className={styles.loading}>加载中...</div> : (
        tab === 'config' ? renderConfig() : tab === 'mapping' ? renderMapping() : renderLogs()
      )}
    </div>
  );
};

export default IMConfigPage;
