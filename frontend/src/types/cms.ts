export type UserRole = 'admin' | 'editor'

export type AuthUser = {
  id: string
  email: string
  display_name: string
  role: UserRole
  avatar_media_id: string | null
  created_at: string
  updated_at: string
}

export type AuthSession = { access_token: string; token_type: 'bearer'; user: AuthUser }

export type CmsArticle = {
  id: string
  slug: string
  status: 'draft' | 'under_review' | 'approved' | 'rejected' | 'published' | 'unpublished'
  title: string
  dek: string
  content_json: Record<string, unknown>
  content_html: string
  topic: string
  tags: string[]
  hero_media_id: string | null
  hero_url: string | null
  created_at: string
  updated_at: string
}
