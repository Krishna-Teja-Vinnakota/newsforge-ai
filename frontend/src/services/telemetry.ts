import { api } from '@/services/api'

const VISITOR_KEY = 'newsforge.visitor.id'
type Metrics = { views: number; likes: number; dislikes: number; engagement_ratio: number; popularity_score: number }
export type TelemetryResponse = { article_id: string; viewer_action: 'like' | 'dislike' | null; metrics: Metrics }

function visitorId() {
  let id = localStorage.getItem(VISITOR_KEY)
  if (!id) { id = crypto.randomUUID(); localStorage.setItem(VISITOR_KEY, id) }
  return id
}

export const telemetryService = {
  view: (articleId: string) => api<TelemetryResponse>(`/articles/${articleId}/view`, { method: 'POST', headers: { 'X-NewsForge-Visitor': visitorId() } }),
  feedback: (articleId: string, action: 'like' | 'dislike') => api<TelemetryResponse>(`/articles/${articleId}/feedback`, { method: 'POST', headers: { 'X-NewsForge-Visitor': visitorId() }, body: JSON.stringify({ action }) }),
}
