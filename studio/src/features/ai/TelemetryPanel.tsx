import { useEffect, useState } from 'react'
import type { Article, RankingSignal } from '../../types'
import { AgentRun, api } from '../../shared/api/client'

type Props = { onNotice: (notice: string) => void; onSimulationComplete: () => void }
type Telemetry = { engagement_score?: number; weight_delta?: number; insight?: string; seo_recommendations?: string[] }

export function TelemetryPanel({ onNotice, onSimulationComplete }: Props) {
  const [articles, setArticles] = useState<Article[]>([])
  const [articleId, setArticleId] = useState('')
  const [working, setWorking] = useState(false)
  const [signals, setSignals] = useState<RankingSignal[]>([])
  const [lastRun, setLastRun] = useState<AgentRun | null>(null)

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
      refreshSignals()
      onNotice(`Success: simulated 1,000 reader visits and re-ranked ${result.affected_leads_count} leads.`)
      onSimulationComplete()
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'Unable to simulate audience engagement.')
    } finally {
      setWorking(false)
    }
  }

  return (
    <section className="telemetry-panel">
      <div>
        <p className="eyebrow">AUDIENCE SIGNALS</p>
        <h2>Editorial telemetry</h2>
        <p>Aggregate performance only. Ranking adjustments are bounded and logged.</p>
        {signals.length ? (
          <div className="signal-list">
            {signals.map((signal) => (
              <small key={signal.topic_geo_key}>
                {signal.topic_geo_key}: {signal.weight_delta >= 0 ? '+' : ''}
                {signal.weight_delta.toFixed(2)} weight
              </small>
            ))}
          </div>
        ) : null}
      </div>
      <div className="telemetry-controls">
        <select value={articleId} onChange={(event) => setArticleId(event.target.value)} disabled={!articles.length}>
          <option value="">{articles.length ? 'Select a published story' : 'No published stories available'}</option>
          {articles.map((article) => (
            <option key={article.id} value={article.id}>
              {article.title}
            </option>
          ))}
        </select>
        <button onClick={() => void recalculate()} disabled={!articleId || working}>
          {working ? 'Calculating...' : 'Recalculate'}
        </button>
        <button className="simulate-visits" onClick={() => void simulate()} disabled={working}>
          {working ? (
            <>
              <span className="button-spinner" />
              Simulating...
            </>
          ) : (
            '⚡ Simulate 1,000 Reader Visits'
          )}
        </button>
      </div>
      {lastRun && <TelemetryResult run={lastRun} />}
    </section>
  )
}

export function TelemetryResult({ run }: { run: AgentRun }) {
  const result = run.output as Telemetry
  if (run.agent !== 'telemetry' || run.status !== 'succeeded') return null
  return (
    <div className="telemetry-result">
      <b>Latest signal</b>
      <span>Engagement {Math.round((result.engagement_score ?? 0) * 100)}%</span>
      <span>
        Ranking delta {(result.weight_delta ?? 0) > 0 ? '+' : ''}
        {result.weight_delta ?? 0}
      </span>
      <p>{result.insight}</p>
      {result.seo_recommendations?.length ? <small>SEO: {result.seo_recommendations.join(' · ')}</small> : null}
    </div>
  )
}
