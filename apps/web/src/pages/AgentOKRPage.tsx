import { useEffect, useState } from 'react'
import { apiClient } from '../services/api'

interface AgentOKRSummary {
  overall: {
    total_recommendations: number
    overall_adoption_rate: number | null
    overall_adoption_rate_pct: number | null
    total_recommendation_yuan: number
  }
  agents: Array<{
    agent_name: string
    total_recommendations: number
    adopted_count: number
    rejected_count: number
    adoption_rate: number | null
    adoption_rate_pct: number | null
    adoption_target_pct: number
    okr_adoption: string
    avg_prediction_error_pct: number | null
    accuracy_target_pct: number | null
    okr_accuracy: string
    avg_response_latency_seconds: number | null
    latency_target_seconds: number | null
    okr_latency: string
    total_recommendation_yuan: number
  }>
}

const AGENT_LABELS: Record<string, string> = {
  business_intel: 'BusinessIntelAgent · 经营智能体',
  ops_flow:       'OpsFlowAgent · 运营流程体',
  people:         'PeopleAgent · 人力决策体',
  marketing:      'MarketingAgent · 营销私域体',
  banquet:        'BanquetAgent · 宴会管理体',
  dish_rd:        'DishRdAgent · 菜研体',
  supplier:       'SupplierAgent · 供应商体',
  compliance:     'ComplianceAgent · 合规证照体',
  fct:            'FctAgent · 业财税体',
}

function OKRBadge({ label }: { label: string }) {
  const color = label.includes('✅') ? '#00b42a'
    : label.includes('❌') ? '#f53f3f'
    : '#86909c'
  return (
    <span style={{
      fontSize: 12, padding: '2px 8px', borderRadius: 10,
      background: color + '18', color, fontWeight: 500,
    }}>
      {label}
    </span>
  )
}

function AdoptionBar({ rate, target }: { rate: number | null; target: number }) {
  const pct = rate ?? 0
  const targetPct = target
  const barColor = pct >= targetPct ? '#00b42a' : pct >= targetPct * 0.8 ? '#ff7d00' : '#f53f3f'
  return (
    <div style={{ position: 'relative' }}>
      <div style={{ height: 8, background: 'var(--border)', borderRadius: 4, overflow: 'visible' }}>
        <div style={{
          height: '100%', width: `${Math.min(pct, 100)}%`,
          background: barColor, borderRadius: 4, transition: 'width .4s',
        }} />
        {/* 目标线 */}
        <div style={{
          position: 'absolute', top: -3, left: `${targetPct}%`,
          width: 2, height: 14, background: '#86909c', borderRadius: 1,
        }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3, fontSize: 11, color: 'var(--text-tertiary)' }}>
        <span style={{ color: barColor, fontWeight: 600 }}>{rate !== null ? `${pct.toFixed(1)}%` : '—'}</span>
        <span>目标 {targetPct}%</span>
      </div>
    </div>
  )
}

export default function AgentOKRPage() {
  const [days, setDays] = useState(7)
  const [summary, setSummary] = useState<AgentOKRSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiClient.get<AgentOKRSummary>(
      `/api/v1/agent-okr/summary?brand_id=brand_001&days=${days}`
    )
      .then(setSummary)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [days])

  const metCount = summary?.agents.filter(a => a.okr_adoption.includes('✅')).length ?? 0
  const totalCount = summary?.agents.length ?? 0

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 600, color: 'var(--text-primary)' }}>
            Agent OKR 达成看板
          </h2>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
            以交付结果为导向 · 每个 Agent 的量化 KPI · 来源于屯象OS Agent战略分析
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

      {/* 总览卡片 */}
      {!loading && summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
          {[
            { label: '总建议次数', value: summary.overall.total_recommendations, unit: '次' },
            { label: '整体采纳率', value: summary.overall.overall_adoption_rate_pct?.toFixed(1) ?? '—', unit: '%' },
            { label: '总预期影响', value: `¥${(summary.overall.total_recommendation_yuan/10000).toFixed(1)}万`, unit: '' },
            { label: 'OKR达标 Agent', value: `${metCount}/${totalCount}`, unit: '个' },
          ].map(item => (
            <div key={item.label} style={{ background: 'var(--bg-card)', borderRadius: 12, padding: '16px 20px', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 6 }}>{item.label}</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>
                {item.value}<span style={{ fontSize: 13, fontWeight: 400, marginLeft: 2 }}>{item.unit}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Agent OKR 表格 */}
      {loading ? (
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>加载中…</div>
      ) : !summary || summary.agents.length === 0 ? (
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
          暂无数据。请先在各 Agent 中记录建议（调用 /api/v1/agent-okr/log），并等待用户响应。
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {summary.agents.map(a => (
            <div key={a.agent_name} style={{
              background: 'var(--bg-card)', borderRadius: 12, padding: '18px 24px',
              border: '1px solid var(--border)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                <div>
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {AGENT_LABELS[a.agent_name] ?? a.agent_name}
                  </span>
                  <span style={{ marginLeft: 10, fontSize: 12, color: 'var(--text-tertiary)' }}>
                    {a.total_recommendations} 次推送 · {a.adopted_count} 接受 / {a.rejected_count} 拒绝 · ¥{a.total_recommendation_yuan.toFixed(0)}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <OKRBadge label={a.okr_adoption} />
                  <OKRBadge label={a.okr_accuracy} />
                  {a.latency_target_seconds && <OKRBadge label={a.okr_latency} />}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24 }}>
                {/* 采纳率 */}
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 8 }}>建议采纳率</div>
                  <AdoptionBar rate={a.adoption_rate_pct} target={a.adoption_target_pct} />
                </div>

                {/* 预测准确度 */}
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 8 }}>预测误差（越小越好）</div>
                  <div style={{ fontSize: 20, fontWeight: 600,
                    color: a.avg_prediction_error_pct === null ? 'var(--text-tertiary)'
                      : a.avg_prediction_error_pct <= (a.accuracy_target_pct ?? 10) ? '#00b42a' : '#f53f3f'
                  }}>
                    {a.avg_prediction_error_pct !== null ? `±${a.avg_prediction_error_pct.toFixed(1)}%` : '—'}
                  </div>
                  {a.accuracy_target_pct && (
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>
                      目标 ±{a.accuracy_target_pct}%
                    </div>
                  )}
                </div>

                {/* 响应时效 */}
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 8 }}>平均响应时效</div>
                  <div style={{ fontSize: 20, fontWeight: 600,
                    color: !a.avg_response_latency_seconds || !a.latency_target_seconds ? 'var(--text-tertiary)'
                      : a.avg_response_latency_seconds <= a.latency_target_seconds ? '#00b42a' : '#f53f3f'
                  }}>
                    {a.avg_response_latency_seconds !== null
                      ? a.avg_response_latency_seconds < 60
                        ? `${a.avg_response_latency_seconds}s`
                        : `${(a.avg_response_latency_seconds / 60).toFixed(0)}min`
                      : '—'}
                  </div>
                  {a.latency_target_seconds && (
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>
                      目标 &lt;{a.latency_target_seconds < 3600
                        ? `${a.latency_target_seconds / 60}分钟`
                        : `${a.latency_target_seconds / 3600}小时`}
                    </div>
                  )}
                  {!a.latency_target_seconds && (
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>无时效要求</div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
