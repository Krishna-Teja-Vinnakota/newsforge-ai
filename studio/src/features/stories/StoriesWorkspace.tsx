import { type KeyboardEvent, useEffect, useMemo, useState } from 'react'
import { api } from '../../shared/api/client'
import { NotionTiptapEditor } from './editor/NotionTiptapEditor'
import type { Article, ArticleStatus, User } from '../../types'
import '../../StoriesWorkspace.css'
import '../../TagPicker.css'
import './StoryFilters.css'

type Topic = { id: string; name: string; slug: string }
type Tag = { id: string; name: string }
type Form = { title: string; dek: string; topic: string; tags: string[]; content_html: string; hero_url: string; hero_media_id: string | null }
type Transition = 'submit' | 'approve' | 'reject' | 'publish' | 'unpublish'

const statuses: ArticleStatus[] = ['draft', 'under_review', 'approved', 'rejected', 'published', 'unpublished']
const pageSizeOptions = [10, 20, 25, 30, 50]
const label = (status: ArticleStatus) => status.replace('_', ' ')
const fresh = (topic = 'general'): Form => ({ title: '', dek: '', topic, tags: [], content_html: '', hero_url: '', hero_media_id: null })
const toForm = (story: Article): Form => ({ title: story.title, dek: story.dek, topic: story.topic, tags: story.tags, content_html: story.content_html, hero_url: story.hero_url ?? '', hero_media_id: story.hero_media_id })

