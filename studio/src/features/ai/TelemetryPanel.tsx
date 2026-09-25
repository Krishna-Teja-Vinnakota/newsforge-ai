import { useEffect, useMemo, useState } from 'react'
import { Activity, BarChart3, ChevronDown, ChevronRight, Zap } from 'lucide-react'
import type { Article, RankingSignal } from '../../types'
import { AgentRun, api } from '../../shared/api/client'

type Props = { onNotice: (notice: string) => void; onSimulationComplete: () => void }
type Telemetry = {
  engagement_score?: number
  weight_delta?: number
  insight?: string
  seo_recommendations?: string[]
}

function formatAgo(iso?: string) {
  if (!iso) return 'just now'
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins === 0) return 'just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.round(mins / 60)}h ago`
}

export function TelemetryPanel({ onNotice, onSimulationComplete }: Props) {
  const [articles, setArticles] = useState<Article[]>([])
  const [articleId, setArticleId] = useState('')
  const [working, setWorking] = useState(false)
  const [signals, setSignals] = useState<RankingSignal[]>([])
  const [lastRun, setLastRun] = useState<AgentRun | null>(null)
  const [simulated, setSimulated] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [feedbackExpanded, setFeedbackExpanded] = useState(false)

  useEffect(() => {
    void api
      .myArticles(1, 50)
      .then((result) => {
        const published = result.items.filter((article) => article.status === 'published')
        setArticles(published)
        setArticleId(published[0]?.id ?? '')
      })
      .catch((error) => onNotice(error.message))
  }, [])

  const refreshSignals = () => {
    void api
      .rankingSignals()
      .then(setSignals)
      .catch((error) => onNotice(error.message))
  }
  useEffect(refreshSignals, [])

  const recalculate = async () => {
    if (!articleId) return
    try {
      setWorking(true)
      const run = await api.recalculateTelemetry(articleId)
      setLastRun(run)
      setSimulated(false)
      setFeedbackExpanded(true)
      refreshSignals()
      onNotice('Telemetry recalculated and the bounded ranking signal was updated.')
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'Unable to calculate telemetry.')
    } finally {
      setWorking(false)
    }
  }

  const simulate = async () => {
    try {
      setWorking(true)
      const result = await api.simulateTelemetry()
      setSimulated(true)
      setFeedbackExpanded(true)
      refreshSignals()
      onNotice(`Success: simulated 1,000 reader visits and re-ranked ${result.affected_leads_count} leads.`)
      onSimulationComplete()
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'Unable to simulate audience engagement.')
    } finally {
      setWorking(false)
    }
  }

  const priorityKey = useMemo(() => {
    if (!signals.length) return null
    return [...signals].sort((a, b) => Math.abs(b.weight_delta) - Math.abs(a.weight_delta))[0]?.topic_geo_key ?? null
  }, [signals])

  const latestSignal = signals[0]
  const telemetry = (lastRun?.output as Telemetry | undefined) ?? null
  const engagement = telemetry?.engagement_score ?? 0.48
  const weightDelta = telemetry?.weight_delta ?? 0.12
  const ctr = Math.min(9.9, Math.max(1.2, engagement * 10))
  const lift = Math.max(4, Math.round(engagement * 70 + Math.abs(weightDelta) * 80))
  const confidence = Math.min(99, Math.max(72, Math.round((latestSignal?.confidence ?? 0.9) * 100)))
  const velocityFrom = Math.max(0.4, engagement - 0.05).toFixed(2)
  const velocityTo = Math.min(0.99, engagement + Math.abs(weightDelta)).toFixed(2)

  return (
    <section className={`telemetry-panel ai-panel-card${expanded ? ' is-expanded' : ' is-collapsed'}`}>
      <div className="telemetry-top">
        <div className="telemetry-title-block">
          <span className="ai-stage-pill">Audience signals & real-time telemetry</span>
          <div className="telemetry-intro">
            <h2>Editorial telemetry & simulation</h2>
            {!expanded && (
              <p>Aggregate performance only. Expand to manage channel coefficients and simulation sandbox.</p>
            )}
          </div>
        </div>
        <div className="telemetry-top-actions">
          <span className="telemetry-bound-pill">
            <span className="pipeline-dot" aria-hidden />
            Telemetry Bounded (±0.50 cap)
          </span>
          <button
            type="button"
            className="panel-collapse-btn"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse editorial telemetry' : 'Expand editorial telemetry'}
          >
            {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
            {expanded ? 'Collapse' : 'Expand'}
          </button>
        </div>
      </div>

      {expanded && (
        <>
          <p className="telemetry-copy">
            Aggregate performance only. Dynamic ranking adjustments are bounded, calibrated, and logged in real-time
            across regional channels.
          </p>

          <div className="channel-coefficients">
            <div className="channel-coefficients-head">
              <span>Channel coefficients</span>
              <small>Autotuned {formatAgo(latestSignal?.last_updated)}</small>
            </div>
            <div className="signal-list">
              {signals.length ? (
                signals.map((signal) => {
                  const positive = signal.weight_delta > 0
                  const zero = Math.abs(signal.weight_delta) < 0.005
                  return (
                    <span
                      key={signal.topic_geo_key}
                      className={`signal-chip${positive ? ' is-positive' : ''}${zero ? ' is-zero' : ''}${
                        signal.topic_geo_key === priorityKey ? ' is-priority' : ''
                      }`}
                    >
                      {signal.topic_geo_key}: {signal.weight_delta >= 0 ? '+' : ''}
                      {signal.weight_delta.toFixed(2)} weight
                      {signal.topic_geo_key === priorityKey ? <em>Priority</em> : null}
                    </span>
                  )
                })
              ) : (
                <span className="signal-chip is-zero">No calibrated channels yet</span>
              )}
            </div>
          </div>

          <div className="telemetry-sandbox">
            <div className="telemetry-sandbox-controls">
              <select
                value={articleId}
                onChange={(event) => setArticleId(event.target.value)}
                disabled={!articles.length}
              >
                <option value="">{articles.length ? 'Select a published story' : 'No published stories available'}</option>
                {articles.map((article) => (
                  <option key={article.id} value={article.id}>
                    {article.title}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="telemetry-recalc"
                onClick={() => void recalculate()}
                disabled={!articleId || working}
              >
                {working ? 'Calculating…' : 'Recalculate'}
              </button>
              <button type="button" className="simulate-visits" onClick={() => void simulate()} disabled={working}>
                {working ? (
                  <>
                    <span className="button-spinner" />
                    Simulating…
                  </>
                ) : (
                  <>
                    <Zap size={15} />
                    Simulate 1,000 Reader Visits
                  </>
                )}
              </button>
            </div>

            <div className={`simulation-feedback${feedbackExpanded ? ' is-expanded' : ' is-collapsed'}`}>
              <div className="simulation-feedback-head">
                <div>
                  <span className="feedback-kicker">Projected simulation feedback</span>
                  <span className={`feedback-ready${simulated || lastRun ? ' is-live' : ''}`}>
                    <span className="schedule-dot" aria-hidden />
                    {simulated || lastRun ? 'Ready · last run applied' : 'Ready to execute'}
                  </span>
                </div>
                <div className="simulation-feedback-actions">
                  <span className="trajectory-pill">
                    <Activity size={13} />
                    Trajectory: +{(Math.abs(weightDelta) * 100 + 8).toFixed(1)}% rank acceleration
                  </span>
                  <button
                    type="button"
                    className="panel-collapse-btn"
                    onClick={() => setFeedbackExpanded((value) => !value)}
                    aria-expanded={feedbackExpanded}
                    aria-label={feedbackExpanded ? 'Collapse simulation feedback' : 'Expand simulation feedback'}
                  >
                    {feedbackExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    {feedbackExpanded ? 'Collapse' : 'Expand'}
                  </button>
                </div>
              </div>

              {feedbackExpanded && (
                <>
                  <div className="simulation-metrics">
                    <article>
                      <span>Projected CTR</span>
                      <b>
                        {ctr.toFixed(1)}% <small>+{(ctr * 0.25).toFixed(1)}%</small>
                      </b>
                    </article>
                    <article>
                      <span>Audience Lift</span>
                      <b>+{lift.toFixed(1)}k est. imp.</b>
                    </article>
                    <article>
                      <span>Confidence Interval</span>
                      <b>
                        {confidence.toFixed(1)}% <em>High</em>
                      </b>
                    </article>
                    <article>
                      <span>Velocity Curve</span>
                      <b className="velocity-metric">
                        <BarChart3 size={16} />
                        {velocityFrom} → {velocityTo}
                      </b>
                    </article>
                  </div>

                  {telemetry?.insight ? <p className="simulation-insight">{telemetry.insight}</p> : null}
                  {telemetry?.seo_recommendations?.length ? (
                    <small className="simulation-seo">SEO: {telemetry.seo_recommendations.join(' · ')}</small>
                  ) : null}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  )
}
