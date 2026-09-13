# ADR-0007 — Fully open source; remove the licensing layer

**Status:** Accepted · **Date:** 2026-07-27 · **Supersedes:** the 0.x open-core model

## Context

Version 0.x shipped an open-core model: an RSA-signed offline license (`licensing.py`,
`/license` router, `require_pro_license` dependency) gated A/B testing and other features, with
a `FREE_VS_PRO.md` comparison. The repository contained `public_key.pem`, and
`private_key.pem` existed on disk (gitignored, but present).

Three problems.

**Adoption.** A prompt library only earns trust once people put their prompts in it. A
gate — even one they never hit — is a reason to evaluate something else, and evaluation
attention is the scarcest resource an unknown project has.

**Credibility of the central claim.** The project's argument is that your prompts should be
files you own, in your repo, with a `git clone` exit cost. Feature flags controlled by a
signature the vendor issues undercut that argument.

**Enforceability.** Offline license verification in a self-hosted Python application where the
user controls the process is a speed bump, not a control. Maintaining a speed bump costs real
code and real review attention.

## Decision

**Remove the licensing layer entirely and ship everything under MIT.**

Deleted: `backend/licensing.py`, `backend/api/routers/license.py`, the `require_pro_license`
dependency and its usages, `docs/FREE_VS_PRO.md`, `public_key.pem`, `private_key.pem`, and the
associated tests.

The **specification** (`spec/`) is published separately under **CC BY 4.0**, so other tools —
including commercial competitors — can implement PromptFile without touching MIT code. A
format that is awkward for competitors to adopt does not become a standard.

Nothing phones home. No telemetry, no account, no hosted dependency.

## Consequences

**Good**

- The "your prompts, your repo, your license" claim is now literally true, with no asterisk.
- Roughly 200 lines of security-sensitive code and its review burden are gone.
- No key material in the repository — one whole class of secret-leak incident removed.
- Contributors can run and test every feature, which is the precondition for contributions.

**Costs**

- No revenue mechanism in the repository. Deliberate. If commercial support, a hosted tier, or
  sponsorship is wanted later, it belongs *around* the project — the architecture stays
  deployment-agnostic and stateless-friendly so a hosted offering remains possible without
  reintroducing gates in the open code.
- The 0.x install base with license files: those files are simply ignored now. No migration
  needed, no breakage.

## Note on MIT vs Apache-2.0

MIT is retained because it is what the repository already used and it is maximally permissive.
**Apache-2.0 is worth considering** for a project that publishes a specification, because it
carries an express patent grant and explicit contributor terms — genuinely useful when
inviting third-party implementations. Switching is a small, well-understood change and needs
sign-off from all copyright holders; it is tracked in [ROADMAP](../ROADMAP.md) rather than
decided unilaterally here.
