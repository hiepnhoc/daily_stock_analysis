import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Download, RefreshCw, Search } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  vnMarketApi,
  type VNAction,
  type VNActionPlan,
  type VNChartPoint,
  type VNDailyPlaybookResponse,
  type VNMarketOverview,
  type VNAlertItem,
  type VNAlertRule,
  type VNAlertRuleResult,
  type VNJournalItem,
  type VNPortfolioItem,
  type VNSectorFlowItem,
} from '../api/vnMarket';
import { getParsedApiError } from '../api/error';
import { formatVNDateTime, isValidVNTicker, parsePortfolioInput, type PortfolioInputError } from '../utils/vnMarket';

const DEFAULT_WATCHLIST = 'HPG,FPT,SSI,VCI,TCB,MWG';
const DEFAULT_PORTFOLIO = 'HPG,1000,30,600,400\nFPT,500,120,500,0';
const WATCHLIST_STORAGE_KEY = 'vn-market-watchlist-v1';
const PORTFOLIO_STORAGE_KEY = 'vn-market-portfolio-v1';
const ALERT_RULES_STORAGE_KEY = 'vn-market-alert-rules-v1';
const DEFAULT_ALERT_RULES: VNAlertRule[] = [
  { id: 'hpg-breakout', ticker: 'HPG', condition: 'near_breakout', threshold: 1, enabled: true, note: 'Sát breakout 1%' },
  { id: 'hpg-stop', ticker: 'HPG', condition: 'near_stop', threshold: 1, enabled: true, note: 'Sát stop 1%' },
];

function readSavedText(key: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  try {
    const saved = window.localStorage.getItem(key);
    return saved && saved.trim() ? saved : fallback;
  } catch {
    return fallback;
  }
}

function saveText(key: string, value: string): boolean {
  if (typeof window === 'undefined') return false;
  try {
    window.localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function readSavedRules(): VNAlertRule[] {
  if (typeof window === 'undefined') return DEFAULT_ALERT_RULES;
  try {
    const raw = window.localStorage.getItem(ALERT_RULES_STORAGE_KEY);
    if (!raw) return DEFAULT_ALERT_RULES;
    const parsed = JSON.parse(raw) as VNAlertRule[];
    return Array.isArray(parsed) && parsed.length ? parsed : DEFAULT_ALERT_RULES;
  } catch {
    return DEFAULT_ALERT_RULES;
  }
}

function saveRules(rules: VNAlertRule[]): boolean {
  if (typeof window === 'undefined') return false;
  try {
    window.localStorage.setItem(ALERT_RULES_STORAGE_KEY, JSON.stringify(rules));
    return true;
  } catch {
    return false;
  }
}

function formatZone(zone?: [number, number] | null): string {
  return zone ? `${zone[0]} - ${zone[1]}` : '--';
}

function formatMoney(value?: number | null): string {
  if (value == null) return '--';
  return new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 }).format(value);
}

type VNWorkspaceSection = 'overview' | 'scanner' | 'analyze' | 'portfolio' | 'alerts';

const workspaceSections: Array<{ id: VNWorkspaceSection; label: string; path: string }> = [
  { id: 'overview', label: 'Tổng quan', path: '/vn-market' },
  { id: 'scanner', label: 'Scanner T+', path: '/vn-market/scanner' },
  { id: 'analyze', label: 'Phân tích mã', path: '/vn-market/analyze' },
  { id: 'portfolio', label: 'Portfolio T+', path: '/vn-portfolio' },
  { id: 'alerts', label: 'Cảnh báo & Nhật ký', path: '/vn-market/alerts' },
];

function sectionFromPath(pathname: string): VNWorkspaceSection {
  if (pathname === '/vn-portfolio' || pathname.endsWith('/portfolio')) return 'portfolio';
  if (pathname.endsWith('/scanner')) return 'scanner';
  if (pathname.endsWith('/analyze')) return 'analyze';
  if (pathname.endsWith('/alerts')) return 'alerts';
  return 'overview';
}

function friendlyError(error: unknown): string {
  const parsed = getParsedApiError(error);
  if (parsed.category === 'local_connection_failed' || parsed.category === 'upstream_timeout') {
    return 'Backend đang khởi động hoặc tạm thời chưa phản hồi. Chờ vài giây rồi thử lại.';
  }
  if (parsed.status === 422) return 'Dữ liệu đầu vào không hợp lệ. Kiểm tra các trường được đánh dấu rồi thử lại.';
  return 'Không hoàn tất được tác vụ. Chi tiết kỹ thuật đã được giữ trong log máy chủ.';
}

const actionTone: Record<string, string> = {
  watch_breakout: 'text-emerald-500',
  buy_zone: 'text-emerald-500',
  watch: 'text-amber-500',
  hold: 'text-sky-500',
  avoid: 'text-rose-500',
  sell_reduce: 'text-rose-500',
};

const actionVerdict: Record<VNAction, { label: string; note: string; className: string }> = {
  buy_zone: {
    label: 'MUA CANH',
    note: 'Chỉ mua trong vùng giá đẹp, không FOMO.',
    className: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-400',
  },
  watch_breakout: {
    label: 'CANH BREAK',
    note: 'Chờ vượt trigger kèm volume xác nhận.',
    className: 'border-cyan-400/40 bg-cyan-500/10 text-cyan-400',
  },
  watch: {
    label: 'THEO DÕI',
    note: 'Chưa đủ đẹp để hành động mạnh.',
    className: 'border-amber-400/40 bg-amber-500/10 text-amber-400',
  },
  hold: {
    label: 'GIỮ',
    note: 'Có thể giữ theo plan, theo dõi stop/target.',
    className: 'border-sky-400/40 bg-sky-500/10 text-sky-400',
  },
  avoid: {
    label: 'TRÁNH MUA',
    note: 'Setup yếu/rủi ro cao, không mua thêm.',
    className: 'border-rose-400/40 bg-rose-500/10 text-rose-400',
  },
  sell_reduce: {
    label: 'BÁN GIẢM',
    note: 'Ưu tiên giảm tỷ trọng phần bán được.',
    className: 'border-rose-400/40 bg-rose-500/10 text-rose-400',
  },
};

function verdictFor(action: VNAction): { label: string; note: string; className: string } {
  return actionVerdict[action] ?? actionVerdict.watch;
}

function displayNewsSource(source?: string): string {
  if (!source) return 'public web news';
  if (source === 'agent-reach:multi-source') return 'multi-source news';
  if (source === 'agent-reach:rss:google-news') return 'Google News RSS';
  if (source === 'agent-reach:jina-reader') return 'Jina Reader';
  if (source === 'agent-reach:exa:mcporter') return 'Exa via Agent Reach';
  if (source === 'agent-reach:rss:direct') return 'VN direct RSS';
  return source.replace(/^agent-reach:/, '').replaceAll(':', ' · ');
}

