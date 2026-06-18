export type EntityKind = 'shastra' | 'gatha' | 'teeka' | 'gatha_teeka' | 'bhaavarth' | 'kalash' | 'page' | 'topic' | 'keyword' | 'publication' | 'table';

export type EdgeKind =
  | 'IS_A'
  | 'PART_OF'
  | 'RELATED_TO'
  | 'ALIAS_OF'
  | 'HAS_TOPIC'
  | 'HAS_TEEKA'
  | 'HAS_PUBLICATION'
  | 'MENTIONS_KEYWORD'
  | 'MENTIONS_TOPIC'
  | 'IN_SHASTRA'
  | 'IN_TEEKA'
  | 'IN_PUBLICATION'
  | 'CONTAINS_DEFINITION'
  | 'CONTAINS_TABLE';

export type TableType = 'index' | 'general';

export interface TableSummary {
  naturalKey: string;
  seq: number;
  caption: LangText[];
  tableType: TableType;
}

export interface TableFull {
  naturalKey: string;
  pgId: string;
  source: string;
  parentNaturalKey: string;
  parentKind:
    | 'topic' | 'keyword' | 'gatha' | 'gatha_teeka'
    | 'gatha_teeka_bhaavarth' | 'kalash' | 'kalash_bhaavarth' | 'page';
  tableType: TableType;
  seq: number;
  caption: LangText[];
  sourceUrl: string | null;
  rawHtml: string;
  cells: string[][];
  // 3-D list: rows × cols × resolved references per cell (snake_case to match API response).
  cell_refs?: DefinitionReference[][][];
  headerRows: number;
  plaintext: string | null;
  mentionedKeywordNaturalKeys: string[];
  mentionedTopicNaturalKeys: string[];
}

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
  definitionSections?: KeywordPageSection[];
  topicExtracts?: DefinitionBlock[];
  topicPath?: string;
}

// Shastra (metadata service)
export interface LangText {
  lang: string;
  script: string;
  text: string;
}

export interface AuthorSummary {
  id: string;
  natural_key: string;
  display_name: LangText[];
  kind: string;
}

export interface ShastraSummary {
  id: string;
  natural_key: string;
  title: LangText[];
  author?: AuthorSummary | string | null;
  anuyogas?: string[];
  gatha_count?: number;
}

export interface ShastraDetail extends ShastraSummary {
  source_url?: string;
  teekas?: TeekaSummary[];
  pdf_page_offset?: number | Array<[number, number]>;
  pustak_offsets?: Record<string, number | Array<[number, number]>> | null;
}

