import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

function formatViolations(violations: Awaited<ReturnType<AxeBuilder["analyze"]>>["violations"]) {
  return violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    targets: violation.nodes.map((node) => node.target.join(" ")),
  }));
}

test("dashboard exposes operable help and has no serious accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  await page.getByRole("button", { name: "About Dashboard" }).click();
  const dialog = page.getByRole("dialog", { name: "Dashboard" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "About Dashboard" })).toBeFocused();

  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = result.violations.filter((item) => item.impact === "critical" || item.impact === "serious");
  expect(formatViolations(serious)).toEqual([]);
});

test("Help Centre connects workflows, global controls, and the complete guide directory", async ({ page }) => {
  await page.goto("/help");
  await expect(page.getByRole("heading", { level: 1, name: "Help Centre" })).toBeVisible();
  await expect(page.getByRole("button", { name: "About Help Centre" })).toBeEnabled();
  await expect(page.getByRole("heading", { name: "From an idea to a usable, evidenced prompt" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "The controls that are available everywhere" })).toBeVisible();
  const globalControls = page.locator('section[aria-labelledby="global-controls-heading"]');
  await expect(globalControls.getByText("Portal map", { exact: true })).toBeVisible();
  await expect(globalControls.getByText("About this page", { exact: true })).toBeVisible();

  const search = page.getByRole("textbox", { name: "Search page guides" });
  await search.fill("prompt-body builder");
  await expect(page.getByRole("heading", { name: "Prompt Studio" })).toBeVisible();
  await expect(page.getByText(/does not open or edit an existing PromptFile/)).toHaveCount(0);

  await page.getByRole("link", { name: "Open Prompt Studio", exact: true }).click();
  await expect(page).toHaveURL(/\/studio$/);
  await expect(page.getByRole("button", { name: "About Prompt Studio" })).toBeEnabled();
});

test("every primary menu destination has a truthful, operable page guide", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/");
  const routes = await page.locator('nav[aria-label="Primary navigation"] a').evaluateAll((links) => (
    links.map((link) => link.getAttribute("href")).filter((href): href is string => Boolean(href))
  ));
  expect(routes.length).toBeGreaterThan(20);

  for (const route of routes) {
    await page.goto(route);
    const guide = page.locator('button[aria-label^="About "]');
    await expect(guide, route).toHaveCount(1);
    await expect(guide, route).toBeEnabled();
  }
});

test("detail pages receive their own workflow guide and the portal map names the shared file flow", async ({ page }) => {
  await page.goto("/prompts/agents/code-reviewer");
  const promptGuide = page.getByRole("button", { name: "About Prompt detail" });
  await expect(promptGuide).toBeEnabled();
  await promptGuide.click();
  const detailDialog = page.getByRole("dialog", { name: "Prompt detail" });
  await expect(detailDialog.getByText("Not on this screen", { exact: true })).toBeVisible();
  await expect(detailDialog.getByText(/does not edit frontmatter/)).toBeVisible();
  await detailDialog.getByRole("button", { name: "Close" }).click();

  await page.getByRole("button", { name: "Open portal map" }).click();
  const map = page.getByRole("dialog", { name: "How Assay fits together" });
  await expect(map.getByText("Shared source of truth", { exact: true })).toBeVisible();
  await expect(map.getByRole("link", { name: "Loops" })).toHaveCount(1);
  await expect(map.getByRole("link", { name: "Verified Loops" })).toHaveCount(0);
});

test("mobile navigation overlays content without shrinking or overflowing the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const menu = page.getByRole("button", { name: "Open navigation" });
  await expect(menu).toBeVisible();

  const geometry = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    mainWidth: document.querySelector("main")?.getBoundingClientRect().width ?? 0,
  }));
  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewport);
  expect(geometry.mainWidth).toBeGreaterThanOrEqual(geometry.viewport - 1);

  await menu.click();
  await expect(page.getByRole("navigation")).toBeVisible();
  await page.getByRole("link", { name: "All Prompts" }).click();
  await expect(page).toHaveURL(/\/prompts$/);
  await expect(page.getByRole("navigation")).toBeHidden();
  await expect(page.getByRole("heading", { name: "All Prompts" })).toBeVisible();
});

test("settings is secret-free and accessible", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.locator('input[type="password"]')).toHaveCount(0);

  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = result.violations.filter((item) => item.impact === "critical" || item.impact === "serious");
  expect(formatViolations(serious)).toEqual([]);
});

test("keyboard users can bypass global navigation", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});

