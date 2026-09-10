import { useState, type MouseEvent } from 'react'
import type { Article } from '../../types'

type Action = 'submit' | 'approve' | 'reject' | 'publish' | 'unpublish'

function HeroFallback({ topic }: { topic: string }) {
  return <div className="story-card-hero-fallback" role="img" aria-label={`${topic} story placeholder`}><svg viewBox="0 0 640 220" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="story-fallback-gradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#183b56"/><stop offset="0.55" stopColor="#2f799d"/><stop offset="1" stopColor="#f08a5d"/></linearGradient></defs><rect width="640" height="220" fill="url(#story-fallback-gradient)"/><circle cx="520" cy="30" r="150" fill="#fff" opacity=".1"/><path d="M0 180 C160 120 260 230 420 160 S560 135 640 175 V220 H0Z" fill="#071d2b" opacity=".3"/></svg><span>{topic.replace('-', ' ')}</span></div>
}

export function StoryCard({ article, canEdit, working, onOpen, onAction }: { article: Article; canEdit: boolean; working: boolean; onOpen: () => void; onAction: (action: Action) => void }) {
  const [imageFailed, setImageFailed] = useState(false)
  const stop = (action: Action) => (event: MouseEvent<HTMLButtonElement>) => { event.stopPropagation(); onAction(action) }
  return <article className="cms-story-card" onClick={onOpen} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') onOpen() }} role="button" tabIndex={0}><div className="story-card-hero">{article.hero_url && !imageFailed ? <img src={article.hero_url} alt="" onError={() => setImageFailed(true)}/> : <HeroFallback topic={article.topic}/>}</div><div className="story-card-content"><span>{article.status.replace('_', ' ')}</span><h2>{article.title}</h2><p>{article.dek}</p><small>{article.editor ? `Reviewer: ${article.editor.display_name}` : 'No reviewer assigned'}</small></div>{canEdit && <footer className="story-card-actions">{article.status === 'draft' && <button onClick={stop('submit')} disabled={working}>Submit</button>}{article.status === 'under_review' && <><button onClick={stop('reject')} disabled={working}>Reject</button><button onClick={stop('approve')} disabled={working}>Approve</button></>}{article.status === 'approved' && <button onClick={stop('publish')} disabled={working}>Publish</button>}{article.status === 'published' && <button onClick={stop('unpublish')} disabled={working}>Unpublish</button>}</footer>}</article>
}
