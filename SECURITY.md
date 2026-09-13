# Security Policy

## Reporting a vulnerability

Report privately through **[GitHub Security Advisories](../../security/advisories/new)** —
not a public issue.

Please include what you did, what happened, and what you expected. A failing test or a
PromptFile that reproduces the problem is worth more than a paragraph.

Expect an acknowledgement within 5 working days. This is a small project and there is no
paid security team behind it; that number is a commitment to answer, not to have a fix.

## What this project claims, and what it does not

Assay ships an injection-defence layer and a red-team corpus, so it is worth stating
plainly where the line is.

**The provenance fence raises the cost of an attack. It is not a safety boundary.**
Tool output is wrapped in a nonce-marked fence and labelled as untrusted data before it
re-enters the model's context, and a scanner flags injection-associated patterns. Both
help. Neither is a guarantee, because the model can still choose to follow instructions in
data it was told to distrust. Detection is measured at roughly 60% on our own corpus, and
the obfuscation, staged and false-authority categories are **known gaps** — listed as gaps
in `assay redteam` output rather than quietly excluded from the denominator.

**A passing red-team run is not evidence of safety.** Against an offline provider it
measures the defences, not model susceptibility, and the report says so in `mode_note`.

**The governance control map is not a compliance assessment.** It records what the tool
does, with the gap stated beside every piece of evidence. It does not make anyone
compliant with the EU AI Act, ISO 42001 or anything else.

If you find a case where the product reports a number that overstates its own security —
a defence appearing to work when it did not, or a rate computed from a run that produced
nothing — treat that as a **security bug and report it as one**. Misleading assurance is
the failure mode this project cares about most.

## Scope

**In scope:** sandbox escapes in the tool layer; controller bypass (a denied tool call
executing); fence forgery that reliably works across runs; secret leakage into the audit
log, the environment fingerprint or memory; template-engine escapes out of Jinja2's
`SandboxedEnvironment`; path traversal in the file store.

**Out of scope:** a model being persuaded by a prompt — that is the threat model, not a
bug, unless a documented control failed to fire; vulnerabilities in third-party model
providers; anything requiring an attacker who already has write access to your prompt
repository, since a PromptFile is code and is trusted as code.

## Running untrusted PromptFiles

Don't. A PromptFile can declare tools, shell commands in loop steps, and model bindings.
It is executable content and deserves the same review a pull request gets. Loops execute
real commands in the workspace root.

## Supported versions

No version has been released yet, so only the latest commit on the default branch receives
security fixes. Beginning with `v1.0.0`, the latest `1.x` minor release will receive security
fixes; older minors and prereleases will be unsupported.
