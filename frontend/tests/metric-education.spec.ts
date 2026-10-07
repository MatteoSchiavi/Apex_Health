import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import type { MetricTrend } from "../src/app/api";
import { explainMetric } from "../src/features/biometrics/education/explain";
import { metricEducationDefinitions } from "../src/features/biometrics/education/definitions";
import { installApi } from "./fixtures";

const en = JSON.parse(readFileSync(new URL("../src/locales/en.json", import.meta.url), "utf8"));
const it = JSON.parse(readFileSync(new URL("../src/locales/it.json", import.meta.url), "utf8"));

const end = "2026-10-04";
const rhr: MetricTrend = {
  metric: "resting_hr", label: "Resting heart rate", unit: "bpm",
  start_date: "2026-09-07", end_date: end,
  points: [{ date: "2026-10-03", value: 46 }, { date: end, value: 47 }],
  // Selected-window mean is deliberately different from the personal baseline.
  stats: { count: 2, mean: 46.5, min: 46, max: 47 },
  reference_range: { state: "available", empirical_range: [42, 48], sample_count: 25,
    required_samples: 14, median: 48, origin: "garmin", as_of: end },
};
const acwr: MetricTrend = {
  ...rhr, metric: "acwr", label: "ACWR", unit: "ratio", reference_range: null,
  points: [{ date: end, value: 1.2 }], stats: {count: 1, mean: 1.2, min: 1.2, max: 1.2},
  calculation_inputs: { metric: "acwr", as_of: end, methodology: "garmin_recorded",
    contributors: [{ metric: "acute_load", value: 120, unit: "Garmin load/week" },
      { metric: "chronic_load", value: 100, unit: "Garmin load/week" }] },
};

