// Shared API types mirroring the FastAPI backend responses.

export interface Article {
  id: number;
  title: string;
  description: string | null;
  url: string;
  source: string | null;
  provider: string;
  author: string | null;
  published_at: string | null;
  published_date: string | null;
  keyword_matched: string | null;
  language: string | null;
  country: string | null;
  image_url: string | null;
  name_of_exam: string;
  exam_category: string;
  board: string;
  conducted_by: string;
  pbt_cbt: string;
  state: string;
  conducted_in: string;
  category: string;
  reason: string;
  exam_year: string;
}

export interface ArticlesList {
  items: Article[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface SearchParams {
  query: string;
  from_date?: string | null;
  to_date?: string | null;
  sources?: string[];
  country?: string;
  language?: string;
  category?: string | null;
  state?: string | null;
  max_results?: number;
}

export interface SearchRunResult {
  search_id: number;
  query: string;
  total_collected: number;
  unique_results: number;
  new_stored: number;
  per_provider: Record<string, number>;
}

export interface SearchHistoryItem {
  id: number;
  query: string;
  from_date: string | null;
  to_date: string | null;
  filters: Record<string, unknown>;
  result_count: number;
  name: string | null;
  is_saved: boolean;
  created_at: string | null;
}

export interface SearchHistoryList {
  items: SearchHistoryItem[];
  count: number;
}

export interface DistEntry {
  key: string | null;
  count: number;
}

export interface TimelineEntry {
  date: string;
  count: number;
}

export interface AnalyticsOverview {
  total_articles: number;
  unique_articles: number;
  source_count: number;
  search_count: number;
  bookmark_count: number;
  by_provider: DistEntry[];
  by_category: DistEntry[];
  by_state: DistEntry[];
  by_exam: DistEntry[];
  timeline: TimelineEntry[];
}

export interface LiveHeadline {
  title: string;
  url: string;
  source: string | null;
  provider: string;
  published_at: string | null;
  image_url: string | null;
}

export interface LiveHeadlines {
  items: LiveHeadline[];
  count: number;
  provider: string;
}

export interface BookmarkItem {
  bookmark_id: number;
  article_id: number;
  bookmarked_at: string | null;
  article: Article | null;
}

export interface User {
  id: number;
  name: string;
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export type ExportFormat = "csv" | "xlsx" | "pdf" | "docx";
