import { api } from '@/services/api'
import type { ApiArticle, ApiArticleList } from '@/types/public-news'

export const publicNewsService = {
  latest: () => api<ApiArticleList>('/articles'),
  trending: () => api<ApiArticleList>('/articles/trending?limit=5'),
  article: (slug: string) => api<ApiArticle>(`/articles/${encodeURIComponent(slug)}`),
}
