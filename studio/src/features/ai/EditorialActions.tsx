import { useEffect, useState } from 'react'
import type { Article } from '../../types'
import { api } from '../../shared/api/client'

export function EditorialActions({ refreshKey, onNotice }: { refreshKey: number; onNotice: (notice: string) => void }) {
  const [articles, setArticles] = useState<Article[]>([])
  const [working, setWorking] = useState<string | null>(null)
  const load = () => { void api.myArticles(1, 30).then(result => setArticles(result.items.filter(article => article.status !== 'published'))).catch(error => onNotice(error.message)) }
  useEffect(load, [refreshKey])
  const advance = async (article: Article, action: 'submit' | 'approve' | 'reject' | 'publish') => {
    try {
      setWorking(article.id)
      const updated = action === 'submit' ? await api.submitArticle(article.id) : action === 'approve' ? await api.approveArticle(article.id) : action === 'reject' ? await api.rejectArticle(article.id) : await api.publishArticle(article.id)
      onNotice(`${updated.title} is now ${updated.status.replace('_', ' ')}.`)
      load()
    } catch (error) { onNotice(error instanceof Error ? error.message : 'Unable to update article status.') } finally { setWorking(null) }
  }
  if (!articles.length) return <section className="ai-runs"><h2>Editorial review</h2><p>No drafts awaiting editorial action.</p></section>
  return <section className="ai-runs"><header><h2>Editorial review</h2><button onClick={load}>Refresh</button></header>{articles.map(article => <article key={article.id}><div><b>{article.title}</b><span>{article.status.replace('_', ' ')}</span></div><small>{article.editor ? `Reviewer: ${article.editor.display_name}` : 'No reviewer assigned'} · Workflow state is persisted</small>{article.hero_url ? <img className="editorial-hero" src={article.hero_url} alt="Draft hero"/> : <div className="editorial-hero fallback">Hero image unavailable</div>}<footer>{article.status === 'draft' && <button onClick={() => void advance(article, 'submit')} disabled={working === article.id}>Submit for Review</button>}{article.status === 'under_review' && <><button onClick={() => void advance(article, 'reject')} disabled={working === article.id}>Reject</button><button className="lead-approve" onClick={() => void advance(article, 'approve')} disabled={working === article.id}>Approve</button></>}{article.status === 'approved' && <button className="lead-approve" onClick={() => void advance(article, 'publish')} disabled={working === article.id}>Publish</button>}</footer></article>)}</section>
}
