import { useEffect, useState } from 'react'
import type { Article, ArticleStatus } from '../../types'
import { api } from '../../shared/api/client'

type DraftForm = { headline: string; lead_paragraph: string; content_html: string; x_copy: string; newsletter_copy: string }

const toForm = (article: Article): DraftForm => {
  const distribution = article.content_json?.distribution as Record<string, string> | undefined
  return { headline: article.title, lead_paragraph: article.dek, content_html: article.content_html, x_copy: distribution?.x_copy ?? `${article.title} — what it means for readers.`, newsletter_copy: distribution?.newsletter_copy ?? article.dek }
}

function HeroImage({ article }: { article: Article }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [article.id, article.hero_url])
  const topic = article.topic.replace(/-/g, ' ').toUpperCase()
  if (!article.hero_url || failed) return <div className="workspace-hero fallback" role="img" aria-label={`${topic} article placeholder`}><span>{topic}</span></div>
  return <div className="workspace-hero"><img src={article.hero_url} alt={`Hero image for ${article.title}`} onError={() => setFailed(true)} /></div>
}

const statusLabel: Record<ArticleStatus, string> = { draft: 'Draft', under_review: 'Under review', approved: 'Approved', rejected: 'Rejected', scheduled: 'Scheduled', published: 'Published', archived: 'Archived' }

export function ProductionWorkspace({ refreshKey, onNotice }: { refreshKey: number; onNotice: (notice: string) => void }) {
  const [articles, setArticles] = useState<Article[]>([])
  const [active, setActive] = useState<Article | null>(null)
  const [form, setForm] = useState<DraftForm | null>(null)
  const [working, setWorking] = useState(false)
  const load = () => { void api.myArticles(1, 30).then(result => {
    setArticles(result.items)
    setActive(current => result.items.find(item => item.id === current?.id) ?? result.items[0] ?? null)
  }).catch(error => onNotice(error.message)) }
  useEffect(load, [refreshKey])
  useEffect(() => { if (active) setForm(toForm(active)) }, [active?.id])
  const updateForm = (field: keyof DraftForm, value: string) => setForm(current => current ? { ...current, [field]: value } : current)
  const save = async () => {
    if (!active || !form) return
    try {
      setWorking(true)
      const article = await api.updateArticle(active.id, { title: form.headline, dek: form.lead_paragraph, content_html: form.content_html, content_json: { ...active.content_json, distribution: { x_copy: form.x_copy, newsletter_copy: form.newsletter_copy } }, topic: active.topic })
      setActive(article); setArticles(items => items.map(item => item.id === article.id ? article : item)); onNotice('Draft saved successfully.')
    } catch (error) { onNotice(error instanceof Error ? error.message : 'Unable to save draft.') } finally { setWorking(false) }
  }
  const transition = async (action: 'submit' | 'approve' | 'reject' | 'publish') => {
    if (!active) return
    try {
      setWorking(true)
      const article = action === 'submit' ? await api.submitArticle(active.id) : action === 'approve' ? await api.approveArticle(active.id) : action === 'reject' ? await api.rejectArticle(active.id) : await api.publishArticle(active.id)
      setActive(article); setArticles(items => items.map(item => item.id === article.id ? article : item)); onNotice(`${article.title} is now ${statusLabel[article.status].toLowerCase()}.`)
    } catch (error) { onNotice(error instanceof Error ? error.message : 'Unable to update the editorial status.') } finally { setWorking(false) }
  }
  if (!active || !form) return <section className="production-workspace"><h2>Production workspace</h2><p>No generated drafts yet. Approve a lead to create one.</p></section>
  const canEdit = !['published', 'archived'].includes(active.status)
  return <section className="production-workspace">
    <header className="workspace-heading"><div><p className="eyebrow">AI DRAFT</p><h2>Production workspace</h2></div><select aria-label="Choose article" value={active.id} onChange={event => setActive(articles.find(article => article.id === event.target.value) ?? null)}>{articles.map(article => <option key={article.id} value={article.id}>{article.title}</option>)}</select></header>
    <div className="lifecycle-bar"><div><span className={`status-badge status-${active.status}`}>{statusLabel[active.status]}</span>{active.status === 'published' && <small>Published {active.published_at ? new Date(active.published_at).toLocaleString() : 'recently'}</small>}</div><div className="lifecycle-actions">{active.status === 'draft' && <><button className="button-secondary" onClick={() => void save()} disabled={working}>Save Draft</button><button className="button-primary" onClick={() => void transition('submit')} disabled={working}>Submit for Review</button></>}{active.status === 'under_review' && <><button className="button-danger" onClick={() => void transition('reject')} disabled={working}>Reject</button><button className="button-success" onClick={() => void transition('approve')} disabled={working}>Approve Draft</button></>}{active.status === 'approved' && <button className="button-publish" onClick={() => void transition('publish')} disabled={working}>Publish Article</button>}{active.status === 'published' && <span className="published-badge">✓ Published</span>}{active.status === 'rejected' && <button className="button-secondary" onClick={() => void save()} disabled={working}>Save Draft</button>}</div></div>
    <div className="workspace-grid"><div className="workspace-fields"><label>Headline<input value={form.headline} disabled={!canEdit} onChange={event => updateForm('headline', event.target.value)} /></label><label>Lead paragraph<textarea value={form.lead_paragraph} disabled={!canEdit} onChange={event => updateForm('lead_paragraph', event.target.value)} /></label><label>Article body<textarea className="article-body-input" value={form.content_html} disabled={!canEdit} onChange={event => updateForm('content_html', event.target.value)} /></label></div><aside><HeroImage article={active} /><section className="distribution"><b>Platform distribution</b><label>X / Twitter<textarea value={form.x_copy} disabled={!canEdit} onChange={event => updateForm('x_copy', event.target.value)} /></label><label>Newsletter<textarea value={form.newsletter_copy} disabled={!canEdit} onChange={event => updateForm('newsletter_copy', event.target.value)} /></label></section></aside></div>
  </section>
}
