import type { AiLead } from '../../shared/api/client'

export function ScoreInspectorDrawer({ lead, onClose }: { lead: AiLead | null; onClose: () => void }) {
  if (!lead) return null
  const base = lead.base_score ?? 0
  const delta = lead.learned_weight_delta ?? 0
  const final = lead.final_score || lead.priority_score || base + delta
  return <div className="score-drawer-backdrop" role="presentation" onMouseDown={onClose}><aside className="score-drawer" role="dialog" aria-modal="true" aria-labelledby="score-inspector-title" onMouseDown={event => event.stopPropagation()}><button className="drawer-close px-3 py-1.5 rounded-lg text-sm font-medium transition-colors button-secondary" onClick={onClose} aria-label="Close score inspector">Close</button><p className="eyebrow">SELECTION AGENT</p><h2 id="score-inspector-title">Score inspection</h2><p className="drawer-headline">{lead.headline}</p><dl className="score-breakdown"><div><dt>Base urgency score</dt><dd>{base.toFixed(2)}</dd></div><div><dt>Telemetry delta</dt><dd className={delta >= 0 ? 'positive' : 'negative'}>{delta >= 0 ? '+' : ''}{delta.toFixed(2)} {lead.geo} Weight</dd></div><div className="score-total"><dt>Final calculation</dt><dd>{final.toFixed(2)}</dd><code>final_score = {base.toFixed(2)} + {delta.toFixed(2)}</code></div></dl><section className="editorial-guidance"><p>Editorial guidance</p><blockquote>{lead.suggested_angle || lead.reasoning || 'The Selection Agent has not supplied a framing angle yet.'}</blockquote></section></aside></div>
}
