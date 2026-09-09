import { AgentRun } from '../../shared/api/client'

type Output = { reporter_brief?: { background?: string; key_questions?: string[] }; social_posts?: string[]; push_notification?: string; provenance?: string[] }

export function ProductionResult({ run }: { run: AgentRun }) {
  if (run.agent !== 'production' || run.status !== 'succeeded') return null
  const output = run.output as Output
  return <div className="production-result"><div><b>Reporter brief</b><p>{output.reporter_brief?.background || 'Review the generated draft against its verified source context.'}</p>{output.reporter_brief?.key_questions?.length ? <small>Verify: {output.reporter_brief.key_questions.join(' · ')}</small> : null}</div><div><b>Distribution</b><p>{output.push_notification || 'No push suggestion available.'}</p>{output.social_posts?.[0] ? <small>{output.social_posts[0]}</small> : null}</div><div className="provenance"><b>Provenance</b><small>{output.provenance?.join(' · ') || 'Editor-supplied context — verify before publication.'}</small></div></div>
}
