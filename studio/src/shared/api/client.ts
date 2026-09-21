import type { Article, RankingSignal, Session, User } from '../../types'

export type AgentRun = {
  id: string
  agent: 'selection' | 'production' | 'telemetry' | 'headline' | 'dek' | 'body' | 'tags'
  status: 'succeeded' | 'failed'
  output: Record<string, unknown>
  input: Record<string, unknown>
  error: string | null
  model: string
  prompt_version: string
  duration_ms: number
  created_at: string
}
export type AiLead = {
  id: string
  headline: string
  topic: string
  geo: string
  status: string
  priority_score: number | null
  suggested_angle: string | null
  reasoning: string | null
  base_score: number
  learned_weight_delta: number
  final_score: number
  previous_rank: number | null
  current_rank: number | null
  rank_shift: number
}
export type TelemetrySimulationResponse = {
  status: 'success'
  updated_signal: RankingSignal
  affected_leads_count: number
}
export type ResetDemoDataResponse = {
  status: 'success'
  seeded_leads: number
  indexed_sources: number
  message: string
}
export type WorkflowState = {
  thread_id: string
  state: Record<string, unknown>
  current_node: string | null
  execution_history: { node: string; status: string; timestamp: string }[]
  checkpoints: { next: string[]; metadata: Record<string, unknown> }
  pending_interrupts: string[]
}

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
const tokenKey = 'newsforge.studio.token'

export const sessionToken = () => localStorage.getItem(tokenKey)
export const saveToken = (token: string) => localStorage.setItem(tokenKey, token)
export const clearToken = () => localStorage.removeItem(tokenKey)

