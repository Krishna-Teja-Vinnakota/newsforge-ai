import type { AiLead } from '../../shared/api/client'

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
        leads.map((lead) => {
          const rankChanged =
            lead.previous_rank !== null && lead.current_rank !== null && lead.previous_rank !== lead.current_rank
          const score = lead.final_score || lead.priority_score || 0
          return (
            <article className={rankChanged ? 'lead-rank-changed' : ''} key={`lead-${lead.id}`}>
              <div>
                <div className="lead-headline">
                  <b>{lead.headline}</b>
                  <RankShiftBadge lead={lead} />
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
    </section>
  )
}
