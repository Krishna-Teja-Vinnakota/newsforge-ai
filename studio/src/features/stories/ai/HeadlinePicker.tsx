import { useState } from 'react'
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
  const [selected, setSelected] = useState(options.includes(current) ? current : '')
  return (
    <fieldset className="headline-picker">
      <legend>Choose a headline</legend>
      {options.map((option) => (
        <label key={option}>
          <input type="radio" name="headline-option" checked={selected === option} onChange={() => setSelected(option)} />
          <span>{option}</span>
        </label>
      ))}
      <footer>
        <button type="button" onClick={onClose}>
          Keep current
        </button>
        <button type="button" onClick={onRegenerate} disabled={disabled}>
          Regenerate
        </button>
        <button type="button" className="primary" onClick={() => onUpdate(selected)} disabled={!selected || disabled}>
          Click to update
        </button>
      </footer>
    </fieldset>
  )
}
