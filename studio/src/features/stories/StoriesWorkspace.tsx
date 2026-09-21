import { type KeyboardEvent, useEffect, useMemo, useState } from 'react'
import { api } from '../../shared/api/client'
import { NotionTiptapEditor } from './editor/NotionTiptapEditor'
import { AiReviewModal, type AiInsights, type AiProposal } from './ai/AiReviewModal'
import { ActionMenu } from '../../ActionMenu'
import type { Article, ArticleStatus, User } from '../../types'
import '../../StoriesWorkspace.css'
import '../../TagPicker.css'
import './StoryFilters.css'

type Topic = { id: string; name: string; slug: string }
type Tag = { id: string; name: string }
type Form = {
  title: string
  dek: string
  topic: string
  tags: string[]
  content_html: string
  content_json: Record<string, unknown>
  hero_url: string
  hero_media_id: string | null
  ai_insights: AiInsights | null
}
type Transition = 'submit' | 'approve' | 'reject' | 'publish' | 'unpublish'

const statuses: ArticleStatus[] = ['draft', 'under_review', 'approved', 'rejected', 'published', 'unpublished']
const pageSizeOptions = [10, 20, 25, 30, 50]
const label = (status: ArticleStatus) => status.replace('_', ' ')
const fresh = (topic = 'general'): Form => ({
  title: '',
  dek: '',
  topic,
  tags: [],
  content_html: '',
  content_json: { type: 'doc', content: [] },
  hero_url: '',
  hero_media_id: null,
  ai_insights: null,
})
const toForm = (story: Article): Form => ({
  title: story.title,
  dek: story.dek,
  topic: story.topic,
  tags: story.tags,
  content_html: story.content_html,
  content_json: story.content_json,
  hero_url: story.hero_url ?? '',
  hero_media_id: story.hero_media_id,
  ai_insights: story.ai_insights ?? null,
})

