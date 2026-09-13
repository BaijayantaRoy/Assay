import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

type RouteContract = {
  path: string;
  heading?: string;
  finalPath?: RegExp;
};

const routes: RouteContract[] = [
  { path: "/" },
  { path: "/prompts", heading: "All Prompts" },
  { path: "/library", heading: "Starter Library" },
  { path: "/studio", heading: "Prompt Studio" },
  { path: "/agents/harnesses", heading: "Harnesses" },
  { path: "/agents/loops", heading: "Loops" },
  { path: "/agents/memory", heading: "Agent Memory" },
  { path: "/context/tokens", heading: "Token Economy" },
  { path: "/datasets", heading: "Eval Lab" },
  { path: "/abtests", heading: "Paired A/B Comparison" },
  { path: "/compare", heading: "Paired A/B Comparison" },
  { path: "/chains", heading: "Loops", finalPath: /\/agents\/loops$/ },
  { path: "/quality/calibration", heading: "Judge Calibration" },
  { path: "/security/redteam", heading: "Red Team" },
  { path: "/governance", heading: "Governance" },
  { path: "/analytics", heading: "Analytics" },
  { path: "/observability", heading: "Observability" },
  { path: "/integrations", heading: "Integrations" },
  { path: "/guardrails", heading: "Guardrails Scanner" },
  { path: "/settings/models", heading: "Global Model Catalogue" },
  { path: "/settings", heading: "Settings" },
  { path: "/spec", heading: "PromptFile v1" },
  { path: "/projects", heading: "Projects" },
];

const mobileRoutes = new Set([
  "/", "/prompts", "/studio", "/agents/harnesses", "/agents/loops",
  "/datasets", "/security/redteam", "/governance", "/settings/models", "/spec",
]);

const accessibilityRoutes = new Set([
  "/prompts", "/studio", "/agents/harnesses", "/security/redteam",
  "/governance", "/spec",
]);

function captureRuntimeErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  return errors;
}

async function assertRoute(page: Page, contract: RouteContract, mobile: boolean) {
  const errors = captureRuntimeErrors(page);
  const response = await page.goto(contract.path);
  expect(response?.status(), `${contract.path} returned an HTTP error`).toBeLessThan(400);
  if (contract.finalPath) await expect(page).toHaveURL(contract.finalPath);

  const heading = contract.heading
    ? page.getByRole("heading", { level: 1, name: contract.heading })
    : page.getByRole("heading", { level: 1 }).first();
  await expect(heading).toBeVisible();
  await expect(page.getByText(/application error|internal server error/i)).toHaveCount(0);

  const geometry = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    mainWidth: document.querySelector("main")?.getBoundingClientRect().width ?? 0,
    headingTop: document.querySelector("h1")?.getBoundingClientRect().top ?? -1,
  }));
  expect(geometry.documentWidth, `${contract.path} overflows horizontally`).toBeLessThanOrEqual(
    geometry.viewport + 1,
  );
  expect(geometry.mainWidth).toBeGreaterThanOrEqual(mobile ? geometry.viewport - 1 : 700);
  expect(geometry.headingTop, `${contract.path} heading is outside the viewport`).toBeGreaterThanOrEqual(0);
  expect(errors, `${contract.path} emitted browser runtime errors`).toEqual([]);
}

for (const contract of routes) {
  test(`desktop route contract: ${contract.path}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await assertRoute(page, contract, false);
  });

  if (mobileRoutes.has(contract.path)) {
    test(`mobile route contract: ${contract.path}`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await assertRoute(page, contract, true);
      await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
    });
  }

  if (accessibilityRoutes.has(contract.path)) {
    test(`accessibility contract: ${contract.path}`, async ({ page }) => {
      await page.goto(contract.path);
      const heading = contract.heading
        ? page.getByRole("heading", { level: 1, name: contract.heading })
        : page.getByRole("heading", { level: 1 }).first();
      await expect(heading).toBeVisible();
      const result = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const serious = result.violations
        .filter((item) => item.impact === "critical" || item.impact === "serious")
        .map((item) => ({
          id: item.id,
          impact: item.impact,
          targets: item.nodes.map((node) => node.target.join(" ")),
        }));
      expect(serious).toEqual([]);
    });
  }
}
