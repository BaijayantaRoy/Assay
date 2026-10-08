# Governance

## Who decides

Assay has one maintainer: [@BaijayantaRoy](https://github.com/BaijayantaRoy). Decisions are
made by that person, in public, with the reasoning written down.

Saying so plainly is the point. A project that implies a committee it does not have is
misrepresenting itself, and this project's entire argument is about not doing that.

## How decisions get recorded

Anything that changes a public contract — the format, a plugin protocol, the REST surface,
the CLI's exit codes — is written as an **Architecture Decision Record** in
[`docs/architecture/adr/`](docs/architecture/adr/) before it ships.

An ADR states the context, the decision, **its cost**, and what was considered and
rejected. It is not a press release:
[ADR-0009](docs/architecture/adr/0009-name-and-spec-brand-separation.md) records what was
never verified. That is the standard. An ADR that lists no costs has not finished.

ADRs are numbered, never renumbered, and never quietly edited after acceptance. A decision
that changes gets a new ADR that supersedes the old one, and the old one stays readable.

## The things that are not up for a vote

These are invariants, not preferences. A change that breaks one is rejected regardless of
how much else it improves.

1. **Never report a number that overstates what was measured.** An unverified run says *not
   checked*, never *passed*. A rate computed from zero usable samples is withheld, not shown
   as `0%`.
2. **`verified` is tri-state.** `None` means nothing was checked. It is not a falsy `False`.
3. **A test that cannot fail is worse than no test.**
4. **Unknown fields in a PromptFile round-trip untouched.**
5. **The public format key is `promptfile:`, never the product's name.**

## The format is not the product

PromptFile v1 is published under CC BY 4.0 and is deliberately vendor-neutral. Anyone may
implement it, including in products competing with this one.

That is a governance commitment, not a licence footnote. Concretely:

- The format's required key, its reserved URI schemes, and its schema `$id` carry no
  product name, so a rename of this project costs implementers nothing. That promise has
  now been tested twice.
- A change to the spec that only makes sense for *this* runtime's convenience is the wrong
  change.
- Spec issues from people building a competing implementation get the same treatment as
  anyone else's — better, if they found something the reference implementation got away with.

If Assay is ever abandoned, the spec and every file written against it survive it. That
is the design, and it is the reason for the separation.

## Compatibility

The spec, the plugin contracts, and the REST API version independently, each with a
12-month deprecation floor. See
[ADR-0004](docs/architecture/adr/0004-compatibility-policy.md). A deprecation is announced
in the changelog with its removal version named at announcement time, not later.

## How this changes

More maintainers, a real decision-making body, a foundation — all are possible and none are
pretended at now. The trigger is people doing the work, not a date. If that happens, this
document gets rewritten and an ADR records why.
