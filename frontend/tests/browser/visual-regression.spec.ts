import { expect, Page, test } from "@playwright/test";
import path from "node:path";

const stableStyle = path.join(__dirname, "visual-regression.css");

async function prepare(page: Page, pathName: string, heading: string) {
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" });
  await page.goto(pathName);
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

test("@visual PromptFile spec desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await prepare(page, "/spec", "PromptFile v1");

  await expect(page).toHaveScreenshot("promptfile-spec-desktop.png", {
    animations: "disabled",
    caret: "hide",
    fullPage: true,
    maxDiffPixelRatio: 0.001,
    stylePath: stableStyle,
  });
});

test("@visual delivery ledger desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await prepare(page, "/delivery", "Delivery status");

  await expect(page).toHaveScreenshot("delivery-status-desktop.png", {
    animations: "disabled",
    caret: "hide",
    fullPage: true,
    maxDiffPixelRatio: 0.001,
    stylePath: stableStyle,
  });
});

test("@visual red-team corpus desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await prepare(page, "/security/redteam", "Red Team");
  await expect(page.getByText("Corpus entries", { exact: true })).toBeVisible();

  await expect(page).toHaveScreenshot("redteam-corpus-desktop.png", {
    animations: "disabled",
    caret: "hide",
    fullPage: false,
  });
});

test("@visual streamed harness desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await prepare(page, "/agents/harnesses", "Harnesses");
  await expect(page.getByText("streamed", { exact: true })).toBeVisible();

  await expect(page).toHaveScreenshot("streamed-harness-desktop.png", {
    animations: "disabled",
    caret: "hide",
    fullPage: true,
    maxDiffPixelRatio: 0.001,
    stylePath: stableStyle,
  });
});

test("@visual mobile navigation overlay", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepare(page, "/delivery", "Delivery status");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();

  await expect(page).toHaveScreenshot("mobile-navigation-overlay.png", {
    animations: "disabled",
    caret: "hide",
    fullPage: false,
    maxDiffPixelRatio: 0.001,
    stylePath: stableStyle,
  });
});

test("@visual Help Centre desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await prepare(page, "/help", "Help Centre");
  await expect(page.getByRole("heading", { name: "From an idea to a usable, evidenced prompt" })).toBeVisible();

  await expect(page).toHaveScreenshot("help-centre-desktop.png", {
    animations: "disabled",
    caret: "hide",
    fullPage: false,
    maxDiffPixelRatio: 0.001,
    stylePath: stableStyle,
  });
});

test("@visual Prompt detail guide desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" });
  await page.goto("/prompts/agents/code-reviewer");
  await expect(page.getByRole("button", { name: "About Prompt detail" })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.getByRole("button", { name: "About Prompt detail" }).click();
  await expect(page.getByRole("dialog", { name: "Prompt detail" })).toBeVisible();

  await expect(page).toHaveScreenshot("prompt-detail-guide-desktop.png", {
    animations: "disabled",
    caret: "hide",
    fullPage: false,
    maxDiffPixelRatio: 0.001,
    stylePath: stableStyle,
  });
});
