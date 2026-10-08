# Support

## Before you open anything

Almost every problem with Assay is one of four things, and three of them have a fast
answer.

| Symptom | Try |
|:--|:--|
| A command behaves unexpectedly | `assay <command> --help`, then [the user guide](docs/user_guide.md) |
| An artifact will not load or run | `assay lint` and `assay spec validate <file>` |
| A plugin is not found | `assay plugins` — it lists load failures, not just successes |
| Something worked before an upgrade | The [changelog](docs/CHANGELOG.md) — every deprecation names its removal version |

## Where to go

| | |
|:--|:--|
| **A question** — how do I, is this supposed to | [GitHub Discussions](https://github.com/BaijayantaRoy/Assay/discussions) |
| **A bug** | [Open an issue](https://github.com/BaijayantaRoy/Assay/issues/new/choose) with the smallest reproducer, the command, the exit code, and your Python / Node / OS versions |
| **A security issue** | **Not a public issue.** [SECURITY.md](SECURITY.md) — private advisory |
| **The spec** | An issue tagged `spec`. Questions about the *format* are more valuable than questions about this implementation |

## The bug report that gets fixed fastest

A failing PromptFile. This project is built so that a bug can usually be expressed as an
artifact plus an eval case that should pass and does not. That is worth more than a
paragraph of description, and it often becomes the regression test.

```bash
assay test path/to/your.prompt.md --json
```

## What to expect

This is a small project with one maintainer and no paid support. You will get an answer;
you will not always get a fix, and you will never get a fix by a date someone promised you.
[SECURITY.md](SECURITY.md) states the one response commitment that exists: an
acknowledgement within five working days on a security report, which is a commitment to
*answer*, not to have a fix.

## What is out of scope

- Debugging your prompts' content. The tool measures artifacts; it does not review them for
  you.
- Model provider behaviour, pricing, or outages.
- A model being persuaded by a prompt — that is the threat model, not a bug, unless a
  documented control failed to fire.
