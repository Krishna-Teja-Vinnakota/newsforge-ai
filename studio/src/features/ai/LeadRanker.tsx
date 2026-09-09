import { FormEvent, useState } from 'react'
import { api } from '../../shared/api/client'

type Props = { onRanked: () => void; onNotice: (notice: string) => void }

export function LeadRanker({ onRanked, onNotice }: Props) {
  const [intake, setIntake] = useState('')
  const [working, setWorking] = useState(false)
  const rank = async (event: FormEvent) => {
    event.preventDefault()
    const leads = intake.split('\n').map((line, index) => {
      const [headline, topic = 'general', geo = 'global'] = line.split('|').map(value => value.trim())
      return { id: `manual-${Date.now()}-${index}`, headline, topic, geo }
    }).filter(lead => lead.headline.length >= 5)
    if (!leads.length) return onNotice('Add at least one lead. Use: headline | topic | location')
    try { setWorking(true); await api.rankLeads(leads); setIntake(''); onNotice('Selection Agent ranked the intake and added it to Lead inbox.'); onRanked() }
    catch (error) { onNotice(error instanceof Error ? error.message : 'Unable to rank leads.') }
    finally { setWorking(false) }
  }
  return <form className="lead-ranker" onSubmit={rank}><div><p className="eyebrow">EDITORIAL INTAKE</p><h2>Rank incoming leads</h2><p>One lead per line: <code>headline | topic | location</code></p></div><textarea value={intake} onChange={event => setIntake(event.target.value)} placeholder={'City council approves a transit budget | local | Seattle\nNew battery standard announced | science | global'} /><button disabled={working}>{working ? 'Ranking…' : 'Run Selection Agent'}</button></form>
}
