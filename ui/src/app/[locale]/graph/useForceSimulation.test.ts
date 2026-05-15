import { describe, expect, test } from "vitest";
import { buildBezierPath, LINK_DISTANCE, CHARGE_STRENGTH, GRAVITY_STRENGTH, REDUCED_MOTION_ALPHA_THRESHOLD } from "./useForceSimulation";

// ─── Bug 2: force constants keep disconnected nodes close to the viewport ─────
//
// The key invariant is that GRAVITY_STRENGTH > 0, so every node — including
// disconnected ones — receives a per-node pull toward the canvas centre.
// Without this, isolated nodes are only repelled by CHARGE_STRENGTH and drift
// out of view.

describe("force simulation constants", () => {
  test("GRAVITY_STRENGTH is positive so disconnected nodes are attracted to centre", () => {
    expect(GRAVITY_STRENGTH).toBeGreaterThan(0);
  });

  test("CHARGE_STRENGTH is negative (repulsion) but not so strong it overwhelms gravity", () => {
    expect(CHARGE_STRENGTH).toBeLessThan(0);
    // If charge were stronger than -1000, gravity at 0.07 can no longer
    // keep unconnected nodes within a typical viewport.
    expect(CHARGE_STRENGTH).toBeGreaterThan(-1000);
  });

  test("LINK_DISTANCE is within a usable screen range", () => {
    expect(LINK_DISTANCE).toBeGreaterThan(50);
    expect(LINK_DISTANCE).toBeLessThan(300);
  });

  test("gravity-to-repulsion ratio keeps disconnected nodes reachable", () => {
    // A rough proxy: |GRAVITY_STRENGTH| / |CHARGE_STRENGTH| should be large
    // enough that gravity wins at short distances (~200 px from centre).
    // The ratio below is the threshold that was validated visually.
    const ratio = Math.abs(GRAVITY_STRENGTH) / Math.abs(CHARGE_STRENGTH);
    expect(ratio).toBeGreaterThan(0.00005);
  });
});

describe("buildBezierPath", () => {
  test("returns a valid SVG cubic Bézier path string", () => {
    const { d } = buildBezierPath(0, 0, 400, 0);
    expect(d).toMatch(/^M -?\d+(\.\d+)? -?\d+(\.\d+)? C .+/);
  });

  test("provides a1 on the left side of source when target is to the right", () => {
    const { a1 } = buildBezierPath(100, 100, 400, 100);
    expect(a1.x).toBe(100 + 110);
    expect(a1.y).toBe(100);
  });

  test("provides a2 on the right side of target when source is to the left", () => {
    const { a2 } = buildBezierPath(100, 100, 400, 100);
    expect(a2.x).toBe(400 - 110);
  });

  test("angle is clamped to [-20, +20] degrees", () => {
    const { angle } = buildBezierPath(0, 0, 0, 500);
    expect(angle).toBeGreaterThanOrEqual(-20);
    expect(angle).toBeLessThanOrEqual(20);
  });

  test("mid-point is defined", () => {
    const { mid } = buildBezierPath(0, 0, 300, 200);
    expect(typeof mid.x).toBe("number");
    expect(typeof mid.y).toBe("number");
  });
});

describe("REDUCED_MOTION_ALPHA_THRESHOLD", () => {
  test("REDUCED_MOTION_ALPHA_THRESHOLD is 0.05", () => {
    expect(REDUCED_MOTION_ALPHA_THRESHOLD).toBe(0.05);
  });

  test("REDUCED_MOTION_ALPHA_THRESHOLD is in a valid range (> 0 and < 0.1)", () => {
    expect(REDUCED_MOTION_ALPHA_THRESHOLD).toBeGreaterThan(0);
    expect(REDUCED_MOTION_ALPHA_THRESHOLD).toBeLessThan(0.1);
  });
});
