import { useEffect, useMemo, useState } from 'react'
import { api } from '../../shared/api/client'
import { StoryEditor } from './StoryEditor'
import type { Article, ArticleStatus, User } from '../../types'
import '../../StoriesWorkspace.css'
import './StoryFilters.css'

type Topic = { id: string; name: string; slug: string }
type Tag = { id: string; name: string }

const statuses: ArticleStatus[] = ['draft', 'under_review', 'approved', 'rejected', 'published', 'unpublished']
const pageSizeOptions = [10, 20, 25, 30, 50]
const label = (status: ArticleStatus) => status.replace('_', ' ')

export function StoriesWorkspace({
  user,
  openArticleId,
  onOpenArticleHandled,
}: {
  user: User
  openArticleId?: string | null
  onOpenArticleHandled?: () => void
}) {
  const [items, setItems] = useState<Article[]>([])
  const [topics, setTopics] = useState<Topic[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [filter, setFilter] = useState<ArticleStatus | 'all'>('all')
  const [editor, setEditor] = useState<Article | 'new' | null>(null)
  const [notice, setNotice] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [total, setTotal] = useState(0)
  const load = () => {
    void api
      .myArticles(page, pageSize)
      .then((result) => {
        setItems(result.items)
        setTotal(result.total)
      })
      .catch((error) => setNotice(error.message))
    void api.topics().then(setTopics)
    void api.tags().then(setTags)
  }
  useEffect(load, [page, pageSize])
  useEffect(() => {
    if (!openArticleId) return
    void api
      .getArticle(openArticleId)
      .then(setEditor)
      .catch((error) => setNotice(error instanceof Error ? error.message : 'Unable to open that story.'))
      .finally(() => onOpenArticleHandled?.())
  }, [openArticleId])
  const visible = useMemo(
    () => (filter === 'all' ? items : items.filter((item) => item.status === filter)),
    [filter, items]
  )
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (editor)
    return (
      <StoryEditor
        story={editor}
        topics={topics}
        tags={tags}
        user={user}
        onBack={() => {
          setEditor(null)
          load()
        }}
        onChanged={(article) =>
          setItems((current) =>
            current.some((item) => item.id === article.id)
              ? current.map((item) => (item.id === article.id ? article : item))
              : [article, ...current]
          )
        }
      />
    )
  return (
    <section className="stories-workspace">
      <header className="stories-toolbar">
        <div>
          <p className="eyebrow">EDITORIAL DESK</p>
          <h1>Stories</h1>
          <div className="story-status-filters">
            {(['all', ...statuses] as const).map((status) => (
              <button
                key={status}
                className={filter === status ? 'active' : ''}
                onClick={() => {
                  setFilter(status)
                  setPage(1)
                }}
              >
                {status === 'all' ? 'All' : label(status)}
              </button>
            ))}
          </div>
        </div>
        <label className="page-size-select">
          Stories per page
          <select
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value))
              setPage(1)
            }}
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </header>
      {notice && <p className="stories-notice">{notice}</p>}
      <div className="stories-scroll">
        <button type="button" className="notion-new-card" onClick={() => setEditor('new')}>
          <span>＋</span>
          <b>New story</b>
          <small>Start with a blank page</small>
        </button>
        {visible.map((article) => (
          <button type="button" className="cms-story-card" key={article.id} onClick={() => setEditor(article)}>
            <div className="story-card-hero">
              {article.hero_url ? <img src={article.hero_url} alt="" /> : <span>{article.topic}</span>}
            </div>
            <div className="story-card-content">
              <span>{label(article.status)}</span>
              <h2>{article.title}</h2>
              <p>{article.dek || 'No summary yet'}</p>
              <small>
                {article.published_at
                  ? `Published ${new Date(article.published_at).toLocaleDateString()}`
                  : `Last updated ${new Date(article.updated_at).toLocaleDateString()}`}
              </small>
            </div>
          </button>
        ))}
      </div>
      {!visible.length && <p className="stories-empty">No stories match this filter.</p>}
      <footer className="cms-pagination">
        <button type="button" disabled={page === 1} onClick={() => setPage((current) => current - 1)}>
          Previous
        </button>
        <b>
          Page {page} of {pages}
        </b>
        <button type="button" disabled={page >= pages} onClick={() => setPage((current) => current + 1)}>
          Next
        </button>
      </footer>
    </section>
  )
}