function StoryEditor({ story, topics, tags, user, onBack, onChanged }: { story: Article | 'new'; topics: Topic[]; tags: Tag[]; user: User; onBack: () => void; onChanged: (article: Article) => void }) {
  const [form, setForm] = useState<Form>(() => story === 'new' ? fresh(topics[0]?.slug) : toForm(story))
  const [tagInput, setTagInput] = useState('')
  const [preview, setPreview] = useState(false)
  const [notice, setNotice] = useState('')
  const [working, setWorking] = useState(false)
  const [article, setArticle] = useState<Article | null>(story === 'new' ? null : story)
  const status = article?.status ?? 'draft'
  const isReviewer = user.role === 'admin' || user.role === 'editor'
  const editable = user.role !== 'audience' && status !== 'published'

  const persist = async () => {
    if (form.title.trim().length < 5) { setNotice('A headline needs at least 5 characters.'); return null }
    const body = { ...form, content_json: article?.content_json ?? { type: 'doc', content: [] } }
    const saved = article ? await api.updateArticle(article.id, body) : await api.createArticle(body)
    setArticle(saved)
    onChanged(saved)
    return saved
  }
  const save = async (submit = false) => {
    try {
      setWorking(true); setNotice('Saving…')
      const saved = await persist()
      if (!saved) return
      if (submit) {
        const updated = await api.submitArticle(saved.id)
        setArticle(updated); onChanged(updated); setNotice('Sent for review.')
      } else setNotice('Draft saved.')
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Unable to save this story.') } finally { setWorking(false) }
  }
  const transition = async (action: Transition) => {
    if (!article) return
    try {
      setWorking(true); setNotice(`${action[0].toUpperCase()}${action.slice(1)}ing…`)
      const updated = action === 'submit' ? await api.submitArticle(article.id) : action === 'approve' ? await api.approveArticle(article.id) : action === 'reject' ? await api.rejectArticle(article.id) : action === 'publish' ? await api.publishArticle(article.id) : await api.unpublishArticle(article.id)
      setArticle(updated); onChanged(updated); setNotice(`Story is now ${label(updated.status)}.`)
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Unable to update this story.') } finally { setWorking(false) }
  }
  const addTag = () => { const value = tagInput.trim().replace(/,$/, ''); if (value && !form.tags.some(tag => tag.toLowerCase() === value.toLowerCase())) setForm(current => ({ ...current, tags: [...current.tags, value] })); setTagInput('') }
  const tagKey = (event: KeyboardEvent<HTMLInputElement>) => { if (event.key === 'Enter' || event.key === ',') { event.preventDefault(); addTag() }; if (event.key === 'Backspace' && !tagInput && form.tags.length) setForm(current => ({ ...current, tags: current.tags.slice(0, -1) })) }
  const upload = async (file?: File) => { if (!file) return; try { setWorking(true); setNotice('Uploading image…'); const media = await api.uploadHero(file); setForm(current => ({ ...current, hero_url: media.url, hero_media_id: media.id })); setNotice('Hero image added.') } catch (error) { setNotice(error instanceof Error ? error.message : 'Unable to upload the image.') } finally { setWorking(false) } }

  return <section className="full-editor"><header className="editor-top"><button type="button" onClick={onBack}>← All stories</button><span aria-live="polite">{notice}</span><div className="editor-actions"><button type="button" onClick={() => setPreview(value => !value)}>{preview ? 'Edit' : 'Preview'}</button>{editable && (status === 'draft' || status === 'rejected' || status === 'unpublished') && <><button type="button" onClick={() => void save()} disabled={working}>Save draft</button>{isReviewer && <button type="button" className="primary" onClick={() => void save(true)} disabled={working}>Send to review</button>}</>}{isReviewer && status === 'under_review' && <><button type="button" className="danger-action" onClick={() => void transition('reject')} disabled={working}>Reject</button><button type="button" className="primary" onClick={() => void transition('approve')} disabled={working}>Approve</button></>}{isReviewer && status === 'approved' && <button type="button" className="primary" onClick={() => void transition('publish')} disabled={working}>Publish</button>}{isReviewer && status === 'published' && <button type="button" onClick={() => void transition('unpublish')} disabled={working}>Unpublish</button>}</div></header>{preview ? <article className="story-preview"><p>{form.topic}</p><h1>{form.title || 'Untitled'}</h1><h2>{form.dek}</h2>{form.hero_url && <img src={form.hero_url} alt=""/>}<div dangerouslySetInnerHTML={{ __html: form.content_html || '<p>Nothing written yet.</p>' }}/></article> : <main><div className="editor-heading"><p className="eyebrow">{label(status)}</p>{!editable && <small>{status === 'published' ? 'Published stories are read-only. Unpublish to make edits.' : 'This story is read-only.'}</small>}</div><input className="editor-title" aria-label="Story headline" value={form.title} onChange={event => setForm(current => ({ ...current, title: event.target.value }))} placeholder="Untitled story" disabled={!editable}/><textarea className="editor-dek" aria-label="Story summary" value={form.dek} onChange={event => setForm(current => ({ ...current, dek: event.target.value }))} placeholder="Write a clear reader summary" disabled={!editable}/><div className="editor-properties"><label>Topic<select value={form.topic} onChange={event => setForm(current => ({ ...current, topic: event.target.value }))} disabled={!editable}>{topics.length ? topics.map(topic => <option key={topic.id} value={topic.slug}>{topic.name}</option>) : <option value={form.topic}>{form.topic}</option>}</select></label><label>Tags<div className="tag-picker">{form.tags.map(tag => <span className="story-tag" key={tag}>#{tag}{editable && <button type="button" aria-label={`Remove ${tag}`} onClick={() => setForm(current => ({ ...current, tags: current.tags.filter(item => item !== tag) }))}>×</button>}</span>)}{editable && <><input list="tag-options" value={tagInput} onChange={event => setTagInput(event.target.value)} onKeyDown={tagKey} onBlur={addTag} placeholder="Add a tag"/><datalist id="tag-options">{tags.map(tag => <option key={tag.id} value={tag.name}/>)}</datalist></>}</div></label></div><label className="hero-card" htmlFor="hero-file">{form.hero_url ? <img src={form.hero_url} alt="Hero"/> : <><b>16:9 Hero image</b><span>Click to upload, or use an image URL below</span></>}<input id="hero-file" type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={event => void upload(event.target.files?.[0])} disabled={!editable}/></label>{editable && <input className="hero-url" value={form.hero_url} onChange={event => setForm(current => ({ ...current, hero_url: event.target.value, hero_media_id: null }))} placeholder="Or paste a public image URL"/>}<NotionTiptapEditor value={form.content_html} onChange={content_html => setForm(current => ({ ...current, content_html }))} editable={editable}/></main>}</section>
}

export function StoriesWorkspace({ user }: { user: User }) {
  const [items, setItems] = useState<Article[]>([])
  const [topics, setTopics] = useState<Topic[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [filter, setFilter] = useState<ArticleStatus | 'all'>('all')
  const [editor, setEditor] = useState<Article | 'new' | null>(null)
  const [notice, setNotice] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [total, setTotal] = useState(0)
  const canAuthor = user.role !== 'audience'
  const load = () => { void api.myArticles(page, pageSize).then(result => { setItems(result.items); setTotal(result.total) }).catch(error => setNotice(error.message)); void api.topics().then(setTopics); void api.tags().then(setTags) }
  useEffect(load, [page, pageSize])
  const visible = useMemo(() => filter === 'all' ? items : items.filter(item => item.status === filter), [filter, items])
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (editor) return <StoryEditor story={editor} topics={topics} tags={tags} user={user} onBack={() => { setEditor(null); load() }} onChanged={article => setItems(current => current.some(item => item.id === article.id) ? current.map(item => item.id === article.id ? article : item) : [article, ...current])}/>
  return <section className="stories-workspace"><header className="stories-toolbar"><div><p className="eyebrow">EDITORIAL DESK</p><h1>Stories</h1><div className="story-status-filters">{(['all', ...statuses] as const).map(status => <button key={status} className={filter === status ? 'active' : ''} onClick={() => { setFilter(status); setPage(1) }}>{status === 'all' ? 'All' : label(status)}</button>)}</div></div><label className="page-size-select">Stories per page<select value={pageSize} onChange={event => { setPageSize(Number(event.target.value)); setPage(1) }}>{pageSizeOptions.map(size => <option key={size} value={size}>{size}</option>)}</select></label></header>{notice && <p className="stories-notice">{notice}</p>}<div className="stories-scroll">{canAuthor && <button type="button" className="notion-new-card" onClick={() => setEditor('new')}><span>＋</span><b>New story</b><small>Start with a blank page</small></button>}{visible.map(article => <button type="button" className="cms-story-card" key={article.id} onClick={() => setEditor(article)}><div className="story-card-hero">{article.hero_url ? <img src={article.hero_url} alt=""/> : <span>{article.topic}</span>}</div><div className="story-card-content"><span>{label(article.status)}</span><h2>{article.title}</h2><p>{article.dek || 'No summary yet'}</p><small>{article.published_at ? `Published ${new Date(article.published_at).toLocaleDateString()}` : `Last updated ${new Date(article.updated_at).toLocaleDateString()}`}</small></div></button>)}</div>{!visible.length && <p className="stories-empty">No stories match this filter.</p>}<footer className="cms-pagination"><button type="button" disabled={page === 1} onClick={() => setPage(current => current - 1)}>Previous</button><b>Page {page} of {pages}</b><button type="button" disabled={page >= pages} onClick={() => setPage(current => current + 1)}>Next</button></footer></section>
}
