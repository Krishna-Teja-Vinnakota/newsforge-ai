export type ApiAuthor = { id: string; display_name: string; avatar_url: string | null }

export type ApiArticle = {
  id: string
  slug: string
  status: 'draft' | 'in_review' | 'scheduled' | 'published' | 'archived'
  title: string
  dek: string
  content_json: Record<string, unknown>
  content_html: string
  topic: string
  tags: string[]
  hero_media_id: string | null
  hero_url: string | null
  creator: ApiAuthor
  editor: ApiAuthor | null
  created_at: string
  updated_at: string
  published_at: string | null
  scheduled_for: string | null
}

export type ApiArticleList = { items: ApiArticle[]; page: number; page_size: number; total: number }
