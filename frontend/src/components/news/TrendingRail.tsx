import { useEffect, useState } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { publicNewsService } from '@/services/public-news'
import type { ApiArticle } from '@/types/public-news'
import { newsRepository } from '@/repositories/news-repository'

export function TrendingRail() {
  const [stories, setStories] = useState<ApiArticle[]>([])
  useEffect(() => {
    void publicNewsService
      .trending()
      .then((result) => setStories(result.items))
      .catch(() => undefined)
  }, [])
  const fallback = newsRepository
    .getTrending()
    .map((trend) => ({ trend, story: newsRepository.getStoryById(trend.storyId)! }))
  return (
    <aside className="trending">
      <p className="eyebrow">
        <span /> Popular right now
      </p>
      {stories.length > 0
        ? stories.map((story, index) => (
            <Link to={`/article/${story.slug}`} key={story.id}>
              <img src={story.hero_url ?? ''} alt="" />
              <strong>0{index + 1}</strong>
              <span>{story.title}</span>
              <ArrowUpRight size={16} />
            </Link>
          ))
        : fallback.map(({ trend, story }, index) => (
            <Link to={`/article?story=${story.id}`} key={`${trend.label}-${index}`}>
              <img src={story.image} alt="" />
              <strong>0{index + 1}</strong>
              <span>{trend.label}</span>
              <ArrowUpRight size={16} />
            </Link>
          ))}
    </aside>
  )
}
