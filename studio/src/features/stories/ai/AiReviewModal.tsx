import { useEffect, useMemo, useState } from 'react'
import { StudioDialog } from '../../../StudioDialog'
import './AiReviewModal.css'

export type AiInsights = {
  reporter_brief?: { background?: string; key_questions?: string[]; shot_list?: string[] }
  social_posts?: string[]
  push_notification?: string
  provenance?: string[]
  model_name?: string
  generated_at?: string
  suggested_tags?: string[]
}

export type AiProposal = {
  title?: string
  dek?: string
  content_html?: string
  content_json?: Record<string, unknown>
  hero_url?: string
  ai_insights?: AiInsights
  used_fallback?: boolean
}

type Field = 'title' | 'dek' | 'content_html' | 'hero_url'
type CurrentStory = Pick<Required<AiProposal>, Field>

const labels: Record<Field, string> = {
  title: 'Headline',
  dek: 'Reader summary',
  content_html: 'Story body',
  hero_url: 'Hero image',
}

function verificationItems(insights?: AiInsights) {
  const questions = insights?.reporter_brief?.key_questions ?? []
  const provenance = insights?.provenance ?? []
  return [...questions, ...provenance].filter(Boolean)
}

export function AiReviewModal({
  proposal,
  current,
  onApply,
  onClose,
}: {
  proposal: AiProposal
  current: CurrentStory
  onApply: (fields: Field[], insights?: AiInsights) => void
  onClose: () => void
}) {
  const changed = useMemo(
    () => (Object.keys(labels) as Field[]).filter((field) => proposal[field] !== undefined && proposal[field] !== current[field]),
    [proposal, current]
  )
  const [selected, setSelected] = useState<Field[]>(changed)
  useEffect(() => setSelected(changed), [changed])
  const checks = verificationItems(proposal.ai_insights)
  const toggle = (field: Field) =>
    setSelected((items) => (items.includes(field) ? items.filter((item) => item !== field) : [...items, field]))

  return (
    <StudioDialog title="Review AI proposal" onClose={onClose} className="ai-review-dialog">
      <div className="ai-review">
        {proposal.used_fallback && (
          <section className="ai-review-fallback" role="alert">
            <b>The AI model did not respond.</b>
            <p>This proposal is a basic template, not model-written copy. Review it carefully or try again.</p>
          </section>
        )}
        <p>Nothing changes until you apply the fields you want to keep.</p>
        {changed.length ? (
          changed.map((field) => (
            <section className="ai-review-field" key={field}>
              <label>
                <input type="checkbox" checked={selected.includes(field)} onChange={() => toggle(field)} />
                <b>Apply {labels[field]}</b>
              </label>
              {field === 'content_html' ? (
                <div className="ai-review-body">
                  <div>
                    <small>Current</small>
                    <div dangerouslySetInnerHTML={{ __html: current.content_html || '<p>Nothing written yet.</p>' }} />
                  </div>
                  <div>
                    <small>Proposed</small>
                    <div dangerouslySetInnerHTML={{ __html: proposal.content_html || '<p>Nothing proposed.</p>' }} />
                  </div>
                </div>
              ) : field === 'hero_url' ? (
                <div className="ai-review-images">
                  <img src={current.hero_url} alt="Current hero" />
                  <img src={proposal.hero_url ?? ''} alt="Proposed hero" />
                </div>
              ) : (
                <div className="ai-review-copy">
                  <span>{current[field] || '—'}</span>
                  <strong>{proposal[field]}</strong>
                </div>
              )}
            </section>
          ))
        ) : (
          <p>The AI did not suggest any content changes.</p>
        )}
        {checks.length > 0 && (
          <section className="ai-review-accuracy">
            <b>Accuracy checks before publishing</b>
            <p>Review these reporting questions and source notes before relying on the proposal.</p>
            <ul>{checks.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
        )}
        <footer className="dialog-actions">
          <button type="button" onClick={onClose}>Keep current draft</button>
          <button type="button" className="dialog-primary" onClick={() => onApply(selected, proposal.ai_insights)} disabled={!selected.length && !proposal.ai_insights}>
            Apply selected
          </button>
        </footer>
      </div>
    </StudioDialog>
  )
}
