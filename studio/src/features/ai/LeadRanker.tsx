import { useState } from 'react'
import { api } from '../../shared/api/client'

type Props = {
  onRanked: () => void
  onNotice: (notice: string) => void
}

type ManualLead = { id: string; headline: string; topic: string; geo: string }

export function LeadRanker({ onRanked, onNotice }: Props) {
  const [working, setWorking] = useState(false)
  const [showIntake, setShowIntake] = useState(false)
  const [intake, setIntake] = useState('')

  const rank = async (leads: ManualLead[] = []) => {
    try {
      setWorking(true)
      const run = await api.rankLeads(leads)
      const ranked = (run.output.ranked as unknown[] | undefined)?.length ?? 0
      onNotice(`Selection Agent ranked ${ranked} lead${ranked === 1 ? '' : 's'} in the inbox.`)
      onRanked()
      setIntake('')
      setShowIntake(false)
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'Unable to run the Selection Agent.')
    } finally {
      setWorking(false)
    }
  }

  const addAndRank = async () => {
    const leads = intake
      .split('\n')
      .map((line, index) => {
        const [headline, topic = 'general', geo = 'global'] = line.split('|').map((value) => value.trim())
        return { id: `manual-${Date.now()}-${index}`, headline, topic, geo }
      })
      .filter((lead) => lead.headline.length >= 5)
    if (!leads.length) return onNotice('Add at least one lead. Use: headline | topic | location')
    await rank(leads)
  }

  return (
    <section className="lead-ranker">
      <div className="lead-ranker-row">
        <div>
          <p className="eyebrow">1. CONTENT SELECTION</p>
          <h2>Content Selection Agent</h2>
          <p>Re-rank the leads already available in the inbox using the latest editorial signals.</p>
        </div>
        <button type="button" onClick={() => void rank()} disabled={working}>
          {working ? 'Ranking…' : 'Run Selection Agent'}
        </button>
      </div>
      <div className="lead-intake">
        <button type="button" className="lead-intake-toggle" onClick={() => setShowIntake((value) => !value)}>
          {showIntake ? 'Hide manual intake' : '+ Add leads manually'}
        </button>
        {showIntake && (
          <>
            <p>
              One lead per line: <code>headline | topic | location</code>
            </p>
            <textarea
              aria-label="Lead intake"
              value={intake}
              onChange={(event) => setIntake(event.target.value)}
              placeholder={
                'City council approves a transit budget | local | Seattle\nNew battery standard announced | science | global'
              }
            />
            <div className="lead-intake-actions">
              <button type="button" onClick={() => setShowIntake(false)} disabled={working}>
                Cancel
              </button>
              <button type="button" className="primary" onClick={() => void addAndRank()} disabled={working || !intake.trim()}>
                {working ? 'Ranking…' : 'Add & rank'}
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
