import { useEffect, useState } from 'react'
import { AiLead, api } from '../../shared/api/client'
import { LeadRanker } from './LeadRanker'
import { LeadInbox } from './LeadInbox'
import { ScoreInspectorDrawer } from './ScoreInspectorDrawer'
import { TelemetryPanel } from './TelemetryPanel'
import './AiDesk.css'
import './LeadInbox.css'
import './DraftAction.css'
import './AiDeskPanels.css'

export function AiDesk({ onDraftCreated }: { onDraftCreated?: (articleId: string) => void }) {
  const [leads, setLeads] = useState<AiLead[]>([]),
    [notice, setNotice] = useState(''),
    [draftingLeadId, setDraftingLeadId] = useState<string | null>(null),
    [resettingDemo, setResettingDemo] = useState(false),
    [inspectedLead, setInspectedLead] = useState<AiLead | null>(null)
  const load = () => {
    void api.aiLeads()
      .then(setLeads)
      .catch((error) => setNotice(error.message))
  }
  useEffect(load, [])
  const decide = async (lead: AiLead, decision: 'reject') => {
    try {
      await api.decideLead(lead.id, decision)
      setNotice(`Lead ${decision}ed.`)
      load()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to update lead.')
    }
  }
  const draftLead = async (lead: AiLead) => {
    try {
      setDraftingLeadId(lead.id)
      const run = await api.produceDraft({
        headline: lead.headline,
        topic: lead.topic,
        context: lead.suggested_angle || lead.reasoning || '',
        target_platforms: ['web', 'twitter', 'newsletter'],
        source_lead_id: lead.id,
      })
      const articleId = (run.output as { article?: { id: string } }).article?.id
      setNotice('Article draft generated successfully! Opening it in Stories…')
      load()
      if (articleId) onDraftCreated?.(articleId)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to generate article draft.')
    } finally {
      setDraftingLeadId(null)
    }
  }
  const resetDemo = async () => {
    if (!window.confirm('Reset demo leads and telemetry?')) return
    try {
      setResettingDemo(true)
      const result = await api.resetDemoData()
      setNotice(result.message)
      load()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to reset the demo scenario.')
    } finally {
      setResettingDemo(false)
    }
  }
  const sortedLeads = [...leads].sort((a, b) => (a.current_rank ?? 99) - (b.current_rank ?? 99))
  return (
    <section className="ai-desk">
      <header>
        <p className="eyebrow">PHASE 7 · AI NEWSROOM</p>
        <h1>AI editorial desk</h1>
        <div>
          <button
            className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors button-secondary"
            onClick={() => void resetDemo()}
            disabled={resettingDemo}
          >
            {resettingDemo ? 'Resetting demo…' : '↻ Reset Demo Scenario'}
          </button>
        </div>
        <p>{notice}</p>
      </header>
      <LeadRanker onRanked={load} onNotice={setNotice} />
      <LeadInbox
        leads={sortedLeads}
        draftingLeadId={draftingLeadId}
        onRefresh={load}
        onReject={(lead) => void decide(lead, 'reject')}
        onApprove={(lead) => void draftLead(lead)}
        onInspect={setInspectedLead}
      />
      <TelemetryPanel onNotice={setNotice} onSimulationComplete={load} />
      <ScoreInspectorDrawer lead={inspectedLead} onClose={() => setInspectedLead(null)} />
    </section>
  )
}
