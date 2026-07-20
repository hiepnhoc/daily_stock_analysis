import type { VNPortfolioHolding } from '../api/vnMarket';

export interface PortfolioInputError {
  line: number;
  message: string;
}

export interface PortfolioParseResult {
  validRows: VNPortfolioHolding[];
  errors: PortfolioInputError[];
}

const VN_TICKER_PATTERN = /^[A-Z]{3}$/;

export function normalizeVNTicker(value: string): string {
  return value.trim().toUpperCase();
}

export function isValidVNTicker(value: string): boolean {
  return VN_TICKER_PATTERN.test(normalizeVNTicker(value));
}

export function parsePortfolioInput(text: string): PortfolioParseResult {
  const validRows: VNPortfolioHolding[] = [];
  const errors: PortfolioInputError[] = [];

  text.split('\n').forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) return;

    const lineNumber = index + 1;
    const columns = line.split(/[\s,;\t]+/).filter(Boolean);
    const ticker = normalizeVNTicker(columns[0] ?? '');
    if (!isValidVNTicker(ticker)) {
      errors.push({ line: lineNumber, message: 'Mã cổ phiếu phải gồm đúng 3 chữ cái A-Z.' });
    }
    if (columns.length !== 5) {
      errors.push({ line: lineNumber, message: 'Cần đúng 5 cột: mã, số lượng, giá vốn, khả dụng, chờ về.' });
      return;
    }

    const values = columns.slice(1).map(Number);
    const [quantity, avgCost, sellableQty, pendingQty] = values;

    if (!values.every(Number.isFinite)) {
      errors.push({ line: lineNumber, message: 'Các cột số phải là số hợp lệ.' });
      return;
    }
    if (![quantity, sellableQty, pendingQty].every(Number.isInteger)) {
      errors.push({ line: lineNumber, message: 'Số lượng, khả dụng và chờ về phải là số nguyên.' });
    }
    if (quantity <= 0) {
      errors.push({ line: lineNumber, message: 'Số lượng phải lớn hơn 0.' });
    }
    if (avgCost <= 0) {
      errors.push({ line: lineNumber, message: 'Giá vốn phải lớn hơn 0.' });
    }
    if (sellableQty < 0 || pendingQty < 0) {
      errors.push({ line: lineNumber, message: 'Khả dụng và chờ về không được âm.' });
    }
    if (sellableQty + pendingQty > quantity) {
      errors.push({ line: lineNumber, message: 'Tổng khả dụng và chờ về không được vượt số lượng.' });
    }

    if (!errors.some((error) => error.line === lineNumber)) {
      validRows.push({ ticker, quantity, avgCost, sellableQty, pendingQty });
    }
  });

  if (!text.trim()) {
    errors.push({ line: 1, message: 'Portfolio đang trống.' });
  }

  return { validRows, errors };
}

export function formatVNDateTime(value?: string | null): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date)} (GMT+7)`;
}
