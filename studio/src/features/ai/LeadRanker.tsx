import { useState } from 'react'
import { api } from '../../shared/api/client'

type Props = {
  onRanked: () => void
  onNotice: (notice: string) => void
}

export function LeadRanker({ onRanked, onNotice }: Props) {
  const [working, setWorking] = useState(false)

  const rank = async () => {
    try {
      setWorking(true)
      const run = await api.rankLeads([])
      const ranked = (run.output.ranked as unknown[] | undefined)?.length ?? 0
      onNotice(`Selection Agent ranked ${ranked} lead${ranked === 1 ? '' : 's'} in the inbox.`)
      onRanked()
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'Unable to run the Selection Agent.')
    } finally {
      setWorking(false)
    }
  }

  return (
    <section className="lead-ranker">
      <div>
        <p className="eyebrow">1. CONTENT SELECTION</p>
        <h2>Content Selection Agent</h2>
        <p>Re-rank the leads already available in the inbox using the latest editorial signals.</p>
      </div>
      <button
        type="button"
        className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors button-primary"
        onClick={() => void rank()}
        disabled={working}
      >
        {working ? 'Ranking…' : 'Run Selection Agent'}
      </button>
    </section>
  )
}
