export type Role = 'admin' | 'editor' | 'reporter' | 'audience'
export type User = { id: string; email: string; display_name: string; role: Role; is_active: boolean; avatar_media_id: string | null; created_at: string; updated_at: string }
export type Session = { access_token: string; token_type: 'bearer'; user: User }
export type ArticleStatus = 'draft' | 'in_review' | 'approved' | 'rejected' | 'scheduled' | 'published' | 'archived'
export type Article = { id: string; title: string; dek: string; topic: string; tags: string[]; content_html: string; content_json: Record<string, unknown>; status: ArticleStatus; updated_at: string; hero_media_id: string | null; hero_url: string | null }