function StoryEditor({
  story,
  topics,
  tags,
  user,
  onBack,
  onChanged,
}: {
  story: Article | 'new'
  topics: Topic[]
  tags: Tag[]
  user: User
  onBack: () => void
  onChanged: (article: Article) => void
}) {
  const [form, setForm] = useState<Form>(() => (story === 'new' ? fresh(topics[0]?.slug) : toForm(story)))
  const [tagInput, setTagInput] = useState('')
  const [preview, setPreview] = useState(false)
  const [notice, setNotice] = useState('')
  const [working, setWorking] = useState(false)
  const [tone, setTone] = useState<'neutral' | 'formal' | 'conversational' | 'urgent'>('neutral')
  const [article, setArticle] = useState<Article | null>(story === 'new' ? null : story)
  const [aiProposal, setAiProposal] = useState<AiProposal | null>(null)
  const [bodyNotes, setBodyNotes] = useState('')
  const [showBodyNotes, setShowBodyNotes] = useState(false)
  const status = article?.status ?? 'draft'
  const isReviewer = user.role === 'admin' || user.role === 'editor'
  const editable = user.role !== 'audience' && status !== 'published'

  const persist = async () => {
    if (form.title.trim().length < 5) {
      setNotice('A headline needs at least 5 characters.')
      return null
    }
    const body = form
    const saved = article ? await api.updateArticle(article.id, body) : await api.createArticle(body)
    setArticle(saved)
    onChanged(saved)
    return saved
  }
  const save = async (submit = false) => {
    try {
      setWorking(true)
      setNotice('Saving…')
      const saved = await persist()
      if (!saved) return
      if (submit) {
        const updated = await api.submitArticle(saved.id)
        setArticle(updated)
        onChanged(updated)
        setNotice('Sent for review.')
      } else setNotice('Draft saved.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to save this story.')
    } finally {
      setWorking(false)
    }
  }
  const transition = async (action: Transition) => {
    if (!article) return
    try {
      setWorking(true)
      setNotice(`${action[0].toUpperCase()}${action.slice(1)}ing…`)
      const updated =
        action === 'submit'
          ? await api.submitArticle(article.id)
          : action === 'approve'
            ? await api.approveArticle(article.id)
            : action === 'reject'
              ? await api.rejectArticle(article.id)
              : action === 'publish'
                ? await api.publishArticle(article.id)
                : await api.unpublishArticle(article.id)
      setArticle(updated)
      onChanged(updated)
      setNotice(`Story is now ${label(updated.status)}.`)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to update this story.')
    } finally {
      setWorking(false)
    }
  }
  const addTag = () => {
    const value = tagInput.trim().replace(/,$/, '')
    if (value && !form.tags.some((tag) => tag.toLowerCase() === value.toLowerCase()))
      setForm((current) => ({ ...current, tags: [...current.tags, value] }))
    setTagInput('')
  }
  const tagKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      addTag()
    }
    if (event.key === 'Backspace' && !tagInput && form.tags.length)
      setForm((current) => ({ ...current, tags: current.tags.slice(0, -1) }))
  }
  const upload = async (file?: File) => {
    if (!file) return
    try {
      setWorking(true)
      setNotice('Uploading image…')
      const media = await api.uploadHero(file)
      setForm((current) => ({ ...current, hero_url: media.url, hero_media_id: media.id }))
      setNotice('Hero image added.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to upload the image.')
    } finally {
      setWorking(false)
    }
  }
  const enhanceWithAi = async () => {
    if (!article) {
      setNotice('Save this story first, then use AI enhancement.')
      return
    }
    try {
      setWorking(true)
      setNotice('Content Production Agent is drafting…')
      const run = await api.produceDraft({
        article_id: article.id,
        headline: form.title.trim() || `Latest ${form.topic.replace(/-/g, ' ')} update`,
        topic: form.topic,
        context: form.dek || `Draft a clear, verified story for the ${form.topic} desk.`,
        target_platforms: ['web'],
        ...(tone === 'neutral' ? {} : { tone }),
      })
      const output = run.output as AiProposal
      setAiProposal({
        title: output.title,
        dek: output.dek,
        content_html: output.content_html,
        content_json: output.content_json,
        hero_url: output.hero_url,
        ai_insights: output.ai_insights,
      })
      setNotice('AI proposal is ready to review.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to enhance this story.')
    } finally {
      setWorking(false)
    }
  }
  const scopedAi = async (
    action: 'headline-generate' | 'headline-grammar' | 'dek-generate' | 'dek-grammar' | 'body-rewrite' | 'body-grammar' | 'body-notes'
  ) => {
    if ((action.startsWith('dek') || action.startsWith('body')) && form.title.trim().length < 5) {
      setNotice('Add a headline first so AI has the necessary story context.')
      return
    }
    if (action === 'body-notes' && !bodyNotes.trim()) {
      setShowBodyNotes(true)
      setNotice('Add your reporting notes, then choose Notes to story again.')
      return
    }
    try {
      setWorking(true)
      setNotice('Preparing AI proposal…')
      const run = action.startsWith('headline')
        ? await api.generateHeadline({ title: form.title, topic: form.topic, context: form.dek || form.content_html, mode: action.endsWith('grammar') ? 'grammar' : 'generate' })
        : action.startsWith('dek')
          ? await api.generateDek({ dek: form.dek, title: form.title, context: form.content_html, mode: action.endsWith('grammar') ? 'grammar' : 'generate' })
          : await api.generateBody({
              content_html: form.content_html,
              title: form.title,
              dek: form.dek,
              notes: bodyNotes,
              mode: action === 'body-notes' ? 'notes_to_story' : action === 'body-grammar' ? 'grammar' : 'rewrite',
            })
      const output = run.output as AiProposal
      setAiProposal(action.startsWith('headline') ? { title: output.title } : action.startsWith('dek') ? { dek: output.dek } : { content_html: output.content_html, content_json: output.content_json })
      setNotice('AI proposal is ready to review.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to prepare an AI proposal.')
    } finally {
      setWorking(false)
    }
  }
  const suggestTags = async () => {
    if (form.title.trim().length < 5) {
      setNotice('Add a headline first so AI can suggest relevant tags.')
      return
    }
    try {
      setWorking(true)
      setNotice('Finding relevant tags…')
      const run = await api.suggestTags({ title: form.title, dek: form.dek, content_html: form.content_html, topic: form.topic, existing_tags: form.tags })
      const output = run.output as { suggested_tags?: string[] }
      setForm((current) => ({ ...current, ai_insights: { ...(current.ai_insights ?? {}), suggested_tags: output.suggested_tags ?? [] } }))
      setNotice('Tag suggestions are ready to review.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to suggest tags.')
    } finally {
      setWorking(false)
    }
  }

  return (
    <section className="full-editor">
      <header className="editor-top">
        <button type="button" onClick={onBack}>
          ← All stories
        </button>
        <span aria-live="polite">{notice}</span>
        <div className="editor-actions">
          <button type="button" onClick={() => setPreview((value) => !value)}>
            {preview ? 'Edit' : 'Preview'}
          </button>
          {editable && (status === 'draft' || status === 'rejected' || status === 'unpublished') && (
            <>
              {article && (
                <>
                  <select
                    aria-label="AI writing tone"
                    value={tone}
                    onChange={(event) => setTone(event.target.value as typeof tone)}
                    disabled={working}
                  >
                    <option value="neutral">Neutral</option>
                    <option value="formal">Formal</option>
                    <option value="conversational">Conversational</option>
                    <option value="urgent">Breaking / urgent</option>
                  </select>
                  <button type="button" onClick={() => void enhanceWithAi()} disabled={working}>
                    {working ? 'Enhancing…' : 'AI enhancement'}
                  </button>
                </>
              )}
              <button type="button" onClick={() => void save()} disabled={working}>
                Save draft
              </button>
              {isReviewer && (
                <button type="button" className="primary" onClick={() => void save(true)} disabled={working}>
                  Send to review
                </button>
              )}
            </>
          )}
          {isReviewer && status === 'under_review' && (
            <>
              <button
                type="button"
                className="danger-action"
                onClick={() => void transition('reject')}
                disabled={working}
              >
                Reject
              </button>
              <button type="button" className="primary" onClick={() => void transition('approve')} disabled={working}>
                Approve
              </button>
            </>
          )}
          {isReviewer && status === 'approved' && (
            <button type="button" className="primary" onClick={() => void transition('publish')} disabled={working}>
              Publish
            </button>
          )}
          {isReviewer && status === 'published' && (
            <button type="button" onClick={() => void transition('unpublish')} disabled={working}>
              Unpublish
            </button>
          )}
        </div>
      </header>
      {preview ? (
        <article className="story-preview">
          <p>{form.topic}</p>
          <h1>{form.title || 'Untitled'}</h1>
          <h2>{form.dek}</h2>
          {form.hero_url && <img src={form.hero_url} alt="" />}
          <div dangerouslySetInnerHTML={{ __html: form.content_html || '<p>Nothing written yet.</p>' }} />
        </article>
      ) : (
        <main>
          <div className="editor-heading">
            <p className="eyebrow">{label(status)}</p>
            {!editable && (
              <small>
                {status === 'published'
                  ? 'Published stories are read-only. Unpublish to make edits.'
                  : 'This story is read-only.'}
              </small>
            )}
          </div>
          <input
            className="editor-title"
            aria-label="Story headline"
            value={form.title}
            onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
            placeholder="Untitled story"
            disabled={!editable}
          />
          {editable && (
            <div className="field-ai-actions">
              <ActionMenu
                label="AI headline actions"
                disabled={working}
                items={[
                  { key: 'generate', label: 'Generate', onSelect: () => void scopedAi('headline-generate') },
                  { key: 'grammar', label: 'Fix grammar', onSelect: () => void scopedAi('headline-grammar'), disabled: !form.title.trim() },
                ]}
              />
            </div>
          )}
          <textarea
            className="editor-dek"
            aria-label="Story summary"
            value={form.dek}
            onChange={(event) => setForm((current) => ({ ...current, dek: event.target.value }))}
            placeholder="Write a clear reader summary"
            disabled={!editable}
          />
          {editable && (
            <div className="field-ai-actions">
              <ActionMenu
                label="AI summary actions"
                disabled={working}
                items={[
                  { key: 'generate', label: 'Generate', onSelect: () => void scopedAi('dek-generate') },
                  { key: 'grammar', label: 'Fix grammar', onSelect: () => void scopedAi('dek-grammar'), disabled: !form.dek.trim() },
                ]}
              />
            </div>
          )}
          <div className="editor-properties">
            <label>
              Topic
              <select
                value={form.topic}
                onChange={(event) => setForm((current) => ({ ...current, topic: event.target.value }))}
                disabled={!editable}
              >
                {topics.length ? (
                  topics.map((topic) => (
                    <option key={topic.id} value={topic.slug}>
                      {topic.name}
                    </option>
                  ))
                ) : (
                  <option value={form.topic}>{form.topic}</option>
                )}
              </select>
            </label>
            <label>
              <span className="tags-label">
                Tags
                {editable && (
                  <ActionMenu
                    label="AI tag actions"
                    align="end"
                    disabled={working || form.tags.length >= 10}
                    items={[{ key: 'suggest', label: 'Suggest with AI', onSelect: () => void suggestTags() }]}
                  />
                )}
              </span>
              <div className="tag-picker">
                {form.tags.map((tag) => (
                  <span className="story-tag" key={tag}>
                    #{tag}
                    {editable && (
                      <button
                        type="button"
                        aria-label={`Remove ${tag}`}
                        onClick={() =>
                          setForm((current) => ({ ...current, tags: current.tags.filter((item) => item !== tag) }))
                        }
                      >
                        ×
                      </button>
                    )}
                  </span>
                ))}
                {(form.ai_insights?.suggested_tags ?? []).filter((tag) => !form.tags.some((item) => item.toLowerCase() === tag.toLowerCase())).map((tag) => (
                  <span className="story-tag story-tag--suggested" key={`suggested-${tag}`}>
                    #{tag}
                    {editable && <>
                      <button type="button" aria-label={`Accept ${tag}`} onClick={() => setForm((current) => ({ ...current, tags: current.tags.length < 10 ? [...current.tags, tag] : current.tags }))}>✓</button>
                      <button type="button" aria-label={`Reject ${tag}`} onClick={() => setForm((current) => ({ ...current, ai_insights: { ...(current.ai_insights ?? {}), suggested_tags: (current.ai_insights?.suggested_tags ?? []).filter((item) => item !== tag) } }))}>×</button>
                    </>}
                  </span>
                ))}
                {editable && (
                  <>
                    <input
                      list="tag-options"
                      value={tagInput}
                      onChange={(event) => setTagInput(event.target.value)}
                      onKeyDown={tagKey}
                      onBlur={addTag}
                      placeholder="Add a tag"
                    />
                    <datalist id="tag-options">
                      {tags.map((tag) => (
                        <option key={tag.id} value={tag.name} />
                      ))}
                    </datalist>
                  </>
                )}
              </div>
            </label>
          </div>
          <label className="hero-card" htmlFor="hero-file">
            {form.hero_url ? (
              <img src={form.hero_url} alt="Hero" />
            ) : (
              <>
                <b>16:9 Hero image</b>
                <span>Click to upload, or use an image URL below</span>
              </>
            )}
            <input
              id="hero-file"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              onChange={(event) => void upload(event.target.files?.[0])}
              disabled={!editable}
            />
          </label>
          {editable && (
            <input
              className="hero-url"
              value={form.hero_url}
              onChange={(event) =>
                setForm((current) => ({ ...current, hero_url: event.target.value, hero_media_id: null }))
              }
              placeholder="Or paste a public image URL"
            />
          )}
          <NotionTiptapEditor
            value={form.content_html}
            onChange={(content_html) => setForm((current) => ({ ...current, content_html }))}
            editable={editable}
          />
          {editable && (
            <section className="body-ai-actions">
              <div>
                <ActionMenu
                  label="AI story tools"
                  disabled={working}
                  items={[
                    { key: 'rewrite', label: 'Rewrite', onSelect: () => void scopedAi('body-rewrite') },
                    { key: 'grammar', label: 'Fix grammar', onSelect: () => void scopedAi('body-grammar'), disabled: !form.content_html },
                    { key: 'notes', label: 'Notes to story', onSelect: () => setShowBodyNotes((value) => !value) },
                  ]}
                />
              </div>
              {showBodyNotes && <div className="body-notes"><textarea value={bodyNotes} onChange={(event) => setBodyNotes(event.target.value)} placeholder="Paste reporter notes, facts, and attributed quotes…" /><button type="button" className="primary" onClick={() => void scopedAi('body-notes')} disabled={working || !bodyNotes.trim()}>Create proposal</button></div>}
            </section>
          )}
          {form.ai_insights && (
            <section className="ai-insights-card">
              <p className="eyebrow">AI PRODUCTION INSIGHTS</p>
              <div className="ai-insights-grid">
                <div>
                  <b>Reporter brief</b>
                  <p>
                    {form.ai_insights.reporter_brief?.background ||
                      'Review the generated draft against its verified source context.'}
                  </p>
                  {form.ai_insights.reporter_brief?.key_questions?.length ? (
                    <small>Verify: {form.ai_insights.reporter_brief.key_questions.join(' · ')}</small>
                  ) : null}
                </div>
                <div>
                  <b>Suggested distribution</b>
                  <p>{form.ai_insights.push_notification || 'No push suggestion available.'}</p>
                  {form.ai_insights.social_posts?.[0] ? <small>{form.ai_insights.social_posts[0]}</small> : null}
                </div>
                <div>
                  <b>Provenance</b>
                  <small>{form.ai_insights.provenance?.join(' · ') || 'Editor-supplied context — verify before publication.'}</small>
                </div>
              </div>
            </section>
          )}
        </main>
      )}
      {aiProposal && (
        <AiReviewModal
          proposal={aiProposal}
          current={{
            title: form.title,
            dek: form.dek,
            content_html: form.content_html,
            hero_url: form.hero_url,
          }}
          onApply={(fields, insights) => {
            setForm((current) => {
              const next = { ...current }
              fields.forEach((field) => {
                const value = aiProposal[field]
                if (value !== undefined) next[field] = value
                if (field === 'content_html' && aiProposal.content_json) next.content_json = aiProposal.content_json
              })
              if (insights) next.ai_insights = insights
              return next
            })
            setAiProposal(null)
            setNotice('Selected AI changes applied locally. Save the draft when ready.')
          }}
          onClose={() => {
            setAiProposal(null)
            setNotice('AI proposal discarded. Your draft is unchanged.')
          }}
        />
      )}
    </section>
  )
}

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
  const canAuthor = user.role !== 'audience'
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
        {canAuthor && (
          <button type="button" className="notion-new-card" onClick={() => setEditor('new')}>
            <span>＋</span>
            <b>New story</b>
            <small>Start with a blank page</small>
          </button>
        )}
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
