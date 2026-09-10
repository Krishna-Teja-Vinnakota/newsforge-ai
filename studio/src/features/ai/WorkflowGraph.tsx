import { useEffect, useState } from 'react'
import { AiLead, api, WorkflowState } from '../../shared/api/client'

const nodes = [
  ['intake', 'Intake'], ['selection', 'Selection'], ['approval_gate', 'Human Approval'],
  ['retrieve_and_draft', 'RAG Draft'], ['editorial_gate', 'Editorial Review'], ['publish', 'Publish'], ['telemetry', 'Telemetry'],
] as const

function nodeStatus(node: string, workflow: WorkflowState | null) {
  if (!workflow) return 'idle'
  if (workflow.pending_interrupts.includes(node)) return 'paused'
  if (workflow.current_node === node) return 'running'
  if (workflow.execution_history.some(event => event.node === node || (node === 'approval_gate' && event.node === 'human_approval') || (node === 'editorial_gate' && event.node === 'editorial_review'))) return 'completed'
  return 'idle'
}

export function WorkflowGraph({ lead, onNotice }: { lead: AiLead | undefined; onNotice: (notice: string) => void }) {
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null)
  const [working, setWorking] = useState(false)
  useEffect(() => {
    if (!workflow?.thread_id) return
    const timer = window.setInterval(() => { void api.workflowState(workflow.thread_id).then(setWorkflow).catch(() => undefined) }, 1500)
    return () => window.clearInterval(timer)
  }, [workflow?.thread_id])
  const start = async () => {
    if (!lead) return
    try { setWorking(true); setWorkflow(await api.startWorkflow(lead)); onNotice('Workflow paused for lead approval.') } catch (error) { onNotice(error instanceof Error ? error.message : 'Unable to start workflow.') } finally { setWorking(false) }
  }
  const resume = async () => {
    if (!workflow) return
    const approval = workflow.pending_interrupts.includes('approval_gate')
    const confirmed = window.confirm(approval ? 'Approve this lead and continue to RAG drafting?' : 'Approve this draft for publishing and telemetry?')
    if (!confirmed) return
    try {
      setWorking(true)
      const next = approval ? await api.resumeWorkflow(workflow.thread_id, { approval_status: 'approved' }) : await api.resumeWorkflow(workflow.thread_id, { editorial_status: 'approved' })
      setWorkflow(next)
      onNotice(next.pending_interrupts.length ? 'Workflow paused for editorial review.' : 'Workflow completed.')
    } catch (error) { onNotice(error instanceof Error ? error.message : 'Unable to resume workflow.') } finally { setWorking(false) }
  }
  return <section className="ai-runs workflow-graph"><header><h2>Newsroom workflow</h2><button onClick={() => void start()} disabled={!lead || working}>{working ? 'Working...' : 'Start workflow'}</button></header><div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{nodes.map(([id, label]) => <span key={id} className={nodeStatus(id, workflow)} style={{ border: '1px solid currentColor', borderRadius: 999, padding: '5px 9px' }}>{label} · {nodeStatus(id, workflow)}</span>)}</div>{workflow?.execution_history.length ? <small>Thread {workflow.thread_id} · {workflow.execution_history.map(event => event.node).join(' → ')}</small> : <small>{lead ? 'Start a lead to trace its durable workflow.' : 'Load a lead to start a workflow.'}</small>}{workflow?.pending_interrupts.length ? <footer><button className="lead-approve" onClick={() => void resume()} disabled={working}>Resume Workflow</button></footer> : null}</section>
}
