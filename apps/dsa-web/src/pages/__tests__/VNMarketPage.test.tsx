import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VNMarketPage from '../VNMarketPage';

const {
  getReadiness,
  getOverview,
  scanWatchlist,
  analyzeTicker,
  getTickerChart,
  exportReport,
  checkPortfolio,
  getDailyPlaybook,
  getSectorFlow,
  checkAlerts,
  checkAlertRules,
  createJournalSignal,
  listJournalSignals,
  getAccounts,
  getSnapshot,
} = vi.hoisted(() => ({
  getReadiness: vi.fn(),
  getOverview: vi.fn(),
  scanWatchlist: vi.fn(),
  analyzeTicker: vi.fn(),
  getTickerChart: vi.fn(),
  exportReport: vi.fn(),
  checkPortfolio: vi.fn(),
  getDailyPlaybook: vi.fn(),
  getSectorFlow: vi.fn(),
  checkAlerts: vi.fn(),
  checkAlertRules: vi.fn(),
  createJournalSignal: vi.fn(),
  listJournalSignals: vi.fn(),
  getAccounts: vi.fn(),
  getSnapshot: vi.fn(),
}));

vi.mock('../../api/vnMarket', () => ({
  vnMarketApi: {
    getReadiness,
    getOverview,
    scanWatchlist,
    analyzeTicker,
    getTickerChart,
    exportReport,
    checkPortfolio,
    getDailyPlaybook,
    getSectorFlow,
    checkAlerts,
    checkAlertRules,
    createJournalSignal,
    listJournalSignals,
  },
}));

vi.mock('../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts,
    getSnapshot,
    createAccount: vi.fn(),
    importOpeningPositions: vi.fn(),
  },
}));

const overview = {
  refDate: '2026-07-22',
  indices: [],
  breadth: { advancers: 0, decliners: 0, ceiling: 0, floor: 0, unchanged: 0 },
  liquidity: { totalValue: null, vs20dPct: null },
  marketBias: 'neutral' as const,
  warnings: [],
};

const playbook = {
  generatedAt: '2026-07-22T13:00:00',
  overview,
  summary: [],
  topSetups: [],
  avoidList: [],
  portfolioActions: [],
  sectorBias: [],
  alerts: [],
  warnings: [],
};

