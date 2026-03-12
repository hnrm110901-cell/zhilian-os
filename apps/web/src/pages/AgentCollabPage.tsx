import { useEffect, useState } from 'react'
import { apiClient } from '../services/api'

interface ConflictItem {
  id: string
  agent_a: string
  agent_b: string
  severity: 'low' | 'medium' | 'high'
  description: string
  winning_agent: string | null
  yuan_saved: number
  created_at: string | null
}

interface DashboardData {
  brand_id: string
  period_days: number
  conflicts: {
    total: number
    resolved: number
    escalated: number
    high_severity: number
    total_yuan_saved: number
    top_conflict_pair: string | null
  }
  optimization: {
    total_runs: number
    total_input_recs: number
    total_output_recs: number
    dedup_rate_pct: number
  }
  recent_conflicts: ConflictItem[]
}

const AGENT_LABELS: Record<string, string> = {
  business_intel: '经营智能体',
  ops_flow:       '运营流程体',
  people:         '人力决策体',
  marketing:      '营销私域体',
  banquet:        '宴会管理体',
  dish_rd:        '菜研体',
  supplier:       '供应商体',
  compliance:     '合规证照体',
  fct:            '业财税体',
}

const SEVERITY_COLORS: Record<string, string> = {
  high:   '#f53f3f',
  medium: '#ff7d00',
  low:    '#86909c',
}

function SeverityBadge({ severity }: { severity: string }) {
  const color = SEVERITY_COLORS[severity] ?? '#86909c'
  const labels: Record<string, string> = { high: '高风险', medium: '中风险', low: '低风险' }
  return (
    <span style={{
      fontSize: 11, padding: '2px 8px', borderRadius: 10,
      background: color + '1a', color, fontWeight: 600,
    }}>
      {labels[severity] ?? severity}
    </span>
  )
}

function KpiCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div style={{
      background: 'var(--bg-card)', borderRadius: 12, padding: '16px 20px',
      border: '1px solid var(--border)',
    }}>
      <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: color ?? 'var(--text-primary)' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

export default function AgentCollabPage() {
  const [days, setDays] = useState(7)
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiClient.get<DashboardData>(
      `/api/v1/agent-collab/dashboard?brand_id=brand_001&days=${days}`
    )
      .then(setDashboard)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [days])

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 600, color: 'var(--text-primary)' }}>
            Agent 协同总线
          </h2>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
            多Agent冲突检测 · 优先级仲裁 · 全局优化 · 噪音过滤
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {[7, 14, 30].map(d => (
            <button key={d} onClick={() => setDays(d)} style={{
              padding: '5px 14px', border: '1px solid var(--border)',
              borderRadius: 6, fontSize: 13, cursor: 'pointer',
              background: days === d ? 'var(--accent)' : 'var(--bg-card)',
              color: days === d ? '#fff' : 'var(--text-secondary)',
            }}>近{d}天</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>加载中…</div>
      ) : !dashboard ? (
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>暂无数据</div>
      ) : (
        <>
          {/* KPI 总览 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
            <KpiCard
              label="冲突检测总数"
              value={dashboard.conflicts.total}
              sub={`已解决 ${dashboard.conflicts.resolved} / 升级 ${dashboard.conflicts.escalated}`}
            />
            <KpiCard
              label="高风险冲突"
              value={dashboard.conflicts.high_severity}
              color={dashboard.conflicts.high_severity > 0 ? '#f53f3f' : '#00b42a'}
              sub="需优先关注"
            />
            <KpiCard
              label="仲裁节省¥"
              value={`¥${(dashboard.conflicts.total_yuan_saved / 10000).toFixed(1)}万`}
              color="#00b42a"
              sub="冲突仲裁保护的潜在收益"
            />
            <KpiCard
              label="建议去重率"
              value={`${dashboard.optimization.dedup_rate_pct.toFixed(1)}%`}
              sub={`${dashboard.optimization.total_input_recs}条→${dashboard.optimization.total_output_recs}条`}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            {/* 最高频冲突对 */}
            <div style={{
              background: 'var(--bg-card)', borderRadius: 12, padding: '18px 24px',
              border: '1px solid var(--border)',
            }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>
                ⚡ 最高频冲突 Agent 对
              </div>
              {dashboard.conflicts.top_conflict_pair ? (
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--accent)', marginBottom: 8 }}>
                  {dashboard.conflicts.top_conflict_pair.split(' vs ').map((a, i) => (
                    <span key={a}>
                      {i > 0 && <span style={{ color: 'var(--text-tertiary)', margin: '0 8px', fontWeight: 400 }}>vs</span>}
                      <span>{AGENT_LABELS[a] ?? a}</span>
                    </span>
                  ))}
                </div>
              ) : (
                <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>近{days}天暂无冲突记录</div>
              )}
              <div style={{ marginTop: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
                  {[
                    { label: '优化运行次数', value: dashboard.optimization.total_runs },
                    { label: '处理建议总数', value: dashboard.optimization.total_input_recs },
                    { label: '输出建议数', value: dashboard.optimization.total_output_recs },
                  ].map(item => (
                    <div key={item.label} style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>{item.value}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>{item.label}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 协同原理说明 */}
            <div style={{
              background: 'var(--bg-card)', borderRadius: 12, padding: '18px 24px',
              border: '1px solid var(--border)',
            }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 14 }}>
                🧠 协同总线工作原理
              </div>
              {[
                { icon: '🔍', step: '冲突检测', desc: '扫描跨Agent建议中的资源争抢/财务约束/矛盾动作' },
                { icon: '⚖️', step: '优先级仲裁', desc: '财务约束→合规风险→Agent优先级→¥影响大小' },
                { icon: '🗑️', step: '去重抑制', desc: '字符2-gram相似度合并重复建议，过滤低影响噪音' },
                { icon: '📊', step: '全局排序', desc: '¥影响×置信度降序，确保最重要的建议排在最前' },
              ].map(item => (
                <div key={item.step} style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
                  <span style={{ fontSize: 16, flexShrink: 0 }}>{item.icon}</span>
                  <div>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{item.step}: </span>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{item.desc}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 近期冲突列表 */}
          <div style={{
            marginTop: 16,
            background: 'var(--bg-card)', borderRadius: 12, padding: '18px 24px',
            border: '1px solid var(--border)',
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>
              📋 近期冲突记录（最近{days}天 · 最多10条）
            </div>
            {dashboard.recent_conflicts.length === 0 ? (
              <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
                近{days}天无冲突记录，Agent协同良好 ✅
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {dashboard.recent_conflicts.map(cf => (
                  <div key={cf.id} style={{
                    display: 'flex', alignItems: 'center', gap: 16,
                    padding: '12px 16px', borderRadius: 8,
                    background: 'var(--bg)', border: '1px solid var(--border)',
                  }}>
                    <SeverityBadge severity={cf.severity} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                        {AGENT_LABELS[cf.agent_a] ?? cf.agent_a}
                        <span style={{ color: 'var(--text-tertiary)', margin: '0 6px' }}>vs</span>
                        {AGENT_LABELS[cf.agent_b] ?? cf.agent_b}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                        {cf.description}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      {cf.winning_agent && (
                        <div style={{ fontSize: 12, color: '#00b42a', fontWeight: 500 }}>
                          ✅ {AGENT_LABELS[cf.winning_agent] ?? cf.winning_agent} 胜出
                        </div>
                      )}
                      {cf.yuan_saved > 0 && (
                        <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                          保护 ¥{cf.yuan_saved.toFixed(0)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
