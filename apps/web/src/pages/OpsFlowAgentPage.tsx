import { useEffect, useState } from 'react'
import { apiClient } from '../services/api'
import css from './OpsFlowAgentPage.module.css'

interface DashboardData {
  store_id: string
  as_of: string
  chain_events_24h: { total: number; total_linkages: number }
  order_layer: { anomaly_count_24h: number; total_loss_yuan: number }
  inventory_layer: { unresolved_alerts: number }
  quality_layer: { inspections_24h: number; avg_score: number }
  recent_events: Array<{
    event_type: string; severity: string; title: string
    linkage_count: number; created_at: string
  }>
  pending_decision: {
    id: string | null; title: string | null
    priority: string | null; impact_yuan: number
  }
}

interface InventoryAlert {
  id: string; dish_name: string; risk_level: string
  current_qty: number; safety_qty: number
  predicted_stockout_hours: number; estimated_loss_yuan: number
  restock_qty_recommended: number
}

interface QualityRecord {
  id: string; dish_name: string; quality_score: number
  status: string; ai_insight: string; created_at: string
}

interface Decision {
  id: string; decision_title: string; priority: string
  involves_order: boolean; involves_inventory: boolean; involves_quality: boolean
  estimated_revenue_impact_yuan: number
  recommendations: Array<{ layer: string; action: string; expected_yuan: number; priority: string }>
  ai_insight: string; status: string
}

const DEFAULT_STORE = localStorage.getItem('store_id') || ''
const SEVERITY_LABEL: Record<string, string> = { critical: '紧急', warning: '预警', info: '提示' }
const RISK_LABEL: Record<string, string> = { critical: '危急', high: '高风险', medium: '中风险', low: '低风险' }
const LAYER_LABEL: Record<string, string> = { order: '订单', inventory: '库存', quality: '质检' }

