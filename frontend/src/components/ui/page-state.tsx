import type { ReactNode } from 'react'

type PageStateProps = { title: string; children?: ReactNode }

export function PageState({ title, children }: PageStateProps) {
  return (
    <section className="page-state" role="status">
      <h1>{title}</h1>
      {children}
    </section>
  )
}
