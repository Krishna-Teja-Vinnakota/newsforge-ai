import { useEffect, useState } from 'react'
import { AgentRun, AiLead, api } from '../../shared/api/client'
import { LeadRanker } from './LeadRanker'
import { LeadInbox } from './LeadInbox'
import { ScoreInspectorDrawer } from './ScoreInspectorDrawer'
import { ProductionWorkspace } from './ProductionWorkspace'
import { TelemetryPanel, TelemetryResult } from './TelemetryPanel'
import { ProductionResult } from './ProductionResult'
import { WorkflowGraph } from './WorkflowGraph'
import './AiDesk.css'
import './LeadInbox.css'
import './DraftAction.css'
import './AiDeskPanels.css'

const intakePresets = [
  {
    id: 'ohio',
    label: '+ Ohio Tech Wire',
    content:
      'Ohio Tech Corridor expands with major microchip facility investment | nation-world | Ohio\nOhio clean-energy manufacturing grants open to regional applicants | climate | Ohio',
  },
  {
    id: 'global-ai',
    label: '+ Global AI & Tech',
    content:
      'Open-source AI foundation releases a new enterprise model | technology | global\nGlobal semiconductor supply chain report highlights capacity growth | technology | global',
  },
  {
    id: 'mixed-national',
    label: '+ Mixed National Wire',
    content:
      'National championship matchup sets a record audience | sports | national\nCity council approves a regional transit budget | local | national\nFederal infrastructure bill advances in the Senate | nation-world | national',
  },
]

export function AiDesk() {
  const [runs, setRuns] = useState<AgentRun[]>([]),
    [leads, setLeads] = useState<AiLead[]>([]),
    [notice, setNotice] = useState(''),
    [draftingLeadId, setDraftingLeadId] = useState<string | null>(null),
    [draftRefresh, setDraftRefresh] = useState(0),
    [resettingDemo, setResettingDemo] = useState(false),
    [preset, setPreset] = useState<{ id: string; content: string } | null>(null),
    [inspectedLead, setInspectedLead] = useState<AiLead | null>(null)
  const load = () => {
    void Promise.all([api.agentRuns(), api.aiLeads()])
      .then(([history, inbox]) => {
        setRuns(history.items)
        setLeads(inbox)
      })
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
      setRuns((items) => [run, ...items])
      setNotice('Article draft generated successfully!')
      setDraftRefresh((value) => value + 1)
      load()
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
      setDraftRefresh((value) => value + 1)
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
      <section className="intake-presets" aria-label="Lead intake presets">
        <span>Quick scenarios</span>
        {intakePresets.map((item) => (
          <button
            key={item.id}
            className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors button-secondary"
            onClick={() => setPreset({ id: `${item.id}-${Date.now()}`, content: item.content })}
          >
            {item.label}
          </button>
        ))}
      </section>
      <LeadRanker preset={preset} onRanked={load} onNotice={setNotice} />
      <WorkflowGraph lead={sortedLeads[0]} onNotice={setNotice} />
      <LeadInbox
        leads={sortedLeads}
        draftingLeadId={draftingLeadId}
        onRefresh={load}
        onReject={(lead) => void decide(lead, 'reject')}
        onApprove={(lead) => void draftLead(lead)}
        onInspect={setInspectedLead}
      />
      <div className="ai-desk-grid">
        <ProductionWorkspace refreshKey={draftRefresh} onNotice={setNotice} />
        <section className="ai-runs">
          <header>
            <h2>Agent run history</h2>
            <button
              className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors button-secondary"
              onClick={load}
            >
              Refresh
            </button>
          </header>
          {runs.map((run) => (
            <article key={run.id}>
              <div>
                <b>{run.agent}</b>
                <span className={run.status}>{run.status}</span>
              </div>
              <ProductionResult run={run} />
              <TelemetryResult run={run} />
            </article>
          ))}
        </section>
      </div>
      <TelemetryPanel
        onRun={(run) => setRuns((items) => [run, ...items])}
        onNotice={setNotice}
        onSimulationComplete={load}
      />
      <ScoreInspectorDrawer lead={inspectedLead} onClose={() => setInspectedLead(null)} />
    </section>
  )
}