describe('VNMarketPage regressions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    getReadiness.mockResolvedValue({ status: 'ready', service: 'vn-market' });
    getOverview.mockResolvedValue(overview);
    listJournalSignals.mockResolvedValue({ items: [] });
    checkAlerts.mockResolvedValue({ items: [] });
    checkAlertRules.mockResolvedValue({ items: [] });
    getDailyPlaybook.mockResolvedValue(playbook);
    checkPortfolio.mockResolvedValue({ items: [] });
    getAccounts.mockResolvedValue({ accounts: [] });
    getSnapshot.mockResolvedValue({ accounts: [] });
  });

  it('auto-loads the first persistent VN account as the canonical Portfolio T+ source', async () => {
    getAccounts.mockResolvedValue({
      accounts: [
        { id: 1, name: 'Generic', market: 'cn', baseCurrency: 'CNY', isActive: true },
        { id: 2, name: 'VN Portfolio', market: 'vn', baseCurrency: 'VND', broker: 'Manual', isActive: true },
      ],
    });
    getSnapshot.mockResolvedValue({
      asOf: '2026-07-22',
      costMethod: 'fifo',
      currency: 'VND',
      accountCount: 1,
      totalCash: 0,
      totalMarketValue: 11385000,
      totalEquity: 11385000,
      realizedPnl: 0,
      unrealizedPnl: -2216500,
      feeTotal: 0,
      taxTotal: 0,
      fxStale: false,
      accounts: [{
        accountId: 2,
        accountName: 'VN Portfolio',
        market: 'vn',
        baseCurrency: 'VND',
        asOf: '2026-07-22',
        costMethod: 'fifo',
        totalCash: 0,
        totalMarketValue: 11385000,
        totalEquity: 11385000,
        realizedPnl: 0,
        unrealizedPnl: -2216500,
        feeTotal: 0,
        taxTotal: 0,
        fxStale: false,
        positions: [{
          symbol: 'HPG', market: 'vn', currency: 'VND', quantity: 550, avgCost: 24730,
          totalCost: 13601500, lastPrice: 20700, marketValueBase: 11385000,
          unrealizedPnlBase: -2216500, valuationCurrency: 'VND', sellableQuantity: 550,
          pendingQuantity: 0, priceSource: 'realtime_quote', priceProvider: 'ssi_iboard',
          priceDate: '2026-07-22', priceStale: false, priceAvailable: true,
        }],
      }],
    });

    render(
      <MemoryRouter initialEntries={['/vn-portfolio']}>
        <VNMarketPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('combobox', { name: 'Tài khoản VN cho Portfolio T+' })).toHaveValue('2');
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledWith({ accountId: 2, costMethod: 'fifo' }));
    expect(screen.getByRole('textbox', { name: 'Danh sách vị thế Portfolio T+' })).toHaveValue('HPG,550,24.73,550,0');
    expect(screen.getByText(/Nguồn chính: Sổ giao dịch SQLite/)).toBeInTheDocument();
    expect(screen.getByText(/VN Portfolio · VND · 1 vị thế · dữ liệu 2026-07-22/)).toBeInTheDocument();
  });

  it('marks edited ledger text as a draft that differs from the persistent account', async () => {
    getAccounts.mockResolvedValue({
      accounts: [{ id: 2, name: 'VN Portfolio', market: 'vn', baseCurrency: 'VND', isActive: true }],
    });
    getSnapshot.mockResolvedValue({
      asOf: '2026-07-22', costMethod: 'fifo', currency: 'VND', accountCount: 1,
      totalCash: 0, totalMarketValue: 11385000, totalEquity: 11385000,
      realizedPnl: 0, unrealizedPnl: -2216500, feeTotal: 0, taxTotal: 0, fxStale: false,
      accounts: [{
        accountId: 2, accountName: 'VN Portfolio', market: 'vn', baseCurrency: 'VND',
        asOf: '2026-07-22', costMethod: 'fifo', totalCash: 0, totalMarketValue: 11385000,
        totalEquity: 11385000, realizedPnl: 0, unrealizedPnl: -2216500, feeTotal: 0,
        taxTotal: 0, fxStale: false,
        positions: [{
          symbol: 'HPG', market: 'vn', currency: 'VND', quantity: 550, avgCost: 24730,
          totalCost: 13601500, lastPrice: 20700, marketValueBase: 11385000,
          unrealizedPnlBase: -2216500, valuationCurrency: 'VND', sellableQuantity: 550,
          pendingQuantity: 0,
        }],
      }],
    });

    render(
      <MemoryRouter initialEntries={['/vn-portfolio']}>
        <VNMarketPage />
      </MemoryRouter>,
    );

    const input = await screen.findByRole('textbox', { name: 'Danh sách vị thế Portfolio T+' });
    await waitFor(() => expect(input).toHaveValue('HPG,550,24.73,550,0'));
    fireEvent.change(input, { target: { value: 'HPG,600,24.73,600,0' } });

    expect(screen.getByRole('status')).toHaveTextContent('Bản nháp đang khác sổ SQLite');
    expect(screen.getByRole('button', { name: 'Sửa vị thế trong sổ' })).toBeInTheDocument();
  });

  it('does not show overview bootstrap failures on the Portfolio T+ tab', async () => {
    getOverview.mockRejectedValue({ code: 'ECONNABORTED', message: 'timeout of 30000ms exceeded' });

    render(
      <MemoryRouter initialEntries={['/vn-portfolio']}>
        <VNMarketPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Portfolio T+' })).toBeInTheDocument();
    await waitFor(() => expect(getOverview).toHaveBeenCalled());
    expect(screen.queryByText('Backend đang khởi động hoặc tạm thời chưa phản hồi. Chờ vài giây rồi thử lại.')).not.toBeInTheDocument();
  });

  it('reports all-failed refresh without recording a successful refresh time', async () => {
    render(
      <MemoryRouter initialEntries={['/vn-market']}>
        <VNMarketPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1));

    getOverview.mockRejectedValue(new Error('overview unavailable'));
    checkAlerts.mockRejectedValue(new Error('alerts unavailable'));
    checkAlertRules.mockRejectedValue(new Error('rules unavailable'));
    getDailyPlaybook.mockRejectedValue(new Error('playbook unavailable'));
    checkPortfolio.mockRejectedValue(new Error('portfolio unavailable'));

    fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Làm mới thất bại ở tất cả khu vực');
    expect(screen.getByText(/Lần làm mới thành công:/)).toHaveTextContent('--');
  });

  it('reports partial refresh and keeps the last-success time unchanged', async () => {
    render(
      <MemoryRouter initialEntries={['/vn-market']}>
        <VNMarketPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1));

    checkAlerts.mockRejectedValue(new Error('alerts unavailable'));
    checkAlertRules.mockRejectedValue(new Error('rules unavailable'));
    getDailyPlaybook.mockRejectedValue(new Error('playbook unavailable'));
    checkPortfolio.mockRejectedValue(new Error('portfolio unavailable'));

    fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Làm mới một phần: 1/3 khu vực thành công');
    expect(screen.getByText(/Lần làm mới thành công:/)).toHaveTextContent('--');
  });

  it('records the refresh time only after all requested panels succeed', async () => {
    render(
      <MemoryRouter initialEntries={['/vn-market']}>
        <VNMarketPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Đã làm mới đầy đủ 3/3 khu vực');
    expect(screen.getByText(/Lần làm mới thành công:/)).not.toHaveTextContent('--');
  });

  it('keeps analysis news visible when the chart request fails', async () => {
    analyzeTicker.mockResolvedValue({
      ticker: 'HPG',
      action: 'watch',
      score: 60,
      confidence: 0.6,
      buyZone: [25, 26],
      breakoutTrigger: 27,
      stopLoss: 24,
      targets: [28, 30],
      positionSizePct: 10,
      reasons: ['Technical setup'],
      riskFlags: [],
      newsCatalyst: {
        checked: true,
        source: 'agent-reach:multi-source',
        freshnessWindow: '7d',
        sentiment: 'neutral',
        catalysts: [{
          title: 'Hòa Phát công bố thông tin mới',
          source: 'CafeF',
          impact: 'medium',
          summary: 'Thông tin kiểm thử',
          sourceRoute: 'agent-reach:rss:google-news',
        }],
        sourcesChecked: [],
        riskFlags: [],
      },
    });
    getTickerChart.mockRejectedValue({ code: 'ECONNABORTED', message: 'chart timeout' });

    render(
      <MemoryRouter initialEntries={['/vn-market/analyze']}>
        <VNMarketPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Phân tích' }));

    expect(await screen.findByText('Hòa Phát công bố thông tin mới')).toBeInTheDocument();
    expect(screen.getByText('Tin tức / Catalyst / Sức khỏe nguồn').closest('details')).toHaveAttribute('open');
  });
});
