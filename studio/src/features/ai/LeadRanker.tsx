import { useEffect, useMemo, useState } from 'react'
import { Plus, Zap } from 'lucide-react'
import { api } from '../../shared/api/client'

type Props = {
  onRanked: () => void
  onNotice: (notice: string) => void
  nextTrendRefreshAt: string | null
  trendRefreshStatus: string
}

type ManualLead = { id: string; headline: string; topic: string; geo: string }
type WeightKey = 'timeliness' | 'economic_impact' | 'local_demand'
type Weights = Record<WeightKey, number>

const WEIGHT_META: { key: WeightKey; label: string }[] = [
  { key: 'timeliness', label: 'Timeliness' },
  { key: 'economic_impact', label: 'Economic Impact' },
  { key: 'local_demand', label: 'Local Demand' },
]

const DEFAULT_WEIGHTS: Weights = {
  timeliness: 40,
  economic_impact: 35,
  local_demand: 25,
}

function refreshLabel(nextRefreshAt: string | null, status: string) {
  if (status === 'disabled') return 'Trend refresh disabled'
  if (!nextRefreshAt) return 'Trend refresh awaiting first run'
  const minutes = Math.max(0, Math.ceil((new Date(nextRefreshAt).getTime() - Date.now()) / 60000))
  return minutes === 0 ? 'Next trend refresh due now' : `Next trend refresh in ${minutes} min`
}

export function LeadRanker({ onRanked, onNotice, nextTrendRefreshAt, trendRefreshStatus }: Props) {
  const [working, setWorking] = useState(false)
  const [showIntake, setShowIntake] = useState(false)
  const [intake, setIntake] = useState('')
  const [showWeights, setShowWeights] = useState(false)
  const [weights, setWeights] = useState<Weights>({ ...DEFAULT_WEIGHTS })
  const [draftWeights, setDraftWeights] = useState<Weights>(weights)
  const [savingWeights, setSavingWeights] = useState(false)

  useEffect(() => {
    void api
      .selectionWeights()
      .then((saved) => {
        const next = {
          timeliness: saved.timeliness,
          economic_impact: saved.economic_impact,
          local_demand: saved.local_demand,
        }
        setWeights(next)
        setDraftWeights(next)
      })
      .catch((error) => onNotice(error instanceof Error ? error.message : 'Unable to load selection weights.'))
  }, [onNotice])

  const total = useMemo(
    () => draftWeights.timeliness + draftWeights.economic_impact + draftWeights.local_demand,
    [draftWeights]
  )
  const validTotal = total === 100

  const rank = async (leads: ManualLead[] = []) => {
    try {
      setWorking(true)
      const run = await api.rankLeads(leads)
      const ranked = (run.output.ranked as unknown[] | undefined)?.length ?? 0
      onNotice(
        `Selection Agent ranked ${ranked} lead${ranked === 1 ? '' : 's'} using Timeliness ${weights.timeliness}%, Economic Impact ${weights.economic_impact}%, Local Demand ${weights.local_demand}%.`
      )
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

  const openEditor = () => {
    setDraftWeights(weights)
    setShowWeights(true)
  }

  const saveWeights = async () => {
    if (!validTotal) {
      onNotice('Weights must add up to exactly 100%.')
      return
    }
    if (Object.values(draftWeights).some((value) => value < 0 || value > 100)) {
      onNotice('Each weight must be between 0 and 100.')
      return
    }
    try {
      setSavingWeights(true)
      const saved = await api.updateSelectionWeights(draftWeights)
      const next = {
        timeliness: saved.timeliness,
        economic_impact: saved.economic_impact,
        local_demand: saved.local_demand,
      }
      setWeights(next)
      setDraftWeights(next)
      setShowWeights(false)
      onNotice(
        `Selection weights saved to the newsroom configuration: Timeliness ${next.timeliness}%, Economic Impact ${next.economic_impact}%, Local Demand ${next.local_demand}%. Run the agent to apply them.`
      )
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'Unable to save selection weights.')
    } finally {
      setSavingWeights(false)
    }
  }

  const resetWeights = () => {
    setDraftWeights({ ...DEFAULT_WEIGHTS })
  }

  const updateDraft = (key: WeightKey, value: string) => {
    const next = Number(value)
    setDraftWeights((current) => ({
      ...current,
      [key]: Number.isFinite(next) ? Math.max(0, Math.min(100, Math.round(next))) : 0,
    }))
  }

  return (
    <section className="lead-ranker ai-panel-card">
      <div className="lead-ranker-top">
        <div className="ai-panel-tags">
          <span className="ai-stage-pill">1. Content selection</span>
        </div>
        <button type="button" className="run-agent-btn" onClick={() => void rank()} disabled={working}>
          {working ? (
            <>
              <span className="button-spinner" aria-hidden />
              Ranking…
            </>
          ) : (
            <>
              <Zap size={16} />
              Run Selection Agent
            </>
          )}
        </button>
      </div>

      <div className="lead-ranker-copy">
        <h2>Content Selection Agent</h2>
        <p>
          Re-rank inbox leads using live editorial signals, audience demand, and desk priorities before curation.
        </p>
        <div className="weight-row">
          <span className="weight-label">Weights:</span>
          <div className="weight-pills" aria-label="Selection weights">
            {WEIGHT_META.map((item) => (
              <span key={item.key}>
                {item.label} <b>({weights[item.key]}%)</b>
              </span>
            ))}
          </div>
          <button type="button" className="text-link-btn" onClick={openEditor}>
            Edit Weights
          </button>
        </div>

        {showWeights && (
          <div className="weight-editor">
            <div className="weight-editor-grid">
              {WEIGHT_META.map((item) => (
                <label key={item.key}>
                  {item.label}
                  <div className="weight-input-row">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={1}
                      value={draftWeights[item.key]}
                      onChange={(event) => updateDraft(item.key, event.target.value)}
                    />
                    <span>%</span>
                  </div>
                </label>
              ))}
            </div>
            <div className={`weight-total${validTotal ? ' is-valid' : ' is-invalid'}`}>
              Total: <b>{total}%</b>
              <span>{validTotal ? 'Ready — must equal 100%' : 'Must equal exactly 100%'}</span>
            </div>
            <div className="weight-editor-actions">
              <button type="button" onClick={resetWeights}>
                Reset defaults
              </button>
              <button type="button" onClick={() => setShowWeights(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="primary"
                onClick={() => void saveWeights()}
                disabled={!validTotal || savingWeights}
              >
                {savingWeights ? 'Saving…' : 'Save weights'}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="lead-ranker-footer">
        <button type="button" className="lead-intake-toggle" onClick={() => setShowIntake((value) => !value)}>
          <Plus size={14} />
          {showIntake ? 'Hide manual intake' : 'Add leads manually'}
        </button>
        <span className="lead-schedule-note">
          <span className="schedule-dot" aria-hidden />
          {refreshLabel(nextTrendRefreshAt, trendRefreshStatus)}
        </span>
      </div>

      {showIntake && (
        <div className="lead-intake">
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
            <button
              type="button"
              className="primary"
              onClick={() => void addAndRank()}
              disabled={working || !intake.trim()}
            >
              {working ? 'Ranking…' : 'Add & rank'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
