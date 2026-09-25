import { type KeyboardEvent, useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Circle,
  FileText,
  ImageIcon,
  Info,
  Lightbulb,
  Pencil,
  Sparkles,
  Tag,
} from 'lucide-react'
import { api, type ChatMessage } from '../../shared/api/client'
import { NotionTiptapEditor } from './editor/NotionTiptapEditor'
import { AiReviewModal, type AiInsights, type AiProposal } from './ai/AiReviewModal'
import { HeadlinePicker } from './ai/HeadlinePicker'
import { StoryChatLauncher } from './ai/StoryChatLauncher'
import { StoryChatPanel, type StoryChatMessage } from './ai/StoryChatPanel'
import { ActionMenu } from '../../ActionMenu'
import type { Article, User } from '../../types'
import { STORY_STAGES, StoryWizardStepper, type StoryStage } from './StoryWizardStepper'
import '../../StoriesWorkspace.css'
import '../../TagPicker.css'

type Topic = { id: string; name: string; slug: string }
type TagItem = { id: string; name: string }
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
type Tone = 'neutral' | 'formal' | 'conversational' | 'urgent'

const label = (status: string) => status.replace('_', ' ')
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
const hasBody = (html: string) => html.replace(/<[^>]+>/g, '').trim().length > 40
const topicLabel = (topics: Topic[], slug: string) =>
  topics.find((topic) => topic.slug === slug)?.name ?? slug.replace(/-/g, ' ')

