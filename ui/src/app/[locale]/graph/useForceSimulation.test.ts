import { describe, expect, test } from "vitest";
import { buildBezierPath } from "./useForceSimulation";

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
