export type DeliveryStage = "verified" | "in_progress" | "queued";

export type DeliveryEvidence = {
  label: string;
  detail: string;
  href?: string;
};

export type DeliveryMilestone = {
  id: string;
  title: string;
  summary: string;
  stage: DeliveryStage;
  verification: string;
  evidence: DeliveryEvidence[];
};

/**
 * Source-controlled product delivery ledger.
 *
 * This is deliberately not inferred from file presence or a long-running background job.
 * A milestone moves to `verified` only when the scoped evidence named below has passed.
 * In-progress and queued work therefore remain visible without being counted as shipped.
 */
export const DELIVERY_STATUS = {
  snapshot: "10 Aug 2026 · live verified checkpoint",
  objective:
    "Close the audited release gaps in priority order, then prove Assay against a benchmark-leading assurance scorecard.",
  milestones: [
    {
      id: "portal-foundations",
      title: "Secure, responsive portal foundations",
      summary:
        "Removed ineffective browser-side credential storage, repaired the mobile navigation shell, and added keyboard, reduced-motion, and theme accessibility coverage.",
      stage: "verified",
      verification:
        "Verified by focused browser interaction and accessibility checks across desktop and mobile layouts.",
      evidence: [
        {
          label: "Secret-free settings",
          detail: "Provider readiness is read from the backend; no API-key fields or localStorage secret path remain.",
          href: "/settings",
        },
        {
          label: "Responsive navigation",
          detail: "The mobile drawer overlays the page without shrinking or horizontally overflowing main content.",
        },
        {
          label: "Accessible shell",
          detail: "Skip navigation, three contrast-checked themes, focus restoration, and reduced-motion behavior are exercised.",
        },
      ],
    },
    {
      id: "honest-assurance",
      title: "Honest assurance contracts",
      summary:
        "Kept verification tri-state, withheld rates without usable samples, exposed governance gaps beside evidence, and pinned the runtime fields consumed by the portal.",
      stage: "verified",
      verification:
        "Verified by the full core suite plus focused backend and /v1 UI-contract checks.",
      evidence: [
        {
          label: "Tri-state verification",
          detail: "Not checked, passed, and failed remain distinct states through core, API, SDK, and portal boundaries.",
          href: "/governance",
        },
        {
          label: "Honest denominators",
          detail: "Unusable runs and zero-sample measurements do not manufacture pass rates or reassuring zeroes.",
        },
        {
          label: "Runtime UI contract",
          detail: "E2E contract checks pin the real JSON fields rather than relying on erased TypeScript types.",
        },
      ],
    },
    {
      id: "streamed-trajectories",
      title: "Native stream-backed agent trajectories",
      summary:
        "Provider tool-call fragments are assembled by stable index, harness turns consume native streams, and each trajectory step records chunk-level delivery evidence.",
      stage: "verified",
      verification:
        "Verified by focused core, API-contract, mutation, and real-browser harness interaction checks.",
      evidence: [
        {
          label: "Visible streamed run",
          detail: "Run Researcher v2 to inspect mock.search → mock.fetch and native chunk counts on every step.",
          href: "/agents/harnesses",
        },
        {
          label: "Fail-closed assembly",
          detail: "Malformed streamed JSON does not become an executable tool call.",
        },
        {
          label: "Trajectory assertions",
          detail: "The reconstructed tool path is evaluated as behavior, not accepted from final text alone.",
        },
      ],
    },
    {
      id: "visual-regression",
      title: "Visual regression release gate",
      summary:
        "A deterministic Playwright snapshot harness now protects the specification, delivery ledger, streamed Harnesses, red-team corpus, and mobile navigation on the same Windows platform used by CI.",
      stage: "verified",
      verification:
        "Five reviewed baselines each pass their latest fresh comparison.",
      evidence: [
        {
          label: "Five reviewed baselines",
          detail: "PromptFile spec, Delivery Status, streamed Harnesses, red-team corpus, and the 390px navigation overlay are captured.",
        },
        {
          label: "Blocking Windows comparison",
          detail: "CI runs the same dedicated command and uploads screenshot differences when the comparison fails.",
        },
      ],
    },
    {
      id: "container-proof",
      title: "Container startup proof",
      summary:
        "The backend and standalone frontend images build, Compose gates frontend startup on backend readiness, and both services expose explicit container health checks.",
      stage: "verified",
      verification:
        "Verified on Docker Desktop 4.75.0: both services healthy and four external HTTP probes returned 200.",
      evidence: [
        {
          label: "Image-level build",
          detail: "The Assay backend and frontend images completed from the current worktree.",
        },
        {
          label: "Health-aware startup",
          detail: "Compose waits for backend health; backend and frontend both reached the healthy state.",
        },
        {
          label: "End-to-end probes",
          detail: "Backend health, Delivery Status, same-origin API health, and workspace health each returned HTTP 200.",
        },
      ],
    },
    {
      id: "security-regression-breadth",
      title: "Expanded fail-closed security regression gate",
      summary:
        "Expanded the deterministic static corpus to 52 attacks across 26 adversarial categories plus 12 benign controls, while rejecting ambiguous corpus semantics before a run can be scored.",
      stage: "verified",
      verification:
        "Real binary: 52/52 attacks usable, 0 errors, 0% ASR, 46.15% detection, and 0% false positives in explicitly scripted defence mode.",
      evidence: [
        {
          label: "Six added risk families",
          detail: "SSRF, cross-tenant access, destructive actions, financial fraud, consent bypass, and privilege escalation now have two deterministic attacks each.",
          href: "/security/redteam",
        },
        {
          label: "Precision controls",
          detail: "Four matching benign controls keep false-positive behavior measurable instead of rewarding a detector that flags everything.",
        },
        {
          label: "Fail-closed corpus contract",
          detail: "Unknown targets, string booleans, invalid tool lists, metadata mismatches, and dishonest benign/adversarial labels are rejected with file-and-line evidence.",
        },
        {
          label: "Deletion-sensitive and cross-surface proof",
          detail: "85 focused security tests, 2/2 targeted mutation kills, two real-process API contracts, one browser/accessibility check, and the reviewed fifth visual baseline pass.",
        },
        {
          label: "Measured detector improvement",
          detail: "Precision-biased patterns detect all 12 new-family attacks; real-run detection moved 25.0% → 46.15% (84.6% relative) without a benign false-positive increase.",
        },
      ],
    },
    {
      id: "release-matrix",
      title: "Full release and distribution matrix",
      summary:
        "Re-run the complete core, backend, E2E, browser, mutation, spec, prompt, docs, SDK, container, and package-integrity gates after the current security delta.",
      stage: "verified",
      verification:
        "Verified on the current worktree across core, backend, E2E, frontend, PromptFile, mutation, performance, benchmark-tooling, SDK, package, docs, and container gates.",
      evidence: [
        {
          label: "Current core verification",
          detail: "632/632 core tests pass in five bounded groups; the result covers runtime, governance, harness, evaluation, PromptFile, red-team, tracing, and related engine behavior.",
        },
        {
          label: "Current backend verification",
          detail: "42/42 backend tests pass. This includes four focused contracts proving a native ChromaDB panic cannot break an ordinary prompt write while process-control signals remain unswallowed.",
        },
        {
          label: "Current security verification",
          detail: "85 focused security tests, both new targeted mutations, two E2E contracts, one browser/accessibility check, five latest visual comparisons, the real 64-entry CLI run, and bundled-resource drift checks pass.",
        },
        {
          label: "Current E2E verification",
          detail: "125/125 E2E cases pass: 41/41 real-binary CLI, 22/22 API, 2/2 proxy, 19/19 real-stdio MCP, 10/10 cross-surface parity, and 31/31 UI-contract cases.",
        },
        {
          label: "Current frontend verification",
          detail: "48/48 browser interaction, responsive-route, and accessibility cases pass; 5/5 reviewed visual baselines pass a fresh comparison; TypeScript, ESLint, and the 30-page production build are green.",
        },
        {
          label: "Current repository verification",
          detail: "All five embedded eval suites pass; lint, shipped-pack spec validation, 46/46 mutation anchors, four bundled-resource drift checks, both performance budgets, and 17/17 benchmark-tooling tests are green.",
        },
        {
          label: "Current distribution verification",
          detail: "Python SDK 7/7, TypeScript SDK type/build/stream contracts, and independent PromptFile schema/conformance checks pass; four wheels, four sdists, and two npm tarballs pass release inventory validation.",
        },
        {
          label: "Current docs and container verification",
          detail: "Strict MkDocs completes; current backend and standalone frontend images build; backend health, Delivery Status, same-origin API health, and workspace health each return HTTP 200 from isolated containers.",
        },
      ],
    },
    {
      id: "benchmark-scorecard",
      title: "Benchmark-leading scorecard",
      summary:
        "Re-measure Assay against the strongest comparable assurance products using the published scorecard, explicit denominators, and reproducible evidence.",
      stage: "in_progress",
      verification:
        "Protocol and fail-closed scorer are verified; competitor trials remain not measured, so no 50%-better claim is made.",
      evidence: [
        {
          label: "Benchmark protocol and live scorecard",
          detail: "Three primary KPIs, six neutral tasks, operator capture tooling, content-verified raw artifacts, generated claim state, a coverage-complete 50-slot role template, and a deterministic operator kit are published. Seventeen benchmark tests pass.",
          href: "/benchmark",
        },
        {
          label: "Current measurement gap",
          detail: "The shared competitor trial ledger has zero qualifying trials. Independent operators and at least three comparators are still required.",
        },
      ],
    },
  ] satisfies DeliveryMilestone[],
};