function message(detail: unknown) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail
      .map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : ''))
      .filter(Boolean)
      .join('. ')
  return 'The NewsForge API is unavailable.'
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let lastError: unknown
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}${path}`, {
        ...init,
        headers: {
          'Content-Type': 'application/json',
          ...(sessionToken() ? { Authorization: `Bearer ${sessionToken()}` } : {}),
          ...init.headers,
        },
      })
      if (!response.ok) throw new Error(message((await response.json().catch(() => null))?.detail))
      return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>)
    } catch (error) {
      lastError = error
      if (error instanceof Error && !error.message.includes('Failed to fetch')) throw error
      if (attempt < 2) await new Promise((resolve) => window.setTimeout(resolve, 350 * (attempt + 1)))
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Could not reach NewsForge. Please try again.')
}

export const api = {
  login: (email: string, password: string) =>
    request<Session>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request<User>('/auth/me'),
  updateProfile: (body: { display_name: string; email?: string; password?: string }) =>
    request<User>('/auth/me', { method: 'PATCH', body: JSON.stringify(body) }),
  myArticles: (page = 1, pageSize = 10) =>
    request<{ items: Article[]; page: number; page_size: number; total: number }>(
      `/cms/articles/mine?page=${page}&page_size=${pageSize}`
    ),
  createArticle: (body: Partial<Article>) =>
    request<Article>('/cms/articles', { method: 'POST', body: JSON.stringify(body) }),
  getArticle: (id: string) => request<Article>(`/cms/articles/${id}`),
  updateArticle: (id: string, body: Partial<Article>) =>
    request<Article>(`/cms/articles/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  submitArticle: (id: string) => request<Article>(`/cms/articles/${id}/submit-review`, { method: 'POST', body: '{}' }),
  approveArticle: (id: string) => request<Article>(`/cms/articles/${id}/approve`, { method: 'POST', body: '{}' }),
  rejectArticle: (id: string) => request<Article>(`/cms/articles/${id}/reject`, { method: 'POST', body: '{}' }),
  publishArticle: (id: string) => request<Article>(`/cms/articles/${id}/publish`, { method: 'POST', body: '{}' }),
  submitArticleForReview: (id: string) =>
    request<Article>(`/cms/articles/${id}/submit-review`, { method: 'POST', body: '{}' }),
  unpublishArticle: (id: string) => request<Article>(`/cms/articles/${id}/unpublish`, { method: 'POST', body: '{}' }),
  agentRuns: () => request<{ items: AgentRun[]; total: number }>('/agents/runs'),
  retryAgentRun: (id: string) => request<AgentRun>(`/agents/runs/${id}/retry`, { method: 'POST', body: '{}' }),
  rankLeads: (leads: { id: string; headline: string; topic: string; geo: string }[]) =>
    request<AgentRun>('/agents/selection/run', { method: 'POST', body: JSON.stringify({ leads }) }),
  produceDraft: (body: {
    headline: string
    topic: string
    context: string
    target_platforms?: string[]
    source_lead_id?: string
    article_id?: string
    tone?: 'formal' | 'conversational' | 'urgent'
  }) => request<AgentRun>('/agents/produce', { method: 'POST', body: JSON.stringify(body) }),
  generateHeadline: (body: { title: string; topic: string; context: string; mode: 'generate' | 'grammar' }) =>
    request<AgentRun>('/agents/headline', { method: 'POST', body: JSON.stringify(body) }),
  generateDek: (body: { dek: string; title: string; context: string; mode: 'generate' | 'grammar' }) =>
    request<AgentRun>('/agents/dek', { method: 'POST', body: JSON.stringify(body) }),
  generateBody: (body: { content_html: string; title: string; dek: string; notes: string; mode: 'rewrite' | 'notes_to_story' | 'grammar' }) =>
    request<AgentRun>('/agents/body', { method: 'POST', body: JSON.stringify(body) }),
  suggestTags: (body: { title: string; dek: string; content_html: string; topic: string; existing_tags: string[] }) =>
    request<AgentRun>('/agents/tags', { method: 'POST', body: JSON.stringify(body) }),
  recalculateTelemetry: (article_id: string) =>
    request<AgentRun>('/agents/telemetry/recalculate', { method: 'POST', body: JSON.stringify({ article_id }) }),
  simulateTelemetry: () =>
    request<TelemetrySimulationResponse>('/telemetry/simulate', {
      method: 'POST',
      body: JSON.stringify({ topic: 'nation-world', geo: 'Ohio', sample_size: 1000 }),
    }),
  resetDemoData: () => request<ResetDemoDataResponse>('/admin/reset-demo', { method: 'POST', body: '{}' }),
  startWorkflow: (lead: { id: string; headline: string; topic: string; geo: string }) =>
    request<WorkflowState>('/workflow/start', { method: 'POST', body: JSON.stringify({ lead }) }),
  resumeWorkflow: (
    threadId: string,
    body: {
      approval_status?: 'approved' | 'rejected'
      editorial_status?: 'approved'
      generated_draft?: Record<string, unknown>
    }
  ) => request<WorkflowState>(`/workflow/${threadId}/resume`, { method: 'POST', body: JSON.stringify(body) }),
  workflowState: (threadId: string) => request<WorkflowState>(`/workflow/${threadId}/state`),
  rankingSignals: () => request<RankingSignal[]>('/telemetry/signals'),
  aiLeads: () => request<AiLead[]>('/agents/leads'),
  decideLead: (id: string, decision: 'approve' | 'reject') =>
    request<AiLead>(`/agents/leads/${id}/${decision}`, { method: 'POST', body: '{}' }),
  users: () => request<User[]>('/users'),
  createUser: (body: { email: string; password: string; display_name: string; role: string }) =>
    request<User>('/users', { method: 'POST', body: JSON.stringify(body) }),
  updateUser: (id: string, body: Partial<User> & { password?: string }) =>
    request<User>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteUser: (id: string) => request<void>(`/users/${id}`, { method: 'DELETE' }),
  topics: () => request<{ id: string; name: string; slug: string; is_active: boolean }[]>('/topics'),
  createTopic: (body: { name: string; slug: string }) =>
    request<{ id: string; name: string; slug: string; is_active: boolean }>('/topics', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateTopic: (id: string, body: { name?: string; is_active?: boolean }) =>
    request<{ id: string; name: string; slug: string; is_active: boolean }>(`/topics/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteTopic: (id: string) => request<void>(`/topics/${id}`, { method: 'DELETE' }),
  tags: () => request<{ id: string; name: string }[]>('/tags'),
  createTag: (name: string) =>
    request<{ id: string; name: string }>('/tags', { method: 'POST', body: JSON.stringify({ name }) }),
  deleteTag: (id: string) => request<void>(`/tags/${id}`, { method: 'DELETE' }),
  uploadHero: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    form.append('purpose', 'hero')
    const response = await fetch(`${baseUrl}/media/upload`, {
      method: 'POST',
      headers: sessionToken() ? { Authorization: `Bearer ${sessionToken()}` } : {},
      body: form,
    })
    if (!response.ok) throw new Error(message((await response.json().catch(() => null))?.detail))
    return response.json() as Promise<{ id: string; url: string }>
  },
}
