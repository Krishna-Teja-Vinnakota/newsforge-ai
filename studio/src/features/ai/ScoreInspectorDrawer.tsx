import type { AiLead } from '../../shared/api/client'

export function ScoreInspectorDrawer({ lead, onClose }: { lead: AiLead | null; onClose: () => void }) {
  if (!lead) return null
  const base = lead.base_score ?? 0
  const delta = lead.learned_weight_delta ?? 0
  const trend = lead.trend_boost ?? 0
  const coverage = lead.coverage_adjustment ?? 0
  const final = lead.final_score ?? lead.priority_score ?? base + delta + trend + coverage
  const sources = Array.from(new Set((lead.trend_evidence ?? []).map((evidence) => evidence.source)))
  return (
    <div className="score-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        className="score-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="score-inspector-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button
          className="drawer-close px-3 py-1.5 rounded-lg text-sm font-medium transition-colors button-secondary"
          onClick={onClose}
          aria-label="Close score inspector"
        >
          Close
        </button>
        <p className="eyebrow">SELECTION AGENT</p>
        <h2 id="score-inspector-title">Score inspection</h2>
        <p className="drawer-headline">{lead.headline}</p>
        <dl className="score-breakdown">
          <div>
            <dt>Base urgency score</dt>
            <dd>{base.toFixed(2)}</dd>
          </div>
          <div>
            <dt>Telemetry delta</dt>
            <dd className={delta >= 0 ? 'positive' : 'negative'}>
              {delta >= 0 ? '+' : ''}
              {delta.toFixed(2)} {lead.geo} Weight
            </dd>
          </div>
          <div>
            <dt>Trend boost</dt>
            <dd className={trend > 0 ? 'positive' : ''}>+{trend.toFixed(2)}</dd>
          </div>
          <div>
            <dt>Coverage adjustment</dt>
            <dd className={coverage >= 0 ? 'positive' : 'negative'}>
              {coverage >= 0 ? '+' : ''}
              {coverage.toFixed(2)}
            </dd>
          </div>
          <div className="score-total">
            <dt>Final calculation</dt>
            <dd>{final.toFixed(2)}</dd>
            <code>
              final_score = {base.toFixed(2)} + {delta.toFixed(2)} + {trend.toFixed(2)} + {coverage.toFixed(2)}
            </code>
          </div>
        </dl>
        {sources.length > 0 && (
          <section className="trend-sources">
            <p>Matched trend sources</p>
            <div>
              {sources.map((source) => (
                <span className="trend-chip" key={source}>
                  {source.replaceAll('_', ' ')}
                </span>
              ))}
            </div>
          </section>
        )}
        <section className="editorial-guidance">
          <p>Editorial guidance</p>
          <blockquote>
            {lead.suggested_angle || lead.reasoning || 'The Selection Agent has not supplied a framing angle yet.'}
          </blockquote>
          {lead.why_now && <p className="why-now">Why now: {lead.why_now}</p>}
        </section>
      </aside>
    </div>
  )
}
