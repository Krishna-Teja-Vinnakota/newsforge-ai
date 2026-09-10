import { useEffect, useMemo, useState } from 'react'
import { api } from '../../shared/api/client'
import type { Article, ArticleStatus, User } from '../../types'
import { StoryCard } from './StoryCard'
import '../../StoriesWorkspace.css'
import './StoryFilters.css'

const statuses: ArticleStatus[] = ['draft', 'under_review', 'approved', 'rejected', 'scheduled', 'published', 'archived']

export function StoriesWorkspace({ user }: { user: User }) {
  const [items, setItems] = useState<Article[]>([])
  const [filter, setFilter] = useState<ArticleStatus | 'all' | 'unpublished'>('all')
  const [working, setWorking] = useState<string | null>(null)
  const [selected, setSelected] = useState<Article | null>(null)
  const load = () => { void api.myArticles(1, 50).then(result => setItems(result.items)) }
  useEffect(load, [])
  const visible = useMemo(() => filter === 'all' ? items : filter === 'unpublished' ? items.filter(item => item.status !== 'published') : items.filter(item => item.status === filter), [filter, items])
  const transition = async (article: Article, action: 'submit' | 'approve' | 'reject' | 'publish' | 'unpublish') => {
    try {
      setWorking(article.id)
      if (action === 'submit') await api.submitArticle(article.id)
      else if (action === 'approve') await api.approveArticle(article.id)
      else if (action === 'reject') await api.rejectArticle(article.id)
      else if (action === 'publish') await api.publishArticle(article.id)
      else await api.unpublishArticle(article.id)
      load()
    } finally { setWorking(null) }
  }
  const editor = user.role === 'admin' || user.role === 'editor'
  return <section className="stories-workspace"><header className="stories-toolbar"><div><p className="eyebrow">EDITORIAL DESK</p><h1>Stories</h1><div className="story-status-filters"><button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>All</button><button className={filter === 'unpublished' ? 'active' : ''} onClick={() => setFilter('unpublished')}>Unpublished</button>{statuses.slice(0, 5).map(status => <button key={status} className={filter === status ? 'active' : ''} onClick={() => setFilter(status)}>{status.replace('_', ' ')}</button>)}</div></div></header><div className="stories-scroll">{visible.map(article => <StoryCard key={article.id} article={article} canEdit={editor} working={working === article.id} onOpen={() => setSelected(article)} onAction={action => void transition(article, action)}/>)}</div>{selected && <div className="story-detail-backdrop" role="presentation" onClick={() => setSelected(null)}><aside className="story-detail-drawer" role="dialog" aria-modal="true" aria-label="Story details" onClick={event => event.stopPropagation()}><button onClick={() => setSelected(null)}>Close</button>{selected.hero_url ? <img src={selected.hero_url} alt=""/> : <div className="hero-card">Hero image unavailable</div>}<p className="eyebrow">{selected.status.replace('_', ' ')}</p><h2>{selected.title}</h2><p>{selected.dek}</p><div dangerouslySetInnerHTML={{ __html: selected.content_html }}/></aside></div>}</section>
}
