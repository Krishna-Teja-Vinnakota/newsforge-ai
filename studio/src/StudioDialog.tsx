import { FormEvent, ReactNode, useEffect } from 'react'
import './StudioDialog.css'

export function StudioDialog({
  title,
  children,
  onClose,
}: {
  title: string
  children: ReactNode
  onClose: () => void
}) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onClose])
  return (
    <div
      className="studio-dialog-layer"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section className="studio-dialog" role="dialog" aria-modal="true" aria-label={title}>
        <header>
          <div>
            <p className="eyebrow">NEWSFORGE STUDIO</p>
            <h2>{title}</h2>
          </div>
          <button className="dialog-close" type="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        {children}
      </section>
    </div>
  )
}

export function DialogForm({ children, onSubmit }: { children: ReactNode; onSubmit: (event: FormEvent) => void }) {
  return (
    <form className="studio-dialog-form" onSubmit={onSubmit}>
      {children}
    </form>
  )
}
