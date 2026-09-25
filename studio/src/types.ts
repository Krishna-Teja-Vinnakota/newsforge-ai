export type Role = 'admin' | 'editor'
export type User = {
  id: string
  email: string
  display_name: string
  role: Role
  is_active: boolean
  avatar_media_id: string | null
  created_at: string
  updated_at: string
}
export type Session = { access_token: string; token_type: 'bearer'; user: User }
export type ArticleStatus = 'draft' | 'under_review' | 'approved' | 'rejected' | 'published' | 'unpublished'
export type Article = {
  id: string
  title: string
  dek: string
  topic: string
  tags: string[]
  content_html: string
  content_json: Record<string, unknown>
  status: ArticleStatus
  updated_at: string
  published_at?: string | null
  hero_media_id: string | null
  hero_url: string | null
  hero_ai_generated?: boolean
  hero_alt_text?: string | null
  hero_disclosure?: string | null
  ai_insights?: {
    reporter_brief?: { background?: string; key_questions?: string[]; shot_list?: string[] }
    social_posts?: string[]
    push_notification?: string
    provenance?: string[]
    model_name?: string
    generated_at?: string
    suggested_tags?: string[]
  } | null
  editor?: { id: string; display_name: string } | null
}

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
  selection_weight_adjustment: number
  final_score: number
  previous_rank: number | null
  current_rank: number | null
  rank_shift: number
  trend_boost: number
  coverage_adjustment: number
  trend_evidence: TrendEvidence[]
  suggested_format: string
  why_now: string | null
  origin: string
  suggested_angle: string
  suggested_publish_window: string
  reasoning: string
  audience_forecast: AudienceForecast | null
}

export interface AudienceForecast {
  status: 'insufficient_data' | 'historical_baseline' | 'calibrated_model'
  horizon_days: number
  predicted_readers: number | null
  lower_bound: number | null
  upper_bound: number | null
  confidence: 'low' | 'medium' | 'high'
  audience_demand: 'low' | 'moderate' | 'high'
  comparable_stories: number
  telemetry_sample_size: number
  model_version: string
  factors: string[]
}

export interface TrendEvidence {
  signal_id: string
  source: string
  label: string
  matched_tokens: string[]
  effective_score: number
}

export interface TelemetrySimulationRequest {
  topic: string
  geo: string
  base_score: number
  sample_size?: number
}