export function StoryEditor({
  story,
  topics,
  tags,
  user,
  onBack,
  onChanged,
}: {
  story: Article | 'new'
  topics: Topic[]
  tags: TagItem[]
  user: User
  onBack: () => void
  onChanged: (article: Article) => void
}) {
  const [form, setForm] = useState<Form>(() => (story === 'new' ? fresh(topics[0]?.slug) : toForm(story)))
  const [tagInput, setTagInput] = useState('')
  const [stage, setStage] = useState<StoryStage>(() => {
    if (story === 'new') return 'details'
    if (story.status === 'published' || story.status === 'under_review' || story.status === 'approved') return 'review'
    return 'details'
  })
  const [notice, setNotice] = useState('')
  const [working, setWorking] = useState(false)
  const [tone, setTone] = useState<Tone>('neutral')
  const [article, setArticle] = useState<Article | null>(story === 'new' ? null : story)
  const [aiProposal, setAiProposal] = useState<AiProposal | null>(null)
  const [bodyNotes, setBodyNotes] = useState('')
  const [showBodyNotes, setShowBodyNotes] = useState(false)
  const [chatMessages, setChatMessages] = useState<StoryChatMessage[]>([])
  const [showChat, setShowChat] = useState(false)
  const [headlineOptions, setHeadlineOptions] = useState<string[] | null>(null)
  const [chatSending, setChatSending] = useState(false)
  const [chatError, setChatError] = useState('')
  const status = article?.status ?? 'draft'
  const isReviewer = user.role === 'admin' || user.role === 'editor'
  const editable = user.role !== 'audience' && status !== 'published'
  const stageIndex = STORY_STAGES.findIndex((item) => item.id === stage)
  const chatReady = {
    saved: Boolean(article),
    headline: form.title.trim().length >= 5,
    body: hasBody(form.content_html),
  }
  const canRefineChat = chatReady.saved && chatReady.headline && chatReady.body
  const completed = useMemo(
    () => ({
      details: hasBody(form.content_html),
      packaging: form.title.trim().length >= 5 && Boolean(form.dek.trim()),
      review: status === 'under_review' || status === 'approved' || status === 'published',
    }),
    [form.title, form.dek, form.content_html, status]
  )

  useEffect(() => {
    if (!editable) {
      setShowChat(false)
      if (story !== 'new') setStage('review')
    }
  }, [editable, story])

  const persist = async () => {
    if (form.title.trim().length < 5) {
      setNotice('A headline needs at least 5 characters.')
      setStage('packaging')
      return null
    }
    const saved = article ? await api.updateArticle(article.id, form) : await api.createArticle(form)
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
        setStage('review')
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
      setNotice('Save this story first, then generate a draft with AI.')
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
      setNotice(error instanceof Error ? error.message : 'Unable to generate a draft.')
    } finally {
      setWorking(false)
    }
  }
  const scopedAi = async (
    action:
      | 'headline-generate'
      | 'headline-grammar'
      | 'dek-generate'
      | 'dek-grammar'
      | 'body-rewrite'
      | 'body-grammar'
      | 'body-notes'
  ) => {
    if ((action.startsWith('dek') || action.startsWith('body')) && form.title.trim().length < 5) {
      setNotice('Add a headline first so AI has the necessary story context.')
      setStage('packaging')
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
        ? await api.generateHeadline({
            title: form.title,
            topic: form.topic,
            context: form.dek || form.content_html,
            mode: action.endsWith('grammar') ? 'grammar' : 'generate',
          })
        : action.startsWith('dek')
          ? await api.generateDek({
              dek: form.dek,
              title: form.title,
              context: form.content_html,
              mode: action.endsWith('grammar') ? 'grammar' : 'generate',
            })
          : await api.generateBody({
              content_html: form.content_html,
              title: form.title,
              dek: form.dek,
              notes: bodyNotes,
              mode: action === 'body-notes' ? 'notes_to_story' : action === 'body-grammar' ? 'grammar' : 'rewrite',
            })
      const output = run.output as AiProposal
      setAiProposal(
        action.startsWith('headline')
          ? { title: output.title }
          : action.startsWith('dek')
            ? { dek: output.dek }
            : { content_html: output.content_html, content_json: output.content_json }
      )
      setNotice('AI proposal is ready to review.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to prepare an AI proposal.')
    } finally {
      setWorking(false)
    }
  }
  const suggestHeadlines = async () => {
    if (!form.title.trim() && !form.dek.trim() && !form.content_html.trim()) {
      setNotice('Add a working headline, summary or body so AI has context for headline options.')
      return
    }
    try {
      setWorking(true)
      setNotice('Drafting three headline options…')
      const run = await api.generateHeadline({
        title: form.title,
        topic: form.topic,
        context: form.dek || form.content_html,
        mode: 'options',
      })
      const output = run.output as { title?: string; options?: string[] }
      const options = output.options?.length ? output.options : output.title ? [output.title] : []
      if (!options.length) throw new Error('No headline options were returned.')
      setHeadlineOptions(options)
      setNotice('Pick a headline, then click to update.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to suggest headlines.')
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
      const run = await api.suggestTags({
        title: form.title,
        dek: form.dek,
        content_html: form.content_html,
        topic: form.topic,
        existing_tags: form.tags,
      })
      const output = run.output as { suggested_tags?: string[] }
      setForm((current) => ({
        ...current,
        ai_insights: { ...(current.ai_insights ?? {}), suggested_tags: output.suggested_tags ?? [] },
      }))
      setNotice('Tag suggestions are ready to review.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to suggest tags.')
    } finally {
      setWorking(false)
    }
  }
  const sendChatMessage = async (text: string): Promise<boolean> => {
    const message = text.trim()
    if (!message || chatSending) return false
    const baseHtml = form.content_html
    const history: ChatMessage[] = chatMessages.map(({ role, content }) => ({ role, content }))
    const pending: StoryChatMessage = { role: 'user', content: message }
    setChatMessages((current) => [...current, pending])
    setChatError('')
    try {
      setChatSending(true)
      const run = await api.chatAboutStory({
        title: form.title,
        dek: form.dek,
        content_html: baseHtml,
        history,
        message,
      })
      const output = run.output as {
        reply?: string
        title?: string | null
        dek?: string | null
        content_html?: string | null
      }
      const proposal = {
        ...(typeof output.title === 'string' ? { title: output.title } : {}),
        ...(typeof output.dek === 'string' ? { dek: output.dek } : {}),
        ...(typeof output.content_html === 'string' ? { content_html: output.content_html } : {}),
      }
      setChatMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: output.reply || "I couldn't process that — try rephrasing your request.",
          ...(Object.keys(proposal).length ? { proposal, baseHtml } : {}),
        },
      ])
      return true
    } catch (error) {
      setChatMessages((current) => current.filter((item) => item !== pending))
      setChatError(error instanceof Error ? error.message : 'Unable to send your chat message.')
      return false
    } finally {
      setChatSending(false)
    }
  }

  const goBack = () => {
    if (stageIndex <= 0) onBack()
    else setStage(STORY_STAGES[stageIndex - 1].id)
  }
  const goNext = () => {
    if (stage === 'packaging' && form.title.trim().length < 5) {
      setNotice('Add a headline of at least 5 characters before continuing.')
      return
    }
    if (stageIndex < STORY_STAGES.length - 1) setStage(STORY_STAGES[stageIndex + 1].id)
  }

  const pageTitle = form.title.trim() || (story === 'new' ? 'Untitled story' : 'Edit story')

  return (
    <section className="full-editor story-wizard">
      <header className="editor-top">
        <button type="button" className="ghost-back" onClick={onBack}>
          <ArrowLeft size={16} /> All stories
        </button>
        <div className="editor-top-meta">
          <p className="eyebrow">{label(status)}</p>
          <h1>{pageTitle}</h1>
        </div>
        <span className="editor-notice" aria-live="polite">
          {notice}
        </span>
      </header>

      <div className="story-wizard-body">
        <StoryWizardStepper stage={stage} completed={completed} onSelect={setStage} />

        {!editable && (
          <p className="story-readonly-banner">
            {status === 'published'
              ? 'Published stories are read-only. Unpublish from Review to make edits.'
              : 'This story is read-only.'}
          </p>
        )}

        {stage === 'details' && (
          <div className="wizard-stage wizard-stage--details">
            <div className="wizard-draft-main">
              <div className="wizard-panel wizard-panel--editor">
                <div className="wizard-panel-head">
                  <div>
                    <p className="eyebrow">STAGE 1</p>
                    <h2>Story details</h2>
                    <p>Write and refine the body. Packaging comes next.</p>
                  </div>
                </div>
                <NotionTiptapEditor
                  value={form.content_html}
                  onChange={(content_html) => setForm((current) => ({ ...current, content_html }))}
                  editable={editable}
                  toolbarEnd={
                    editable ? (
                      <ActionMenu
                        label="AI writing tools"
                        variant="sparkle"
                        align="end"
                        disabled={working}
                        items={[
                          { key: 'rewrite', label: 'Rewrite', onSelect: () => void scopedAi('body-rewrite') },
                          {
                            key: 'grammar',
                            label: 'Fix grammar',
                            onSelect: () => void scopedAi('body-grammar'),
                            disabled: !form.content_html,
                          },
                          {
                            key: 'notes',
                            label: 'Notes to story',
                            onSelect: () => setShowBodyNotes((value) => !value),
                          },
                        ]}
                      />
                    ) : undefined
                  }
                />
                {editable && showBodyNotes && (
                  <section className="body-ai-actions">
                    <div className="body-notes">
                      <textarea
                        value={bodyNotes}
                        onChange={(event) => setBodyNotes(event.target.value)}
                        placeholder="Paste reporter notes, facts, and attributed quotes…"
                      />
                      <button
                        type="button"
                        className="primary"
                        onClick={() => void scopedAi('body-notes')}
                        disabled={working || !bodyNotes.trim()}
                      >
                        Create proposal
                      </button>
                    </div>
                  </section>
                )}
              </div>
            </div>

            <aside className="wizard-draft-aside">
              <div className="wizard-side-card">
                <div className="wizard-side-card-head">
                  <h3>
                    <FileText size={16} /> Packaging snapshot
                  </h3>
                  {editable && (
                    <button type="button" className="text-link" onClick={() => setStage('packaging')}>
                      <Pencil size={13} /> Edit packaging
                    </button>
                  )}
                </div>
                <ul className="brief-meta-list">
                  <li>
                    <Sparkles size={14} />
                    <div>
                      <span>Headline</span>
                      <b>{form.title.trim() || 'Untitled story'}</b>
                    </div>
                  </li>
                  <li>
                    <Tag size={14} />
                    <div>
                      <span>Topic</span>
                      <b>{topicLabel(topics, form.topic)}</b>
                    </div>
                    {form.tags[0] && <em>{form.tags[0]}</em>}
                  </li>
                  <li className="brief-meta-hero">
                    <ImageIcon size={14} />
                    <div>
                      <span>Hero</span>
                      <b>{form.hero_url ? 'Image attached' : 'No hero image'}</b>
                    </div>
                    {form.hero_url ? (
                      <img className="brief-thumb" src={form.hero_url} alt="" />
                    ) : (
                      <span className="brief-thumb brief-thumb--empty" aria-hidden />
                    )}
                  </li>
                </ul>
              </div>

              {editable && (
                <div className="wizard-side-card wizard-side-card--ai">
                  <div className="wizard-side-card-head">
                    <h3>
                      <Sparkles size={16} /> AI desk
                      <Info size={14} className="muted-icon" aria-hidden />
                    </h3>
                  </div>
                  <p className="wizard-side-copy">
                    Generate a full draft from notes, or open chat to refine specific passages.
                  </p>
                  <div className="ai-generate-banner">
                    <div className="ai-generate-banner-copy">
                      <Lightbulb size={18} />
                      <div>
                        <b>Generate draft with AI</b>
                        <small>Uses your packaging, tone, and saved story context.</small>
                      </div>
                    </div>
                    <select
                      aria-label="AI writing tone"
                      value={tone}
                      onChange={(event) => setTone(event.target.value as Tone)}
                      disabled={working || !article}
                    >
                      <option value="neutral">Neutral</option>
                      <option value="formal">Formal</option>
                      <option value="conversational">Conversational</option>
                      <option value="urgent">Breaking / urgent</option>
                    </select>
                    <button
                      type="button"
                      className="generate-draft-btn"
                      onClick={() => void enhanceWithAi()}
                      disabled={working || !article}
                    >
                      <Sparkles size={16} />
                      {working ? 'Generating…' : 'Generate draft'}
                    </button>
                    {!article && <p className="wizard-side-hint">Save a draft once to unlock AI draft generation.</p>}
                  </div>

                  <div className="refine-ready-block">
                    <p className="refine-ready-title">Refine story chat unlocks when:</p>
                    <ul className="refine-ready-list">
                      <li className={chatReady.saved ? 'is-ready' : undefined}>
                        {chatReady.saved ? <CheckCircle2 size={15} /> : <Circle size={15} />}
                        <span>Story saved</span>
                      </li>
                      <li className={chatReady.headline ? 'is-ready' : undefined}>
                        {chatReady.headline ? <CheckCircle2 size={15} /> : <Circle size={15} />}
                        <span>Headline ready (5+ chars)</span>
                      </li>
                      <li className={chatReady.body ? 'is-ready' : undefined}>
                        {chatReady.body ? <CheckCircle2 size={15} /> : <Circle size={15} />}
                        <span>Body drafted</span>
                      </li>
                    </ul>
                    <button
                      type="button"
                      className="secondary-wide"
                      onClick={() => setShowChat(true)}
                      disabled={!canRefineChat}
                    >
                      Open refine chat
                    </button>
                  </div>
                </div>
              )}
            </aside>
          </div>
        )}

        {stage === 'packaging' && (
          <div className="wizard-stage wizard-stage--packaging">
            <div className="wizard-panel">
              <div className="wizard-panel-head">
                <div>
                  <p className="eyebrow">STAGE 2</p>
                  <h2>Headline & Summary</h2>
                  <p>Set the headline, summary, topic, tags, and hero image.</p>
                </div>
              </div>

              <label className="wizard-field">
                Headline
                <div className="ai-field">
                  <textarea
                    className="packaging-headline"
                    aria-label="Story headline"
                    value={form.title}
                    onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                    placeholder="Write a clear, specific headline"
                    disabled={!editable}
                    rows={2}
                  />
                  {editable && (
                    <button
                      type="button"
                      className="ai-field-trigger"
                      aria-label="Generate headline options"
                      title="Generate headline options"
                      disabled={working}
                      onClick={() => void suggestHeadlines()}
                    >
                      <Sparkles size={15} />
                    </button>
                  )}
                </div>
              </label>
              <div className={`headline-picker-shell${headlineOptions ? ' is-open' : ''}`}>
                {editable && headlineOptions && (
                  <HeadlinePicker
                    options={headlineOptions}
                    current={form.title}
                    disabled={working}
                    onRegenerate={() => void suggestHeadlines()}
                    onClose={() => setHeadlineOptions(null)}
                    onUpdate={(headline) => {
                      setForm((current) => ({ ...current, title: headline }))
                      setHeadlineOptions(null)
                      setNotice('Headline updated. Save the draft to keep it.')
                    }}
                  />
                )}
              </div>

              <label className="wizard-field">
                Reader summary
                <div className="ai-field">
                  <textarea
                    className="packaging-dek"
                    aria-label="Story summary"
                    value={form.dek}
                    onChange={(event) => setForm((current) => ({ ...current, dek: event.target.value }))}
                    placeholder="Write a clear reader summary"
                    disabled={!editable}
                    rows={3}
                  />
                  {editable && (
                    <button
                      type="button"
                      className="ai-field-trigger"
                      aria-label="Generate summary"
                      title="Generate summary"
                      disabled={working}
                      onClick={() => void scopedAi('dek-generate')}
                    >
                      <Sparkles size={15} />
                    </button>
                  )}
                </div>
              </label>

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
                  <span className="tags-label">Tags</span>
                  <div className="tag-picker">
                    {form.tags.map((tag) => (
                      <span className="story-tag" key={tag}>
                        #{tag}
                        {editable && (
                          <button
                            type="button"
                            aria-label={`Remove ${tag}`}
                            onClick={() =>
                              setForm((current) => ({
                                ...current,
                                tags: current.tags.filter((item) => item !== tag),
                              }))
                            }
                          >
                            ×
                          </button>
                        )}
                      </span>
                    ))}
                    {(form.ai_insights?.suggested_tags ?? [])
                      .filter((tag) => !form.tags.some((item) => item.toLowerCase() === tag.toLowerCase()))
                      .map((tag) => (
                        <span className="story-tag story-tag--suggested" key={`suggested-${tag}`}>
                          #{tag}
                          {editable && (
                            <>
                              <button
                                type="button"
                                aria-label={`Accept ${tag}`}
                                onClick={() =>
                                  setForm((current) => ({
                                    ...current,
                                    tags: current.tags.length < 10 ? [...current.tags, tag] : current.tags,
                                  }))
                                }
                              >
                                ✓
                              </button>
                              <button
                                type="button"
                                aria-label={`Reject ${tag}`}
                                onClick={() =>
                                  setForm((current) => ({
                                    ...current,
                                    ai_insights: {
                                      ...(current.ai_insights ?? {}),
                                      suggested_tags: (current.ai_insights?.suggested_tags ?? []).filter(
                                        (item) => item !== tag
                                      ),
                                    },
                                  }))
                                }
                              >
                                ×
                              </button>
                            </>
                          )}
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
                    <ImageIcon size={22} />
                    <b>Hero image</b>
                    <span>Upload a 16:9 image, or paste a URL below</span>
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
            </div>

            <aside className="wizard-draft-aside">
              <div className="wizard-side-card">
                <div className="wizard-side-card-head">
                  <h3>Workflow</h3>
                </div>
                <dl className="review-status-list">
                  <div>
                    <dt>Status</dt>
                    <dd className="status-pill">{label(status)}</dd>
                  </div>
                  <div>
                    <dt>Headline</dt>
                    <dd>{form.title.trim().length >= 5 ? 'Ready' : 'Needs work'}</dd>
                  </div>
                  <div>
                    <dt>Summary</dt>
                    <dd>{form.dek.trim() ? 'Ready' : 'Needs work'}</dd>
                  </div>
                  <div>
                    <dt>Body</dt>
                    <dd>{hasBody(form.content_html) ? 'Ready' : 'Needs work'}</dd>
                  </div>
                  <div>
                    <dt>Hero</dt>
                    <dd>{form.hero_url ? 'Attached' : 'Optional'}</dd>
                  </div>
                </dl>
              </div>

              {editable && (
                <div className="wizard-side-card wizard-side-card--ai">
                  <div className="wizard-side-card-head">
                    <h3>
                      <Sparkles size={16} /> AI desk
                      <Info size={14} className="muted-icon" aria-hidden />
                    </h3>
                  </div>
                  <p className="wizard-side-copy">Generate packaging fields from your story details.</p>
                  <div className="ai-desk-actions">
                    <button type="button" onClick={() => void suggestHeadlines()} disabled={working}>
                      Suggest 3 headlines
                    </button>
                    <button type="button" onClick={() => void scopedAi('headline-generate')} disabled={working}>
                      Generate headline
                    </button>
                    <button
                      type="button"
                      onClick={() => void scopedAi('headline-grammar')}
                      disabled={working || !form.title.trim()}
                    >
                      Fix headline grammar
                    </button>
                    <button type="button" onClick={() => void scopedAi('dek-generate')} disabled={working}>
                      Generate summary
                    </button>
                    <button
                      type="button"
                      onClick={() => void scopedAi('dek-grammar')}
                      disabled={working || !form.dek.trim()}
                    >
                      Fix summary grammar
                    </button>
                    <button
                      type="button"
                      onClick={() => void suggestTags()}
                      disabled={working || form.tags.length >= 10}
                    >
                      Suggest tags
                    </button>
                  </div>
                </div>
              )}
            </aside>
          </div>
        )}

        {stage === 'review' && (
          <div className="wizard-stage wizard-stage--review">
            <div className="wizard-panel review-preview-panel">
              <div className="wizard-panel-head">
                <div>
                  <p className="eyebrow">STAGE 3</p>
                  <h2>Review story</h2>
                  <p>Check the full package before submitting or publishing.</p>
                </div>
                {editable && (
                  <button type="button" className="text-link" onClick={() => setStage('details')}>
                    <Pencil size={13} /> Continue editing
                  </button>
                )}
              </div>
              <article className="story-preview story-preview--embedded">
                <p>{topicLabel(topics, form.topic)}</p>
                <h1>{form.title || 'Untitled'}</h1>
                <h2>{form.dek}</h2>
                {form.tags.length > 0 && (
                  <div className="brief-tag-row">
                    {form.tags.map((tag) => (
                      <span key={tag}>#{tag}</span>
                    ))}
                  </div>
                )}
                {form.hero_url && <img src={form.hero_url} alt="" />}
                <div dangerouslySetInnerHTML={{ __html: form.content_html || '<p>Nothing written yet.</p>' }} />
              </article>
            </div>

            <aside className="wizard-draft-aside">
              <div className="wizard-side-card">
                <div className="wizard-side-card-head">
                  <h3>Workflow</h3>
                </div>
                <dl className="review-status-list">
                  <div>
                    <dt>Status</dt>
                    <dd className="status-pill">{label(status)}</dd>
                  </div>
                  <div>
                    <dt>Headline</dt>
                    <dd>{form.title.trim().length >= 5 ? 'Ready' : 'Needs work'}</dd>
                  </div>
                  <div>
                    <dt>Body</dt>
                    <dd>{hasBody(form.content_html) ? 'Ready' : 'Needs work'}</dd>
                  </div>
                  <div>
                    <dt>Hero</dt>
                    <dd>{form.hero_url ? 'Attached' : 'Optional'}</dd>
                  </div>
                </dl>
                {isReviewer && status === 'under_review' && (
                  <div className="review-actions">
                    <button
                      type="button"
                      className="danger-action"
                      onClick={() => void transition('reject')}
                      disabled={working}
                    >
                      Reject
                    </button>
                    <button
                      type="button"
                      className="primary"
                      onClick={() => void transition('approve')}
                      disabled={working}
                    >
                      Approve
                    </button>
                  </div>
                )}
                {isReviewer && status === 'approved' && (
                  <button
                    type="button"
                    className="primary full-width"
                    onClick={() => void transition('publish')}
                    disabled={working}
                  >
                    Publish
                  </button>
                )}
                {isReviewer && status === 'published' && (
                  <button
                    type="button"
                    className="full-width"
                    onClick={() => void transition('unpublish')}
                    disabled={working}
                  >
                    Unpublish
                  </button>
                )}
              </div>

              {form.ai_insights && (
                <div className="wizard-side-card">
                  <div className="wizard-side-card-head">
                    <h3>AI production insights</h3>
                  </div>
                  <div className="ai-insights-stack">
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
                      <small>
                        {form.ai_insights.provenance?.join(' · ') ||
                          'Editor-supplied context — verify before publication.'}
                      </small>
                    </div>
                  </div>
                </div>
              )}
            </aside>
          </div>
        )}
      </div>

      <footer className="story-wizard-footer">
        <button type="button" onClick={goBack}>
          <ArrowLeft size={16} /> {stageIndex === 0 ? 'All stories' : 'Back'}
        </button>
        <div className="story-wizard-footer-actions">
          {editable && (status === 'draft' || status === 'rejected' || status === 'unpublished') && (
            <button type="button" onClick={() => void save()} disabled={working}>
              Save draft
            </button>
          )}
          {stage !== 'review' && (
            <button type="button" className="primary" onClick={goNext}>
              Continue to {STORY_STAGES[stageIndex + 1]?.label ?? 'next'} <ArrowRight size={16} />
            </button>
          )}
          {stage === 'review' &&
            editable &&
            isReviewer &&
            (status === 'draft' || status === 'rejected' || status === 'unpublished') && (
              <button type="button" className="primary" onClick={() => void save(true)} disabled={working}>
                Send to review <ArrowRight size={16} />
              </button>
            )}
        </div>
      </footer>

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
      {article && editable && stage === 'details' && canRefineChat && (
        <StoryChatLauncher open={showChat} onToggle={() => setShowChat((value) => !value)} />
      )}
      {showChat && article && editable && canRefineChat && (
        <StoryChatPanel
          messages={chatMessages}
          sending={chatSending}
          error={chatError}
          currentHtml={form.content_html}
          onSend={sendChatMessage}
          onApply={(proposal) => {
            setAiProposal(proposal)
            setShowChat(false)
          }}
          onClose={() => setShowChat(false)}
        />
      )}
    </section>
  )
}
