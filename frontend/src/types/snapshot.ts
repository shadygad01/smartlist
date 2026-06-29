// Constitutional Production Data Contract
// Every field maps 1:1 to presentation_snapshot.json
// No field may be invented by the frontend.

export interface Lineage {
  scan_id: string;
  producer: string;
  parent_artifacts: string[];
  generation_timestamp: string;
  git_commit: string;
  gate_version: string;
  workflow_run?: string;
  source_fingerprints: Record<string, string>;
}

export interface NearConstitutionalTicker {
  ticker: string;
  candidate_r2: number;
  expected_reward_score: number;
  candidate_entry_zone: number;
  current_price: number;
  sector: string;
  distance_to_constitutional: number;
  need_move_pct: number;
}

export interface ActivePosition {
  ticker: string;
  current_price: number;
  status: string;
  constitutional_entry_price: number | null;
  distance: number | null;
  waiting_for_reason: string;
  action: string;
  constitutional_memory: number;
  candidate_r2: number;
  expected_reward_score: number;
  last_scan: string;
  generated_at: string;
  source: string;
  last_price_update: string;
  return_pct: number | null;
}

export interface ReAccumulationEvent {
  event_id: string;
  ticker: string;
  event_type: string;
  event_index: number;
  event_date: string;
  event_end_date: string;
  event_cluster_days: number;
  constitutional_entry_price: number;
  constitutional_r2: number;
  constitutional_score: number;
  sector: string;
  signal_version: string;
  current_price: number;
  return_pct: number;
  peak_return_pct: number;
  days_active: number;
  status: string;
}

export interface UniverseItem {
  ticker: string;
  current_price: number;
  status: string;
  constitutional_entry_price: number | null;
  distance: number | null;
  waiting_for_reason: string;
  action: string;
  constitutional_memory: number;
  candidate_r2: number | null;
  expected_reward_score: number | null;
  last_scan: string;
  generated_at: string;
  source: string;
  last_price_update: string;
  return_pct: number | null;
}

export interface TimelineEvent {
  event_id?: string;
  ticker?: string;
  event_type?: string;
  event_date?: string;
  constitutional_entry_price?: number;
  constitutional_r2?: number;
  constitutional_score?: number;
  current_price?: number;
  return_pct?: number;
  sector?: string;
  [key: string]: unknown;
}

export interface Statistics {
  total_timeline_events: number;
  total_tickers_in_timeline: number;
  near_constitutional_count: number;
  active_count: number;
  re_accumulation_count: number;
  first_buys_count?: number;
  premium_count?: number;
  future_candidates_count?: number;
  universe_size?: number;
  new_events_today: number;
}

export interface ResearchInsight {
  question: string;
  conclusion: string;
  confidence: string;
}

export interface StockDNA {
  ticker: string;
  first_buy_date: string;
  first_buy_price: number;
  buy_count: number;
  re_accum_count: number;
  avg_entry_price: number;
  current_price: number;
  avg_return_pct: number;
  best_return_pct: number;
  worst_return_pct: number;
  historical_buy_zone_low: number;
  historical_buy_zone_high: number;
  constitutional_memory_hits: number;
  constitutional_memory_confidence: string;
  last_event_date: string | null;
  last_updated: string;
}

export interface MPIBehavior {
  ticker: string;
  phase: string;
  confidence: number;
  confidence_label: string;
  explanation: string;
  historical_cases: number;
  similarity_score: number;
  avg_mfe40: number;
  avg_drawdown: number;
  avg_holding_days: number;
}

export interface ValuationCard {
  ticker: string;
  valuation_date: string;
  weighted_fair_value: number | null;
  bull_case: number | null;
  base_case: number | null;
  bear_case: number | null;
  analyst_consensus_price: number | null;
  last_stmt_year: number | null;
}

export interface ProductionSnapshot {
  scan_id: string;
  generated_at: string;
  price_data_as_of: string;
  market_date: string;
  market_status: string;
  build_hash: string;
  commit: string;
  last_scan_ts: string;
  _lineage: Lineage;
  near_constitutional: NearConstitutionalTicker[];
  active: ActivePosition[];
  re_accumulation: ReAccumulationEvent[];
  first_buys: ReAccumulationEvent[];
  timeline: TimelineEvent[];
  future_candidates: UniverseItem[];
  watchlist: string[];
  universe_snapshot: UniverseItem[];
  new_events_today: TimelineEvent[];
  stock_dna: Record<string, StockDNA>;
  mpi_behavior: Record<string, MPIBehavior>;
  valuation: Record<string, ValuationCard>;
  statistics: Statistics;
  health_stars: string;
  health_label: string;
  health_narrative: string;
  research_insights: ResearchInsight[];
  knowledge_count: number;
}
