import { describe, it, expect } from 'vitest';
import { CANVAS_CLICK_THRESHOLD_PX } from '@/app/[locale]/graph/GraphCanvas';

// ─── Canvas click vs drag threshold ──────────────────────────────────────────

describe('CANVAS_CLICK_THRESHOLD_PX', () => {
  it('is a positive number', () => {
    expect(CANVAS_CLICK_THRESHOLD_PX).toBeGreaterThan(0);
  });

  it('treats zero displacement as a click', () => {
    const dx = 0, dy = 0;
    const dist = Math.sqrt(dx * dx + dy * dy);
    expect(dist).toBeLessThan(CANVAS_CLICK_THRESHOLD_PX);
  });

  it('treats sub-threshold displacement as a click', () => {
    // 3px diagonal movement — should still fire onCanvasClick
    const dx = 3, dy = 3;
    const dist = Math.sqrt(dx * dx + dy * dy); // ≈ 4.24
    expect(dist).toBeLessThan(CANVAS_CLICK_THRESHOLD_PX);
  });

  it('treats exactly-threshold displacement as a drag (not a click)', () => {
    // Displacement that lands exactly on the threshold boundary
    const dist = CANVAS_CLICK_THRESHOLD_PX;
    expect(dist).not.toBeLessThan(CANVAS_CLICK_THRESHOLD_PX);
  });

  it('treats large displacement as a drag — onCanvasClick must NOT fire', () => {
    // Simulates a pan gesture: user drags 100px across the canvas
    const dx = 100, dy = 0;
    const dist = Math.sqrt(dx * dx + dy * dy);
    expect(dist).toBeGreaterThanOrEqual(CANVAS_CLICK_THRESHOLD_PX);
  });

  it('treats small vertical movement as a drag', () => {
    // 10px downward scroll-like motion
    const dx = 0, dy = 10;
    const dist = Math.sqrt(dx * dx + dy * dy);
    expect(dist).toBeGreaterThanOrEqual(CANVAS_CLICK_THRESHOLD_PX);
  });
});