async function showMetric(page: Page, payload: MetricTrend, options: Parameters<typeof installApi>[1] = {}) {
  await installApi(page, options);
  await page.route(url => url.pathname === `/metrics/${payload.metric}`, route => route.fulfill({ json: payload }));
  await page.goto(`/app/biometrics/${payload.metric}`);
  await expect(page.locator(".hero-number")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
const disclosure = (page: Page) => page.locator("details").filter({has: page.locator('summary[aria-controls]')});
const contextLabels = (payload: MetricTrend) => explainMetric(payload)!.context.map(fact => fact.label.key);

test("measured context uses the API median and preserves non-causal influences separately", () => {
  const result = explainMetric(rhr)!;
  expect(result.semanticType).toBe("measured");
  expect(result.actualCalculation).toBeUndefined();
  expect(result.context.find(fact => fact.label.key === "metricEducation.vs_baseline")?.display)
    .toMatchObject({ value: -1, unit: "bpm" });
  expect(result.provenance).toEqual([{key:"metricEducation.source_value",values:{source:"Garmin"}}]);
  expect(result.knownInfluences.length).toBeGreaterThan(0);
  expect(explainMetric(structuredClone(rhr))).toEqual(result);
});

test("unavailable, invalid or stale ranges cannot create a current baseline comparison", () => {
  const ref = rhr.reference_range!;
  for (const range of [null, {...ref, state:"INSUFFICIENT_DATA", median:null, empirical_range:null},
    {...ref, as_of:"2026-10-03"}, {...ref, empirical_range:[48,42] as [number,number]},
    {...ref, empirical_range:[42,NaN] as [number,number]}]) {
    const payload = {...rhr,reference_range:range};
    expect(contextLabels(payload)).not.toContain("metricEducation.vs_baseline");
    expect(contextLabels(payload)).not.toContain("metricEducation.range_status");
  }
  for (const origin of ["observations", "unknown", "toString"]) {
    expect(explainMetric({...rhr,reference_range:{...ref,origin}})!.provenance).toEqual([]);
  }
});

test("unreviewed and empty metrics have no fabricated education", () => {
  for (const metric of ["future_unknown", "toString"]) {
    expect(explainMetric({...rhr,metric})).toBeNull();
  }
  expect(explainMetric({...rhr,points:[{date:end,value:null}]})).toBeNull();
  expect(explainMetric({...rhr,points:[{date:end,value:Infinity}]})).toBeNull();
});

test("only persisted same-date, complete ACWR inputs become calculation contributors", () => {
  const result = explainMetric(acwr)!;
  expect(result.semanticType).toBe("apex_derived");
  expect(result.actualCalculation?.asOf).toBe(end);
  expect(result.actualCalculation?.contributors.map(fact => fact.display)).toEqual(acwr.calculation_inputs!.contributors);
  for (const metric of ["resting_hr", "provider_sleep_score", "recovery"]) {
    expect(explainMetric({...acwr,metric})!.actualCalculation).toBeUndefined();
  }
  const snapshot = acwr.calculation_inputs!;
  for (const calculation_inputs of [null, {...snapshot,metric:"recovery"}, {...snapshot,as_of:"2026-10-03"},
    {...snapshot,contributors:snapshot.contributors.slice(0,1)},
    {...snapshot,contributors:[snapshot.contributors[0],snapshot.contributors[0]]},
    {...snapshot,contributors:[snapshot.contributors[0],{...snapshot.contributors[1],value:0}]},
    {...snapshot,contributors:[snapshot.contributors[0],{...snapshot.contributors[1],value:NaN}]},
    {...snapshot,contributors:[snapshot.contributors[0],{...snapshot.contributors[1],unit:"TRIMP/week"}]}]) {
    expect(explainMetric({...acwr,calculation_inputs})!.actualCalculation).toBeUndefined();
  }
  const unknownMethod = explainMetric({...acwr,calculation_inputs:{...snapshot,methodology:"unreviewed_method"}})!;
  expect(unknownMethod.actualCalculation).toBeDefined();
  expect(unknownMethod.methodology.map(text=>text.key)).not.toContain("metricEducation.methods.unreviewed_method");
});

test("every curated definition and explanation resolves to real English and Italian copy", () => {
  const lookup = (catalog: unknown, key: string) => key.split(".").reduce<unknown>((node,part) =>
    node && typeof node === "object" ? (node as Record<string,unknown>)[part] : undefined,catalog);
  for (const metric of Object.keys(metricEducationDefinitions)) {
    const explanation = explainMetric({...rhr,metric,reference_range:null})!;
    const texts = [explanation.identity.label, explanation.definition, explanation.whyItMatters,
      ...explanation.knownInfluences,...explanation.actionableFactors,...explanation.methodology,...explanation.limitations];
    for (const text of texts.filter(Boolean)) for (const catalog of [en,it]) {
      expect(lookup(catalog,text!.key),text!.key).toEqual(expect.any(String));
      expect((lookup(catalog,text!.key) as string).trim().length,text!.key).toBeGreaterThan(0);
    }
  }
});

test("disclosure starts closed, preserves the hero, toggles with pointer and keyboard and emits only minimal utility events", async ({page}) => {
  await showMetric(page,rhr);
  const panel = disclosure(page);
  const summary = panel.locator("summary");
  const chart = page.getByRole("img",{name:/Resting Heart Rate · bpm ·/});
  const heroBefore = await page.locator(".hero-number").boundingBox();
  const chartBefore = await chart.boundingBox();
  const scrollBefore = await page.evaluate(() => scrollY);
  await expect(summary).toHaveAttribute("aria-expanded","false");
  await expect(panel.getByRole("heading",{name:"Your context",exact:true})).not.toBeVisible();
  expect(await panel.evaluate(element=>(element as HTMLDetailsElement).open)).toBe(false);
  expect(await panel.evaluate(element=>Boolean(element.nextElementSibling?.matches('[role="img"]')))).toBe(true);
  await page.waitForLoadState("networkidle");
  const requests:string[]=[];
  page.on("request",request=>{if(["fetch","xhr"].includes(request.resourceType()))requests.push(request.url());});
  await summary.click();
  await expect(summary).toHaveAttribute("aria-expanded","true");
  await expect(panel.getByRole("heading",{name:"Your context",exact:true})).toBeVisible();
  await expect(panel.getByRole("heading",{name:"Why today?",exact:true})).toHaveCount(0);
  await expect(panel).toContainText("-1.0 bpm");
  await expect(panel).toContainText("25 days / previous 4 weeks");
  await expect(panel).toContainText("Source · Garmin");
  expect(await page.locator(".hero-number").boundingBox()).toEqual(heroBefore);
  const chartExpanded = await chart.boundingBox();
  expect(chartExpanded!.width).toBe(chartBefore!.width);
  expect(chartExpanded!.height).toBe(chartBefore!.height);
  const panelBox = await panel.boundingBox();
  expect(chartExpanded!.y).toBeGreaterThanOrEqual(panelBox!.y+panelBox!.height);
  await summary.click();
  await expect(summary).toHaveAttribute("aria-expanded","false");
  await summary.press("Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(summary).toBeFocused();
  expect(await summary.evaluate(element=>getComputedStyle(element).outlineStyle)).not.toBe("none");
  await summary.press("Enter");
  await expect(summary).toHaveAttribute("aria-expanded","true");
  await summary.press("Space");
  await expect(summary).toHaveAttribute("aria-expanded","false");
  expect((await chart.boundingBox())!.y + await page.evaluate(() => scrollY)).toBe(chartBefore!.y + scrollBefore);
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every(url => new URL(url).pathname === "/alpha/events")).toBe(true);
});

test("context follows existing duration and imperial-unit formatting", async ({page}) => {
  for (const [metric,value,unit,expected] of [
    ["sleep_duration",7.5,"h","7:30 h"],
    ["weight",70,"kg","154.3 lb"],
  ] as const) {
    await showMetric(page,{...rhr,metric,unit,reference_range:null,points:[{date:end,value}]},{units:"imperial"});
    await disclosure(page).locator("summary").click();
    await expect(disclosure(page).locator("dd")).toHaveText(expected);
  }
});

test("ACWR uses actual inputs for Why today; incomplete snapshots fall back to context", async ({page}) => {
  await showMetric(page,acwr);
  await disclosure(page).locator("summary").click();
  await expect(disclosure(page).getByRole("heading",{name:"Why today?",exact:true})).toBeVisible();
  await expect(disclosure(page)).toContainText("120.0 Garmin load/week");
  await expect(disclosure(page)).toContainText("100.0 Garmin load/week");
  await expect(disclosure(page)).toContainText(`Calculated for ${end}`);
  await expect(disclosure(page).getByRole("heading",{name:"Your context",exact:true})).toHaveCount(0);
  await page.route(url=>url.pathname==='/metrics/acwr',route=>route.fulfill({json:{...acwr,calculation_inputs:null}}));
  await page.reload();
  await expect(disclosure(page).locator("summary")).toHaveAttribute("aria-expanded","false");
  await disclosure(page).locator("summary").click();
  await expect(disclosure(page).getByRole("heading",{name:"Your context",exact:true})).toBeVisible();
  await expect(disclosure(page).getByRole("heading",{name:"Why today?",exact:true})).toHaveCount(0);
});

test("Recovery and provider scores never invent Why today or provider provenance", async ({page}) => {
  for (const metric of ["recovery","provider_sleep_score"]) {
    await showMetric(page,{...acwr,metric,calculation_inputs:null});
    await disclosure(page).locator("summary").click();
    await expect(disclosure(page).getByRole("heading",{name:"Your context",exact:true})).toBeVisible();
    await expect(disclosure(page).getByRole("heading",{name:"Why today?",exact:true})).toHaveCount(0);
    await expect(disclosure(page)).not.toContainText("Source · Garmin");
    await expect(disclosure(page).getByRole("heading",{name:metric==='recovery'?"How Apex calculates this":"About this calculation",exact:true})).toBeVisible();
  }
});

for (const locale of ["en","it"] as const) for (const width of [320,390,1440]) {
  test(`${locale} expanded content at ${width}px stays accessible and within the viewport`,async ({page})=>{
    await page.setViewportSize({width,height:900});
    await page.emulateMedia({reducedMotion:"reduce"});
    await showMetric(page,rhr,{locale,theme:locale==='it'?'dark':'light'});
    const panel=disclosure(page);
    const pageWidthBefore = await page.evaluate(()=>document.documentElement.scrollWidth);
    await panel.locator("summary").click();
    await expect(panel.getByRole("heading",{name:locale==='it'?"Il tuo contesto":"Your context",exact:true})).toBeVisible();
    const sections=panel.locator("section");
    const context=await sections.nth(0).boundingBox();
    const definition=await sections.nth(1).boundingBox();
    if(width<768)expect(definition!.y).toBeGreaterThanOrEqual(context!.y+context!.height);
    else expect(definition!.y).toBe(context!.y);
    expect(await panel.evaluate(element=>element.scrollWidth<=element.clientWidth)).toBe(true);
    // The pre-existing shell/header overflows at 320px; this feature must not add overflow.
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(pageWidthBefore);
    if(width>=390)expect(pageWidthBefore).toBeLessThanOrEqual(width);
    const violations=(await new AxeBuilder({page}).include('details:has(summary[aria-controls])').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations;
    expect(violations).toEqual([]);
  });
}


const recoverySnapshot: MetricTrend = {
  ...rhr, metric: "recovery", reference_range: null, unit: "/100", points: [{ date: end, value: 80 }],
  definition: { id: "recovery", display_name: "Recovery estimate", kind: "heuristic",
    validation_level: "heuristic", formula_version: "recovery-v2", formula: "Recorded weighted components",
    minimum_data_requirements: "Available components", missing_data_behavior: "Omit missing inputs",
    limitations: [], prohibited_claims: [] },
  calculation_provenance: { metric: "recovery", value: 80, as_of: end, formula_version: "recovery-v2",
    inputs: { sleep_quality: 80, hrv_deviation: null },
    components: { sleep_quality: { value: 0.8, active: true, weight: 0.2, normalized_weight: 1 },
      hrv_deviation: { value: null, active: false, weight: 0.35, normalized_weight: null } },
    weights: { sleep_quality: { value: 0.2, version: 2, id: 12, effective_from: "2026-10-01T00:00:00Z" } },
    baselines: { hrv: { value: null, observed_days: 5, required_days: 7 } },
    sources: { sleep_quality: { attribution: "apex_derived" }, hrv_deviation: { provider: null, attribution: "unavailable" } },
    missing_inputs: ["hrv_deviation"], missing_components: ["hrv_deviation"],
    coverage: { status: "limited_coverage", available_components: 1, total_components: 2 } },
  calculation_inputs: { metric: "recovery", as_of: end, methodology: "recovery-v2",
    contributors: [{ metric: "sleep_quality", value: 80, unit: "/100" }] },
};

test("canonical scientific kind and exact score record enrich the existing contract", () => {
  const result = explainMetric(recoverySnapshot)!;
  expect(result.semanticType).toBe("apex_derived");
  expect(result.heuristic).toBe(true);
  expect(result.actualCalculation?.contributors.map(item => item.display)).toEqual(recoverySnapshot.calculation_inputs!.contributors);
  expect(result.methodology).toContainEqual({ key: "metricEducation.registry.formulaVersion", values: { version: "recovery-v2" } });
  expect(result.provenance).toContainEqual({ key: "metricEducation.registry.baselineCoverageNamed", values: { baseline: "hrv", count: 5, required: 7 } });
  expect(result.limitations.map(item => item.key)).not.toContain("metricEducation.limits.composite_inputs_unavailable");
  expect(result.calculationDetails).toHaveLength(2);
});

test("wrong-date, mismatched-value, inactive and invented score operands stay unavailable", () => {
  const snapshot = recoverySnapshot.calculation_provenance!;
  for (const calculation_provenance of [null, { ...snapshot, as_of: "2026-10-03" }, { ...snapshot, value: 81 },
    { ...snapshot, value: NaN }, { ...snapshot, components: null }]) {
    expect(explainMetric({ ...recoverySnapshot, calculation_provenance } as MetricTrend)!.actualCalculation).toBeUndefined();
  }
  for (const contributor of [{ metric: "sleep_quality", value: 79, unit: "/100" },
    { metric: "hrv_deviation", value: 55, unit: "ms" }]) {
    expect(explainMetric({ ...recoverySnapshot, calculation_inputs: { metric: "recovery", as_of: end, contributors: [contributor] } })!.actualCalculation).toBeUndefined();
  }
});

test("recorded recovery details render in Italian without reconstructing missing history", async ({ page }) => {
  await showMetric(page, recoverySnapshot, { locale: "it" });
  const panel = disclosure(page);
  await panel.locator("summary").first().click();
  await expect(panel.getByRole("heading", { name: "Perché oggi?", exact: true })).toBeVisible();
  await expect(panel).toContainText("recovery-v2");
  await expect(panel).toContainText("Stima euristica Apex");
  await expect(panel).toContainText("5 giorni osservati, 7 richiesti");
  await expect(panel).not.toContainText("Il calcolo storico esatto non è stato salvato");
  const violations = (await new AxeBuilder({ page }).include('details:has(summary[aria-controls])').withTags(['wcag2a','wcag2aa']).analyze()).violations;
  expect(violations).toEqual([]);
});
