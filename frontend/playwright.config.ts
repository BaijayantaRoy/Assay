import { defineConfig } from "@playwright/test";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "..");
const localPython = path.join(repoRoot, "venv", "Scripts", "python.exe");
const python = process.env.ASSAY_TEST_PYTHON || (process.platform === "win32" ? localPython : "python");

export default defineConfig({
  testDir: "./tests/browser",
  outputDir: "./test-results/browser",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "line",
  snapshotPathTemplate: "{testDir}/__screenshots__/{platform}/{testFileName}/{arg}{ext}",
  use: {
    baseURL: "http://127.0.0.1:3001",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`,
      cwd: repoRoot,
      url: "http://127.0.0.1:8001/health",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        ASSAY_WORKSPACE: repoRoot,
        ASSAY_ENABLE_LEGACY_API: "",
      },
    },
    {
      command: "npm run dev",
      cwd: __dirname,
      url: "http://127.0.0.1:3001",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        ASSAY_BACKEND_URL: "http://127.0.0.1:8001",
      },
    },
  ],
});
