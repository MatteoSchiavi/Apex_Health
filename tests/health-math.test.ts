import { describe, expect, test } from "bun:test";
import { readinessFromRecovery, trainingLoadSummary } from "../src/lib/apex/healthMath";

describe("training load in consistent weekly units", () => {
  test("steady daily training has ACWR 1, not 7", () => {
    expect(trainingLoadSummary(70, 280)).toEqual({ acute: 70, chronic: 70, acwr: 1 });
  });
  test("a doubled recent week has ratio 2", () => {
    expect(trainingLoadSummary(140, 280).acwr).toBe(2);
  });
  test("no chronic history has no ratio", () => {
    expect(trainingLoadSummary(0, 0).acwr).toBeNull();
  });
  test("rest days still contribute zero to the full calendar window", () => {
    expect(trainingLoadSummary(70, 70)).toEqual({ acute: 70, chronic: 17.5, acwr: 4 });
  });
});

describe("readiness", () => {
  test("greater strain decreases readiness for the same recovery", () => {
    expect(readinessFromRecovery(70, 80)).toBe(58);
    expect(readinessFromRecovery(70, 20)).toBe(82);
  });
  test("missing strain leaves recovery unchanged", () => {
    expect(readinessFromRecovery(70, null)).toBe(70);
  });
  test("missing or invalid recovery cannot yield readiness", () => {
    expect(readinessFromRecovery(null, 50)).toBeNull();
    expect(readinessFromRecovery(NaN, 50)).toBeNull();
  });
  test("bounds are 0 to 100", () => {
    expect(readinessFromRecovery(95, 0)).toBe(100);
    expect(readinessFromRecovery(5, 100)).toBe(0);
  });
});
