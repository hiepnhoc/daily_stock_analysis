import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../portfolio';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('../index', () => ({
  default: {
    post,
  },
}));

describe('portfolioApi opening positions', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('maps VN opening holdings to the persistent ledger contract', async () => {
    post.mockResolvedValueOnce({
      data: {
        account_id: 7,
        import_id: 'vn-text-2026-07-20-abcd1234',
        inserted_events: 2,
        holdings: 1,
      },
    });

    const result = await portfolioApi.importOpeningPositions({
      accountId: 7,
      asOf: '2026-07-20',
      importId: 'vn-text-2026-07-20-abcd1234',
      holdings: [
        {
          symbol: 'FPT',
          quantity: 100,
          avgCost: 125000,
          sellableQuantity: 70,
          pendingQuantity: 30,
        },
      ],
    });

    expect(post).toHaveBeenCalledWith('/api/v1/portfolio/opening-positions', {
      account_id: 7,
      as_of: '2026-07-20',
      import_id: 'vn-text-2026-07-20-abcd1234',
      holdings: [
        {
          symbol: 'FPT',
          quantity: 100,
          avg_cost: 125000,
          sellable_quantity: 70,
          pending_quantity: 30,
        },
      ],
    });
    expect(result).toEqual({
      accountId: 7,
      importId: 'vn-text-2026-07-20-abcd1234',
      insertedEvents: 2,
      holdings: 1,
    });
  });

  it('sends explicit VN price units in CSV preview and commit forms', async () => {
    post.mockResolvedValue({ data: { broker: 'generic_vn', record_count: 0, skipped_count: 0, error_count: 0, records: [], errors: [] } });
    const file = new File(['csv'], 'vn.csv', { type: 'text/csv' });

    await portfolioApi.parseCsvImport('generic_vn', file, 'thousand_vnd');
    const parseForm = post.mock.calls[0][1] as FormData;
    expect(parseForm.get('broker')).toBe('generic_vn');
    expect(parseForm.get('price_unit')).toBe('thousand_vnd');
    expect(parseForm.get('file')).toBe(file);

    post.mockResolvedValueOnce({ data: { broker: 'generic_vn', dry_run: true, inserted_count: 0, duplicate_count: 0, failed_count: 0, errors: [] } });
    await portfolioApi.commitCsvImport(7, 'generic_vn', file, true, 'vnd');
    const commitForm = post.mock.calls[1][1] as FormData;
    expect(commitForm.get('account_id')).toBe('7');
    expect(commitForm.get('price_unit')).toBe('vnd');
    expect(commitForm.get('dry_run')).toBe('true');
  });
});
