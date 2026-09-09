import { api } from '@/services/api'
import type { AuthSession, AuthUser, CmsArticle } from '@/types/cms'

type ArticleWrite = Pick<CmsArticle, 'title' | 'dek' | 'content_json' | 'content_html' | 'topic' | 'tags'> & { hero_media_id?: string | null }

export const cmsService = {
  login: (email: string, password: string) => api<AuthSession>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  register: (display_name: string, email: string, password: string) => api<AuthSession>('/auth/register', { method: 'POST', body: JSON.stringify({ display_name, email, password }) }),
  me: () => api<AuthUser>('/auth/me'),
  createArticle: (article: ArticleWrite) => api<CmsArticle>('/cms/articles', { method: 'POST', body: JSON.stringify(article) }),
  updateArticle: (id: string, article: Partial<ArticleWrite>) => api<CmsArticle>(`/cms/articles/${id}`, { method: 'PATCH', body: JSON.stringify(article) }),
  submitForReview: (id: string) => api<CmsArticle>(`/cms/articles/${id}/submit-review`, { method: 'POST', body: JSON.stringify({}) }),
  publish: (id: string, scheduled_for?: string) => api<CmsArticle>(`/cms/articles/${id}/publish`, { method: 'POST', body: JSON.stringify(scheduled_for ? { scheduled_for } : {}) }),
  unpublish: (id: string) => api<CmsArticle>(`/cms/articles/${id}/unpublish`, { method: 'POST', body: JSON.stringify({}) }),
  myArticles: () => api<{ items: CmsArticle[] }>('/cms/articles/mine'),
  uploadMedia: (file: File, purpose: 'inline' | 'hero' | 'avatar') => {
    const body = new FormData()
    body.append('file', file)
    body.append('purpose', purpose)
    return api<{ id: string; url: string }>('/media/upload', { method: 'POST', body })
  },
}
