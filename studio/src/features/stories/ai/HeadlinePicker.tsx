import { useState } from 'react'
import { RefreshCw, Sparkles } from 'lucide-react'
import './HeadlinePicker.css'

export function HeadlinePicker({
  options,
  current,
  disabled,
  onUpdate,
  onRegenerate,
  onClose,
}: {
  options: string[]
  current: string
  disabled: boolean
  onUpdate: (headline: string) => void
  onRegenerate: () => void
  onClose: () => void
}) {
  const [selected, setSelected] = useState(options.includes(current) ? current : options[0] ?? '')
  return (
    <fieldset className="headline-picker">
      <legend>
        <Sparkles size={14} /> Headline options
      </legend>
      <p className="headline-picker-hint">Pick one option to replace your current headline.</p>
      <div className="headline-picker-options">
        {options.map((option, index) => (
          <label key={option} className={selected === option ? 'is-selected' : undefined}>
            <input
              type="radio"
              name="headline-option"
              checked={selected === option}
              onChange={() => setSelected(option)}
            />
            <span className="headline-picker-rank">{index + 1}</span>
            <span className="headline-picker-text">{option}</span>
          </label>
        ))}
      </div>
      <footer>
        <button type="button" onClick={onClose}>
          Keep current
        </button>
        <button type="button" onClick={onRegenerate} disabled={disabled}>
          <RefreshCw size={14} /> Regenerate
        </button>
        <button type="button" className="primary" onClick={() => onUpdate(selected)} disabled={!selected || disabled}>
          Use headline
        </button>
      </footer>
    </fieldset>
  )
}
