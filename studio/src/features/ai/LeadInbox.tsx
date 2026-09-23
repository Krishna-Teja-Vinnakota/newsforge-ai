import { useEffect, useState } from 'react'
import type { AiLead } from '../../shared/api/client'

const pageSize = 6

function RankShiftBadge({ lead }: { lead: AiLead }) {
  const previous = lead.previous_rank
  const current = lead.current_rank
  if (previous === null || current === null || previous === current)
    return <span className="rank-shift rank-flat">--</span>
  const difference = Math.abs(previous - current)
  return current < previous ? (
    <span className="rank-shift rank-up">▲ Up {difference}</span>
  ) : (
    <span className="rank-shift rank-down">▼ Down {difference}</span>
  )
}

export function LeadInbox({
  leads,
  draftingLeadId,
  onRefresh,
  onReject,
  onApprove,
  onInspect,
}: {
  leads: AiLead[]
  draftingLeadId: string | null
  onRefresh: () => void
  onReject: (lead: AiLead) => void
  onApprove: (lead: AiLead) => void
  onInspect: (lead: AiLead) => void
}) {
  const [page, setPage] = useState(1)
  const pages = Math.max(1, Math.ceil(leads.length / pageSize))
  const visibleLeads = leads.slice((page - 1) * pageSize, page * pageSize)
  useEffect(() => setPage((current) => Math.min(current, pages)), [pages])
  return (
    <section className="ai-leads">
      <header>
        <div>
          <p className="eyebrow">2. CURATE & SELECTION DESK</p>
          <h2>Lead inbox</h2>
        </div>
        <button
          className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors button-secondary"
          onClick={onRefresh}
        >
          Refresh
        </button>
      </header>
      {leads.length ? (
        visibleLeads.map((lead) => {
          const rankChanged =
            lead.previous_rank !== null && lead.current_rank !== null && lead.previous_rank !== lead.current_rank
          const score = lead.final_score ?? lead.priority_score ?? 0
          return (
            <article className={rankChanged ? 'lead-rank-changed' : ''} key={`lead-${lead.id}`}>
              <div>
                <div className="lead-headline">
                  <b>{lead.headline}</b>
                  <RankShiftBadge lead={lead} />
                  {lead.origin === 'trend_feed' && <span className="origin-badge">From trends</span>}
                  {(lead.trend_boost ?? 0) > 0 && <span className="trend-chip">Trending</span>}
                  {lead.suggested_format && lead.suggested_format !== 'standard' && (
                    <span className="format-badge">{lead.suggested_format}</span>
                  )}
                  <button
                    className="score-pill"
                    onClick={() => onInspect(lead)}
                    aria-label={`Inspect score for ${lead.headline}`}
                  >
                    Score {score.toFixed(2)}
                  </button>
                </div>
                <small>
                  {lead.topic} · rank {lead.current_rank ?? '—'}
                </small>
                <p>{lead.suggested_angle || lead.reasoning || 'Awaiting selection run.'}</p>
              </div>
              <span className={`lead-status status-${lead.status}`}>{lead.status}</span>
              {lead.status === 'pending' && (
                <footer>
                  <button
                    className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors button-danger"
                    onClick={() => onReject(lead)}
                  >
                    Reject
                  </button>
                  <button
                    className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors button-primary"
                    onClick={() => onApprove(lead)}
                    disabled={draftingLeadId === lead.id}
                  >
                    {draftingLeadId === lead.id ? 'Drafting…' : 'Approve & draft'}
                  </button>
                </footer>
              )}
            </article>
          )
        })
      ) : (
        <p className="ai-empty">Run Selection Agent with approved intake leads to populate this inbox.</p>
      )}
      {leads.length > pageSize && (
        <footer className="lead-pagination">
          <button type="button" disabled={page === 1} onClick={() => setPage((current) => current - 1)}>
            Previous
          </button>
          <b>
            Page {page} of {pages}
          </b>
          <button type="button" disabled={page === pages} onClick={() => setPage((current) => current + 1)}>
            Next
          </button>
        </footer>
      )}
    </section>
  )
}
