import apiClient from './index';

export type VNMarketBias = 'bullish' | 'neutral' | 'cautious' | 'bearish';
export type VNAction = 'buy_zone' | 'watch_breakout' | 'watch' | 'hold' | 'avoid' | 'sell_reduce';

export interface VNIndexSnapshot {
  code: string;
  name: string;
  close: number | null;
  changePct: number | null;
  volume?: number | null;
  value?: number | null;
}

export interface VNMarketOverview {
  refDate: string | null;
  indices: VNIndexSnapshot[];
  breadth: {
    advancers: number;
    decliners: number;
    ceiling: number;
    floor: number;
    unchanged: number;
  };
  liquidity: {
    totalValue: number | null;
    vs20dPct: number | null;
  };
  marketBias: VNMarketBias;
  warnings: string[];
}

export interface VNScanRequest {
  watchlist: string[];
  mode: 'tplus' | 'breakout' | 'pullback';
}

export interface VNNewsItem {
  title: string;
  source: string;
  date?: string | null;
  url?: string | null;
  impact: 'high' | 'medium' | 'low';
  summary: string;
}

export interface VNNewsCatalyst {
  checked: boolean;
  source: string;
  checkedAt?: string | null;
  freshnessWindow: string;
  sentiment: 'positive' | 'neutral' | 'negative' | 'mixed' | 'unknown';
  catalysts: VNNewsItem[];
  riskFlags: string[];
  dataQuality?: Record<string, unknown>;
}

export interface VNActionPlan {
  ticker: string;
  action: VNAction;
  score: number;
  confidence: number;
  buyZone?: [number, number] | null;
  breakoutTrigger?: number | null;
  stopLoss?: number | null;
  targets: number[];
  positionSizePct?: number | null;
  reasons: string[];
  riskFlags: string[];
  dataQuality?: Record<string, unknown>;
  newsCatalyst?: VNNewsCatalyst | null;
}

export interface VNScanResponse {
  items: VNActionPlan[];
}

export interface VNChartPoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  ema20: number | null;
  ema60: number | null;
  ma50: number | null;
  ma200: number | null;
  vol20: number | null;
  rsi14: number | null;
  macd: number | null;
  macdSignal: number | null;
  macdHist: number | null;
}

export interface VNChartResponse {
  ticker: string;
  items: VNChartPoint[];
  dataQuality?: Record<string, unknown>;
}

export interface VNReportResponse {
  htmlPath: string | null;
  jsonPath: string | null;
  summary: string;
}

export interface VNPortfolioHolding {
  ticker: string;
  quantity: number;
  avgCost: number;
  sellableQty: number;
  pendingQty: number;
}

export interface VNPortfolioItem extends VNPortfolioHolding {
  currentPrice: number | null;
  marketValue: number | null;
  pl: number | null;
  plPct: number | null;
  action: VNAction;
  stopLoss?: number | null;
  targets: number[];
  todayPlan: string[];
  pendingPlan: string;
  riskFlags: string[];
}

export interface VNPortfolioCheckResponse {
  items: VNPortfolioItem[];
}

export interface VNSectorFlowItem {
  sector: string;
  tickers: string[];
  avgScore: number;
  candidateCount: number;
  bias: 'positive' | 'neutral' | 'weak';
  topCandidates: string[];
  riskFlags: string[];
}

export interface VNAlertItem {
  ticker: string;
  action: VNAction;
  score: number;
  alerts: Array<{ type: string; message: string }>;
}

export interface VNAlertRule {
  id: string;
  ticker: string;
  condition: string;
  threshold: number;
  enabled: boolean;
  note: string;
}

export interface VNAlertRuleResult {
  rule: VNAlertRule;
  ticker: string;
  condition: string;
  triggered: boolean;
  currentValue: number | null;
  message: string;
  planAction?: string;
  score?: number;
}

export interface VNJournalItem {
  id: string;
  createdAt: string;
  ticker: string;
  action: string;
  score: number;
  note: string;
}

export interface VNDailyPlaybookResponse {
  generatedAt: string;
  overview: VNMarketOverview;
  summary: string[];
  topSetups: VNActionPlan[];
  avoidList: VNActionPlan[];
  sectorBias: VNSectorFlowItem[];
  portfolioActions: Array<{
    ticker: string;
    action: string;
    plPct: number | null;
    sellableQty: number;
    pendingQty: number;
    plan: string[];
    pendingPlan?: string | null;
  }>;
  warnings: string[];
}

export const vnMarketApi = {
  async getOverview(): Promise<VNMarketOverview> {
    const { data } = await apiClient.get<VNMarketOverview>('/api/v1/vn/market-overview');
    return data;
  },

  async scanWatchlist(payload: VNScanRequest): Promise<VNScanResponse> {
    const { data } = await apiClient.post<VNScanResponse>('/api/v1/vn/scan', payload);
    return data;
  },

  async analyzeTicker(ticker: string): Promise<VNActionPlan> {
    const { data } = await apiClient.get<VNActionPlan>(`/api/v1/vn/analyze/${encodeURIComponent(ticker)}`);
    return data;
  },

  async getTickerChart(ticker: string, days = 160): Promise<VNChartResponse> {
    const { data } = await apiClient.get<VNChartResponse>(`/api/v1/vn/chart/${encodeURIComponent(ticker)}`, { params: { days } });
    return data;
  },

  async exportReport(payload: VNScanRequest): Promise<VNReportResponse> {
    const { data } = await apiClient.post<VNReportResponse>('/api/v1/vn/report', payload);
    return data;
  },

  async checkPortfolio(holdings: VNPortfolioHolding[]): Promise<VNPortfolioCheckResponse> {
    const { data } = await apiClient.post<VNPortfolioCheckResponse>('/api/v1/vn/portfolio-check', { holdings });
    return data;
  },

  async getDailyPlaybook(payload: { watchlist: string[]; holdings: VNPortfolioHolding[]; mode: 'tplus' | 'breakout' | 'pullback' }): Promise<VNDailyPlaybookResponse> {
    const { data } = await apiClient.post<VNDailyPlaybookResponse>('/api/v1/vn/daily-playbook', payload);
    return data;
  },

  async getSectorFlow(payload: VNScanRequest): Promise<{ items: VNSectorFlowItem[] }> {
    const { data } = await apiClient.post<{ items: VNSectorFlowItem[] }>('/api/v1/vn/sector-flow', payload);
    return data;
  },

  async checkAlerts(payload: VNScanRequest): Promise<{ items: VNAlertItem[] }> {
    const { data } = await apiClient.post<{ items: VNAlertItem[] }>('/api/v1/vn/alerts/check', payload);
    return data;
  },

  async checkAlertRules(rules: VNAlertRule[]): Promise<{ items: VNAlertRuleResult[] }> {
    const { data } = await apiClient.post<{ items: VNAlertRuleResult[] }>('/api/v1/vn/alerts/rules/check', { rules });
    return data;
  },

  async createJournalSignal(payload: { ticker: string; action: string; score: number; note: string }): Promise<VNJournalItem> {
    const { data } = await apiClient.post<VNJournalItem>('/api/v1/vn/journal', payload);
    return data;
  },

  async listJournalSignals(): Promise<{ items: VNJournalItem[] }> {
    const { data } = await apiClient.get<{ items: VNJournalItem[] }>('/api/v1/vn/journal');
    return data;
  },
};
