import { useEffect, useMemo, useState } from 'react'
import { Clock3, RefreshCw } from 'lucide-react'
import { AiLead, api, type HealthStatus, type TrendStatus } from '../../shared/api/client'
import { LeadRanker } from './LeadRanker'
import { LeadInbox } from './LeadInbox'
import { ScoreInspectorDrawer } from './ScoreInspectorDrawer'
import { TelemetryPanel } from './TelemetryPanel'
import './AiDesk.css'
import './LeadInbox.css'
import './DraftAction.css'
import './AiDeskPanels.css'

export function AiDesk({ onDraftCreated }: { onDraftCreated?: (articleId: string) => void }) {
  const [leads, setLeads] = useState<AiLead[]>([])
  const [notice, setNotice] = useState('')
  const [draftingLeadId, setDraftingLeadId] = useState<string | null>(null)
  const [resettingDemo, setResettingDemo] = useState(false)
  const [inspectedLead, setInspectedLead] = useState<AiLead | null>(null)
  const [updatedAt, setUpdatedAt] = useState(() => Date.now())
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [trendStatus, setTrendStatus] = useState<TrendStatus | null>(null)

  const load = () => {
    void api
      .aiLeads()
      .then((items) => {
        setLeads(items)
        setUpdatedAt(Date.now())
      })
      .catch((error) => setNotice(error.message))
  }
  useEffect(load, [])

  useEffect(() => {
    const loadOperationalStatus = () => {
      void Promise.all([api.health(), api.trendStatus()])
        .then(([nextHealth, nextTrends]) => {
          setHealth(nextHealth)
          setTrendStatus(nextTrends)
        })
        .catch((error) => setNotice(error instanceof Error ? error.message : 'Unable to load pipeline status.'))
    }
    loadOperationalStatus()
    const timer = window.setInterval(loadOperationalStatus, 30_000)
    return () => window.clearInterval(timer)
  }, [])

  const decide = async (lead: AiLead, decision: 'reject') => {
    try {
      await api.decideLead(lead.id, decision)
      setNotice(`Lead ${decision}ed.`)
      load()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to update lead.')
    }
  }

  const draftLead = async (lead: AiLead) => {
    try {
      setDraftingLeadId(lead.id)
      const run = await api.produceDraft({
        headline: lead.headline,
        topic: lead.topic,
        context: lead.suggested_angle || lead.reasoning || '',
        target_platforms: ['web', 'twitter', 'newsletter'],
        source_lead_id: lead.id,
      })
      const articleId = (run.output as { article?: { id: string } }).article?.id
      setNotice(
        run.used_fallback
          ? 'The AI model did not respond, so this draft is a basic template. Opening it in Stories…'
          : 'Article draft generated successfully! Opening it in Stories…'
      )
      load()
      if (articleId) onDraftCreated?.(articleId)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to generate article draft.')
    } finally {
      setDraftingLeadId(null)
    }
  }

  const resetDemo = async () => {
    if (!window.confirm('Reset demo leads and telemetry?')) return
    try {
      setResettingDemo(true)
      const result = await api.resetDemoData()
      setNotice(result.message)
      load()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to reset the demo scenario.')
    } finally {
      setResettingDemo(false)
    }
  }

  const sortedLeads = useMemo(
    () => [...leads].sort((a, b) => (a.current_rank ?? 99) - (b.current_rank ?? 99)),
    [leads]
  )
  const pendingCount = leads.filter((lead) => lead.status === 'pending').length
  const minutesAgo = Math.max(0, Math.round((Date.now() - updatedAt) / 60000))
  const pipelineHealthy = health?.status === 'ok' && health.features.ai_agents === true
  const pipelineLabel = health === null
    ? 'Checking pipeline…'
    : pipelineHealthy
      ? 'Pipeline Healthy'
      : health.status === 'degraded'
        ? 'Pipeline Degraded'
        : 'AI Agents Disabled'
  const healthyTrendSources = trendStatus?.sources.filter((source) =>
    ['success', 'success_empty'].includes(source.status)
  ).length ?? 0
  const trendGeo = trendStatus?.sources[0]?.geo
  const trendSyncLabel = trendStatus === null
    ? 'Checking trend feeds…'
    : trendStatus.status === 'disabled'
      ? 'Trend feeds: Disabled'
      : trendStatus.sources.length === 0
        ? 'Trend feeds: Not configured'
        : `${trendGeo ?? 'Configured'} trend feeds: ${healthyTrendSources}/${trendStatus.sources.length} healthy`
  const nextTrendRefreshAt = trendStatus?.sources
    .map((source) => source.next_refresh_at)
    .filter((value): value is string => Boolean(value))
    .sort()[0] ?? null

  return (
    <section className="ai-desk">
      <header className="ai-desk-header">
        <div className="ai-desk-header-copy">
          <p className="eyebrow">PHASE 7 · AI NEWSROOM</p>
          <div className="ai-desk-title-row">
            <h1>AI editorial desk</h1>
            <span className={`pipeline-badge${pipelineHealthy ? '' : ' is-degraded'}`}>
              <span className="pipeline-dot" aria-hidden />
              {pipelineLabel}
            </span>
          </div>
        </div>
        <div className="ai-desk-header-actions">
          <span className="ai-desk-updated">
            <Clock3 size={14} />
            Updated {minutesAgo === 0 ? 'just now' : `${minutesAgo}m ago`}
          </span>
          <button type="button" className="ai-desk-reset" onClick={() => void resetDemo()} disabled={resettingDemo}>
            <RefreshCw size={14} className={resettingDemo ? 'is-spinning' : undefined} />
            {resettingDemo ? 'Resetting…' : 'Reset Demo Scenario'}
          </button>
        </div>
      </header>

      {(notice || leads.length > 0) && (
        <div className="ai-desk-banner">
          <div className="ai-desk-banner-copy">
            <span className="ai-desk-banner-dot" aria-hidden />
            <p>
              {notice ||
                `Selection Agent ranked ${leads.length} lead${leads.length === 1 ? '' : 's'} in the inbox based on real-time editorial signals${
                  pendingCount ? ` · ${pendingCount} pending review` : ''
                }.`}
            </p>
          </div>
          <span className="desk-sync-pill">{trendSyncLabel}</span>
        </div>
      )}

      <LeadRanker
        onRanked={load}
        onNotice={setNotice}
        nextTrendRefreshAt={nextTrendRefreshAt}
        trendRefreshStatus={trendStatus?.status ?? 'checking'}
      />
      <LeadInbox
        leads={sortedLeads}
        draftingLeadId={draftingLeadId}
        onRefresh={load}
        onReject={(lead) => void decide(lead, 'reject')}
        onApprove={(lead) => void draftLead(lead)}
        onInspect={setInspectedLead}
      />
      <TelemetryPanel onNotice={setNotice} onSimulationComplete={load} />
      <ScoreInspectorDrawer lead={inspectedLead} onClose={() => setInspectedLead(null)} />
    </section>
  )
}
