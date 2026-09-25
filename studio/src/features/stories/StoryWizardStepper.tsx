import { Check } from 'lucide-react'

export type StoryStage = 'details' | 'packaging' | 'review'

export const STORY_STAGES: { id: StoryStage; label: string; hint: string }[] = [
  { id: 'details', label: 'Story details', hint: 'Write and refine the body' },
  { id: 'packaging', label: 'Headline & Summary', hint: 'Headline, summary, topic & image' },
  { id: 'review', label: 'Review', hint: 'Preview and hand off' },
]

export function StoryWizardStepper({
  stage,
  completed,
  onSelect,
}: {
  stage: StoryStage
  completed: Partial<Record<StoryStage, boolean>>
  onSelect: (stage: StoryStage) => void
}) {
  const activeIndex = STORY_STAGES.findIndex((item) => item.id === stage)

  return (
    <nav className="story-stepper" aria-label="Story stages">
      <ol>
        {STORY_STAGES.map((item, index) => {
          const isActive = item.id === stage
          const isDone = Boolean(completed[item.id]) && !isActive
          const isPast = index < activeIndex
          const state = isActive ? 'active' : isDone || isPast ? 'done' : 'upcoming'
          const showRail = index < STORY_STAGES.length - 1
          return (
            <li key={item.id} className={`story-step story-step--${state}`}>
              <button type="button" onClick={() => onSelect(item.id)} aria-current={isActive ? 'step' : undefined}>
                <span className="story-step-index">
                  {isDone || isPast ? <Check size={14} strokeWidth={2.5} /> : index + 1}
                </span>
                <span className="story-step-copy">
                  <b>{item.label}</b>
                  <small>{item.hint}</small>
                </span>
              </button>
              {showRail && (
                <span
                  className={`story-step-rail${index < activeIndex ? ' story-step-rail--filled' : ''}`}
                  aria-hidden
                />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