export default function OpsFlowAgentPage() {
  const [tab, setTab] = useState<'dashboard' | 'chain' | 'inventory' | 'quality' | 'decision'>('dashboard')
  const [storeId] = useState(DEFAULT_STORE)
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [invAlerts, setInvAlerts] = useState<InventoryAlert[]>([])
  const [qualityRecords, setQualityRecords] = useState<QualityRecord[]>([])
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [loading, setLoading] = useState(true)
  const [acceptingId, setAcceptingId] = useState<string | null>(null)

  useEffect(() => {
    fetchDashboard()
  }, [storeId])

  useEffect(() => {
    if (tab === 'inventory') fetchInventoryAlerts()
    if (tab === 'quality') fetchQualityRecords()
    if (tab === 'decision') fetchDecisions()
  }, [tab, storeId])

  async function fetchDashboard() {
    setLoading(true)
    try {
      const data = await apiClient.get<DashboardData>(`/api/v1/ops-flow/stores/${storeId}/dashboard`)
      setDashboard(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function fetchInventoryAlerts() {
    try {
      const data = await apiClient.get<{ alerts: InventoryAlert[] }>(
        `/api/v1/ops-flow/stores/${storeId}/inventory-alerts?unresolved_only=true`
      )
      setInvAlerts(data.alerts)
    } catch (e) { console.error(e) }
  }

  async function fetchQualityRecords() {
    try {
      const data = await apiClient.get<{ records: QualityRecord[] }>(
        `/api/v1/ops-flow/stores/${storeId}/quality-records?limit=20`
      )
      setQualityRecords(data.records)
    } catch (e) { console.error(e) }
  }

  async function fetchDecisions() {
    try {
      const data = await apiClient.get<{ decisions: Decision[] }>(
        `/api/v1/ops-flow/stores/${storeId}/decisions?limit=10`
      )
      setDecisions(data.decisions)
    } catch (e) { console.error(e) }
  }

  async function handleAcceptDecision(decisionId: string) {
    setAcceptingId(decisionId)
    try {
      await apiClient.post('/api/v1/ops-flow/decisions/accept', { decision_id: decisionId })
      await fetchDecisions()
    } catch (e) { console.error(e) }
    finally { setAcceptingId(null) }
  }

  async function handleOptimize() {
    try {
      await apiClient.post(`/api/v1/ops-flow/stores/${storeId}/optimize?brand_id=brand_001&lookback_hours=24`, {})
      await fetchDecisions()
      setTab('decision')
    } catch (e) { console.error(e) }
  }

  const tabs = [
    { key: 'dashboard', label: '驾驶舱' },
    { key: 'chain',     label: '联动事件' },
    { key: 'inventory', label: '库存预警' },
    { key: 'quality',   label: '菜品质检' },
    { key: 'decision',  label: '优化决策' },
  ] as const

  return (
    <div className={css.page}>
      <div className={css.header}>
        <h2 className={css.title}>OpsFlowAgent · 运营流程体</h2>
        <p className={css.subtitle}>出品链三层联动 · 订单异常 → 库存核查 → 质检复盘 · 1个事件驱动3层响应</p>
      </div>

      {/* Tab 导航 */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '8px 18px', border: 'none', background: 'transparent', cursor: 'pointer',
              fontSize: 14, fontWeight: tab === t.key ? 600 : 400,
              color: tab === t.key ? 'var(--accent)' : 'var(--text-secondary)',
              borderBottom: tab === t.key ? '2px solid var(--accent)' : '2px solid transparent',
              marginBottom: -1,
            }}
          >{t.label}</button>
        ))}
        <div style={{ flex: 1 }} />
        <button onClick={handleOptimize}
          style={{ padding: '6px 16px', background: 'var(--accent)', color: '#fff',
            border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer', marginBottom: 4 }}>
          生成优化建议
        </button>
      </div>

      {/* 驾驶舱 */}
      {tab === 'dashboard' && (
        loading ? <div className={css.loading}>加载中…</div> :
        dashboard ? (
          <>
            {/* KPI 四格 */}
            <div className={css.kpiRow}>
              <div className={`${css.kpiCard} ${dashboard.chain_events_24h.total > 0 ? css.kpiWarn : css.kpiOk}`}>
                <div className={css.kpiLabel}>24h 联动事件</div>
                <div className={css.kpiValue}>{dashboard.chain_events_24h.total}</div>
                <div className={css.kpiSub}>触发联动 {dashboard.chain_events_24h.total_linkages} 次</div>
              </div>
              <div className={`${css.kpiCard} ${dashboard.order_layer.anomaly_count_24h > 0 ? css.kpiCritical : css.kpiOk}`}>
                <div className={css.kpiLabel}>订单异常</div>
                <div className={css.kpiValue}>{dashboard.order_layer.anomaly_count_24h}</div>
                <div className={css.kpiSub}>预估损失 ¥{dashboard.order_layer.total_loss_yuan.toFixed(0)}</div>
              </div>
              <div className={`${css.kpiCard} ${dashboard.inventory_layer.unresolved_alerts > 0 ? css.kpiWarn : css.kpiOk}`}>
                <div className={css.kpiLabel}>库存预警（待处理）</div>
                <div className={css.kpiValue}>{dashboard.inventory_layer.unresolved_alerts}</div>
                <div className={css.kpiSub}>需立即补货</div>
              </div>
              <div className={`${css.kpiCard} ${dashboard.quality_layer.avg_score < 75 ? css.kpiCritical : dashboard.quality_layer?.avg_score < 85 ? css.kpiWarn : css.kpiOk}`}>
                <div className={css.kpiLabel}>今日质检均分</div>
                <div className={css.kpiValue}>{dashboard.quality_layer.avg_score || '—'}</div>
                <div className={css.kpiSub}>检测 {dashboard.quality_layer.inspections_24h} 次</div>
              </div>
            </div>

            <div className={css.layerGrid}>
              {/* 近期联动事件 */}
              <div className={`${css.section} ${css.chainEvents}`}>
                <div className={css.sectionHeader}>
                  <span className={css.sectionTitle}>🔗 近期出品链联动事件</span>
                  <button onClick={() => setTab('chain')} style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>查看全部</button>
                </div>
                <div className={css.sectionBody}>
                  {dashboard.recent_events.length === 0 ? (
                    <div className={css.emptyState}>暂无事件，出品链运营正常 ✓</div>
                  ) : (
                    <div className={css.eventList}>
                      {dashboard.recent_events.map((e, i) => (
                        <div key={i} className={css.eventItem}>
                          <div className={`${css.severityDot} ${e.severity === 'critical' ? css.dotCritical : e.severity === 'warning' ? css.dotWarning : css.dotInfo}`} />
                          <div style={{ flex: 1 }}>
                            <div className={css.eventTitle}>{e.title}</div>
                            <div className={css.eventMeta}>
                              <span className={css.layerBadge}>{SEVERITY_LABEL[e.severity] ?? e.severity}</span>
                              联动 {e.linkage_count} 层 · {new Date(e.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* 待处理决策 */}
              {dashboard.pending_decision.id && (
                <div className={`${css.section} ${css.chainEvents}`}>
                  <div className={css.sectionHeader}>
                    <span className={css.sectionTitle}>🎯 待处理优化决策</span>
                    <button onClick={() => setTab('decision')} style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>查看详情</button>
                  </div>
                  <div className={css.sectionBody}>
                    <div className={css.decisionCard}>
                      <div className={css.decisionTitle}>{dashboard.pending_decision.title}</div>
                      <div className={css.decisionMeta}>
                        <span className={`${css.priorityBadge} ${css[dashboard.pending_decision.priority?.toLowerCase() as 'p0'] || ''}`}>
                          {dashboard.pending_decision.priority}
                        </span>
                        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                          预计影响 ¥{dashboard.pending_decision.impact_yuan.toFixed(0)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : <div className={css.emptyState}>暂无数据</div>
      )}

      {/* 联动事件 Tab */}
      {tab === 'chain' && (
        <ChainEventsTab storeId={storeId} />
      )}

      {/* 库存预警 Tab */}
      {tab === 'inventory' && (
        <div className={css.section}>
          <div className={css.sectionHeader}>
            <span className={css.sectionTitle}>📦 库存预警（未处理）</span>
            <span className={css.sectionCount}>{invAlerts.length} 条</span>
          </div>
          <div className={css.sectionBody}>
            {invAlerts.length === 0
              ? <div className={css.emptyState}>当前无库存预警 ✓</div>
              : invAlerts.map(a => (
                <div key={a.id} className={css.alertItem}>
                  <div>
                    <div className={css.alertName}>{a.dish_name}</div>
                    <div className={css.alertDetail}>
                      库存 {a.current_qty} / 安全线 {a.safety_qty} 份 · 约 {a.predicted_stockout_hours.toFixed(1)}h 后售罄 · 建议补 {a.restock_qty_recommended} 份
                    </div>
                  </div>
                  <span className={`${css.riskBadge} ${a.risk_level === 'critical' ? css.riskCritical : a.risk_level === 'high' ? css.riskHigh : a.risk_level === 'medium' ? css.riskMedium : css.riskLow}`}>
                    {RISK_LABEL[a.risk_level] ?? a.risk_level}
                  </span>
                </div>
              ))
            }
          </div>
        </div>
      )}

      {/* 质检 Tab */}
      {tab === 'quality' && (
        <div className={css.section}>
          <div className={css.sectionHeader}>
            <span className={css.sectionTitle}>🔍 菜品质检记录</span>
            <span className={css.sectionCount}>{qualityRecords.length} 条</span>
          </div>
          <div className={css.sectionBody}>
            {qualityRecords.length === 0
              ? <div className={css.emptyState}>暂无质检记录</div>
              : qualityRecords.map(r => (
                <div key={r.id} className={css.alertItem}>
                  <div>
                    <div className={css.alertName}>{r.dish_name}</div>
                    <div className={css.alertDetail}>{r.ai_insight}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span className={`${css.riskBadge} ${r.status === 'fail' ? css.riskCritical : r.status === 'warning' ? css.riskHigh : css.riskOk}`}>
                      {r.quality_score.toFixed(0)} 分
                    </span>
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                      {r.status === 'pass' ? '✓ 合格' : r.status === 'warning' ? '⚠ 警告' : '✗ 不合格'}
                    </div>
                  </div>
                </div>
              ))
            }
          </div>
        </div>
      )}

      {/* 优化决策 Tab */}
      {tab === 'decision' && (
        <div>
          {decisions.length === 0
            ? <div className={css.emptyState}>暂无优化决策，点击「生成优化建议」触发分析</div>
            : decisions.map(d => (
              <div key={d.id} className={css.section} style={{ marginBottom: 16 }}>
                <div className={css.sectionHeader}>
                  <div className={css.sectionTitle}>
                    <span className={`${css.priorityBadge} ${css[d.priority.toLowerCase() as 'p0']}`}>{d.priority}</span>
                    {d.decision_title}
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    ¥{d.estimated_revenue_impact_yuan.toFixed(0)} 预期影响
                  </span>
                </div>
                <div className={css.sectionBody}>
                  <div className={css.decisionMeta}>
                    {d.involves_order && <span className={css.layerTag}>订单层</span>}
                    {d.involves_inventory && <span className={css.layerTag}>库存层</span>}
                    {d.involves_quality && <span className={css.layerTag}>质检层</span>}
                  </div>
                  <div className={css.recList}>
                    {(d.recommendations || []).map((r, i) => (
                      <div key={i} className={css.recItem}>
                        <span className={css.recBullet}>▸</span>
                        <span>[{LAYER_LABEL[r.layer] ?? r.layer}] {r.action}
                          {r.expected_yuan > 0 && ` · ¥${r.expected_yuan.toFixed(0)}`}
                        </span>
                      </div>
                    ))}
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--text-tertiary)', margin: '12px 0 0' }}>{d.ai_insight}</p>
                  {d.status === 'pending' && (
                    <button
                      className={css.acceptBtn}
                      disabled={acceptingId === d.id}
                      onClick={() => handleAcceptDecision(d.id)}
                    >
                      {acceptingId === d.id ? '处理中…' : '✓ 一键确认执行'}
                    </button>
                  )}
                  {d.status !== 'pending' && (
                    <div style={{ marginTop: 12, fontSize: 12, color: '#00b42a', fontWeight: 500 }}>
                      ✓ 已{d.status === 'accepted' ? '接受' : d.status === 'rejected' ? '拒绝' : '自动执行'}
                    </div>
                  )}
                </div>
              </div>
            ))
          }
        </div>
      )}
    </div>
  )
}

// 联动事件子组件
function ChainEventsTab({ storeId }: { storeId: string }) {
  const [events, setEvents] = useState<Array<{
    id: string; event_type: string; severity: string; source_layer: string
    title: string; description: string; impact_yuan: number
    linkage_count: number; resolved: boolean; created_at: string
  }>>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.get<{ events: typeof events }>(`/api/v1/ops-flow/stores/${storeId}/chain-events?limit=30`)
      .then((d: { events: typeof events }) => setEvents(d.events))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [storeId])

  if (loading) return <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-tertiary)' }}>加载中…</div>

  if (events.length === 0) return (
    <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
      暂无联动事件，出品链运营状态正常 ✓
    </div>
  )

  return (
    <div>
      {events.map(e => (
        <div key={e.id} style={{
          background: 'var(--bg-card)', borderRadius: 10, padding: '14px 18px',
          marginBottom: 10, border: '1px solid var(--border)',
          borderLeft: `3px solid ${e.severity === 'critical' ? '#f53f3f' : e.severity === 'warning' ? '#ff7d00' : '#165dff'}`
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{e.title}</span>
            <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
              {new Date(e.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
          {e.description && <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '0 0 8px' }}>{e.description}</p>}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
              源：{({ order: '订单层', inventory: '库存层', quality: '质检层' }[e.source_layer] ?? e.source_layer)}
            </span>
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
              联动 {e.linkage_count} 层
            </span>
            {e.impact_yuan > 0 && (
              <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'rgba(245,63,63,.08)', color: '#f53f3f' }}>
                ¥{e.impact_yuan.toFixed(0)} 影响
              </span>
            )}
            {e.resolved && (
              <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'rgba(0,180,42,.08)', color: '#00b42a' }}>✓ 已解决</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
