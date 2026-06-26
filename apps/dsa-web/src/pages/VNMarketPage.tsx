import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Download, RefreshCw, Search } from 'lucide-react';
import {
  vnMarketApi,
  type VNActionPlan,
  type VNMarketOverview,
  type VNPortfolioHolding,
  type VNPortfolioItem,
} from '../api/vnMarket';

const DEFAULT_WATCHLIST = 'HPG,FPT,SSI,VCI,TCB,MWG';
const DEFAULT_PORTFOLIO = 'HPG,1000,30,600,400\nFPT,500,120,500,0';

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

const VNMarketPage: React.FC = () => {
  const [watchlistText, setWatchlistText] = useState(DEFAULT_WATCHLIST);
  const [analyzeTickerText, setAnalyzeTickerText] = useState('HPG');
  const [portfolioText, setPortfolioText] = useState(DEFAULT_PORTFOLIO);
  const [overview, setOverview] = useState<VNMarketOverview | null>(null);
  const [items, setItems] = useState<VNActionPlan[]>([]);
  const [analysis, setAnalysis] = useState<VNActionPlan | null>(null);
  const [portfolioItems, setPortfolioItems] = useState<VNPortfolioItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isCheckingPortfolio, setIsCheckingPortfolio] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<string | null>(null);

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
    try {
      setAnalysis(await vnMarketApi.analyzeTicker(ticker));
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
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-secondary-text">Vietnam equities</p>
        <h1 className="mt-2 text-2xl font-semibold text-foreground">VN Market / T+ Workspace</h1>
        <p className="mt-2 max-w-3xl text-sm text-secondary-text">
          VNINDEX context, stock analysis, portfolio T+, watchlist scanner, action plans, and HTML/JSON export.
        </p>
      </section>

      {error ? <div className="rounded-2xl border border-red-300 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
      {exportResult ? <div className="rounded-2xl border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-800">{exportResult}</div> : null}

      <section className="grid gap-4 md:grid-cols-4">
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">Market bias</div><div className="mt-1 text-xl font-semibold capitalize">{overview?.marketBias ?? '--'}</div></div>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">VNINDEX</div><div className="mt-1 text-xl font-semibold">{overview?.indices?.[0]?.close?.toFixed?.(2) ?? '--'}</div></div>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">Advancers / Decliners</div><div className="mt-1 text-xl font-semibold">{overview ? `${overview.breadth.advancers} / ${overview.breadth.decliners}` : '--'}</div></div>
        <div className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs text-secondary-text">Warnings</div><div className="mt-1 text-sm text-secondary-text">{overview?.warnings?.join(', ') || '--'}</div></div>
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
            </div>
          ) : null}
        </div>

        <div className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-semibold text-foreground">Portfolio T+</h2>
          <p className="mt-1 text-xs text-secondary-text">Mỗi dòng: mã, số lượng, giá vốn, khả dụng, chờ về. Ví dụ: HPG,1000,30,600,400</p>
          <textarea className="mt-4 min-h-28 w-full rounded-2xl border border-border bg-base p-3 text-sm text-foreground" value={portfolioText} onChange={(event) => setPortfolioText(event.target.value)} />
          <button type="button" className="btn-primary mt-3 inline-flex items-center gap-2" onClick={() => void runPortfolioCheck()} disabled={isCheckingPortfolio}>{isCheckingPortfolio ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}Check Portfolio</button>
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

      <section className="rounded-3xl border border-border bg-surface p-6">
        <label className="block text-sm font-medium text-foreground">Watchlist Việt Nam</label>
        <textarea className="mt-2 min-h-24 w-full rounded-2xl border border-border bg-base p-3 text-sm text-foreground outline-none focus:border-[hsl(var(--primary))]" value={watchlistText} onChange={(event) => setWatchlistText(event.target.value)} />
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => void runScan()} disabled={isLoading}>{isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}{isLoading ? 'Scanning...' : 'Scan T+'}</button>
          <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void exportReport()} disabled={isExporting}>{isExporting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}{isExporting ? 'Exporting...' : 'Export HTML/JSON'}</button>
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
