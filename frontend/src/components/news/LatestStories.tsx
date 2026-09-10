import { useEffect, useState } from 'react'
import { Bookmark } from 'lucide-react'
import { Link } from 'react-router-dom'

import { newsRepository } from '@/repositories/news-repository'
import { publicNewsService } from '@/services/public-news'
import type { ApiArticle } from '@/types/public-news'

export function LatestStories() {
  const [stories, setStories] = useState<ApiArticle[]>([])
  const [saved, setSaved] = useState<string[]>([])
  useEffect(() => {
    void publicNewsService
      .latest()
      .then((result) => setStories(result.items))
      .catch(() => undefined)
  }, [])
  const toggle = (id: string) =>
    setSaved((items) => (items.includes(id) ? items.filter((item) => item !== id) : [...items, id]))
  const fallback = newsRepository.getSnapshot().stories.slice(0, 3)
  return (
    <section className="story-grid" id="latest">
      {stories.length > 0
        ? stories.slice(0, 3).map((story, index) => (
            <article className="story-card" key={story.id}>
              <div className="card-image-wrap">
                {story.hero_url && <img src={story.hero_url} alt="" className="card-image" />}
                <button
                  onClick={() => toggle(story.id)}
                  className={'save ' + (saved.includes(story.id) ? 'saved' : '')}
                  aria-label="Save story"
                >
                  <Bookmark size={18} fill={saved.includes(story.id) ? 'currentColor' : 'none'} />
                </button>
                <span className="story-number">0{index + 1}</span>
              </div>
              <p className="category">{story.topic}</p>
              <h3>
                <Link to={`/article/${story.slug}`}>{story.title}</Link>
              </h3>
              <div className="card-meta">
                {story.creator.display_name}
                <span>·</span>
                {new Date(story.published_at ?? story.created_at).toLocaleDateString()}
              </div>
            </article>
          ))
        : fallback.map((story, index) => (
            <article className="story-card" key={story.id}>
              <div className="card-image-wrap">
                <img src={story.image} alt="" className="card-image" />
                <button
                  onClick={() => toggle(story.id)}
                  className={'save ' + (saved.includes(story.id) ? 'saved' : '')}
                  aria-label="Save story"
                >
                  <Bookmark size={18} fill={saved.includes(story.id) ? 'currentColor' : 'none'} />
                </button>
                <span className="story-number">0{index + 1}</span>
              </div>
              <p className="category">{story.category}</p>
              <h3>
                <Link to={`/article?story=${story.id}`}>{story.title}</Link>
              </h3>
              <div className="card-meta">
                {story.author}
                <span>·</span>
                {story.readTime}
              </div>
            </article>
          ))}
    </section>
  )
}
