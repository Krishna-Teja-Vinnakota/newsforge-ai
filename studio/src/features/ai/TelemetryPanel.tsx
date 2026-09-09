import { useEffect, useState } from 'react'
import type { Article } from '../../types'
import { AgentRun, api } from '../../shared/api/client'

type Props = { onRun: (run: AgentRun) => void; onNotice: (notice: string) => void }
type Telemetry = { engagement_score?: number; weight_delta?: number; insight?: string; seo_recommendations?: string[] }

export function TelemetryPanel({ onRun, onNotice }: Props) {
  const [articles, setArticles] = useState<Article[]>([]), [articleId, setArticleId] = useState(''), [working, setWorking] = useState(false)
  useEffect(() => { void api.myArticles(1, 50).then(result => { const published = result.items.filter(article => article.status === 'published'); setArticles(published); setArticleId(published[0]?.id ?? '') }).catch(error => onNotice(error.message)) }, [])
  const recalculate = async () => { if (!articleId) return; try { setWorking(true); const run = await api.recalculateTelemetry(articleId); onRun(run); onNotice('Telemetry recalculated and the bounded ranking signal was updated.') } catch (error) { onNotice(error instanceof Error ? error.message : 'Unable to calculate telemetry.') } finally { setWorking(false) } }
  return <section className="telemetry-panel"><div><p className="eyebrow">AUDIENCE SIGNALS</p><h2>Editorial telemetry</h2><p>Aggregate performance only. Ranking adjustments are bounded and logged.</p></div><div className="telemetry-controls"><select value={articleId} onChange={event => setArticleId(event.target.value)} disabled={!articles.length}><option value="">{articles.length ? 'Select a published story' : 'No published stories available'}</option>{articles.map(article => <option key={article.id} value={article.id}>{article.title}</option>)}</select><button onClick={() => void recalculate()} disabled={!articleId || working}>{working ? 'Calculating…' : 'Recalculate'}</button></div></section>
}

export function TelemetryResult({ run }: { run: AgentRun }) {
  const result = run.output as Telemetry
  if (run.agent !== 'telemetry' || run.status !== 'succeeded') return null
  return <div className="telemetry-result"><b>Latest signal</b><span>Engagement {Math.round((result.engagement_score ?? 0) * 100)}%</span><span>Ranking delta {(result.weight_delta ?? 0) > 0 ? '+' : ''}{result.weight_delta ?? 0}</span><p>{result.insight}</p>{result.seo_recommendations?.length ? <small>SEO: {result.seo_recommendations.join(' · ')}</small> : null}</div>
}
