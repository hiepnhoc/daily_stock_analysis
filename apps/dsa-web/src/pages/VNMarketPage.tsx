import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, RefreshCw, Search } from 'lucide-react';
import {
  vnMarketApi,
  type VNActionPlan,
  type VNChartPoint,
  type VNDailyPlaybookResponse,
  type VNMarketOverview,
  type VNAlertItem,
  type VNAlertRule,
  type VNAlertRuleResult,
  type VNJournalItem,
  type VNPortfolioHolding,
  type VNPortfolioItem,
  type VNSectorFlowItem,
} from '../api/vnMarket';

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

function parsePortfolio(text: string): VNPortfolioHolding[] {
  return text.split('\n').map((line) => line.trim()).filter(Boolean).map((line) => {
    const [ticker, quantity, avgCost, sellableQty, pendingQty] = line.split(/[\s,;\t]+/);
    return {
      ticker: (ticker ?? '').toUpperCase(),
      quantity: Number(quantity ?? 0),
      avgCost: Number(avgCost ?? 0),
      sellableQty: Number(sellableQty ?? 0),
      pendingQty: Number(pendingQty ?? 0),
    };
  }).filter((item) => item.ticker && Number.isFinite(item.quantity));
}

const actionTone: Record<string, string> = {
  watch_breakout: 'text-emerald-500',
  buy_zone: 'text-emerald-500',
  watch: 'text-amber-500',
  hold: 'text-sky-500',
  avoid: 'text-rose-500',
  sell_reduce: 'text-rose-500',
};

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
  const [error, setError] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const portfolioRef = useRef<HTMLDivElement | null>(null);

  const watchlist = useMemo(
    () => watchlistText.split(/[\s,;]+/).map((item) => item.trim().toUpperCase()).filter(Boolean),
    [watchlistText],
  );

  const loadOverview = async () => {
    try {
      setOverview(await vnMarketApi.getOverview());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  useEffect(() => {
    if (window.location.pathname === '/vn-portfolio') {
      window.setTimeout(() => portfolioRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
    }
  }, []);

  const saveWatchlist = () => {
    setSaveStatus(saveText(WATCHLIST_STORAGE_KEY, watchlistText) ? 'Đã lưu watchlist VN trên browser này.' : 'Không lưu được watchlist trên browser này.');
  };

  const resetWatchlist = () => {
    setWatchlistText(DEFAULT_WATCHLIST);
    setSaveStatus('Đã reset watchlist về mặc định; bấm Save nếu muốn ghi đè bản lưu.');
  };

  const savePortfolio = () => {
    setSaveStatus(saveText(PORTFOLIO_STORAGE_KEY, portfolioText) ? 'Đã lưu Portfolio T+ trên browser này.' : 'Không lưu được Portfolio T+ trên browser này.');
  };

  const resetPortfolio = () => {
    setPortfolioText(DEFAULT_PORTFOLIO);
    setSaveStatus('Đã reset portfolio về ví dụ mặc định; bấm Save nếu muốn ghi đè bản lưu.');
  };

  const runScan = async () => {
    setIsLoading(true);
    setError(null);
    setExportResult(null);
    try {
      const response = await vnMarketApi.scanWatchlist({ watchlist, mode: 'tplus' });
      setItems(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  const runAnalyze = async () => {
    const ticker = analyzeTickerText.trim().toUpperCase();
    if (!ticker) return;
    setIsAnalyzing(true);
    setError(null);
    setChartItems([]);
    try {
      const [analysisResponse, chartResponse] = await Promise.all([
        vnMarketApi.analyzeTicker(ticker),
        vnMarketApi.getTickerChart(ticker, 160),
      ]);
      setAnalysis(analysisResponse);
      setChartItems(chartResponse.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const runPortfolioCheck = async () => {
    setIsCheckingPortfolio(true);
    setError(null);
    try {
      const response = await vnMarketApi.checkPortfolio(parsePortfolio(portfolioText));
      setPortfolioItems(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsCheckingPortfolio(false);
    }
  };

  const runSectorFlow = async () => {
    setError(null);
    try {
      const response = await vnMarketApi.getSectorFlow({ watchlist, mode: 'tplus' });
      setSectorItems(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const runAlerts = async () => {
    setError(null);
    try {
      const [alertsResponse, rulesResponse] = await Promise.all([
        vnMarketApi.checkAlerts({ watchlist, mode: 'tplus' }),
        vnMarketApi.checkAlertRules(alertRules),
      ]);
      setAlertItems(alertsResponse.items);
      setAlertRuleResults(rulesResponse.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const updateAlertRule = (id: string, patch: Partial<VNAlertRule>) => {
    setAlertRules((rules) => rules.map((rule) => rule.id === id ? { ...rule, ...patch } : rule));
  };

  const addAlertRule = () => {
    const id = `rule-${Date.now()}`;
    setAlertRules((rules) => [...rules, { id, ticker: 'HPG', condition: 'price_above', threshold: 0, enabled: true, note: '' }]);
  };

  const removeAlertRule = (id: string) => {
    setAlertRules((rules) => rules.filter((rule) => rule.id !== id));
  };

  const saveAlertRules = () => {
    setSaveStatus(saveRules(alertRules) ? 'Đã lưu alert rules trên browser này.' : 'Không lưu được alert rules trên browser này.');
  };

  const resetAlertRules = () => {
    setAlertRules(DEFAULT_ALERT_RULES);
    setAlertRuleResults([]);
    setSaveStatus('Đã reset alert rules về ví dụ mặc định; bấm Save Rules nếu muốn ghi đè bản lưu.');
  };

  const runDailyPlaybook = async () => {
    setError(null);
    try {
      const response = await vnMarketApi.getDailyPlaybook({ watchlist, holdings: parsePortfolio(portfolioText), mode: 'tplus' });
      setPlaybook(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const refreshLivePanels = async () => {
    await loadOverview();
    await Promise.allSettled([
      vnMarketApi.getDailyPlaybook({ watchlist, holdings: parsePortfolio(portfolioText), mode: 'tplus' }).then(setPlaybook),
      vnMarketApi.checkPortfolio(parsePortfolio(portfolioText)).then((response) => setPortfolioItems(response.items)),
      vnMarketApi.checkAlerts({ watchlist, mode: 'tplus' }).then((response) => setAlertItems(response.items)),
      vnMarketApi.checkAlertRules(alertRules).then((response) => setAlertRuleResults(response.items)),
    ]);
    setLastAutoRefreshAt(new Date().toLocaleTimeString('vi-VN'));
  };

  useEffect(() => {
    if (!autoRefreshMinutes) return undefined;
    const interval = window.setInterval(() => {
      void refreshLivePanels();
    }, autoRefreshMinutes * 60_000);
    return () => window.clearInterval(interval);
  }, [autoRefreshMinutes, watchlistText, portfolioText, alertRules]);

  const saveJournal = async () => {
    const source = analysis ?? items[0];
    if (!source) return;
    setError(null);
    try {
      await vnMarketApi.createJournalSignal({ ticker: source.ticker, action: source.action, score: source.score, note: journalNote });
      const response = await vnMarketApi.listJournalSignals();
      setJournalItems(response.items);
      setJournalNote('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const exportReport = async () => {
    setIsExporting(true);
    setError(null);
    try {
      const response = await vnMarketApi.exportReport({ watchlist, mode: 'tplus' });
      setExportResult(`${response.summary}: ${response.htmlPath ?? 'no html'} / ${response.jsonPath ?? 'no json'}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <section className="rounded-3xl border border-border bg-surface p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-secondary-text">Vietnam equities</p>
            <h1 className="mt-2 text-2xl font-semibold text-foreground">VN Market / T+ Workspace</h1>
            <p className="mt-2 max-w-3xl text-sm text-secondary-text">
              VNINDEX context, stock analysis, portfolio T+, watchlist scanner, action plans, and HTML/JSON export.
            </p>
          </div>
          <div className="rounded-2xl border border-border bg-base p-3 text-xs text-secondary-text">
            <label className="block font-medium text-foreground">Auto-refresh</label>
            <select className="mt-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-foreground" value={autoRefreshMinutes} onChange={(event) => setAutoRefreshMinutes(Number(event.target.value))}>
              <option value={0}>Off</option>
              <option value={1}>1m</option>
              <option value={5}>5m</option>
              <option value={15}>15m</option>
            </select>
            <button type="button" className="btn-secondary ml-2" onClick={() => void refreshLivePanels()}>Refresh now</button>
            <div className="mt-2">Last: {lastAutoRefreshAt ?? '--'}</div>
          </div>
        </div>
      </section>

      {error ? <div className="rounded-2xl border border-red-300 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
      {exportResult ? <div className="rounded-2xl border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-800">{exportResult}</div> : null}
      {saveStatus ? <div className="rounded-2xl border border-sky-300 bg-sky-50 p-4 text-sm text-sky-800">{saveStatus}</div> : null}

      <section className="grid gap-4 md:grid-cols-4">
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">Market bias</div><div className="mt-1 text-xl font-semibold capitalize">{overview?.marketBias ?? '--'}</div></div>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">VNINDEX</div><div className="mt-1 text-xl font-semibold">{overview?.indices?.[0]?.close?.toFixed?.(2) ?? '--'}</div></div>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">Advancers / Decliners</div><div className="mt-1 text-xl font-semibold">{overview ? `${overview.breadth.advancers} / ${overview.breadth.decliners}` : '--'}</div></div>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">Warnings</div><div className="mt-1 text-sm text-secondary-text">{overview?.warnings?.join(', ') || '--'}</div></div>
      </section>

      <section className="rounded-3xl border border-border bg-surface p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold text-foreground">Daily Playbook</h2>
            <p className="mt-1 text-xs text-secondary-text">Tổng hợp market, watchlist, sector và portfolio thành kế hoạch hành động hôm nay.</p>
          </div>
          <button type="button" className="btn-primary" onClick={() => void runDailyPlaybook()}>Generate Plan</button>
        </div>
        {playbook ? (
          <div className="mt-5 grid gap-4 xl:grid-cols-3">
            <div className="rounded-2xl border border-border bg-base p-4 text-sm xl:col-span-1">
              <div className="text-xs text-secondary-text">Generated {playbook.generatedAt}</div>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-secondary-text">{playbook.summary.map((line) => <li key={line}>{line}</li>)}</ul>
              <div className="mt-3 text-xs text-amber-500">Warnings: {playbook.warnings.join('; ') || '--'}</div>
            </div>
            <div className="rounded-2xl border border-border bg-base p-4 text-sm">
              <h3 className="font-medium text-foreground">Top setup</h3>
              <div className="mt-3 space-y-2">{playbook.topSetups.slice(0, 4).map((item) => <div key={item.ticker} className="flex justify-between gap-3"><span>{item.ticker} <span className={actionTone[item.action]}>{item.action}</span></span><span>score {item.score}</span></div>) || null}</div>
              {playbook.topSetups.length === 0 ? <div className="mt-3 text-secondary-text">Chưa có setup đủ đẹp, ưu tiên quan sát.</div> : null}
            </div>
            <div className="rounded-2xl border border-border bg-base p-4 text-sm">
              <h3 className="font-medium text-foreground">Portfolio action</h3>
              <div className="mt-3 space-y-3">{playbook.portfolioActions.map((item) => <div key={item.ticker}><div className="flex justify-between gap-3"><strong>{item.ticker}</strong><span>{item.plPct ?? '--'}%</span></div><ul className="mt-1 list-disc pl-5 text-xs text-secondary-text">{item.plan.map((line) => <li key={line}>{line}</li>)}</ul><div className="mt-1 text-xs text-amber-500">{item.pendingPlan}</div></div>)}</div>
              {playbook.portfolioActions.length === 0 ? <div className="mt-3 text-secondary-text">Chưa nhập portfolio hoặc không có vị thế.</div> : null}
            </div>
            <div className="rounded-2xl border border-border bg-base p-4 text-sm xl:col-span-3">
              <h3 className="font-medium text-foreground">Sector bias</h3>
              <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-5">{playbook.sectorBias.map((item) => <div key={item.sector} className="rounded-xl border border-border p-3"><div className="font-medium">{item.sector}</div><div className="text-xs text-secondary-text">{item.bias} · {item.avgScore}</div><div className="mt-1 text-xs text-emerald-500">{item.topCandidates.join(', ') || '--'}</div></div>)}</div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-semibold text-foreground">Analyze Stock VN</h2>
          <p className="mt-1 text-xs text-secondary-text">Phân tích một mã theo VN T+: vùng mua, breakout, stop, target, size và risk.</p>
          <div className="mt-4 flex gap-3">
            <input className="flex-1 rounded-2xl border border-border bg-base p-3 text-sm text-foreground" value={analyzeTickerText} onChange={(event) => setAnalyzeTickerText(event.target.value)} placeholder="HPG" />
            <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => void runAnalyze()} disabled={isAnalyzing}>{isAnalyzing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}Analyze</button>
          </div>
          {analysis ? (
            <div className="mt-5 rounded-2xl border border-border bg-base p-4 text-sm">
              <div className="flex items-center justify-between gap-3"><strong className="text-lg">{analysis.ticker}</strong><span className={actionTone[analysis.action]}>{analysis.action} · score {analysis.score}</span></div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <div>Buy zone: {formatZone(analysis.buyZone)}</div><div>Breakout: {analysis.breakoutTrigger ?? '--'}</div><div>Stop: {analysis.stopLoss ?? '--'}</div><div>Targets: {analysis.targets.join(' / ') || '--'}</div><div>Size: {analysis.positionSizePct ?? 0}%</div><div>Confidence: {(analysis.confidence * 100).toFixed(0)}%</div>
              </div>
              <div className="mt-3 text-secondary-text">Reasons: {analysis.reasons.join('; ') || '--'}</div>
              <div className="mt-2 text-amber-500">Risk: {analysis.riskFlags.join('; ')}</div>
              <div className="mt-4 rounded-2xl border border-border bg-surface p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-medium text-foreground">News/Catalyst</h3>
                  <span className="text-xs text-secondary-text">
                    {analysis.newsCatalyst?.checked ? `checked ${analysis.newsCatalyst.freshnessWindow} · ${analysis.newsCatalyst.source}` : 'chưa kiểm chứng news/catalyst'}
                  </span>
                </div>
                {analysis.newsCatalyst?.catalysts?.length ? (
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-xs text-secondary-text">
                    {analysis.newsCatalyst.catalysts.map((item) => (
                      <li key={`${item.source}-${item.title}`}>
                        <span className="text-foreground">{item.title}</span>
                        <span> · {item.source}{item.date ? ` · ${item.date}` : ''} · impact {item.impact}</span>
                        {item.url ? <a className="ml-1 text-[hsl(var(--primary))] underline" href={item.url} target="_blank" rel="noreferrer">link</a> : null}
                        {item.summary ? <div className="mt-1">{item.summary}</div> : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="mt-2 text-xs text-secondary-text">{analysis.newsCatalyst?.riskFlags?.join('; ') || 'Chưa có tin/catalyst nổi bật từ public web.'}</div>
                )}
                {analysis.newsCatalyst?.riskFlags?.length ? <div className="mt-2 text-xs text-amber-500">{analysis.newsCatalyst.riskFlags.join('; ')}</div> : null}
              </div>
              <VNPriceChart points={chartItems} plan={analysis} />
            </div>
          ) : null}
        </div>

        <div ref={portfolioRef} className="scroll-mt-24 rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-semibold text-foreground">Portfolio T+</h2>
          <p className="mt-1 text-xs text-secondary-text">Mỗi dòng: mã, số lượng, giá vốn, khả dụng, chờ về. Ví dụ: HPG,1000,30,600,400</p>
          <textarea className="mt-4 min-h-28 w-full rounded-2xl border border-border bg-base p-3 text-sm text-foreground" value={portfolioText} onChange={(event) => setPortfolioText(event.target.value)} />
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => void runPortfolioCheck()} disabled={isCheckingPortfolio}>{isCheckingPortfolio ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}Check Portfolio</button>
            <button type="button" className="btn-secondary" onClick={savePortfolio}>Save Portfolio</button>
            <button type="button" className="btn-secondary" onClick={resetPortfolio}>Reset Example</button>
          </div>
          <div className="mt-4 space-y-3">
            {portfolioItems.map((item) => (
              <div key={item.ticker} className="rounded-2xl border border-border bg-base p-4 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3"><strong className="text-base">{item.ticker}</strong><span className={item.plPct != null && item.plPct >= 0 ? 'text-emerald-500' : 'text-rose-500'}>{item.plPct ?? '--'}% · {formatMoney(item.pl)}</span></div>
                <div className="mt-2 grid gap-2 md:grid-cols-2"><div>Giá hiện tại: {item.currentPrice ?? '--'}</div><div>Giá trị: {formatMoney(item.marketValue)}</div><div>Khả dụng: {item.sellableQty}</div><div>Chờ về: {item.pendingQty}</div></div>
                <ul className="mt-3 list-disc space-y-1 pl-5 text-secondary-text">{item.todayPlan.map((line) => <li key={line}>{line}</li>)}</ul>
                <div className="mt-2 text-amber-500">{item.pendingPlan}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-3">
        <div className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-semibold text-foreground">Sector Flow</h2>
          <p className="mt-1 text-xs text-secondary-text">Gom watchlist theo ngành để xem nhóm nào đang có setup tốt.</p>
          <button type="button" className="btn-secondary mt-3" onClick={() => void runSectorFlow()}>Update Sector Flow</button>
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
          <h2 className="font-semibold text-foreground">Alerts VN</h2>
          <p className="mt-1 text-xs text-secondary-text">Check breakout/stop/RSI/volume alerts cho watchlist + rule riêng.</p>
          <div className="mt-3 flex flex-wrap gap-2"><button type="button" className="btn-secondary" onClick={() => void runAlerts()}>Check Alerts</button><button type="button" className="btn-secondary" onClick={addAlertRule}>Add Rule</button><button type="button" className="btn-secondary" onClick={saveAlertRules}>Save Rules</button><button type="button" className="btn-secondary" onClick={resetAlertRules}>Reset</button></div>
          <div className="mt-4 space-y-2 text-xs">
            {alertRules.map((rule) => (
              <div key={rule.id} className="grid min-w-0 gap-2 rounded-2xl border border-border bg-base p-3 sm:grid-cols-2 2xl:grid-cols-[auto_minmax(0,0.8fr)_minmax(0,1.25fr)_minmax(0,0.65fr)_minmax(0,1fr)_auto]">
                <label className="flex min-w-0 items-center gap-1"><input type="checkbox" checked={rule.enabled} onChange={(event) => updateAlertRule(rule.id, { enabled: event.target.checked })} />On</label>
                <input className="min-w-0 rounded-xl border border-border bg-surface px-2 py-1 text-foreground" value={rule.ticker} onChange={(event) => updateAlertRule(rule.id, { ticker: event.target.value.toUpperCase() })} />
                <select className="min-w-0 rounded-xl border border-border bg-surface px-2 py-1 text-foreground" value={rule.condition} onChange={(event) => updateAlertRule(rule.id, { condition: event.target.value })}>
                  <option value="price_above">Price above</option><option value="price_below">Price below</option><option value="rsi_above">RSI above</option><option value="rsi_below">RSI below</option><option value="volume_ratio_above">Volume ratio above</option><option value="near_breakout">Near breakout %</option><option value="near_stop">Near stop %</option>
                </select>
                <input className="min-w-0 rounded-xl border border-border bg-surface px-2 py-1 text-foreground" type="number" step="0.01" value={rule.threshold} onChange={(event) => updateAlertRule(rule.id, { threshold: Number(event.target.value) })} />
                <input className="min-w-0 rounded-xl border border-border bg-surface px-2 py-1 text-foreground sm:col-span-2 2xl:col-span-1" value={rule.note} placeholder="note" onChange={(event) => updateAlertRule(rule.id, { note: event.target.value })} />
                <button type="button" className="btn-secondary justify-self-start" onClick={() => removeAlertRule(rule.id)}>X</button>
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
          <h2 className="font-semibold text-foreground">Journal / T+ Backtest</h2>
          <p className="mt-1 text-xs text-secondary-text">Lưu signal hiện tại để sau này kiểm tra T+3/T+5.</p>
          <textarea className="mt-3 min-h-20 w-full rounded-2xl border border-border bg-base p-3 text-sm text-foreground" value={journalNote} onChange={(event) => setJournalNote(event.target.value)} placeholder="Ghi chú signal..." />
          <div className="mt-3 flex gap-2"><button type="button" className="btn-secondary" onClick={() => void saveJournal()}>Save Signal</button><button type="button" className="btn-secondary" onClick={() => void vnMarketApi.listJournalSignals().then((response) => setJournalItems(response.items))}>Reload</button></div>
          <div className="mt-4 max-h-64 space-y-2 overflow-auto text-sm">
            {journalItems.map((item) => (<div key={item.id} className="rounded-2xl border border-border bg-base p-3"><strong>{item.ticker}</strong> {item.action} · score {item.score}<div className="text-xs text-secondary-text">{item.createdAt} · {item.note || '--'}</div></div>))}
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-border bg-surface p-6">
        <label className="block text-sm font-medium text-foreground">Watchlist Việt Nam</label>
        <textarea className="mt-2 min-h-24 w-full rounded-2xl border border-border bg-base p-3 text-sm text-foreground outline-none focus:border-[hsl(var(--primary))]" value={watchlistText} onChange={(event) => setWatchlistText(event.target.value)} />
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => void runScan()} disabled={isLoading}>{isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}{isLoading ? 'Scanning...' : 'Scan T+'}</button>
          <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void exportReport()} disabled={isExporting}>{isExporting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}{isExporting ? 'Exporting...' : 'Export HTML/JSON'}</button>
          <button type="button" className="btn-secondary" onClick={saveWatchlist}>Save Watchlist</button>
          <button type="button" className="btn-secondary" onClick={resetWatchlist}>Reset Example</button>
        </div>
      </section>

      <section className="overflow-hidden rounded-3xl border border-border bg-surface">
        <div className="border-b border-border p-4"><h2 className="font-semibold text-foreground">T+ Action Plans</h2><p className="text-xs text-secondary-text">Không phải khuyến nghị đầu tư; ưu tiên quản trị rủi ro và tránh FOMO.</p></div>
        <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-sm"><thead className="bg-hover text-left text-xs uppercase text-secondary-text"><tr><th className="p-3">Ticker</th><th className="p-3">Action</th><th className="p-3">Score</th><th className="p-3">Buy zone</th><th className="p-3">Breakout</th><th className="p-3">Stop</th><th className="p-3">Targets</th><th className="p-3">Size</th><th className="p-3">Risk flags</th></tr></thead><tbody>{items.length === 0 ? (<tr><td className="p-5 text-center text-secondary-text" colSpan={9}>Chưa có kết quả scan.</td></tr>) : items.map((item) => (<tr key={item.ticker} className="border-t border-border align-top"><td className="p-3 font-semibold text-foreground">{item.ticker}</td><td className={`p-3 font-medium ${actionTone[item.action] ?? ''}`}>{item.action}</td><td className="p-3">{item.score}</td><td className="p-3">{formatZone(item.buyZone)}</td><td className="p-3">{item.breakoutTrigger ?? '--'}</td><td className="p-3">{item.stopLoss ?? '--'}</td><td className="p-3">{item.targets.length ? item.targets.join(' / ') : '--'}</td><td className="p-3">{item.positionSizePct ?? 0}%</td><td className="max-w-md p-3 text-xs text-secondary-text">{item.riskFlags.join('; ')}</td></tr>))}</tbody></table></div>
      </section>
    </div>
  );
};

export default VNMarketPage;
