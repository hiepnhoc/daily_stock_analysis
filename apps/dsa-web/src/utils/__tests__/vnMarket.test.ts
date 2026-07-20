import { describe, expect, it } from 'vitest';
import { formatVNDateTime, parsePortfolioInput } from '../vnMarket';

describe('parsePortfolioInput', () => {
  it('parses valid rows and normalizes ticker', () => {
    const result = parsePortfolioInput('hpg,1000,30,600,400\nFPT 500 120 500 0');

    expect(result.errors).toEqual([]);
    expect(result.validRows).toEqual([
      { ticker: 'HPG', quantity: 1000, avgCost: 30, sellableQty: 600, pendingQty: 400 },
      { ticker: 'FPT', quantity: 500, avgCost: 120, sellableQty: 500, pendingQty: 0 },
    ]);
  });

  it('returns line-specific errors and never silently accepts junk', () => {
    const result = parsePortfolioInput('HPG,abc,30,-100,foo\n???\nSSI,100,25,80,30');

    expect(result.validRows).toEqual([]);
    expect(result.errors.map((error) => error.line)).toEqual(expect.arrayContaining([1, 2, 3]));
    expect(result.errors.some((error) => error.message.includes('3 chữ cái'))).toBe(true);
    expect(result.errors.some((error) => error.message.includes('không được vượt'))).toBe(true);
  });
});

describe('formatVNDateTime', () => {
  it('labels timestamps with Vietnam timezone', () => {
    expect(formatVNDateTime('2026-07-10T03:58:00Z')).toContain('(GMT+7)');
  });
});
