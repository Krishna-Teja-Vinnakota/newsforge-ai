import { useEffect, useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'

import { telemetryService } from '@/services/telemetry'

type Metrics = { views: number; likes: number; dislikes: number; engagement_ratio: number; popularity_score: number }
type FeedbackButtonsProps = { articleId: string; initialMetrics?: Partial<Metrics> }

export function FeedbackButtons({ articleId, initialMetrics = {} }: FeedbackButtonsProps) {
  const [metrics, setMetrics] = useState<Metrics>({
    views: 0,
    likes: 0,
    dislikes: 0,
    engagement_ratio: 0,
    popularity_score: 0,
    ...initialMetrics,
  })
  const [active, setActive] = useState<'like' | 'dislike' | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    void telemetryService
      .view(articleId)
      .then((result) => setMetrics(result.metrics))
      .catch(() => undefined)
  }, [articleId])
  const send = async (action: 'like' | 'dislike') => {
    setError('')
    try {
      const result = await telemetryService.feedback(articleId, action)
      setActive(result.viewer_action)
      setMetrics(result.metrics)
    } catch {
      setError('Feedback could not be saved.')
    }
  }
  return (
    <div className="feedback-widget">
      <span>Was this story useful?</span>
      <div>
        <button className={active === 'like' ? 'active' : ''} onClick={() => void send('like')}>
          <ThumbsUp size={16} /> {metrics.likes}
        </button>
        <button className={active === 'dislike' ? 'active' : ''} onClick={() => void send('dislike')}>
          <ThumbsDown size={16} /> {metrics.dislikes}
        </button>
      </div>
      {error && <small>{error}</small>}
    </div>
  )
}
