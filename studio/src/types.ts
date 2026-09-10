export type Role = 'admin' | 'editor' | 'reporter' | 'audience'
export type User = { id: string; email: string; display_name: string; role: Role; is_active: boolean; avatar_media_id: string | null; created_at: string; updated_at: string }
export type Session = { access_token: string; token_type: 'bearer'; user: User }
export type ArticleStatus = 'draft' | 'under_review' | 'approved' | 'rejected' | 'scheduled' | 'published' | 'archived'
export type Article = { id: string; title: string; dek: string; topic: string; tags: string[]; content_html: string; content_json: Record<string, unknown>; status: ArticleStatus; updated_at: string; published_at?: string | null; hero_media_id: string | null; hero_url: string | null; editor?: { id: string; display_name: string } | null }

export interface RankingSignal {
  topic_geo_key: string
  topic: string
  geo: string
  weight_delta: number
  sample_size: number
  confidence: number
  last_updated: string
}

export interface RankedLead {
  lead_id: string
  headline: string
  priority_score: number
  base_score: number
  learned_weight_delta: number
  final_score: number
  previous_rank: number | null
  current_rank: number | null
  rank_shift: number
  suggested_angle: string
  suggested_publish_window: string
  reasoning: string
}

export interface TelemetrySimulationRequest {
  topic: string
  geo: string
  base_score: number
  sample_size?: number
}
