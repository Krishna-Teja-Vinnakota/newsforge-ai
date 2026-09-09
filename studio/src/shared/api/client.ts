import type { Article, Session, User } from '../../types'

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
const tokenKey = 'newsforge.studio.token'

export const sessionToken = () => localStorage.getItem(tokenKey)
export const saveToken = (token: string) => localStorage.setItem(tokenKey, token)
export const clearToken = () => localStorage.removeItem(tokenKey)

function message(detail: unknown) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => typeof item === 'object' && item && 'msg' in item ? String(item.msg) : '').filter(Boolean).join('. ')
  return 'The NewsForge API is unavailable.'
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let lastError: unknown
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(sessionToken() ? { Authorization: `Bearer ${sessionToken()}` } : {}), ...init.headers } })
      if (!response.ok) throw new Error(message((await response.json().catch(() => null))?.detail))
      return response.status === 204 ? undefined as T : response.json() as Promise<T>
    } catch (error) {
      lastError = error
      if (error instanceof Error && !error.message.includes('Failed to fetch')) throw error
      if (attempt < 2) await new Promise(resolve => window.setTimeout(resolve, 350 * (attempt + 1)))
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Could not reach NewsForge. Please try again.')
}

export const api = {
  login: (email: string, password: string) => request<Session>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request<User>('/auth/me'),
  updateProfile: (body: { display_name: string; email?: string; password?: string }) => request<User>('/auth/me', { method: 'PATCH', body: JSON.stringify(body) }),
  myArticles: (page = 1, pageSize = 10) => request<{ items: Article[]; page: number; page_size: number; total: number }>(`/cms/articles/mine?page=${page}&page_size=${pageSize}`),
  createArticle: (body: Partial<Article>) => request<Article>('/cms/articles', { method: 'POST', body: JSON.stringify(body) }),
  updateArticle: (id: string, body: Partial<Article>) => request<Article>(`/cms/articles/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  submitArticle: (id: string) => request<Article>(`/cms/articles/${id}/submit-review`, { method: 'POST', body: '{}' }),
  approveArticle: (id: string) => request<Article>(`/cms/articles/${id}/approve`, { method: 'POST', body: '{}' }),
  rejectArticle: (id: string) => request<Article>(`/cms/articles/${id}/reject`, { method: 'POST', body: '{}' }),
  publishArticle: (id: string) => request<Article>(`/cms/articles/${id}/publish`, { method: 'POST', body: '{}' }),
  unpublishArticle: (id: string) => request<Article>(`/cms/articles/${id}/unpublish`, { method: 'POST', body: '{}' }),
  users: () => request<User[]>('/users'),
  createUser: (body: { email: string; password: string; display_name: string; role: string }) => request<User>('/users', { method: 'POST', body: JSON.stringify(body) }),
  updateUser: (id: string, body: Partial<User> & { password?: string }) => request<User>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteUser: (id: string) => request<void>(`/users/${id}`, { method: 'DELETE' }),
  topics: () => request<{ id: string; name: string; slug: string; is_active: boolean }[]>('/topics'),
  createTopic: (body: { name: string; slug: string }) => request<{ id: string; name: string; slug: string; is_active: boolean }>('/topics', { method: 'POST', body: JSON.stringify(body) }),
  updateTopic: (id: string, body: { name?: string; is_active?: boolean }) => request<{ id: string; name: string; slug: string; is_active: boolean }>(`/topics/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteTopic: (id: string) => request<void>(`/topics/${id}`, { method: 'DELETE' }),
  tags: () => request<{ id: string; name: string }[]>('/tags'),
  createTag: (name: string) => request<{ id: string; name: string }>('/tags', { method: 'POST', body: JSON.stringify({ name }) }),
  deleteTag: (id: string) => request<void>(`/tags/${id}`, { method: 'DELETE' }),
  uploadHero: async (file: File) => {
    const form = new FormData(); form.append('file', file); form.append('purpose', 'hero')
    const response = await fetch(`${baseUrl}/media/upload`, { method: 'POST', headers: sessionToken() ? { Authorization: `Bearer ${sessionToken()}` } : {}, body: form })
    if (!response.ok) throw new Error(message((await response.json().catch(() => null))?.detail))
    return response.json() as Promise<{ id: string; url: string }>
  },
}