test("light, dark, and eye-care themes retain accessible contrast", async ({ page }) => {
  await page.goto("/settings");
  const theme = page.getByRole("button", { name: /Switch to .+ theme/ });
  await expect(theme).toBeVisible();

  for (const expectedClass of ["eye-care", "light", "dark"] as const) {
    await theme.click();
    if (expectedClass === "light") {
      await expect(page.locator("html")).not.toHaveClass(/dark|eye-care/);
    } else {
      await expect(page.locator("html")).toHaveClass(new RegExp(expectedClass));
    }
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = result.violations.filter(
      (item) => item.impact === "critical" || item.impact === "serious",
    );
    expect(formatViolations(serious), `${expectedClass} theme violations`).toEqual([]);
  }
});

test("reduced-motion preference suppresses interface transitions", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const durationMs = await page.getByRole("button", { name: "Collapse navigation" })
    .evaluate((element) => getComputedStyle(element).transitionDuration.split(",").map((value) => {
      const duration = value.trim();
      return duration.endsWith("ms") ? Number.parseFloat(duration) : Number.parseFloat(duration) * 1000;
    }));
  expect(Math.max(...durationMs)).toBeLessThanOrEqual(0.02);
});

test("stream-backed harness exposes delivery evidence on its trajectory", async ({ page }) => {
  await page.goto("/agents/harnesses");
  await expect(page.getByRole("heading", { name: "Harnesses" })).toBeVisible();
  await expect(page.getByText("streamed", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Run harness" }).click();

  await expect(page.getByText("completed", { exact: true })).toBeVisible();
  await expect(page.getByText(/native provider stream · \d+ chunks?/).first()).toBeVisible();
  await expect(page.getByText("mock.search", { exact: true }).first()).toBeVisible();
});

test("delivery status separates verified, active, and queued work", async ({ page }) => {
  await page.goto("/delivery");
  await expect(page.getByRole("heading", { name: "Delivery status" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Done · verified" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Being built" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Next in sequence" })).toBeVisible();
  const verified = page.getByRole("region", { name: "Done · verified" });
  await expect(verified.getByRole("heading", { level: 3 }).first()).toHaveText(
    "Full release and distribution matrix",
  );
  await expect(page.getByText("Benchmark-leading scorecard", { exact: true })).toBeVisible();
  await expect(page.getByText(/competitor trials remain not measured/)).toBeVisible();
  await page.getByRole("link", { name: "Benchmark protocol and live scorecard" }).click();
  await expect(page.getByRole("heading", { name: "Benchmark scorecard" })).toBeVisible();
  await expect(page.getByText("50%-better competitive claim withheld", { exact: true })).toBeVisible();
  await expect(page.getByText("Competitive KPIs proven")).toBeVisible();
  await expect(page.getByText("Not measured on the shared task corpus", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Shared protocol kit ready" })).toBeVisible();
  await expect(page.getByText(/Seventeen benchmark tests plus schema/)).toBeVisible();
  await expect(page.getByText(/50 assignment slots planned across 5 products/)).toBeVisible();
  await expect(page.getByText(/Role template—not evidence/)).toBeVisible();
  const operatorKit = page.getByRole("link", { name: /Download operator kit/ });
  await expect(operatorKit).toHaveAttribute("href", "/benchmark/assay-assurance-wedge-v1.zip");
  await expect(page.getByText("Operator kit SHA-256", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Minimum evidence still required" })).toBeVisible();
  await expect(page.getByText(/40 qualifying trial records minimum/)).toBeVisible();
  await expect(page.getByText(/0 of 3 required comparators currently qualify/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Machine-verifiable evidence source" })).toBeVisible();

  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = result.violations.filter(
    (item) => item.impact === "critical" || item.impact === "serious",
  );
  expect(formatViolations(serious)).toEqual([]);
});

test("red-team portal exposes the measured static corpus scope", async ({ page }) => {
  await page.goto("/security/redteam");
  await expect(page.getByRole("heading", { name: "Red Team" })).toBeVisible();
  await expect(page.getByText("Corpus entries", { exact: true })).toBeVisible();
  await expect(page.getByText("64", { exact: true })).toBeVisible();
  await expect(page.getByText("52", { exact: true })).toBeVisible();
  await expect(page.getByText("12", { exact: true })).toBeVisible();
  await expect(page.getByText("27", { exact: true })).toBeVisible();
  await expect(page.getByText("ssrf", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("privilege_escalation", { exact: true }).first()).toBeVisible();

  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = result.violations.filter(
    (item) => item.impact === "critical" || item.impact === "serious",
  );
  expect(formatViolations(serious)).toEqual([]);
});