function sourceStatusTone(status: string): string {
  if (status === 'available') return 'text-emerald-500';
  if (status === 'partial') return 'text-amber-500';
  return 'text-rose-500';
}

function routeGroupKey(sourceRoute?: string | null): 'google' | 'agentReach' {
  return sourceRoute === 'agent-reach:rss:google-news' ? 'google' : 'agentReach';
}

const lineColors = {
  ema20: '#22d3ee',
  ema60: '#a78bfa',
  ma50: '#fbbf24',
  ma200: '#94a3b8',
};

function VNPriceChart({ points, plan }: { points: VNChartPoint[]; plan?: VNActionPlan | null }) {
  const data = points.filter((point) => point.open != null && point.high != null && point.low != null && point.close != null);
  if (data.length < 5) {
    return <div className="mt-4 rounded-2xl border border-border bg-base p-4 text-sm text-secondary-text">Chưa đủ dữ liệu chart.</div>;
  }
  const width = 760;
  const priceHeight = 250;
  const volumeHeight = 70;
  const padding = { top: 18, right: 18, bottom: 22, left: 44 };
  const chartWidth = width - padding.left - padding.right;
  const planLevels = [plan?.buyZone?.[0], plan?.buyZone?.[1], plan?.breakoutTrigger, plan?.stopLoss, ...(plan?.targets ?? [])].filter((value): value is number => value != null && Number.isFinite(value));
  const values = data.flatMap((point) => [point.high, point.low, point.ema20, point.ema60, point.ma50, point.ma200]).filter((value): value is number => value != null && Number.isFinite(value));
  const minPrice = Math.min(...values, ...planLevels);
  const maxPrice = Math.max(...values, ...planLevels);
  const priceRange = Math.max(maxPrice - minPrice, 0.01);
  const maxVolume = Math.max(...data.map((point) => point.volume ?? 0), 1);
  const x = (index: number) => padding.left + (index / Math.max(data.length - 1, 1)) * chartWidth;
  const y = (value: number) => padding.top + ((maxPrice - value) / priceRange) * (priceHeight - padding.top - padding.bottom);
  const candleWidth = Math.max(2, Math.min(8, chartWidth / data.length * 0.58));
  const linePath = (key: keyof Pick<VNChartPoint, 'ema20' | 'ema60' | 'ma50' | 'ma200'>) => data.map((point, index) => point[key] == null ? null : `${index === 0 ? 'M' : 'L'} ${x(index).toFixed(1)} ${y(point[key] as number).toFixed(1)}`).filter(Boolean).join(' ');
  const latest = data[data.length - 1];
  const indicatorData = data.slice(-60);
  const rsiPoints = indicatorData.filter((point) => point.rsi14 != null);
  const macdValues = indicatorData.flatMap((point) => [point.macd, point.macdSignal, point.macdHist]).filter((value): value is number => value != null && Number.isFinite(value));
  const macdAbsMax = Math.max(...macdValues.map((value) => Math.abs(value)), 0.01);
  const marker = (label: string, value: number | null | undefined, color: string, dash = '6 4') => {
    if (value == null || !Number.isFinite(value)) return null;
    const yy = y(value);
    return <g key={`${label}-${value}`}><line x1={padding.left} y1={yy} x2={width - padding.right} y2={yy} stroke={color} strokeDasharray={dash} strokeWidth="1.4" /><rect x={width - padding.right - 92} y={yy - 9} width="90" height="18" rx="6" fill="#020617" opacity="0.82" /><text x={width - padding.right - 86} y={yy + 4} fill={color} fontSize="10">{label} {value}</text></g>;
  };
  return (
    <div className="mt-4 rounded-2xl border border-border bg-base p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-secondary-text">
        <span>{data[0].date} → {latest.date}</span>
        <span>Close {latest.close} · EMA20 {latest.ema20 ?? '--'} · EMA60 {latest.ema60 ?? '--'}</span>
      </div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${priceHeight + volumeHeight}`} className="min-w-[720px] rounded-xl bg-slate-950/40">
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const yy = padding.top + ratio * (priceHeight - padding.top - padding.bottom);
            const price = maxPrice - ratio * priceRange;
            return <g key={ratio}><line x1={padding.left} y1={yy} x2={width - padding.right} y2={yy} stroke="#1f2937" /><text x={8} y={yy + 4} fill="#94a3b8" fontSize="10">{price.toFixed(2)}</text></g>;
          })}
          {data.map((point, index) => {
            const xx = x(index);
            const bullish = (point.close ?? 0) >= (point.open ?? 0);
            const color = bullish ? '#10b981' : '#ef4444';
            const openY = y(point.open as number);
            const closeY = y(point.close as number);
            const highY = y(point.high as number);
            const lowY = y(point.low as number);
            const bodyY = Math.min(openY, closeY);
            const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);
            const volumeY = priceHeight + volumeHeight - ((point.volume ?? 0) / maxVolume) * (volumeHeight - 12);
            return <g key={`${point.date}-${index}`}><line x1={xx} y1={highY} x2={xx} y2={lowY} stroke={color} /><rect x={xx - candleWidth / 2} y={bodyY} width={candleWidth} height={bodyHeight} fill={color} opacity="0.9" /><rect x={xx - candleWidth / 2} y={volumeY} width={candleWidth} height={priceHeight + volumeHeight - volumeY} fill={color} opacity="0.35" /></g>;
          })}
          {plan?.buyZone ? <rect x={padding.left} y={y(plan.buyZone[1])} width={chartWidth} height={Math.max(y(plan.buyZone[0]) - y(plan.buyZone[1]), 2)} fill="#10b981" opacity="0.10" /> : null}
          <path d={linePath('ema20')} fill="none" stroke={lineColors.ema20} strokeWidth="1.6" />
          <path d={linePath('ema60')} fill="none" stroke={lineColors.ema60} strokeWidth="1.6" />
          <path d={linePath('ma50')} fill="none" stroke={lineColors.ma50} strokeWidth="1.2" strokeDasharray="4 3" />
          <path d={linePath('ma200')} fill="none" stroke={lineColors.ma200} strokeWidth="1.2" strokeDasharray="5 4" />
          {marker('BUY↓', plan?.buyZone?.[0], '#10b981', '3 3')}
          {marker('BUY↑', plan?.buyZone?.[1], '#10b981', '3 3')}
          {marker('BRK', plan?.breakoutTrigger, '#38bdf8')}
          {marker('STOP', plan?.stopLoss, '#fb7185')}
          {(plan?.targets ?? []).slice(0, 2).map((target, index) => marker(`T${index + 1}`, target, '#fbbf24'))}
        </svg>
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-secondary-text">
        <span style={{ color: lineColors.ema20 }}>EMA20</span><span style={{ color: lineColors.ema60 }}>EMA60</span><span style={{ color: lineColors.ma50 }}>MA50</span><span style={{ color: lineColors.ma200 }}>MA200</span><span className="text-emerald-500">Buy zone</span><span className="text-sky-400">Breakout</span><span className="text-rose-400">Stop</span><span className="text-amber-400">Targets</span><span>Volume bars bên dưới</span>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-slate-950/30 p-3">
          <div className="mb-2 flex items-center justify-between text-xs text-secondary-text"><span>RSI14</span><span>{latest.rsi14?.toFixed?.(1) ?? '--'}</span></div>
          <div className="relative h-16 overflow-hidden rounded-lg bg-slate-950/50">
            <div className="absolute left-0 right-0 top-[30%] border-t border-rose-400/40" /><div className="absolute left-0 right-0 top-[70%] border-t border-emerald-400/40" />
            <svg viewBox="0 0 300 64" className="h-full w-full"><path d={rsiPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${(index / Math.max(rsiPoints.length - 1, 1)) * 300} ${64 - ((point.rsi14 ?? 50) / 100) * 64}`).join(' ')} fill="none" stroke="#22d3ee" strokeWidth="2" /></svg>
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-secondary-text"><span>30</span><span>50</span><span>70</span></div>
        </div>
        <div className="rounded-xl border border-border bg-slate-950/30 p-3">
          <div className="mb-2 flex items-center justify-between text-xs text-secondary-text"><span>MACD</span><span>{latest.macd?.toFixed?.(2) ?? '--'} / {latest.macdSignal?.toFixed?.(2) ?? '--'}</span></div>
          <div className="relative h-16 overflow-hidden rounded-lg bg-slate-950/50">
            <div className="absolute left-0 right-0 top-1/2 border-t border-slate-500/50" />
            <div className="flex h-full items-center gap-[1px] px-1">{indicatorData.map((point, index) => { const hist = point.macdHist ?? 0; const height = Math.max(Math.abs(hist) / macdAbsMax * 30, 1); return <div key={`${point.date}-macd-${index}`} className="flex flex-1 items-center justify-center"><div className={hist >= 0 ? 'bg-emerald-500/70' : 'bg-rose-500/70'} style={{ height, width: '70%', transform: hist >= 0 ? 'translateY(-50%)' : 'translateY(50%)' }} /></div>; })}</div>
          </div>
          <div className="mt-1 text-[10px] text-secondary-text">Histogram xanh/đỏ quanh đường 0; MACD cắt signal cần xác nhận thêm bằng giá/volume.</div>
        </div>
      </div>
    </div>
  );
}

const VNMarketPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const activeSection = sectionFromPath(location.pathname);
  const [watchlistText, setWatchlistText] = useState(() => readSavedText(WATCHLIST_STORAGE_KEY, DEFAULT_WATCHLIST));
  const [analyzeTickerText, setAnalyzeTickerText] = useState('HPG');
  const [portfolioText, setPortfolioText] = useState(() => readSavedText(PORTFOLIO_STORAGE_KEY, DEFAULT_PORTFOLIO));
  const [overview, setOverview] = useState<VNMarketOverview | null>(null);
  const [items, setItems] = useState<VNActionPlan[]>([]);
  const [analysis, setAnalysis] = useState<VNActionPlan | null>(null);
  const [chartItems, setChartItems] = useState<VNChartPoint[]>([]);
  const [portfolioItems, setPortfolioItems] = useState<VNPortfolioItem[]>([]);
  const [sectorItems, setSectorItems] = useState<VNSectorFlowItem[]>([]);
  const [alertItems, setAlertItems] = useState<VNAlertItem[]>([]);
  const [alertRules, setAlertRules] = useState<VNAlertRule[]>(() => readSavedRules());
  const [alertRuleResults, setAlertRuleResults] = useState<VNAlertRuleResult[]>([]);
  const [journalItems, setJournalItems] = useState<VNJournalItem[]>([]);
  const [journalNote, setJournalNote] = useState('');
  const [playbook, setPlaybook] = useState<VNDailyPlaybookResponse | null>(null);
  const [autoRefreshMinutes, setAutoRefreshMinutes] = useState(0);
  const [lastAutoRefreshAt, setLastAutoRefreshAt] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isCheckingPortfolio, setIsCheckingPortfolio] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [isGeneratingPlaybook, setIsGeneratingPlaybook] = useState(false);
  const [isLoadingSector, setIsLoadingSector] = useState(false);
  const [isLoadingAlerts, setIsLoadingAlerts] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSavingJournal, setIsSavingJournal] = useState(false);
  const [isOverviewLoading, setIsOverviewLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [portfolioErrors, setPortfolioErrors] = useState<PortfolioInputError[]>([]);
  const [portfolioResultAt, setPortfolioResultAt] = useState<string | null>(null);
  const [scanResultAt, setScanResultAt] = useState<string | null>(null);
  const [analysisResultAt, setAnalysisResultAt] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);


  const watchlist = useMemo(
    () => watchlistText.split(/[\s,;]+/).map((item) => item.trim().toUpperCase()).filter(Boolean),
    [watchlistText],
  );

  const loadOverview = async (attempt = 0) => {
    setIsOverviewLoading(true);
    try {
      await vnMarketApi.getReadiness();
      setOverview(await vnMarketApi.getOverview());
      setError(null);
    } catch (err) {
      setError(friendlyError(err));
      if (attempt < 2) {
        window.setTimeout(() => void loadOverview(attempt + 1), 1_500 * (attempt + 1));
      }
    } finally {
      setIsOverviewLoading(false);
    }
  };

  useEffect(() => {
    void loadOverview();
    // Initial readiness/overview bootstrap owns its bounded retry loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  useEffect(() => {
    setError(null);
    setSaveStatus(null);
    setExportResult(null);
  }, [activeSection]);

  const saveWatchlist = () => {
    setSaveStatus(saveText(WATCHLIST_STORAGE_KEY, watchlistText) ? 'Đã lưu watchlist VN trên trình duyệt này.' : 'Không lưu được watchlist trên trình duyệt này.');
  };

  const resetWatchlist = () => {
    setWatchlistText(DEFAULT_WATCHLIST);
    setItems([]);
    setScanResultAt(null);
    setPlaybook(null);
    setSaveStatus('Đã reset watchlist về mặc định; bấm Lưu nếu muốn ghi đè bản lưu.');
  };

  const savePortfolio = () => {
    setSaveStatus(saveText(PORTFOLIO_STORAGE_KEY, portfolioText) ? 'Đã lưu Portfolio T+ trên trình duyệt này.' : 'Không lưu được Portfolio T+ trên trình duyệt này.');
  };

  const resetPortfolio = () => {
    setPortfolioText(DEFAULT_PORTFOLIO);
    setPortfolioItems([]);
    setPortfolioErrors([]);
    setPortfolioResultAt(null);
    setPlaybook(null);
    setSaveStatus('Đã reset portfolio về ví dụ mặc định; bấm Lưu nếu muốn ghi đè bản lưu.');
  };

  const runScan = async () => {
    const invalidTickers = watchlist.filter((ticker) => !isValidVNTicker(ticker));
    if (!watchlist.length || invalidTickers.length) {
      setError(invalidTickers.length ? `Watchlist có mã không hợp lệ: ${invalidTickers.join(', ')}` : 'Watchlist đang trống.');
      return;
    }
    setIsLoading(true);
    setError(null);
    setExportResult(null);
    try {
      const response = await vnMarketApi.scanWatchlist({ watchlist, mode: 'tplus' });
      setItems(response.items);
      setScanResultAt(new Date().toISOString());
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const runAnalyze = async () => {
    const ticker = analyzeTickerText.trim().toUpperCase();
    if (!isValidVNTicker(ticker)) {
      setError('Mã phân tích phải gồm đúng 3 chữ cái A-Z.');
      return;
    }
    setIsAnalyzing(true);
    setError(null);
    setAnalysis(null);
    setChartItems([]);
    try {
      const [analysisResponse, chartResponse] = await Promise.all([
        vnMarketApi.analyzeTicker(ticker),
        vnMarketApi.getTickerChart(ticker, 160),
      ]);
      setAnalysis(analysisResponse);
      setChartItems(chartResponse.items);
      setAnalysisResultAt(new Date().toISOString());
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const runPortfolioCheck = async () => {
    const parsed = parsePortfolioInput(portfolioText);
    setPortfolioErrors(parsed.errors);
    if (parsed.errors.length) {
      setError('Portfolio có dữ liệu không hợp lệ. Request chưa được gửi lên backend.');
      return;
    }
    setIsCheckingPortfolio(true);
    setError(null);
    try {
      const response = await vnMarketApi.checkPortfolio(parsed.validRows);
      setPortfolioItems(response.items);
      setPortfolioResultAt(new Date().toISOString());
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsCheckingPortfolio(false);
    }
  };

  const runSectorFlow = async () => {
    setIsLoadingSector(true);
    setError(null);
    try {
      const response = await vnMarketApi.getSectorFlow({ watchlist, mode: 'tplus' });
      setSectorItems(response.items);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsLoadingSector(false);
    }
  };

  const runAlerts = async () => {
    setIsLoadingAlerts(true);
    setError(null);
    try {
      const [alertsResponse, rulesResponse] = await Promise.all([
        vnMarketApi.checkAlerts({ watchlist, mode: 'tplus' }),
        vnMarketApi.checkAlertRules(alertRules),
      ]);
      setAlertItems(alertsResponse.items);
      setAlertRuleResults(rulesResponse.items);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsLoadingAlerts(false);
    }
  };

  const updateAlertRule = (id: string, patch: Partial<VNAlertRule>) => {
    setAlertRules((rules) => rules.map((rule) => rule.id === id ? { ...rule, ...patch } : rule));
    setAlertRuleResults([]);
  };

  const addAlertRule = () => {
    const id = `rule-${Date.now()}`;
    setAlertRules((rules) => [...rules, { id, ticker: 'HPG', condition: 'price_above', threshold: 0, enabled: true, note: '' }]);
    setAlertRuleResults([]);
  };

  const removeAlertRule = (id: string) => {
    setAlertRules((rules) => rules.filter((rule) => rule.id !== id));
    setAlertRuleResults([]);
  };

  const saveAlertRules = () => {
    setSaveStatus(saveRules(alertRules) ? 'Đã lưu luật cảnh báo trên trình duyệt này.' : 'Không lưu được luật cảnh báo.');
  };

  const resetAlertRules = () => {
    setAlertRules(DEFAULT_ALERT_RULES);
    setAlertRuleResults([]);
    setSaveStatus('Đã reset luật cảnh báo về ví dụ mặc định.');
  };

  const runDailyPlaybook = async () => {
    const parsed = parsePortfolioInput(portfolioText);
    if (parsed.errors.length) {
      setPortfolioErrors(parsed.errors);
      setError('Portfolio có dữ liệu không hợp lệ nên chưa thể tạo kế hoạch ngày.');
      return;
    }
    setIsGeneratingPlaybook(true);
    setError(null);
    try {
      const response = await vnMarketApi.getDailyPlaybook({ watchlist, holdings: parsed.validRows, mode: 'tplus' });
      setPlaybook(response);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsGeneratingPlaybook(false);
    }
  };

  const refreshLivePanels = async () => {
    const parsed = parsePortfolioInput(portfolioText);
    setIsRefreshing(true);
    try {
      await loadOverview();
      const tasks: Promise<unknown>[] = [
        vnMarketApi.checkAlerts({ watchlist, mode: 'tplus' }).then((response) => setAlertItems(response.items)),
        vnMarketApi.checkAlertRules(alertRules).then((response) => setAlertRuleResults(response.items)),
      ];
      if (!parsed.errors.length) {
        tasks.push(vnMarketApi.getDailyPlaybook({ watchlist, holdings: parsed.validRows, mode: 'tplus' }).then(setPlaybook));
        tasks.push(vnMarketApi.checkPortfolio(parsed.validRows).then((response) => setPortfolioItems(response.items)));
      }
      await Promise.allSettled(tasks);
      setLastAutoRefreshAt(new Date().toISOString());
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (!autoRefreshMinutes) return undefined;
    const interval = window.setInterval(() => {
      void refreshLivePanels();
    }, autoRefreshMinutes * 60_000);
    return () => window.clearInterval(interval);
    // Inputs are listed explicitly so changing watchlist/portfolio/rules restarts the timer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefreshMinutes, watchlistText, portfolioText, alertRules]);

  const saveJournal = async () => {
    const source = analysis ?? items[0];
    if (!source) {
      setError('Hãy phân tích hoặc scan ít nhất một mã trước khi lưu nhật ký.');
      return;
    }
    setError(null);
    setIsSavingJournal(true);
    try {
      await vnMarketApi.createJournalSignal({ ticker: source.ticker, action: source.action, score: source.score, note: journalNote });
      const response = await vnMarketApi.listJournalSignals();
      setJournalItems(response.items);
      setJournalNote('');
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsSavingJournal(false);
    }
  };

  const exportReport = async () => {
    setIsExporting(true);
    setError(null);
    try {
      const response = await vnMarketApi.exportReport({ watchlist, mode: 'tplus' });
      setExportResult(`${response.summary}: ${response.htmlPath ?? 'không có HTML'} / ${response.jsonPath ?? 'không có JSON'}`);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="min-w-0 space-y-4 overflow-x-hidden p-4 sm:space-y-6 sm:p-6">
      <section className="min-w-0 rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-secondary-text">Chứng khoán Việt Nam</p>
            <h1 className="mt-2 text-2xl font-semibold text-foreground">Không gian giao dịch VN / T+</h1>
            <p className="mt-2 max-w-3xl text-sm text-secondary-text">
              Bối cảnh VNINDEX, phân tích kỹ thuật, portfolio T+, scanner, kế hoạch hành động và xuất báo cáo.
            </p>
          </div>
          <div className="rounded-2xl border border-border bg-base p-3 text-xs text-secondary-text">
            <label htmlFor="vn-auto-refresh" className="block font-medium text-foreground">Tự động làm mới</label>
            <select id="vn-auto-refresh" aria-label="Chu kỳ tự động làm mới" className="mt-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-foreground" value={autoRefreshMinutes} onChange={(event) => setAutoRefreshMinutes(Number(event.target.value))}>
              <option value={0}>Tắt</option>
              <option value={1}>1 phút</option>
              <option value={5}>5 phút</option>
              <option value={15}>15 phút</option>
            </select>
            <button type="button" className="btn-secondary ml-2 inline-flex items-center gap-2" onClick={() => void refreshLivePanels()} disabled={isRefreshing}>{isRefreshing ? <RefreshCw className="h-4 w-4 animate-spin" /> : null}Làm mới</button>
            <div className="mt-2">Lần cuối: {formatVNDateTime(lastAutoRefreshAt)}</div>
          </div>
        </div>
      </section>

      <nav aria-label="Điều hướng VN Market" className="flex max-w-full gap-2 overflow-x-auto rounded-2xl border border-border bg-surface p-2">
        {workspaceSections.map((section) => (
          <button key={section.id} type="button" onClick={() => navigate(section.path)} aria-current={activeSection === section.id ? 'page' : undefined} className={`shrink-0 rounded-xl px-3 py-2 text-sm font-medium transition ${activeSection === section.id ? 'bg-[hsl(var(--primary))] text-white' : 'text-secondary-text hover:bg-hover hover:text-foreground'}`}>
            {section.label}
          </button>
        ))}
      </nav>

      {error ? <div className="rounded-2xl border border-red-300 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
      {exportResult ? <div className="rounded-2xl border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-800">{exportResult}</div> : null}
      {saveStatus ? <div className="rounded-2xl border border-sky-300 bg-sky-50 p-4 text-sm text-sky-800">{saveStatus}</div> : null}

      <section className={`${activeSection === 'overview' ? 'grid' : 'hidden'} min-w-0 gap-4 md:grid-cols-4`}>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">Xu hướng thị trường</div><div className="mt-1 text-xl font-semibold capitalize">{isOverviewLoading ? 'Đang tải…' : overview?.marketBias ?? '--'}</div></div>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">VNINDEX</div><div className="mt-1 text-xl font-semibold">{overview?.indices?.[0]?.close?.toFixed?.(2) ?? '--'}</div></div>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">Tăng / Giảm</div><div className="mt-1 text-xl font-semibold">{overview ? `${overview.breadth.advancers} / ${overview.breadth.decliners}` : '--'}</div></div>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">Cảnh báo</div><div className="mt-1 text-sm text-secondary-text">{overview?.warnings?.join(', ') || '--'}</div></div>
      </section>

      <section className={`${activeSection === 'overview' ? 'block' : 'hidden'} min-w-0 rounded-3xl border border-border bg-surface p-4 sm:p-6`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold text-foreground">Kế hoạch trong ngày</h2>
            <p className="mt-1 text-xs text-secondary-text">Tổng hợp market, watchlist, sector và portfolio thành kế hoạch hành động hôm nay.</p>
          </div>
          <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => void runDailyPlaybook()} disabled={isGeneratingPlaybook}>{isGeneratingPlaybook ? <RefreshCw className="h-4 w-4 animate-spin" /> : null}{isGeneratingPlaybook ? 'Đang tạo…' : 'Tạo kế hoạch'}</button>
        </div>
        {playbook ? (
          <div className="mt-5 grid gap-4 xl:grid-cols-3">
            <div className="rounded-2xl border border-border bg-base p-4 text-sm xl:col-span-1">
              <div className="text-xs text-secondary-text">Tạo lúc {formatVNDateTime(playbook.generatedAt)}</div>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-secondary-text">{playbook.summary.map((line) => <li key={line}>{line}</li>)}</ul>
              <div className="mt-3 text-xs text-amber-500">Warnings: {playbook.warnings.join('; ') || '--'}</div>
            </div>
            <div className="rounded-2xl border border-border bg-base p-4 text-sm">
              <h3 className="font-medium text-foreground">Setup có thể hành động</h3>
              <div className="mt-3 space-y-2">{playbook.topSetups.slice(0, 4).map((item) => <div key={item.ticker} className="flex justify-between gap-3"><span>{item.ticker} <span className={actionTone[item.action]}>{verdictFor(item.action).label}</span></span><span>điểm {item.score}</span></div>) || null}</div>
              {playbook.topSetups.length === 0 ? <div className="mt-3 text-secondary-text">Không có setup hành động — ưu tiên quan sát và giữ tiền mặt.</div> : null}
            </div>
            <div className="rounded-2xl border border-border bg-base p-4 text-sm">
              <h3 className="font-medium text-foreground">Hành động Portfolio</h3>
              <div className="mt-3 space-y-3">{playbook.portfolioActions.map((item) => <div key={item.ticker}><div className="flex justify-between gap-3"><strong>{item.ticker}</strong><span>{item.plPct ?? '--'}%</span></div><ul className="mt-1 list-disc pl-5 text-xs text-secondary-text">{item.plan.map((line) => <li key={line}>{line}</li>)}</ul><div className="mt-1 text-xs text-amber-500">{item.pendingPlan}</div></div>)}</div>
              {playbook.portfolioActions.length === 0 ? <div className="mt-3 text-secondary-text">Chưa nhập portfolio hoặc không có vị thế.</div> : null}
            </div>
            <div className="rounded-2xl border border-border bg-base p-4 text-sm xl:col-span-3">
              <h3 className="font-medium text-foreground">Xu hướng ngành</h3>
              <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-5">{playbook.sectorBias.map((item) => <div key={item.sector} className="rounded-xl border border-border p-3"><div className="font-medium">{item.sector}</div><div className="text-xs text-secondary-text">{item.bias} · {item.avgScore}</div><div className="mt-1 text-xs text-emerald-500">{item.topCandidates.join(', ') || '--'}</div></div>)}</div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="min-w-0">
        <div className={`${activeSection === 'analyze' ? 'block' : 'hidden'} min-w-0 max-w-full rounded-3xl border border-border bg-surface p-4 sm:p-6`}>
          <h2 className="font-semibold text-foreground">Phân tích cổ phiếu VN</h2>
          <p className="mt-1 text-xs text-secondary-text">Phân tích một mã theo VN T+: vùng mua, breakout, stop, target, size và risk.</p>
          <div className="mt-4 flex gap-3">
            <input aria-label="Mã cổ phiếu cần phân tích" className="min-w-0 flex-1 rounded-2xl border border-border bg-base p-3 text-sm text-foreground" value={analyzeTickerText} onChange={(event) => { setAnalyzeTickerText(event.target.value); setAnalysis(null); setChartItems([]); setAnalysisResultAt(null); }} placeholder="HPG" />
            <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => void runAnalyze()} disabled={isAnalyzing}>{isAnalyzing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}{isAnalyzing ? 'Đang phân tích…' : 'Phân tích'}</button>
          </div>
          {analysis ? (
            <div className="mt-5 min-w-0 rounded-2xl border border-border bg-base p-4 text-sm">
              <div className="mb-3 text-xs text-secondary-text">Kết quả lúc {formatVNDateTime(analysisResultAt)}</div>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <strong className="text-lg">{analysis.ticker}</strong>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${verdictFor(analysis.action).className}`}>Kết luận: {verdictFor(analysis.action).label}</span>
                    <span className="text-xs text-secondary-text">{verdictFor(analysis.action).note}</span>
                  </div>
                </div>
                <span className={actionTone[analysis.action]}>{verdictFor(analysis.action).label} · điểm {analysis.score}</span>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <div>Vùng mua: {formatZone(analysis.buyZone)}</div><div>Breakout: {analysis.breakoutTrigger ?? '--'}</div><div>Cắt lỗ: {analysis.stopLoss ?? '--'}</div><div>Mục tiêu: {analysis.targets.join(' / ') || '--'}</div><div>Tỷ trọng: {analysis.positionSizePct ?? 0}%</div><div>Độ tin cậy: {(analysis.confidence * 100).toFixed(0)}%</div>
              </div>
              <div className="mt-3 text-secondary-text">Lý do: {analysis.reasons.join('; ') || '--'}</div>
              <div className="mt-2 text-amber-500">Rủi ro: {analysis.riskFlags.join('; ')}</div>
              <details className="mt-4 rounded-2xl border border-border bg-surface p-3">
                <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2">
                  <h3 className="font-medium text-foreground">Tin tức / Catalyst / Sức khỏe nguồn</h3>
                  <span className="text-xs text-secondary-text">
                    {analysis.newsCatalyst?.checked ? `đã kiểm tra ${analysis.newsCatalyst.freshnessWindow} · ${displayNewsSource(analysis.newsCatalyst.source)} · sắc thái ${analysis.newsCatalyst.sentiment}` : 'chưa kiểm chứng news/catalyst'}
                  </span>
                </summary>
                {analysis.newsCatalyst?.sourcesChecked?.length ? (
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                    {analysis.newsCatalyst.sourcesChecked.map((source) => (
                      <span key={`${source.name}-${source.route}`} className={`rounded-full border border-border bg-base px-2 py-1 ${sourceStatusTone(source.status)}`} title={source.warning || source.route || undefined}>
                        {source.name}: {source.status} · {source.items}
                      </span>
                    ))}
                  </div>
                ) : null}
                {analysis.newsCatalyst?.catalysts?.length ? (
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    {([
                      { key: 'google', title: 'Google News RSS', note: 'Tin lấy từ Google News aggregator.' },
                      { key: 'agentReach', title: 'Agent Reach / Public routes', note: 'Tin lấy từ direct RSS, Jina Reader, Exa/mcporter nếu khả dụng.' },
                    ] as const).map((group) => {
                      const groupItems = analysis.newsCatalyst?.catalysts.filter((item) => routeGroupKey(item.sourceRoute) === group.key) ?? [];
                      return (
                        <div key={group.key} className="rounded-2xl border border-border bg-base p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <h4 className="text-sm font-semibold text-foreground">{group.title}</h4>
                              <p className="mt-1 text-[11px] text-secondary-text">{group.note}</p>
                            </div>
                            <span className="rounded-full border border-border px-2 py-1 text-[11px] text-secondary-text">{groupItems.length} tin</span>
                          </div>
                          {groupItems.length ? (
                            <ul className="mt-3 list-disc space-y-2 pl-5 text-xs text-secondary-text">
                              {groupItems.map((item) => (
                                <li key={`${item.source}-${item.sourceRoute}-${item.title}`}>
                                  <span className="text-foreground">{item.title}</span>
                                  <span> · publisher {item.source}{item.date ? ` · ${item.date}` : ''} · impact {item.impact}{item.tone ? ` · tone ${item.tone}` : ''} · route {displayNewsSource(item.sourceRoute ?? undefined)}</span>
                                  {item.url ? <a aria-label={`Mở bài: ${item.title}`} className="ml-1 text-[hsl(var(--primary))] underline" href={item.url} target="_blank" rel="noreferrer">Mở bài</a> : null}
                                  {item.summary && item.summary !== item.title ? <div className="mt-1">{item.summary}</div> : null}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <div className="mt-3 rounded-xl border border-dashed border-border p-3 text-xs text-secondary-text">Chưa có tin từ nhóm nguồn này trong lần check hiện tại.</div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-2 text-xs text-secondary-text">{analysis.newsCatalyst?.riskFlags?.join('; ') || 'Chưa có tin/catalyst nổi bật từ public web.'}</div>
                )}
                {analysis.newsCatalyst?.riskFlags?.length ? <div className="mt-2 text-xs text-amber-500">{analysis.newsCatalyst.riskFlags.join('; ')}</div> : null}
              </details>
              <VNPriceChart points={chartItems} plan={analysis} />
            </div>
          ) : null}
        </div>

        <div className={`${activeSection === 'portfolio' ? 'block' : 'hidden'} min-w-0 max-w-full rounded-3xl border border-border bg-surface p-4 sm:p-6`}>
          <h2 className="font-semibold text-foreground">Portfolio T+</h2>
          <p id="vn-portfolio-help" className="mt-1 text-xs text-secondary-text">Mỗi dòng: mã, số lượng, giá vốn (nghìn đồng), khả dụng, chờ về. Ví dụ: HPG,1000,30,600,400</p>
          <label htmlFor="vn-portfolio-input" className="sr-only">Danh sách vị thế Portfolio T+</label>
          <textarea id="vn-portfolio-input" aria-describedby="vn-portfolio-help vn-portfolio-errors" className={`mt-4 min-h-28 w-full max-w-full rounded-2xl border bg-base p-3 text-sm text-foreground ${portfolioErrors.length ? 'border-rose-500' : 'border-border'}`} value={portfolioText} onChange={(event) => { setPortfolioText(event.target.value); setPortfolioItems([]); setPortfolioErrors([]); setPortfolioResultAt(null); setPlaybook(null); }} />
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => void runPortfolioCheck()} disabled={isCheckingPortfolio}>{isCheckingPortfolio ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}{isCheckingPortfolio ? 'Đang kiểm tra…' : 'Kiểm tra Portfolio'}</button>
            <button type="button" className="btn-secondary" onClick={savePortfolio}>Lưu Portfolio</button>
            <button type="button" className="btn-secondary" onClick={resetPortfolio}>Dùng ví dụ mặc định</button>
          </div>
          <div id="vn-portfolio-errors" aria-live="polite">{portfolioErrors.length ? <ul className="mt-3 space-y-1 rounded-2xl border border-rose-400/50 bg-rose-500/10 p-3 text-sm text-rose-400">{portfolioErrors.map((item, index) => <li key={`${item.line}-${index}`}>Dòng {item.line}: {item.message}</li>)}</ul> : null}</div>
          {portfolioResultAt ? <div className="mt-3 text-xs text-secondary-text">Kết quả lúc {formatVNDateTime(portfolioResultAt)}</div> : null}
          <div className="mt-4 space-y-3">
            {portfolioItems.map((item, index) => {
              const displayName = item.name?.trim();
              const verdict = verdictFor(item.action);
              return (
                <div key={item.ticker} className="rounded-2xl border border-border bg-base p-4 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full border border-[hsl(var(--primary)/0.28)] bg-[hsl(var(--primary)/0.10)] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[hsl(var(--primary))]">#{index + 1}</span>
                        <strong className="text-lg text-foreground">{item.ticker}</strong>
                        {displayName ? <span className="text-sm text-secondary-text">— {displayName}</span> : null}
                      </div>
                      <div className="mt-1 text-xs text-secondary-text">Phân tích danh mục cho mã {item.ticker}</div>
                    </div>
                    <span className={item.plPct != null && item.plPct >= 0 ? 'text-emerald-500' : 'text-rose-500'}>{item.plPct ?? '--'}% · {formatMoney(item.pl)}</span>
                  </div>
                  <div className={`mt-3 rounded-2xl border p-3 ${verdict.className}`}>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] opacity-80">Khuyến nghị cuối · {item.ticker}</div>
                    <div className="mt-1 text-2xl font-black uppercase tracking-wide">{verdict.label}</div>
                    <div className="mt-1 text-xs opacity-90">{verdict.note}</div>
                  </div>
                  <div className="mt-3 grid gap-2 md:grid-cols-2"><div>Mã: <strong>{item.ticker}</strong></div><div>Giá hiện tại: {item.currentPrice ?? '--'} nghìn đồng</div><div>Giá trị: {formatMoney(item.marketValue)} nghìn đồng</div><div>Khả dụng: {item.sellableQty}</div><div>Chờ về: {item.pendingQty}</div></div>
                  <div className="mt-3 text-xs font-semibold uppercase tracking-wide text-secondary-text">Kế hoạch chi tiết · {item.ticker}</div>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-secondary-text">{item.todayPlan.map((line) => <li key={line}>{line}</li>)}</ul>
                  <div className="mt-2 text-amber-500">{item.ticker}: {item.pendingPlan}</div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className={`${activeSection === 'alerts' ? 'grid' : 'hidden'} min-w-0 gap-6 xl:grid-cols-3`}>
        <div className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-semibold text-foreground">Dòng tiền ngành</h2>
          <p className="mt-1 text-xs text-secondary-text">Gom watchlist theo ngành để xem nhóm nào đang có setup tốt.</p>
          <button type="button" className="btn-secondary mt-3 inline-flex items-center gap-2" onClick={() => void runSectorFlow()} disabled={isLoadingSector}>{isLoadingSector ? <RefreshCw className="h-4 w-4 animate-spin" /> : null}{isLoadingSector ? 'Đang tải…' : 'Cập nhật dòng tiền ngành'}</button>
          <div className="mt-4 space-y-2 text-sm">
            {sectorItems.map((item) => (
              <div key={item.sector} className="rounded-2xl border border-border bg-base p-3">
                <div className="flex justify-between gap-3"><strong>{item.sector}</strong><span>{item.bias} · {item.avgScore}</span></div>
                <div className="mt-1 text-xs text-secondary-text">{item.tickers.join(', ')}</div>
                <div className="mt-1 text-xs text-emerald-500">Top: {item.topCandidates.join(', ') || '--'}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-semibold text-foreground">Cảnh báo VN</h2>
          <p className="mt-1 text-xs text-secondary-text">Check breakout/stop/RSI/volume alerts cho watchlist + rule riêng.</p>
          <div className="mt-3 flex flex-wrap gap-2"><button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void runAlerts()} disabled={isLoadingAlerts}>{isLoadingAlerts ? <RefreshCw className="h-4 w-4 animate-spin" /> : null}{isLoadingAlerts ? 'Đang kiểm tra…' : 'Kiểm tra cảnh báo'}</button><button type="button" className="btn-secondary" onClick={addAlertRule}>Thêm luật</button><button type="button" className="btn-secondary" onClick={saveAlertRules}>Lưu luật</button><button type="button" className="btn-secondary" onClick={resetAlertRules}>Reset</button></div>
          <div className="mt-4 space-y-2 text-xs">
            {alertRules.map((rule) => (
              <div key={rule.id} className="grid min-w-0 gap-2 rounded-2xl border border-border bg-base p-3 sm:grid-cols-2 2xl:grid-cols-[auto_minmax(0,0.8fr)_minmax(0,1.25fr)_minmax(0,0.65fr)_minmax(0,1fr)_auto]">
                <label className="flex min-w-0 items-center gap-1"><input type="checkbox" checked={rule.enabled} onChange={(event) => updateAlertRule(rule.id, { enabled: event.target.checked })} />On</label>
                <input aria-label={`Mã cảnh báo ${rule.ticker}`} className="min-w-0 rounded-xl border border-border bg-surface px-2 py-1 text-foreground" value={rule.ticker} onChange={(event) => updateAlertRule(rule.id, { ticker: event.target.value.toUpperCase() })} />
                <select aria-label={`Điều kiện cảnh báo ${rule.ticker}`} className="min-w-0 rounded-xl border border-border bg-surface px-2 py-1 text-foreground" value={rule.condition} onChange={(event) => updateAlertRule(rule.id, { condition: event.target.value })}>
                  <option value="price_above">Price above</option><option value="price_below">Price below</option><option value="rsi_above">RSI above</option><option value="rsi_below">RSI below</option><option value="volume_ratio_above">Volume ratio above</option><option value="near_breakout">Near breakout %</option><option value="near_stop">Near stop %</option>
                </select>
                <input aria-label={`Ngưỡng cảnh báo ${rule.ticker}`} className="min-w-0 rounded-xl border border-border bg-surface px-2 py-1 text-foreground" type="number" step="0.01" value={rule.threshold} onChange={(event) => updateAlertRule(rule.id, { threshold: Number(event.target.value) })} />
                <input aria-label={`Ghi chú cảnh báo ${rule.ticker}`} className="min-w-0 rounded-xl border border-border bg-surface px-2 py-1 text-foreground sm:col-span-2 2xl:col-span-1" value={rule.note} placeholder="Ghi chú" onChange={(event) => updateAlertRule(rule.id, { note: event.target.value })} />
                <button type="button" aria-label={`Xóa luật ${rule.ticker}`} className="btn-secondary justify-self-start" onClick={() => removeAlertRule(rule.id)}>Xóa</button>
              </div>
            ))}
          </div>
          <div className="mt-4 space-y-2 text-sm">
            {alertRuleResults.map((item) => (<div key={`${item.rule.id}-${item.ticker}`} className={`rounded-2xl border p-3 ${item.triggered ? 'border-amber-400 bg-amber-500/10 text-amber-300' : 'border-border bg-base text-secondary-text'}`}><strong>{item.ticker}</strong> · {item.message} <span className="text-xs">score {item.score ?? '--'}</span></div>))}
            {alertItems.map((item) => (
              <div key={item.ticker} className="rounded-2xl border border-border bg-base p-3">
                <strong>{item.ticker}</strong> <span className="text-secondary-text">score {item.score}</span>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-secondary-text">{item.alerts.map((alert) => <li key={`${item.ticker}-${alert.type}-${alert.message}`}>{alert.message}</li>)}</ul>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-semibold text-foreground">Nhật ký / Kiểm chứng T+</h2>
          <p className="mt-1 text-xs text-secondary-text">Lưu signal hiện tại để sau này kiểm tra T+3/T+5.</p>
          <textarea aria-label="Ghi chú nhật ký tín hiệu" className="mt-3 min-h-20 w-full rounded-2xl border border-border bg-base p-3 text-sm text-foreground" value={journalNote} onChange={(event) => setJournalNote(event.target.value)} placeholder="Ghi chú tín hiệu..." />
          <div className="mt-3 flex gap-2"><button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void saveJournal()} disabled={isSavingJournal}>{isSavingJournal ? <RefreshCw className="h-4 w-4 animate-spin" /> : null}{isSavingJournal ? 'Đang lưu…' : 'Lưu tín hiệu'}</button><button type="button" className="btn-secondary" onClick={() => void vnMarketApi.listJournalSignals().then((response) => setJournalItems(response.items))}>Tải lại</button></div>
          <div className="mt-4 max-h-64 space-y-2 overflow-auto text-sm">
            {journalItems.map((item) => (<div key={item.id} className="rounded-2xl border border-border bg-base p-3"><strong>{item.ticker}</strong> {item.action} · score {item.score}<div className="text-xs text-secondary-text">{item.createdAt} · {item.note || '--'}</div></div>))}
          </div>
        </div>
      </section>

      <section className={`${activeSection === 'scanner' ? 'block' : 'hidden'} min-w-0 rounded-3xl border border-border bg-surface p-4 sm:p-6`}>
        <label htmlFor="vn-watchlist" className="block text-sm font-medium text-foreground">Watchlist Việt Nam</label>
        <textarea id="vn-watchlist" aria-label="Danh sách mã scanner" className="mt-2 min-h-24 w-full max-w-full rounded-2xl border border-border bg-base p-3 text-sm text-foreground outline-none focus:border-[hsl(var(--primary))]" value={watchlistText} onChange={(event) => { setWatchlistText(event.target.value); setItems([]); setScanResultAt(null); setPlaybook(null); setSectorItems([]); setAlertItems([]); }} />
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => void runScan()} disabled={isLoading}>{isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}{isLoading ? 'Đang quét…' : 'Quét T+'}</button>
          <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void exportReport()} disabled={isExporting}>{isExporting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}{isExporting ? 'Đang xuất…' : 'Xuất HTML/JSON'}</button>
          <button type="button" className="btn-secondary" onClick={saveWatchlist}>Lưu Watchlist</button>
          <button type="button" className="btn-secondary" onClick={resetWatchlist}>Dùng ví dụ mặc định</button>
        </div>
      </section>

      <section className={`${activeSection === 'scanner' ? 'block' : 'hidden'} min-w-0 max-w-full overflow-hidden rounded-3xl border border-border bg-surface`}>
        <div className="border-b border-border p-4"><h2 className="font-semibold text-foreground">Kế hoạch hành động T+</h2>{scanResultAt ? <p className="mt-1 text-xs text-secondary-text">Kết quả lúc {formatVNDateTime(scanResultAt)}</p> : null}<p className="text-xs text-secondary-text">Không phải khuyến nghị đầu tư; ưu tiên quản trị rủi ro và tránh FOMO.</p></div>
        <div className="space-y-3 p-4 md:hidden">
          {items.length === 0 ? <div className="rounded-2xl border border-dashed border-border p-4 text-center text-sm text-secondary-text">Chưa có kết quả scan.</div> : items.map((item) => (
            <article key={`mobile-${item.ticker}`} className="min-w-0 rounded-2xl border border-border bg-base p-4 text-sm">
              <div className="flex items-start justify-between gap-3"><strong className="text-lg">{item.ticker}</strong><span className={`font-semibold ${actionTone[item.action] ?? ''}`}>{verdictFor(item.action).label}</span></div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs"><div>Điểm: <strong>{item.score}</strong></div><div>Tỷ trọng: {item.positionSizePct ?? 0}%</div><div>Vùng mua: {formatZone(item.buyZone)}</div><div>Breakout: {item.breakoutTrigger ?? '--'}</div><div>Stop: {item.stopLoss ?? '--'}</div><div>Target: {item.targets.length ? item.targets.join(' / ') : '--'}</div></div>
              <div className="mt-3 break-words text-xs text-secondary-text">{item.riskFlags.join('; ') || 'Không có cảnh báo bổ sung.'}</div>
            </article>
          ))}
        </div>
        <div className="hidden max-w-full overflow-x-auto md:block"><table className="w-full min-w-[980px] text-sm"><thead className="bg-hover text-left text-xs uppercase text-secondary-text"><tr><th className="p-3">Mã</th><th className="p-3">Hành động</th><th className="p-3">Điểm</th><th className="p-3">Vùng mua</th><th className="p-3">Breakout</th><th className="p-3">Stop</th><th className="p-3">Mục tiêu</th><th className="p-3">Tỷ trọng</th><th className="p-3">Cảnh báo rủi ro</th></tr></thead><tbody>{items.length === 0 ? (<tr><td className="p-5 text-center text-secondary-text" colSpan={9}>Chưa có kết quả scan.</td></tr>) : items.map((item) => (<tr key={item.ticker} className="border-t border-border align-top"><td className="p-3 font-semibold text-foreground">{item.ticker}</td><td className={`p-3 font-medium ${actionTone[item.action] ?? ''}`}>{verdictFor(item.action).label}</td><td className="p-3">{item.score}</td><td className="p-3">{formatZone(item.buyZone)}</td><td className="p-3">{item.breakoutTrigger ?? '--'}</td><td className="p-3">{item.stopLoss ?? '--'}</td><td className="p-3">{item.targets.length ? item.targets.join(' / ') : '--'}</td><td className="p-3">{item.positionSizePct ?? 0}%</td><td className="max-w-md p-3 text-xs text-secondary-text">{item.riskFlags.join('; ')}</td></tr>))}</tbody></table></div>
      </section>
    </div>
  );
};

export default VNMarketPage;
