import { useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, Clock3 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { FeedbackButtons } from '@/components/news/FeedbackButtons'
import { TrendingRail } from '@/components/news/TrendingRail'
import { publicNewsService } from '@/services/public-news'
import type { ApiArticle, ApiArticleNeighbors } from '@/types/public-news'

export function ApiArticleReader({ slug }: { slug: string }) {
  const [article, setArticle] = useState<ApiArticle | null>(null)
  const [neighbors, setNeighbors] = useState<ApiArticleNeighbors>({ previous: null, next: null })
  const [error, setError] = useState('')
  useEffect(() => {
    void publicNewsService
      .article(slug)
      .then((result) => {
        setArticle(result)
        return publicNewsService.neighbors(result.slug)
      })
      .then(setNeighbors)
      .catch((reason) => setError(reason instanceof Error ? reason.message : 'Story unavailable.'))
  }, [slug])
  if (error)
    return (
      <section className="page-state">
        <p className="eyebrow">
          <span /> NewsForge
        </p>
        <h1>{error}</h1>
        <Link className="read-button" to="/">
          Return home
        </Link>
      </section>
    )
  if (!article)
    return (
      <section className="page-state">
        <p className="eyebrow">
          <span /> NewsForge
        </p>
        <h1>Loading the story.</h1>
      </section>
    )
  return (
    <section className="article-layout">
      <article className="article-page">
        <Link className="back-link" to="/">
          <ArrowLeft size={16} /> Back to latest
        </Link>
        <p className="eyebrow article-category">
          <span /> {article.topic}
        </p>
        <h1>{article.title}</h1>
        <p className="article-dek">{article.dek}</p>
        <div className="article-info">
          {article.creator.avatar_url ? (
            <img src={article.creator.avatar_url} className="avatar" alt="" />
          ) : (
            <span className="avatar">
              {article.creator.display_name
                .split(' ')
                .map((part) => part[0])
                .join('')
                .slice(0, 2)}
            </span>
          )}
          <div>
            <b>By {article.creator.display_name}</b>
            <small>Published {new Date(article.published_at ?? article.created_at).toLocaleDateString()}</small>
          </div>
          <span className="article-read">
            <Clock3 size={15} />
            Updated {new Date(article.updated_at).toLocaleDateString()}
          </span>
        </div>
        {article.hero_url && <img className="article-image" src={article.hero_url} alt="" />}
        <article className="public-story-content" dangerouslySetInnerHTML={{ __html: article.content_html }} />
        <FeedbackButtons articleId={article.id} />
        <nav className="article-navigation" aria-label="Article navigation">
          {neighbors.previous ? <Link to={`/article/${neighbors.previous.slug}`}><ArrowLeft size={16} /><span><small>Previous story</small>{neighbors.previous.title}</span></Link> : <span className="article-navigation-empty" />}
          {neighbors.next ? <Link className="next" to={`/article/${neighbors.next.slug}`}><span><small>Next story</small>{neighbors.next.title}</span><ArrowRight size={16} /></Link> : <span className="article-navigation-empty" />}
        </nav>
      </article>
      <TrendingRail />
    </section>
  )
}
