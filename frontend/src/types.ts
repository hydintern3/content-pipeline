export type Platform = "xiaohongshu" | "zhihu" | "zhihu_qa" | "official_account" | "toutiao" | "shipinhao";

export interface MaterialPayload {
  title_hint: string;
  raw_content: string;
  keywords: string[];
  image_paths: string[];
  target_platforms: Platform[];
}

export interface MaterialRecord extends MaterialPayload {
  id: number;
  source_type: string;
  source_ref: string;
  created_at: string;
}

export interface Article {
  id: number;
  material_id: number;
  platform: Platform;
  title: string;
  content: string;
  format: string;
  status: string;
  created_at: string;
}

export interface ArticleFollowUp {
  id: number;
  source_article_id: number;
  result_article_id: number;
  instruction: string;
  model: string;
  created_at: string;
}

export interface PublishTask {
  id: number;
  article_id: number;
  platform: Platform;
  mode: string;
  status: "pending" | "success" | "failed" | string;
  result_message: string;
  output_path: string;
  created_at: string;
}

export interface ComplianceRisk {
  term: string;
  category: string;
  level: string;
  suggestion: string;
  start: number;
  end: number;
  platform: string;
}

export interface ComplianceResult {
  article_id?: number;
  platform: Platform;
  status: string;
  risk_count: number;
  risks: ComplianceRisk[];
  cached?: boolean;
  mode?: "mock" | "regex_only" | "llm" | string;
}

export interface BatchItem {
  id: number;
  row_number: number;
  status: string;
  title_hint: string;
  error_message: string;
  result: Record<string, unknown>;
}

export interface BatchJob {
  id: number;
  filename: string;
  status: string;
  total_count: number;
  success_count: number;
  failed_count: number;
  result_message: string;
  created_at: string;
  updated_at: string;
  items?: BatchItem[];
}

export interface TaskJob {
  id: string;
  type: string;
  status: "pending" | "running" | "success" | "failed" | string;
  celery_task_id?: string;
  queue_name?: string;
  priority?: number;
  retry_count?: number;
  max_retries?: number;
  progress: {
    current: number;
    total: number;
    percent: number;
    message: string;
  };
  result: Record<string, unknown>;
  error_message: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ObservabilityLogItem {
  id: number;
  event_type: string;
  level: string;
  message: string;
  path: string;
  method: string;
  status_code: number;
  duration_ms: number;
  details: Record<string, unknown>;
  created_at: string;
}

export interface LlmCallMetricItem {
  id: number;
  operation: string;
  platform: string;
  model: string;
  success: boolean;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: string;
  error_message: string;
  created_at: string;
}

export interface ObservabilitySummary {
  window_hours: number;
  requests: {
    count: number;
    error_count: number;
    avg_latency_ms: number;
  };
  llm: {
    count: number;
    success_count: number;
    error_count: number;
    avg_latency_ms: number;
    total_tokens: number;
    estimated_cost_usd: string;
  };
  recent_logs: ObservabilityLogItem[];
  recent_llm_calls: LlmCallMetricItem[];
}

export interface ImageVariant {
  id: number;
  platform: Platform;
  usage: string;
  width: number;
  height: number;
  output_path: string;
  file_size: number;
}

export interface ImageAsset {
  id: number;
  original_name: string;
  original_path: string;
  topic: string;
  status: string;
  variants: ImageVariant[];
}

export interface GenerationHistoryItem {
  id: string;
  title_hint: string;
  keywords: string[];
  target_platforms: Platform[];
  generated_platforms: Platform[];
  article_count: number;
  created_at: string;
  updated_at: string;
}

export interface GenerationHistoryDetail extends GenerationHistoryItem {
  material: MaterialPayload & {
    source_type: string;
    source_ref: string;
  };
  articles: Article[];
}

export interface RuntimeConfig {
  app_database_url: string;
  llm: {
    api_key?: string;
    api_key_configured?: boolean;
    base_url: string;
    model: string;
  };
  generation: {
    concurrency: number;
  };
  compliance: {
    mock: boolean;
    llm_model: string;
    cache_size: number;
    auto_check: boolean;
    concurrency: number;
  };
  database: {
    url?: string;
    configured?: boolean;
  };
  publish: {
    pending_output_dir: string;
  };
  wechat: {
    app_id: string;
    app_secret?: string;
    app_secret_configured?: boolean;
    auto_publish: boolean;
    enable_mass_send: boolean;
  };
  scheduler?: {
    enabled: boolean;
    interval_minutes: number;
  };
}

export interface ConfigEnvelope {
  env_overrides: Record<string, boolean>;
  config: RuntimeConfig;
}
