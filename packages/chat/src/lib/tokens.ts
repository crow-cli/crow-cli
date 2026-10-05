/** Compact token count — crow-client's `fmt_tokens` (app/info.rs:345). */
export function fmtTokens(value: number): string {
  if (!Number.isFinite(value)) return "0";
  if (value < 1000) return String(Math.round(value));
  if (value < 1_000_000) return `${(value / 1000).toFixed(1)}K`;
  return `${(value / 1_000_000).toFixed(1)}M`;
}

/**
 * Fraction of the ceiling consumed, `0..1`. A zero ceiling reads as empty
 * rather than dividing by zero (crow-client's `ContextUsage::fraction`).
 */
export function usageFraction(used: number, size: number): number {
  if (!Number.isFinite(used) || !Number.isFinite(size) || size <= 0) return 0;
  return Math.min(1, Math.max(0, used / size));
}
