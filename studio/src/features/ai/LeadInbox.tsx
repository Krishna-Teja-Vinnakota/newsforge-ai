import { useEffect, useMemo, useState } from 'react'
import { ArrowDownWideNarrow, ArrowRight, ArrowUpWideNarrow, RefreshCw } from 'lucide-react'
import type { AiLead } from '../../shared/api/client'

type StatusTab = 'pending' | 'approved' | 'published' | 'rejected' | 'all'
type SortMode = 'score' | 'rank' | 'headline'
type SortDir = 'asc' | 'desc'

const ORIGIN_LABELS: Record<string, string> = {
  trend_feed: 'From trends',
  manual: 'Manual',
  wire: 'Wire desk',
  ingest: 'Ingest',
}

function originKey(lead: AiLead) {
  return (lead.origin || 'manual').trim() || 'manual'
}

function originLabel(origin: string) {
  if (ORIGIN_LABELS[origin]) return ORIGIN_LABELS[origin]
  return origin.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function leadScore(lead: AiLead) {
  const value = lead.final_score ?? lead.priority_score ?? 0
  return Number.isFinite(value) ? Number(value) : 0
}

function RankShiftBadge({ lead }: { lead: AiLead }) {
  const previous = lead.previous_rank
  const current = lead.current_rank
  if (previous === null || current === null || previous === current)
    return <span className="rank-shift rank-flat">—</span>
  const difference = Math.abs(previous - current)
  return current < previous ? (
    <span className="rank-shift rank-up">Up {difference}</span>
  ) : (
    <span className="rank-shift rank-down">Down {difference}</span>
  )
}

function sourceLabel(lead: AiLead) {
  return lead.trend_evidence?.[0]?.source || (originKey(lead) === 'trend_feed' ? 'Trend Feed' : 'Wire Desk')
}

function compactReaders(value: number) {
  return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function audienceLabel(lead: AiLead) {
  const forecast = lead.audience_forecast
  if (!forecast) return { text: 'Audience data pending', title: '' }
  const title = `${forecast.confidence} confidence · ${forecast.comparable_stories} comparable stories · ${compactReaders(forecast.telemetry_sample_size)} reader sample`
  if (forecast.lower_bound !== null && forecast.upper_bound !== null) {
    return {
      text: `${forecast.horizon_days}-day forecast: ${compactReaders(forecast.lower_bound)}–${compactReaders(forecast.upper_bound)} · ${forecast.confidence} confidence`,
      title,
    }
  }
  const learning = forecast.next_stage_target
    ? ` · Learning ${forecast.completed_stories ?? 0}/${forecast.next_stage_target} stories`
    : ''
  return { text: `Demand: ${forecast.audience_demand}${learning}`, title }
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
  const [tab, setTab] = useState<StatusTab>('pending')
  const [sort, setSort] = useState<SortMode>('score')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [originFilter, setOriginFilter] = useState<string>('all')
  const [page, setPage] = useState(1)
  const pageSize = 6

  const originOptions = useMemo(() => {
    const unique = new Set<string>()
    leads.forEach((lead) => unique.add(originKey(lead)))
    ;['trend_feed', 'manual'].forEach((origin) => unique.add(origin))
    return [...unique].sort((a, b) => originLabel(a).localeCompare(originLabel(b)))
  }, [leads])

  const counts = useMemo(() => {
    const next = { pending: 0, approved: 0, published: 0, rejected: 0 }
    leads.forEach((lead) => {
      if (lead.status in next) next[lead.status as keyof typeof next] += 1
    })
    return next
  }, [leads])

  const originCounts = useMemo(() => {
    const next: Record<string, number> = {}
    leads.forEach((lead) => {
      const key = originKey(lead)
      next[key] = (next[key] ?? 0) + 1
    })
    return next
  }, [leads])

  const filtered = useMemo(() => {
    const byStatus = tab === 'all' ? leads : leads.filter((lead) => lead.status === tab)
    const byOrigin =
      originFilter === 'all' ? byStatus : byStatus.filter((lead) => originKey(lead) === originFilter)
    const direction = sortDir === 'asc' ? 1 : -1
    return [...byOrigin].sort((a, b) => {
      let result = 0
      if (sort === 'headline') {
        result = a.headline.localeCompare(b.headline)
      } else if (sort === 'rank') {
        result =
          (a.current_rank ?? Number.POSITIVE_INFINITY) - (b.current_rank ?? Number.POSITIVE_INFINITY)
        if (result === 0) result = leadScore(b) - leadScore(a)
      } else {
        result = leadScore(a) - leadScore(b)
        if (result === 0) {
          result =
            (a.current_rank ?? Number.POSITIVE_INFINITY) - (b.current_rank ?? Number.POSITIVE_INFINITY)
        }
      }
      return result * direction
    })
  }, [leads, tab, sort, sortDir, originFilter])

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const visibleLeads = filtered.slice((page - 1) * pageSize, page * pageSize)
  useEffect(() => setPage(1), [tab, sort, sortDir, originFilter])
  useEffect(() => setPage((current) => Math.min(current, pages)), [pages])

  const onSortChange = (next: SortMode) => {
    setSort(next)
    setSortDir(next === 'headline' || next === 'rank' ? 'asc' : 'desc')
  }

  const tabs: { id: StatusTab; label: string; count?: number }[] = [
    { id: 'pending', label: 'Pending Review', count: counts.pending },
    { id: 'approved', label: 'Approved', count: counts.approved },
    { id: 'published', label: 'Published', count: counts.published },
    { id: 'rejected', label: 'Rejected', count: counts.rejected },
  ]

  return (
    <section className="ai-leads ai-panel-card">
      <header className="ai-leads-header">
        <div>
          <span className="ai-stage-pill">2. Curate & selection desk</span>
          <div className="ai-leads-title-row">
            <h2>Lead inbox</h2>
            <span className="item-count-pill">{filtered.length} shown · {leads.length} total</span>
          </div>
        </div>
        <div className="ai-leads-controls">
          <label className="ai-sort-select">
            <span>Sort</span>
            <select
              value={sort}
              onChange={(event) => onSortChange(event.target.value as SortMode)}
              aria-label="Sort leads"
            >
              <option value="score">AI Score</option>
              <option value="rank">Current rank</option>
              <option value="headline">Headline</option>
            </select>
          </label>
          <button
            type="button"
            className="ai-sort-dir"
            onClick={() => setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))}
            aria-label={sortDir === 'asc' ? 'Switch to descending' : 'Switch to ascending'}
            title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
          >
            {sortDir === 'asc' ? <ArrowUpWideNarrow size={16} /> : <ArrowDownWideNarrow size={16} />}
            <span>{sortDir === 'asc' ? 'Asc' : 'Desc'}</span>
          </button>
          <button type="button" className="ai-refresh-btn" onClick={onRefresh}>
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </header>

      <nav className="ai-lead-tabs" aria-label="Lead status filters">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            className={tab === item.id ? 'active' : undefined}
            onClick={() => setTab(item.id)}
          >
            {item.label}
            {typeof item.count === 'number' ? ` (${item.count})` : ''}
          </button>
        ))}
      </nav>

      <div className="origin-filter-bar" aria-label="Filter by origin">
        <span className="origin-filter-label">Origin</span>
        <div className="origin-filter-list">
          <button
            type="button"
            className={`origin-filter-chip${originFilter === 'all' ? ' is-active' : ''}`}
            onClick={() => setOriginFilter('all')}
          >
            All origins
            <em>{leads.length}</em>
          </button>
          {originOptions.map((origin) => (
            <button
              key={origin}
              type="button"
              className={`origin-filter-chip origin-badge${originFilter === origin ? ' is-active' : ''}`}
              onClick={() => setOriginFilter(origin)}
            >
              {originLabel(origin)}
              <em>{originCounts[origin] ?? 0}</em>
            </button>
          ))}
        </div>
      </div>

      {filtered.length ? (
        <div className="ai-lead-list">
          {visibleLeads.map((lead) => {
            const rankChanged =
              lead.previous_rank !== null && lead.current_rank !== null && lead.previous_rank !== lead.current_rank
            const score = leadScore(lead)
            const angle = lead.suggested_angle || lead.reasoning || lead.why_now || 'Awaiting selection run.'
            const origin = originKey(lead)
            return (
              <article className={`ai-lead-card${rankChanged ? ' lead-rank-changed' : ''}`} key={`lead-${lead.id}`}>
                <div className="ai-lead-main">
                  <div className="lead-headline">
                    <b>{lead.headline}</b>
                    <RankShiftBadge lead={lead} />
                    <span className="origin-badge">{originLabel(origin)}</span>
                    {(lead.trend_boost ?? 0) > 0 && <span className="trend-chip">Trending</span>}
                    {lead.suggested_format && lead.suggested_format !== 'standard' && (
                      <span className="format-badge">{lead.suggested_format}</span>
                    )}
                    <button
                      type="button"
                      className="score-pill"
                      onClick={() => onInspect(lead)}
                      aria-label={`Inspect score for ${lead.headline}`}
                    >
                      Score {score.toFixed(2)}
                    </button>
                  </div>
                  <p className="lead-meta-line">
                    <span>{lead.topic.replace(/-/g, ' ')}</span>
                    <span>·</span>
                    <span>rank {lead.current_rank ?? '—'}</span>
                    <span>·</span>
                    <span>Source: {sourceLabel(lead)}</span>
                    <span>·</span>
                    <span className="lead-readership" title={audienceLabel(lead).title}>
                      {audienceLabel(lead).text}
                    </span>
                  </p>
                  <div className="ai-angle-brief">
                    <strong>AI Angle Brief:</strong> {angle}
                  </div>
                </div>
                <div className="ai-lead-actions">
                  <span className={`lead-status status-${lead.status}`}>{lead.status}</span>
                  {lead.status === 'pending' && (
                    <div className="lead-action-row">
                      <button type="button" className="lead-reject-btn" onClick={() => onReject(lead)}>
                        Reject
                      </button>
                      <button
                        type="button"
                        className="lead-approve-btn"
                        onClick={() => onApprove(lead)}
                        disabled={draftingLeadId === lead.id}
                      >
                        {draftingLeadId === lead.id ? (
                          'Drafting…'
                        ) : (
                          <>
                            Approve & draft <ArrowRight size={14} />
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </article>
            )
          })}
        </div>
      ) : (
        <p className="ai-empty">
          {leads.length
            ? 'No leads match these filters. Try another status or origin.'
            : 'Run Selection Agent with approved intake leads to populate this inbox.'}
        </p>
      )}

      {filtered.length > pageSize && (
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
