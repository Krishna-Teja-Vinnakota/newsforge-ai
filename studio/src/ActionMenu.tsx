import { type KeyboardEvent as ReactKeyboardEvent, useEffect, useRef, useState } from 'react'
import { Wand2 } from 'lucide-react'
import './ActionMenu.css'

export type ActionMenuItem = {
  key: string
  label: string
  onSelect: () => void
  disabled?: boolean
}

export function ActionMenu({
  label,
  items,
  disabled = false,
  align = 'start',
}: {
  label: string
  items: ActionMenuItem[]
  disabled?: boolean
  align?: 'start' | 'end'
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const clickOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', clickOutside)
    window.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', clickOutside)
      window.removeEventListener('keydown', close)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const firstEnabled = listRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')
    firstEnabled?.focus()
  }, [open])

  const focusEnabled = (delta: number) => {
    const buttons = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])
    if (!buttons.length) return
    const current = buttons.indexOf(document.activeElement as HTMLButtonElement)
    const next = (current + delta + buttons.length) % buttons.length
    buttons[next]?.focus()
  }

  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      focusEnabled(1)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      focusEnabled(-1)
    } else if (event.key === 'Home') {
      event.preventDefault()
      listRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus()
    } else if (event.key === 'End') {
      event.preventDefault()
      const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
      buttons?.[buttons.length - 1]?.focus()
    }
  }

  return (
    <div className="action-menu" ref={containerRef}>
      <button
        type="button"
        ref={triggerRef}
        className="action-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      >
        <Wand2 size={16} />
      </button>
      {open && (
        <div
          className={`action-menu-list${align === 'end' ? ' align-end' : ''}`}
          role="menu"
          ref={listRef}
          onKeyDown={onMenuKeyDown}
        >
          {items.map((item) => (
            <button
              type="button"
              role="menuitem"
              key={item.key}
              disabled={item.disabled}
              onClick={() => {
                item.onSelect()
                setOpen(false)
                triggerRef.current?.focus()
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
