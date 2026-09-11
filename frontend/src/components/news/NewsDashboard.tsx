import { useEffect, useMemo, useState } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { newsRepository } from '@/repositories/news-repository'
import { publicNewsService } from '@/services/public-news'
import type { ApiArticle } from '@/types/public-news'

type FeedStory = { key: string; title: string; dek: string; topic: string; image: string; meta: string; to: string }

function fixtureStories(): FeedStory[] {
  const snapshot = newsRepository.getSnapshot()
  return [snapshot.hero, ...snapshot.stories].map((story, index) => ({
    key: String('id' in story ? story.id : `hero-${index}`),
    title: story.title,
    dek: story.excerpt,
    topic: story.category,
    image: story.image,
    meta: `${story.author} · ${story.readTime}`,
    to: 'id' in story ? `/article?story=${String(story.id)}` : '/article',
  }))
}

function apiStories(items: ApiArticle[]): FeedStory[] {
  return items.map((story) => ({
    key: story.id,
    title: story.title,
    dek: story.dek,
    topic: story.topic,
    image: story.hero_url ?? '',
    meta: `${story.creator.display_name} · ${new Date(story.published_at ?? story.created_at).toLocaleDateString()}`,
    to: `/article/${story.slug}`,
  }))
}

function fill(items: FeedStory[], amount: number) {
  const source = items.length ? items : fixtureStories()
  return Array.from({ length: amount }, (_, index) => ({
    ...source[index % source.length],
    key: `${source[index % source.length].key}-${index}`,
  }))
}

export function NewsDashboard() {
  const [articles, setArticles] = useState<ApiArticle[]>([])
  useEffect(() => {
    void publicNewsService
      .latest()
      .then((result) => setArticles(result.items))
      .catch(() => undefined)
  }, [])
  const feed = useMemo(() => fill(articles.length ? apiStories(articles) : fixtureStories(), 11), [articles])
  const hero = feed[0],
    medium = feed.slice(1, 3),
    compact = feed.slice(3, 11)
  const categoryGroups = Object.entries(
    (articles.length ? apiStories(articles) : fixtureStories()).reduce<Record<string, FeedStory[]>>((groups, story) => {
      ;(groups[story.topic] ??= []).push(story)
      return groups
    }, {})
  )
  return (
    <section className="news-dashboard">
      <div className="dashboard-feed">
        <div className="hero-column">
          <article className="latest-hero">
            <Link to={hero.to}>
              <img src={hero.image} alt="" />
              <div className="latest-copy">
                <p>{hero.topic} · Latest</p>
                <h1>{hero.title}</h1>
                <span>{hero.dek}</span>
                <small>{hero.meta}</small>
              </div>
            </Link>
          </article>
          <section className="medium-stories">
            {medium.map((story) => (
              <article key={story.key}>
                <Link to={story.to}>
                  <img src={story.image} alt="" />
                  <p>{story.topic}</p>
                  <h2>{story.title}</h2>
                  <span>{story.dek}</span>
                  <small>{story.meta}</small>
                </Link>
              </article>
            ))}
          </section>
        </div>
        <section className="compact-grid">
          {compact.map((story) => (
            <article key={story.key}>
              <Link to={story.to}>
                <img src={story.image} alt="" />
                <div>
                  <p>{story.topic}</p>
                  <h3>{story.title}</h3>
                  <small>{story.meta}</small>
                </div>
                <ArrowUpRight size={16} />
              </Link>
            </article>
          ))}
        </section>
      </div>
      <div className="category-rows">
        {categoryGroups.map(([category, stories]) => (
          <section key={category} className="category-row">
            <header>
              <h2>{category}</h2>
              <a href="#top">
                See more <ArrowUpRight size={15} />
              </a>
            </header>
            <div>
              {stories.map((story) => (
                <Link to={story.to} key={story.key}>
                  <img src={story.image} alt="" />
                  <span>{story.title}</span>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  )
}
