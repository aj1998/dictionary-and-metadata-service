export type EntityKind = 'shastra' | 'gatha' | 'topic' | 'keyword';

export type EdgeKind =
  | 'IS_A'
  | 'PART_OF'
  | 'RELATED_TO'
  | 'ALIAS_OF'
  | 'HAS_TOPIC'
  | 'MENTIONS_KEYWORD'
  | 'MENTIONS_TOPIC'
  | 'IN_SHASTRA'
  | 'IN_TEEKA'
  | 'IN_PUBLICATION'
  | 'CONTAINS_DEFINITION';

export interface GraphNode {
  nk: string;
  kind: EntityKind;
  title_hi: string;
  title_en?: string;
  meta?: Record<string, unknown>;
  degree: number;
}

export interface GraphEdge {
  id: string;
  src: string;
  dst: string;
  kind: EdgeKind;
  weight: number;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  focus_nk: string;
  depth: number;
}

// Pagination wrapper used by list endpoints
export interface Paginated<T> {
  pagination: { total: number; limit: number; offset: number };
  items: T[];
}

// Activity / stats (data service)
export interface ActivityRow {
  id: string;
  run_at: string;         // ISO-8601
  source: string;
  entities_touched: number;
}

export interface EntityCounts {
  shastras: number;
  gathas: number;
  topics: number;
  keywords: number;
}

// Entity detail returned by data:/v1/entity/{kind}/{nk}/detail
export interface EntityDetail {
  nk: string;
  kind: EntityKind;
  title_hi: string;
  title_en?: string;
  description?: string;
  stats: Record<string, number>;
  connected: Array<{
    nk: string;
    kind: EntityKind;
    title_hi: string;
    title_en?: string;
    edge_kind: EdgeKind;
  }>;
}

// Shastra (metadata service)
export interface LangText {
  lang: string;
  script: string;
  text: string;
}

export interface ShastraSummary {
  id: string;
  natural_key: string;
  title: LangText[];
  author?: string;
  anuyogas?: string[];
  gatha_count?: number;
}

export interface ShastraDetail extends ShastraSummary {
  source_url?: string;
  teekas?: TeekaSummary[];
}

export interface TeekaSummary {
  id: string;
  natural_key: string;
  teekakar: string;
  publisher?: string;
  year?: number;
  language?: string;
}

// Keyword (data service)
export interface KeywordSummary {
  id: string;
  natural_key: string;
  display_text: string;
  source_url?: string;
}

export interface KeywordDetail extends KeywordSummary {
  aliases: Array<{ id: string; alias_text: string; source: string }>;
  definition: unknown | null;
}

export interface LetterCount {
  letter: string;
  count: number;
}

// Topic (data service)
export interface TopicSummary {
  id: string;
  natural_key: string;
  display_text: LangText[];
  source: string;
  is_leaf: boolean;
  topic_path: string;
  parent_keyword: KeywordSummary | null;
}

export interface TopicDetail extends TopicSummary {
  is_synthetic: boolean;
  parent_topic: { id: string; natural_key: string; display_text: LangText[] } | null;
  extracts: unknown[];
}

// Gatha (data service)
export interface GathaSummary {
  id: string;
  natural_key: string;
  gatha_number: string;
  shastra: { natural_key: string; title: LangText[] };
  adhikaar: LangText[];
  heading: LangText[];
}

export interface GathaDetail extends GathaSummary {
  prakrit: { natural_key: string; text: LangText[]; is_kalash: boolean } | null;
  sanskrit: { natural_key: string; text: LangText[] } | null;
  hindi_chhand: Array<{ natural_key: string; chhand_index: number; chhand_type: string; text: LangText[] }>;
  word_meanings: unknown | null;
  teeka_mapping?: unknown;
}

// Navigation service neighbor response
export interface TopicNeighborItem {
  natural_key: string;
  display_text_hi: string;
  label: string;
  edge_type: EdgeKind;
  edge_direction: 'outbound' | 'inbound' | 'undirected';
  weight: number;
  is_stub: boolean;
}

export interface TopicNeighborsResponse {
  topic_natural_key: string;
  neighbors: TopicNeighborItem[];
}

// Query service search result
export interface SearchResult {
  topic_nk: string;
  title_hi: string;
  overlap: { matched: number; total: number };
  score: number;
  matched_tokens: string[];
  excerpt: string;
  mentions: Array<{ kind: EntityKind; ref: string }>;
}

export interface SearchResponse {
  results: SearchResult[];
}
