import { FormEvent, useEffect, useMemo, useState } from 'react'
import type { JSONContent } from '@tiptap/react'
import { ArrowUpRight, Eye, ImagePlus, Send } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { ArticlePreview } from '@/components/cms/ArticlePreview'
import { TiptapEditor } from '@/components/cms/TiptapEditor'
import { clearAccessToken, getAccessToken } from '@/services/api'
import { cmsService } from '@/services/cms'
import type { AuthUser, CmsArticle } from '@/types/cms'

const emptyDocument: JSONContent = { type: 'doc', content: [{ type: 'paragraph' }] }

export function StudioPage() {
  const navigate = useNavigate()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [articles, setArticles] = useState<CmsArticle[]>([])
  const [article, setArticle] = useState<CmsArticle | null>(null)
  const [title, setTitle] = useState('')
  const [dek, setDek] = useState('')
  const [topic, setTopic] = useState('general')
  const [tags, setTags] = useState('')
  const [contentJson, setContentJson] = useState<JSONContent>(emptyDocument)
  const [contentHtml, setContentHtml] = useState('')
  const [heroMediaId, setHeroMediaId] = useState<string | null>(null)
  const [heroUrl, setHeroUrl] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [message, setMessage] = useState('')

  const draftPayload = useMemo(
    () => ({
      title,
      dek,
      content_json: contentJson,
      content_html: contentHtml,
      topic,
      tags: tags
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean),
      hero_media_id: heroMediaId,
    }),
    [contentHtml, contentJson, dek, heroMediaId, tags, title, topic]
  )

  useEffect(() => {
    if (!getAccessToken()) {
      navigate('/login')
      return
    }
    void Promise.all([cmsService.me(), cmsService.myArticles()])
      .then(([currentUser, result]) => {
        setUser(currentUser)
        setArticles(result.items)
      })
      .catch(() => {
        clearAccessToken()
        navigate('/login')
      })
  }, [navigate])

  const selectArticle = (next: CmsArticle) => {
    setArticle(next)
    setTitle(next.title)
    setDek(next.dek)
    setTopic(next.topic)
    setTags(next.tags.join(', '))
    setContentJson(next.content_json as JSONContent)
    setContentHtml(next.content_html)
    setHeroUrl(next.hero_url)
    setHeroMediaId(next.hero_media_id)
    setMessage('')
  }
  const newArticle = () => {
    setArticle(null)
    setTitle('')
    setDek('')
    setTopic('general')
    setTags('')
    setContentJson(emptyDocument)
    setContentHtml('')
    setHeroMediaId(null)
    setHeroUrl(null)
    setMessage('New draft ready.')
  }
  const saveDraft = async (event?: FormEvent) => {
    event?.preventDefault()
    setMessage('Saving…')
    try {
      const saved = article
        ? await cmsService.updateArticle(article.id, draftPayload)
        : await cmsService.createArticle(draftPayload)
      setArticle(saved)
      setHeroUrl(saved.hero_url)
      setArticles((items) => [saved, ...items.filter((item) => item.id !== saved.id)])
      setMessage('Draft saved.')
      return saved
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'Could not save the draft.')
      return null
    }
  }
  const submit = async () => {
    const saved = article ?? (await saveDraft())
    if (!saved) return
    try {
      const updated = await cmsService.submitForReview(saved.id)
      setArticle(updated)
      setArticles((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setMessage('Sent for editorial review.')
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'Could not submit the draft.')
    }
  }
  const publish = async () => {
    if (!article) return
    try {
      const updated = await cmsService.publish(article.id)
      setArticle(updated)
      setArticles((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setMessage('Published to NewsForge.')
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'Could not publish the article.')
    }
  }
  const uploadHero = async (file?: File) => {
    if (!file) return
    try {
      const media = await cmsService.uploadMedia(file, 'hero')
      setHeroMediaId(media.id)
      setHeroUrl(media.url)
      setMessage('Hero image ready. Save the draft to attach it.')
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'Image upload failed.')
    }
  }

  return (
    <section className="studio-page">
      <div className="studio-head">
        <div>
          <p className="eyebrow">
            <span /> NewsForge Studio
          </p>
          <h1>Draft a story.</h1>
          <p>{user ? `Writing as ${user.display_name} · ${user.role}` : 'Loading your workspace…'}</p>
        </div>
        <div>
          <Link to="/" className="studio-link">
            <Eye size={16} /> View site
          </Link>
          <button
            onClick={() => {
              clearAccessToken()
              navigate('/login')
            }}
            className="studio-link"
          >
            Sign out
          </button>
        </div>
      </div>
      <div className="studio-layout">
        <aside className="studio-sidebar">
          <button onClick={newArticle} className="read-button">
            New story <ArrowUpRight size={16} />
          </button>
          <p className="eyebrow">
            <span /> Your stories
          </p>
          {articles.length === 0 ? (
            <p className="sidebar-empty">Your drafts will appear here.</p>
          ) : (
            articles.map((item) => (
              <button
                key={item.id}
                onClick={() => selectArticle(item)}
                className={article?.id === item.id ? 'story-list-item active' : 'story-list-item'}
              >
                <span>{item.status.replace('_', ' ')}</span>
                <b>{item.title}</b>
                <small>{new Date(item.updated_at).toLocaleDateString()}</small>
              </button>
            ))
          )}
        </aside>
        <form className="studio-editor" onSubmit={(event) => void saveDraft(event)}>
          <input
            className="story-title-input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Give this story a clear title"
            required
          />
          <textarea
            className="story-dek-input"
            value={dek}
            onChange={(event) => setDek(event.target.value)}
            placeholder="Write the dek — why this story matters."
          />
          <div className="studio-meta">
            <label>
              Topic
              <input value={topic} onChange={(event) => setTopic(event.target.value)} />
            </label>
            <label>
              Tags
              <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="climate, cities" />
            </label>
            <span>{article ? `Last saved ${new Date(article.updated_at).toLocaleTimeString()}` : 'New draft'}</span>
          </div>
          <div className="hero-upload">
            {heroUrl ? (
              <img src={heroUrl} alt="Story hero" />
            ) : (
              <label>
                <ImagePlus size={20} /> Add hero image
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  onChange={(event) => void uploadHero(event.target.files?.[0])}
                />
              </label>
            )}
          </div>
          <TiptapEditor
            content={contentJson}
            onChange={(json, html) => {
              setContentJson(json)
              setContentHtml(html)
            }}
          />
          <div className="studio-actions">
            <span>{message}</span>
            <button className="studio-link" type="button" onClick={() => setPreviewOpen(true)}>
              <Eye size={16} /> Preview
            </button>
            <button className="studio-link" type="submit">
              Save draft <ArrowUpRight size={16} />
            </button>
            <button
              className="read-button"
              type="button"
              onClick={() => void submit()}
              disabled={article?.status !== 'draft' && article !== null}
            >
              Send to review <Send size={16} />
            </button>
            {article?.status === 'approved' && (
              <button className="read-button" type="button" onClick={() => void publish()}>
                Publish <ArrowUpRight size={16} />
              </button>
            )}
          </div>
        </form>
      </div>
      {previewOpen && (
        <ArticlePreview
          article={{ title, dek, content_html: contentHtml, topic, hero_url: heroUrl }}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </section>
  )
}