export interface TeekaSummary {
  id: string;
  natural_key: string;
  teekakar: AuthorSummary | string | null;
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

export interface DefinitionReference {
  text: string;
  inline_reference: boolean;
  needs_manual_match: boolean;
  is_teeka: boolean;
  teeka_name: string;
  shastra_name: string | null;
  match_method: string | null;
  resolved_fields: Array<{ field: string; value: string }>;
}

export interface DefinitionBlock {
  kind: string;
  text_devanagari: string | null;
  hindi_translation: string | null;
  references: DefinitionReference[];
  is_orphan_translation: boolean;
  is_bullet_point: boolean;
  raw_html: string | null;
  table_rows: unknown | null;
  target_keyword: unknown | null;
  target_topic_path: string | null;
  target_url: string | null;
  is_self: boolean;
  target_exists: boolean;
  match_natural_keys?: string[];
  // Rendered <ol>/<li> list number captured by the parser from the HTML source.
  // Present only when the block originates from a <li> inside an <ol>. Reflects
  // the effective browser-rendered number (respects <ol start="N">). Null otherwise.
  list_number?: number | null;
}

export interface DefinitionEntry {
  definition_index: number;
  blocks: DefinitionBlock[];
  raw_html: string | null;
}

export interface KeywordPageSection {
  section_index: number;
  section_kind: string;
  h2_text: string;
  definitions: DefinitionEntry[];
  label_topic_seeds: unknown[];
  extra_blocks: unknown[];
}

export interface KeywordDefinitionData {
  created_at: string;
  keyword_id: string;
  natural_key: string;
  page_sections: KeywordPageSection[];
  redirect_aliases: unknown[];
  source_url: string;
  updated_at: string;
}

export interface KeywordDetail extends KeywordSummary {
  aliases: Array<{ id: string; alias_text: string; source: string }>;
  definition: KeywordDefinitionData | null;
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
  extract_count: number;
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

export interface WordMeaningEntry {
  source_word: LangText[];
  meanings: LangText[];
  position: number;
}

export interface GathaWordMeanings {
  natural_key: string;
  gatha_natural_key: string;
  source_language: string;
  full_anyavaarth?: string | null;
  entries: WordMeaningEntry[];
}

export interface TaggedTerm {
  source_word: string;
  meaning: string;
  position?: number;
  /** Char offsets of `meaning` within `full_anyavaarth` (computed at ingest time). */
  start_offset?: number | null;
  end_offset?: number | null;
}

export interface TeekaGathaMapping {
  natural_key: string;
  teeka_natural_key: string;
  gatha_natural_key: string;
  anvayartha: LangText[];
  tagged_terms: TaggedTerm[];
  full_anyavaarth?: string | null;
  is_related: string[];
}

export interface BhaavarthShortFontOccurrence {
  start_offset: number;
  end_offset: number;
}

export interface BhaavarthShortFontEntry {
  marker_number: number;
  marker_devanagari: string;
  anchor_text: string;
  meaning: string;
  is_definition: boolean;
  occurrences: BhaavarthShortFontOccurrence[];
}

export interface TeekaBhaavarth {
  natural_key: string;
  gatha_teeka_natural_key: string;
  publication_natural_key?: string;
  publisher_id?: string;
  text: LangText[];
  shortfont_entries?: BhaavarthShortFontEntry[];
}

export interface GathaTeekaSanskrit {
  natural_key: string;
  gatha_natural_key: string;
  teeka_natural_key?: string;
  text: LangText[];
}

export interface GataHindiBhaavarth {
  natural_key: string;
  gatha_teeka_natural_key?: string;
  publication_natural_key?: string;
  text: LangText[];
}

export interface GathaKalash {
  natural_key: string;
  kalash_number: string;
  teeka_natural_key: string;
  is_secondary: boolean;
  prakrit: { natural_key: string; text: LangText[] } | null;
  sanskrit: { natural_key: string; text: LangText[] } | null;
  hindi: { natural_key: string; text: LangText[] } | null;
  bhaavarth: Array<{ natural_key: string; text: LangText[]; shortfont_entries?: BhaavarthShortFontEntry[] }>;
  word_meanings: {
    natural_key?: string;
    entries: Array<{
      source_word: string;
      meaning: string;
      position: number;
      start_offset?: number | null;
      end_offset?: number | null;
    }>;
    full_anyavaarth?: string;
  } | null;
}

export interface GathaIdentifierField {
  name: string;
  label: string;
  value: string;
  display?: string;
}

export interface GathaIdentifier {
  fields: GathaIdentifierField[];
  compact: string;
  is_compound: boolean;
}

export interface AdjacentGathaItem {
  natural_key: string;
  compact: string;
  gatha_number: string;
}

export interface GathaAdjacentResponse {
  shastra_nk: string;
  current_nk: string;
  previous: AdjacentGathaItem | null;
  next: AdjacentGathaItem | null;
}

export interface GathaDetail extends GathaSummary {
  prakrit_verse_marker?: string | null;
  prakrit: { natural_key: string; text: LangText[]; is_kalash: boolean } | null;
  sanskrit: { natural_key: string; text: LangText[] } | null;
  hindi_chhand: Array<{ natural_key: string; chhand_index: number; chhand_type: string; text: LangText[] }>;
  word_meanings: { prakrit: GathaWordMeanings | null; sanskrit: GathaWordMeanings | null } | null;
  teeka_mapping?: TeekaGathaMapping[];
  teeka_bhaavarth?: TeekaBhaavarth[];
  teeka_sanskrit?: GathaTeekaSanskrit[];
  kalashas?: GathaKalash[];
  identifier?: GathaIdentifier;
}

export type ExtractMatchTargetCollection =
  | 'gatha_prakrit'
  | 'gatha_sanskrit'
  | 'gatha_teeka_sanskrit'
  | 'gatha_teeka_bhaavarth_hindi'
  | 'kalash_sanskrit'
  | 'kalash_hindi'
  | 'kalash_bhaavarth_hindi';

export interface ExtractMatch {
  natural_key: string;
  target: {
    collection: ExtractMatchTargetCollection;
    natural_key: string;
    shastra_natural_key?: string;
    gatha_natural_key?: string;
    lang: 'pra' | 'san' | 'hin';
  };
  match: {
    status: 'matched' | 'unmatched' | 'target_missing';
    char_start: number | null;
    char_end: number | null;
  };
}

// Kalash (data service)
export interface KalashWordMeaningEntry {
  source_word: string;
  meaning: string;
  position: number;
}

export interface KalashWordMeanings {
  kalash_id: string;
  kalash_natural_key: string;
  teeka_natural_key: string;
  kalash_number: string;
  entries: KalashWordMeaningEntry[];
}

export interface KalashDetail {
  id: string;
  natural_key: string;
  kalash_number: string;
  teeka: {
    id: string;
    natural_key: string;
    shastra: { natural_key: string; title: LangText[] };
    teekakar?: { natural_key: string; display_name: LangText[] } | null;
  };
  sanskrit?: { natural_key: string; text: LangText[] } | null;
  hindi?: { natural_key: string; text: LangText[] } | null;
  bhaavarth: Array<{ natural_key: string; publisher_id: string; text: LangText[] }>;
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

// Query service — topic match (Phase 2)
export interface TopicExtractBlock {
  block_index: number;
  text_hi: string;
}

export interface TopicRef {
  shastra_natural_key: string | null;
  gatha_number: number | null;
  teeka_natural_key: string | null;
  page_number: number | null;
}

export interface TopicMatchItem {
  topic_natural_key: string;
  topic_pg_id: string;
  display_text_hi: string;
  ancestors_hi: string[];
  is_leaf: boolean;
  source: string;
  similarity: number;
  score: number;
  extract_count: number;
  extracts_hi: TopicExtractBlock[] | null;
  references: TopicRef[] | null;
}

export interface TopicsMatchResponse {
  matches: TopicMatchItem[];
  tool_trace_id: string;
}

export type KeywordMatchKind = 'exact' | 'alias' | 'suffix_strip' | 'none';

export interface KeywordResolveSuggestion {
  keyword_natural_key: string;
  similarity: number;
}

export interface KeywordResolution {
  input_token: string;
  match_kind: KeywordMatchKind;
  keyword_natural_key?: string | null;
  keyword_id?: string | null;
  definitions?: { source_natural_key: string; block_index: number; text_hi: string }[] | null;
  suggestions?: KeywordResolveSuggestion[] | null;
}

export interface KeywordResolveBatchResponse {
  resolutions: KeywordResolution[];
  tool_trace_id: string;
}

export interface NeighborTopic {
  topic_natural_key: string;
  display_text_hi: string;
}

export interface NeighborGatha {
  shastra_natural_key: string;
  gatha_number: number | null;
}

export interface NeighborKeyword {
  keyword_natural_key: string;
}

export interface TopicNeighbors {
  related_topics: NeighborTopic[];
  mentioned_in_gathas: NeighborGatha[];
  related_keywords: NeighborKeyword[];
}

export interface RankedTopicItem {
  topic_natural_key: string;
  topic_pg_id: string;
  display_text_hi: string;
  ancestors_hi: string[];
  score: number;
  overlap_count: number;
  matched_seed_keywords: string[];
  is_leaf: boolean;
  source: string;
  extracts_hi: TopicExtractBlock[] | null;
  references: TopicRef[] | null;
  neighbors: TopicNeighbors | null;
}

export interface GraphRAGResponse {
  ranked_topics: RankedTopicItem[];
  unresolved_tokens: string[];
  tool_trace_id: string;
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
