"""``assay`` — the Assay command line.

Built on argparse with no required third-party dependencies, so it installs anywhere
and starts fast. Every command supports ``--json`` for scripting, and exit codes are
stable contract:

===== ==========================================================
Code  Meaning
===== ==========================================================
0     success
1     generic failure
2     usage error (argparse)
3     validation / lint failure
4     eval failure — the gate ``assay test`` gives CI
5     policy violation
6     provider or network failure
===== ==========================================================
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import sys
from pathlib import Path
from typing import Any

from assay_core import (
    AssayError,
    ModelCatalog,
    PromptFile,
    Runtime,
    Workspace,
    __version__ as CORE_VERSION,
    agentsmd,
    discover,
)
from assay_core.builtins.evaluators import aggregate  # noqa: F401  (re-exported for plugins)

from . import output
from .output import die, emit, heading, kv, table

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2
EXIT_VALIDATION, EXIT_EVAL, EXIT_POLICY, EXIT_PROVIDER = 3, 4, 5, 6

CLI_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def bounded_workers(raw: str) -> int:
    """Argparse type for the public provider-call concurrency ceiling."""
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer between 1 and 32") from exc
    if not 1 <= value <= 32:
        raise argparse.ArgumentTypeError("must be between 1 and 32")
    return value


def parse_vars(pairs: list[str] | None) -> dict[str, Any]:
    """``-v key=value``. Values that parse as JSON become typed; otherwise strings."""
    result: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            die(f"Invalid --var {pair!r}; expected key=value", EXIT_USAGE)
        key, _, raw = pair.partition("=")
        if raw.startswith("@"):
            path = Path(raw[1:])
            if not path.is_file():
                die(f"File not found for {key}: {path}", EXIT_USAGE)
            result[key] = path.read_text(encoding="utf-8")
            continue
        try:
            result[key] = json.loads(raw)
        except json.JSONDecodeError:
            result[key] = raw
    return result


def load_vars_file(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        die(f"Variables file not found: {path}", EXIT_USAGE)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        return yaml.safe_load(text) or {}
    return json.loads(text)


def context(args: argparse.Namespace) -> tuple[Workspace, Any, Runtime]:
    ws = Workspace.find(getattr(args, "workspace", None))
    store = ws.store()
    rt = Runtime(workspace=ws, default_model=getattr(args, "model", None))
    return ws, store, rt


def executor_for(artifact: PromptFile, runtime: Runtime):
    """Return the right engine for an artifact's kind.

    Prompts, harnesses and loops all expose ``evaluate(...)`` with the same report
    shape, so ``assay test`` treats them uniformly — one command gates all three.
    """
    from assay_core import AgentRuntime, LoopRuntime

    if artifact.is_loop:
        return LoopRuntime(runtime)
    if artifact.is_harness:
        return AgentRuntime(runtime)
    return runtime


def resolve_prompt(store, target: str) -> PromptFile:
    """Accept an id, an ``id@version``, or a filesystem path."""
    if "@" in target and not Path(target).exists():
        prompt_id, _, raw_version = target.rpartition("@")
        try:
            return store.get(prompt_id, version=int(raw_version))
        except ValueError:
            pass
    path = Path(target)
    if path.is_file():
        return PromptFile.load(path)
    return store.get(target)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_init(args):
    if args.from_url:
        prompts, safe_source = _download_init_source(
            args.from_url, allow_local=args.allow_local_url
        )
        target = Path(args.path or ".").resolve()
        existing = next((target / name for name in ("assay.yaml", "assay.yml", ".assay.yaml")
                         if (target / name).is_file()), None)
        if existing:
            ws = Workspace.find(target)
        elif args.dry_run:
            ws = Workspace(root=target, config={
                "name": args.name or target.name, "prompts": "./prompts"
            })
        else:
            ws = Workspace.init(target, name=args.name)
        store = ws.store()
        conflicts = [prompt.id for prompt in prompts if store.path_for(prompt.id).exists()]
        invalid = [
            {"id": prompt.id, "problems": prompt.validate()}
            for prompt in prompts if prompt.validate()
        ]
        report = {
            "source": safe_source,
            "workspace": str(target),
            "artifacts": len(prompts),
            "conflicts": conflicts,
            "invalid": invalid,
            "dry_run": bool(args.dry_run),
            "written": [],
        }
        if invalid:
            emit(args, report)
            if not args.json:
                output.fail(f"{len(invalid)} downloaded artifact(s) are invalid")
            return EXIT_VALIDATION
        if conflicts and not args.force:
            emit(args, report)
            if not args.json:
                output.fail("conflicting ids: " + ", ".join(conflicts))
                output.dim("Re-run with --force only after reviewing the dry-run report.")
            return EXIT_FAIL
        if not args.dry_run:
            for prompt in prompts:
                stored = store.put(prompt)
                report["written"].append(str(stored.path or store.path_for(stored.id)))
        emit(args, report)
        if not args.json:
            heading("Remote workspace preview" if args.dry_run else "Workspace imported")
            kv("source", safe_source)
            kv("artifacts", len(prompts))
            kv("conflicts", len(conflicts))
            kv("written", len(report["written"]))
        return EXIT_OK

    ws = Workspace.init(args.path or ".", name=args.name)
    sample = ws.prompts_root / "hello.prompt.md"
    if not sample.exists():
        sample.parent.mkdir(parents=True, exist_ok=True)
        sample.write_text(SAMPLE_PROMPT, encoding="utf-8")
    emit(args, {"workspace": str(ws.root), "config": str(ws.config_path)})
    if not args.json:
        heading("Workspace ready")
        kv("root", ws.root)
        kv("config", ws.config_path)
        kv("prompts", ws.prompts_root)
        print("\nNext:  assay ls   ·   assay run demo/hello -v name=World   ·   assay test")
    return EXIT_OK


def _download_init_source(url: str, *, allow_local: bool = False) -> tuple[list[PromptFile], str]:
    """Fetch a bounded PromptFile or `/v1/export` document without following redirects."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    import httpx

    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        die("--from requires an HTTPS URL", EXIT_USAGE)
    if parsed.username or parsed.password or parsed.fragment:
        die("--from URLs may not contain credentials or fragments", EXIT_USAGE)
    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        }
    except OSError as exc:
        die(f"cannot resolve --from host: {type(exc).__name__}", EXIT_PROVIDER)
    non_public = [
        address for address in addresses
        if not ipaddress.ip_address(address).is_global
    ]
    if non_public and not allow_local:
        die("--from resolved to a non-public address; pass --allow-local-url only for a "
            "server you control", EXIT_USAGE)
    if parsed.scheme != "https" and not (allow_local and non_public):
        die("--from requires HTTPS (HTTP is allowed only with --allow-local-url)", EXIT_USAGE)

    limit = 10 * 1024 * 1024
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    die("--from redirects are refused; use the final reviewed URL", EXIT_PROVIDER)
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared and int(declared) > limit:
                    die("--from responses larger than 10 MiB are refused", EXIT_VALIDATION)
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > limit:
                        die("--from responses larger than 10 MiB are refused", EXIT_VALIDATION)
                    chunks.append(chunk)
    except httpx.HTTPStatusError as exc:
        die(f"--from request failed with HTTP {exc.response.status_code}", EXIT_PROVIDER)
    except httpx.RequestError as exc:
        die(f"--from request failed: {type(exc).__name__}", EXIT_PROVIDER)
    except ValueError:
        die("--from returned an invalid Content-Length", EXIT_VALIDATION)
    text = b"".join(chunks).decode("utf-8")
    prompts: list[PromptFile] = []
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        document = None
    candidates = document.get("prompts") if isinstance(document, dict) else None
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, str):
                prompts.append(PromptFile.parse(candidate))
            elif isinstance(candidate, dict):
                data = dict(candidate)
                prompts.append(PromptFile(data=data, body=str(data.pop("body", "") or "")))
            else:
                die("--from export contains a non-PromptFile item", EXIT_VALIDATION)
    else:
        try:
            prompts = [PromptFile.parse(text)]
        except AssayError as exc:
            die(f"--from content is not a PromptFile or v1 export: {exc}", EXIT_VALIDATION)
    if not prompts:
        die("--from export contains no PromptFiles", EXIT_VALIDATION)
    safe_source = f"{parsed.scheme}://{parsed.hostname}{':' + str(parsed.port) if parsed.port else ''}{parsed.path}"
    return prompts, safe_source


def cmd_new(args):
    ws, store, _ = context(args)
    target = store.path_for(args.id)
    if target.exists() and not args.force:
        die(f"{target} already exists (use --force)", EXIT_FAIL)
    body = args.body or "Write your prompt here. Use {{ variable }} placeholders."
    pf = PromptFile(
        data={
            "promptfile":  1,
            "id": args.id,
            "name": args.name or args.id.rsplit("/", 1)[-1].replace("-", " ").title(),
            "description": args.description or "",
            "version": 1,
            "kind": args.kind,
            "status": "draft",
            "tags": args.tag or [],
            "engine": {"template": "jinja2", "strict": True},
            "model": {"primary": args.model or ws.default_model or "echo/echo"},
        },
        body=body,
    )
    store.put(pf)
    emit(args, {"id": pf.id, "path": str(target)})
    if not args.json:
        print(f"Created {target}")
    return EXIT_OK


def cmd_import(args):
    """Migrate a foreign prompt/eval config without overstating what translated."""
    from assay_core.builtins.importers import load_import_source, load_registry_source

    ws, store, _ = context(args)
    remote_registry = args.source.split("://", 1)[0].lower() if "://" in args.source else None
    if remote_registry in {"langfuse", "promptlayer"}:
        if args.import_format and args.import_format != remote_registry:
            die(
                f"{args.source} requires --format {remote_registry}, not {args.import_format}",
                EXIT_VALIDATION,
            )
        source = load_registry_source(
            args.source,
            prefix=args.prefix,
            label=args.label,
            version=args.registry_version,
            base_url=args.base_url,
        )
    else:
        if args.label or args.registry_version or args.base_url:
            die("--label, --version and --base-url apply only to registry URIs", EXIT_USAGE)
        source = load_import_source(args.source, prefix=args.prefix)
    registry = ws.registry()

    importer = None
    importer_name = args.import_format or remote_registry
    if importer_name:
        importer = registry.get("assay.importers", importer_name)
        if not importer.detect(source):
            die(f"{args.source} is not recognized as {importer_name}", EXIT_VALIDATION)
    else:
        load_errors: list[str] = []
        for name in registry.names("assay.importers"):
            try:
                candidate = registry.get("assay.importers", name)
            except AssayError as exc:
                load_errors.append(f"{name}: {exc}")
                continue
            if candidate.detect(source):
                importer, importer_name = candidate, name
                break
        if importer is None:
            detail = f" ({'; '.join(load_errors)})" if load_errors else ""
            die(f"No installed importer recognizes {args.source}{detail}", EXIT_VALIDATION)

    artifacts = importer.to_promptfiles(source)
    if not artifacts:
        die(f"{importer_name} importer produced no PromptFiles", EXIT_VALIDATION)
    if not all(isinstance(artifact, PromptFile) for artifact in artifacts):
        die(f"{importer_name} importer returned an invalid artifact", EXIT_VALIDATION)

    existing = set(store.list())
    collisions = sorted(artifact.id for artifact in artifacts if artifact.id in existing)
    if collisions and not args.force:
        die(
            "Import would overwrite existing PromptFiles: " + ", ".join(collisions)
            + " (use --force only after reviewing --dry-run)",
            EXIT_FAIL,
        )

    problems: dict[str, list[str]] = {}
    for artifact in artifacts:
        errors = artifact.validate()
        if errors:
            problems[artifact.id] = errors
    if problems:
        if args.json:
            emit(args, {"format": importer_name, "validation_errors": problems})
        else:
            for prompt_id, errors in problems.items():
                output.fail(f"{prompt_id}: " + "; ".join(errors))
        return EXIT_VALIDATION

    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for artifact in artifacts:
        target = store.path_for(artifact.id)
        rows.append({"id": artifact.id, "path": str(target), "evals": len(artifact.evals)})
        for warning in (artifact.data.get("x-import") or {}).get("warnings", []):
            warnings.append({"id": artifact.id, "warning": str(warning)})
        if not args.dry_run:
            store.put(artifact)

    payload = {
        "format": importer_name,
        "source": source.metadata.get("source_uri", str(source.path)),
        "dry_run": bool(args.dry_run),
        "written": 0 if args.dry_run else len(rows),
        "artifacts": rows,
        "warnings": warnings,
    }
    emit(args, payload)
    if not args.json:
        action = "Would write" if args.dry_run else "Imported"
        print(f"{action} {len(rows)} PromptFile(s) from {importer_name}.")
        for row in rows:
            print(f"  {row['id']}  ({row['evals']} eval cases)  {row['path']}")
        for item in warnings:
            output.warn(f"{item['id']}: {item['warning']}")
        if warnings:
            print("  Review x-import warnings before treating migrated evals as equivalent.")
    return EXIT_OK


def cmd_ls(args):
    ws, store, _ = context(args)
    rows = []
    for prompt_id in store.list(prefix=args.prefix):
        try:
            pf = store.get(prompt_id)
        except Exception as exc:
            rows.append({"id": prompt_id, "error": str(exc)})
            continue
        if args.tag and not set(args.tag) & set(pf.tags):
            continue
        if args.status and pf.status != args.status:
            continue
        rows.append({
            "id": pf.id, "version": pf.version, "kind": pf.kind, "status": pf.status,
            "model": pf.model_ref or "-", "tags": ",".join(pf.tags) or "-",
            "evals": len(pf.evals),
        })
    emit(args, {"workspace": ws.name, "count": len(rows), "prompts": rows})
    if not args.json:
        if not rows:
            print("No prompts found. Try 'assay new my/first-prompt'.")
        else:
            table(rows, ["id", "version", "kind", "status", "model", "evals", "tags"])
    return EXIT_OK


def cmd_show(args):
    _, store, _ = context(args)
    pf = resolve_prompt(store, args.id)
    if args.json:
        emit(args, pf.to_dict())
        return EXIT_OK
    if args.raw:
        print(pf.to_text(), end="")
        return EXIT_OK
    heading(f"{pf.id}@{pf.version}")
    kv("name", pf.name)
    kv("description", pf.data.get("description") or "-")
    kv("kind / status", f"{pf.kind} / {pf.status}")
    kv("model", pf.model_ref or "-")
    kv("renderer", pf.renderer_id)
    kv("variables", ", ".join(sorted(pf.template_variables())) or "-")
    kv("capabilities", ", ".join(sorted(pf.required_capabilities)) or "-")
    kv("evals", len(pf.evals))
    kv("guardrails", ", ".join(g.get("type", "?") for g in pf.guardrails) or "-")
    if pf.extensions:
        kv("extensions", ", ".join(pf.extensions))
    if pf.path:
        kv("path", pf.path)
    return EXIT_OK


def cmd_render(args):
    _, store, rt = context(args)
    pf = resolve_prompt(store, args.id)
    variables = {**load_vars_file(args.vars_file), **parse_vars(args.var)}
    rendered = rt.render(pf, variables, model=args.model)
    if args.json:
        emit(args, {"model": rendered.model,
                    "messages": [m.to_dict() for m in rendered.messages],
                    "params": rendered.params})
    else:
        for message in rendered.messages:
            heading(message.role)
            print(message.content)
    return EXIT_OK


def cmd_run(args):
    _, store, rt = context(args)
    pf = resolve_prompt(store, args.id)
    variables = {**load_vars_file(args.vars_file), **parse_vars(args.var)}
    params = parse_vars(args.param) or None
    if args.stream:
        async def consume_stream():
            final = None
            async for event in rt.astream(
                pf,
                variables,
                model=args.model,
                params=params,
                skip_guardrails=args.no_guardrails,
            ):
                if args.json:
                    print(json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")))
                elif event.type == "delta":
                    print(event.delta, end="", flush=True)
                if event.result is not None:
                    final = event.result
            return final

        result = asyncio.run(consume_stream())
        if result is None:
            raise AssayError("stream ended without a completed result")
        if not args.json:
            print()
    else:
        result = rt.run(pf, variables, model=args.model,
                        params=params,
                        skip_guardrails=args.no_guardrails)
    if args.json:
        if not args.stream:
            emit(args, result.to_dict())
    elif not args.stream:
        print(result.text)
    if not args.json and not args.quiet:
        usage = result.completion.usage
        output.dim(
            f"\n─ {result.completion.provider}/{result.completion.model} · "
            f"{usage.input_tokens}→{usage.output_tokens} tok · "
            f"{result.completion.latency_ms}ms · ${result.cost_usd:.6f}"
            + (f" · fallback {result.fallback_used}" if result.fallback_used else "")
            + (f" · stream {result.streaming.get('mode')}" if result.streaming else "")
        )
        for event in result.guardrail_events:
            output.warn(f"guardrail {event['guardrail']}: {event['reason']}")
    return EXIT_OK


def cmd_test(args):
    ws, store, rt = context(args)
    targets = [args.id] if args.id else list(store.list(prefix=args.prefix))
    reports, failed, unverified = [], 0, 0
    for target in targets:
        pf = resolve_prompt(store, target)
        if not pf.evals:
            unverified += 1
            reports.append({
                "prompt_id": pf.id, "prompt_version": pf.version,
                "passed": None, "score": None, "usable": False,
                "score_ci": {
                    "point": None, "low": None, "high": None, "level": 0.95,
                    "usable_cases": 0, "excluded_unverified_cases": 0,
                    "method": "withheld", "reason": "zero usable cases",
                },
                "cases": [], "total_assertions": 0, "failed_assertions": 0,
                "unverified_cases": 0, "total_cost_usd": 0.0,
                "failure_attribution": [],
                "error": "no eval cases defined",
            })
            if args.require_evals:
                failed += 1
            if not args.json:
                output.warn(f"{pf.id}: not checked — no eval cases defined")
            continue

        engine = executor_for(pf, rt)
        if pf.is_agentic:
            report = engine.evaluate(pf, model=args.model)
        elif args.max_workers > 1:
            report = asyncio.run(engine.aevaluate(
                pf,
                model=args.model,
                judge_model=args.judge_model,
                max_concurrency=args.max_workers,
            ))
        else:
            report = engine.evaluate(pf, model=args.model, judge_model=args.judge_model)
        reports.append(report)
        if report["passed"] is False:
            failed += 1
        elif report["passed"] is None:
            unverified += 1
            if args.require_evals:
                failed += 1
        if not args.json:
            mark = (output.PASS if report["passed"] is True else
                    output.FAIL if report["passed"] is False else "?")
            kind = f" [{pf.kind}]" if pf.is_agentic else ""
            score = (f"{report['score']:.2f}" if report["score"] is not None
                     else "not checked")
            print(f"{mark} {pf.id}@{pf.version}{kind}  score={score}  "
                  f"({report['total_assertions'] - report['failed_assertions']}"
                  f"/{report['total_assertions']} assertions)  "
                  f"${report['total_cost_usd']:.4f}")
            interval = report.get("score_ci") or {}
            execution = report.get("execution") or {}
            if not args.quiet and execution.get("mode") == "bounded_concurrent":
                output.dim(
                    f"    execution: {execution['mode']} · "
                    f"≤{execution['max_concurrency']} active case(s) · "
                    f"{execution['wallclock_ms']:.1f}ms"
                )
            if not args.quiet and interval.get("low") is not None:
                output.dim(
                    f"    95% case-cluster CI {interval['low']:.2f}–{interval['high']:.2f} "
                    f"across {interval['usable_cases']} usable case(s)"
                )
            elif not args.quiet and interval.get("reason"):
                output.dim(
                    f"    score interval withheld: {interval['reason']} "
                    f"({interval.get('usable_cases', 0)} usable case(s))"
                )
            for case in report["cases"]:
                if case["passed"]:
                    # Surface trajectory shape even on success — an agent that passes
                    # in nine iterations today and nineteen tomorrow is drifting.
                    if not args.quiet and case.get("tool_calls") is not None:
                        output.dim(
                            f"    ✓ {case['id']}: {case.get('iterations', 0)} iter · "
                            f"{' → '.join(case['tool_calls']) or 'no tools'}"
                        )
                    elif not args.quiet and case.get("cycles") is not None:
                        output.dim(f"    ✓ {case['id']}: {case['cycles']} cycle(s) · "
                                   f"{case.get('status', '')}")
                    continue
                print(f"    ✗ case {case['id']}")
                if case.get("tool_calls") is not None:
                    print(f"        trajectory: {case.get('iterations', 0)} iterations · "
                          f"{' → '.join(case['tool_calls']) or 'no tool calls'} · "
                          f"status={case.get('status')}")
                for r in case.get("results", []):
                    if not r["passed"]:
                        print(f"        {r['evaluator']}: {r['reason']}")
                if case.get("error"):
                    print(f"        error: {case['error']}")
            for item in report.get("failure_attribution", []):
                output.warn(
                    f"attribution {item['component_type']}:{item['component']} — "
                    f"{item['failure_count']} failure(s) in {', '.join(item['cases'])}"
                )

    total_cost = round(sum(r.get("total_cost_usd", 0) for r in reports), 6)
    overall_passed = False if failed else (None if unverified else True)
    summary = {"passed": overall_passed, "prompts": len(reports),
               "failed": failed, "unverified": unverified,
               "total_cost_usd": total_cost, "reports": reports}
    if args.json:
        emit(args, summary)
    else:
        print()
        message = (f"{len(reports) - failed - unverified} passed · {failed} failed · "
                   f"{unverified} not checked · ${total_cost:.4f}")
        (output.fail if failed else output.warn if unverified else output.ok)(message)
    return EXIT_OK if failed == 0 else EXIT_EVAL


def cmd_agent(args):
    """Run a harness and show the whole trajectory, not just the answer."""
    from assay_core import AgentRuntime

    _, store, rt = context(args)
    harness = resolve_prompt(store, args.id)
    if not harness.is_harness:
        die(f"{harness.id!r} is kind {harness.kind!r}, not a harness. Use 'assay run'.", EXIT_USAGE)

    variables = {**load_vars_file(args.vars_file), **parse_vars(args.var)}
    if args.goal:
        variables["goal"] = args.goal

    approver = _make_approver(args)
    live = (not args.json) and (not args.quiet)

    trajectory = AgentRuntime(rt).run(
        harness, variables, model=args.model, approver=approver,
        sandbox_root=args.sandbox, dry_run=args.dry_run,
        on_step=(lambda step: output.render_step(step)) if live else None,
    )

    if args.json:
        emit(args, trajectory.to_dict())
    else:
        output.render_trajectory_summary(trajectory)
    return EXIT_OK if trajectory.status == "completed" else EXIT_EVAL


def cmd_loop(args):
    """Run an outer loop: steps, verification, repeat until the goal is met."""
    from assay_core import LoopRuntime

    _, store, rt = context(args)
    artifact = resolve_prompt(store, args.id)
    if not artifact.is_loop:
        die(f"{artifact.id!r} is kind {artifact.kind!r}, not a loop.", EXIT_USAGE)

    variables = {**load_vars_file(args.vars_file), **parse_vars(args.var)}
    if args.goal:
        variables["goal"] = args.goal
    live = (not args.json) and (not args.quiet)

    run = LoopRuntime(rt).run(
        artifact, variables, model=args.model, max_cycles=args.max_cycles,
        dry_run=args.dry_run,
        on_cycle=(lambda cycle: output.render_cycle(cycle)) if live else None,
    )

    if args.json:
        emit(args, run.to_dict())
    else:
        output.render_loop_summary(run)
    return EXIT_OK if run.goal_met else EXIT_EVAL


def _make_approver(args):
    """Approval gate for tools listed under ``control.require_approval``."""
    if args.yes:
        def approve(call):
            return {"approved": True, "actor": approve.actor,
                    "reason": "CLI --yes approval"}
        approve.actor = args.approver_id or os.getenv("ASSAY_APPROVER_ID") or "unattributed"
        return approve
    if args.json or not sys.stdin.isatty():
        # Non-interactive: deny rather than silently auto-approving. A gate that
        # opens itself when nobody is watching is not a gate.
        def deny_noninteractive(call):
            return {"approved": False, "actor": deny_noninteractive.actor,
                    "reason": "non-interactive approval unavailable"}
        deny_noninteractive.actor = (
            args.approver_id or os.getenv("ASSAY_APPROVER_ID") or "unattributed"
        )
        return deny_noninteractive

    def ask(call):
        output.warn(f"approval required: {call.name}({json.dumps(call.arguments, default=str)[:200]})")
        try:
            approved = input("    allow? [y/N] ").strip().lower() in ("y", "yes")
            return {"approved": approved, "actor": ask.actor, "reason": "interactive CLI"}
        except (EOFError, KeyboardInterrupt):
            return {"approved": False, "actor": ask.actor, "reason": "input interrupted"}

    ask.actor = args.approver_id or os.getenv("ASSAY_APPROVER_ID") or "unattributed"
    return ask


def cmd_lint(args):
    ws, store, _ = context(args)
    root = Path(args.path) if args.path else ws.prompts_root
    files = discover(root)
    problems: list[dict] = []
    policy = ws.policy if args.policy else {}

    for path in files:
        try:
            pf = PromptFile.load(path)
        except AssayError as exc:
            problems.append({"path": str(path), "level": "error", "message": exc.message})
            continue
        for message in pf.validate(strict=not args.schema_only):
            level = "error" if not message.startswith("<root>: '") else "warning"
            problems.append({"path": str(path), "prompt_id": pf.id,
                             "level": level, "message": message})
        problems.extend(_policy_problems(pf, path, policy))

    errors = [p for p in problems if p["level"] == "error"]
    warnings = [p for p in problems if p["level"] == "warning"]
    if args.json:
        emit(args, {"files": len(files), "errors": len(errors),
                    "warnings": len(warnings), "problems": problems})
    else:
        for problem in problems:
            marker = output.FAIL if problem["level"] == "error" else output.WARN
            print(f"{marker} {problem['path']}\n     {problem['message']}")
        print()
        summary = f"{len(files)} files · {len(errors)} errors · {len(warnings)} warnings"
        (output.ok if not errors else output.fail)(summary)

    if errors:
        return EXIT_VALIDATION
    if warnings and args.strict:
        return EXIT_VALIDATION
    return EXIT_OK


def _policy_problems(pf: PromptFile, path: Path, policy: dict) -> list[dict]:
    from assay_core.promptfile import NON_EXECUTABLE_KINDS

    found = []
    if pf.status in (policy.get("forbid_status") or []):
        found.append({"path": str(path), "prompt_id": pf.id, "level": "error",
                      "message": f"policy: status {pf.status!r} is forbidden"})
    if (pf.status in (policy.get("require_evals_for") or [])
            and not pf.evals and pf.kind not in NON_EXECUTABLE_KINDS):
        found.append({"path": str(path), "prompt_id": pf.id, "level": "error",
                      "message": f"policy: status {pf.status!r} requires eval cases"})
    allowed = policy.get("allowed_models")
    if allowed and pf.model_ref and pf.model_ref not in allowed:
        found.append({"path": str(path), "prompt_id": pf.id, "level": "error",
                      "message": f"policy: model {pf.model_ref!r} is not in allowed_models"})

    # An uncalibrated judge produces a number that looks like a measurement and is not.
    # Workspaces gating deploys on judge scores can require the certificate to exist.
    if policy.get("require_calibrated_judge"):
        uses_judge = any(
            a.get("type") == "llm_judge"
            for case in pf.evals for a in (case.get("assert") or [])
        )
        if uses_judge and not pf.data.get("calibration"):
            found.append({
                "path": str(path), "prompt_id": pf.id, "level": "error",
                "message": "policy: uses llm_judge but has no calibration certificate. "
                           "Run 'assay judge calibrate --write', or drop "
                           "require_calibrated_judge.",
            })
    return found


def cmd_diff(args):
    _, store, _ = context(args)
    import difflib

    left = resolve_prompt(store, args.left)
    right = resolve_prompt(store, args.right) if args.right else store.get(left.id)
    diff = list(difflib.unified_diff(
        left.to_text().splitlines(keepends=True),
        right.to_text().splitlines(keepends=True),
        fromfile=f"{left.id}@{left.version}", tofile=f"{right.id}@{right.version}",
    ))
    if args.json:
        emit(args, {"changed": bool(diff), "diff": "".join(diff)})
    elif not diff:
        print("No differences.")
    else:
        output.print_diff("".join(diff))
    return EXIT_OK


def cmd_history(args):
    _, store, _ = context(args)
    entries = store.history(args.id)
    if args.json:
        emit(args, {"id": args.id, "history": entries})
    elif not entries:
        print("No git history (not a repository, or file never committed).")
    else:
        table([{**e, "commit": e.get("commit", "")[:8]} for e in entries],
              ["commit", "date", "author", "message"])
    return EXIT_OK


def cmd_models(args):
    ws, _, _ = context(args)
    catalog = ModelCatalog.autoload(ws.root)
    if args.action == "sync":
        return _models_sync(args, catalog)
    rows = [
        {"ref": f"{m.provider}/{m.id}", "name": m.display_name,
         "context": m.context_window or "-",
         "in$/M": m.input_cost_per_mtok, "out$/M": m.output_cost_per_mtok,
         "capabilities": ",".join(sorted(m.capabilities)) or "-"}
        for m in catalog.all()
        if not args.provider or m.provider == args.provider
    ]
    rows.sort(key=lambda r: r["ref"])
    if args.json:
        emit(args, {"count": len(rows), "models": rows})
    else:
        table(rows, ["ref", "name", "context", "in$/M", "out$/M", "capabilities"])
    return EXIT_OK


#: Where the model catalogue comes from, in preference order.
#:
#: models.dev is the primary because it is purpose-built for exactly this: an MIT-licensed
#: open database of model specifications covering 75+ providers, stored as reviewable TOML
#: and contributed by pull request, with a JSON API. Pricing and context windows move
#: constantly, and a project that hardcodes them is wrong within weeks.
#:
#: OpenRouter is the fallback because it aggregates live routing data across 300+ models,
#: which is a different and complementary view — it knows what is actually servable today.
MODEL_SOURCES = {
    "models.dev": "https://models.dev/api.json",
    "openrouter": "https://openrouter.ai/api/v1/models",
}


def _parse_models_dev(payload: dict, url: str) -> list[dict]:
    """models.dev: ``{provider: {models: {id: {...}}}}``.

    Written tolerantly on purpose. This is a community database that gains fields over
    time, and a sync that hard-fails on an unfamiliar key would break the day someone
    adds one. Anything unreadable is skipped and counted rather than guessed at.
    """
    entries: list[dict] = []
    for provider_id, provider in (payload or {}).items():
        if not isinstance(provider, dict):
            continue
        models = provider.get("models")
        if not isinstance(models, dict):
            continue
        for model_id, model in models.items():
            if not isinstance(model, dict):
                continue
            cost = model.get("cost") or {}
            limit = model.get("limit") or {}
            modalities = model.get("modalities") or {}
            capabilities = set(modalities.get("input") or []) | {"text"}
            if model.get("reasoning"):
                capabilities.add("reasoning")
            if model.get("tool_call"):
                capabilities.add("tools")
            entries.append({
                "id": model_id,
                "provider": provider_id,
                "display_name": model.get("name") or model_id,
                "context_window": int(limit.get("context") or 0),
                "max_output_tokens": int(limit.get("output") or 0),
                # models.dev quotes cost per million tokens already — no scaling.
                "input_cost_per_mtok": float(cost.get("input") or 0),
                "output_cost_per_mtok": float(cost.get("output") or 0),
                "capabilities": sorted(capabilities),
                "released": model.get("release_date") or "",
                "source": url,
            })
    return entries


def _parse_openrouter(payload: dict, url: str) -> list[dict]:
    """OpenRouter: ``{"data": [...]}``, priced per token rather than per million."""
    entries: list[dict] = []
    for item in (payload or {}).get("data", []):
        ref = item.get("id", "")
        provider, _, model_id = ref.partition("/")
        if not model_id:
            continue
        pricing = item.get("pricing") or {}
        entries.append({
            "id": model_id,
            "provider": provider,
            "display_name": item.get("name") or model_id,
            "context_window": item.get("context_length") or 0,
            "max_output_tokens": (item.get("top_provider") or {}).get("max_completion_tokens") or 0,
            "input_cost_per_mtok": float(pricing.get("prompt") or 0) * 1e6,
            "output_cost_per_mtok": float(pricing.get("completion") or 0) * 1e6,
            "capabilities": sorted(
                set((item.get("architecture") or {}).get("input_modalities") or []) | {"text"}
            ),
            "source": url,
        })
    return entries


def _models_sync(args, catalog):
    """Refresh the local catalogue from a public model database.

    Tries models.dev first and falls back to OpenRouter, so a sync still succeeds when one
    source is down — and says which one it used rather than leaving the reader to guess
    where the numbers came from.

    The result is written to ``~/.assay/models.json``. Nothing in the engine hardcodes
    pricing: the catalogue is plain data, which is the whole point. A vendor changing its
    prices should not require a release of this project.
    """
    import httpx

    if args.source:
        # An explicit URL wins, and the parser is chosen by shape rather than by name so
        # a mirror or a pinned snapshot works without extra flags.
        attempts = [("custom", args.source)]
    else:
        attempts = list(MODEL_SOURCES.items())

    entries: list[dict] = []
    used: str | None = None
    problems: list[str] = []

    for name, url in attempts:
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                payload = client.get(url).json()
        except Exception as exc:
            problems.append(f"{name}: {type(exc).__name__}: {exc}")
            continue

        parsed = (
            _parse_openrouter(payload, url)
            if isinstance(payload, dict) and "data" in payload
            else _parse_models_dev(payload, url)
        )
        if parsed:
            entries, used = parsed, url
            break
        problems.append(f"{name}: responded, but no models could be read from the payload")

    if not entries:
        die("Model sync failed.\n  " + "\n  ".join(problems)
            + "\n  The bundled offline catalogue is still in use.", EXIT_PROVIDER)

    providers = sorted({e["provider"] for e in entries})
    target = Path(os.getenv("ASSAY_HOME") or (Path.home() / ".assay")) / "models.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "models": entries,
                "synced_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(),
                "source": used,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ModelCatalog.reset()

    emit(args, {
        "synced": len(entries), "providers": len(providers),
        "path": str(target), "source": used, "problems": problems,
    })
    if not args.json:
        output.ok(f"Synced {len(entries)} models from {len(providers)} providers → {target}")
        print(f"  source: {used}")
        for problem in problems:
            print(f"  fell back after — {problem}")
    return EXIT_OK


def cmd_audit(args):
    """Inspect the run log, or produce a control-mapping report for an assessor."""
    from assay_core.governance import (
        AuditLog,
        aggregate_audit_logs,
        annex_iv_dossier,
        control_report,
    )

    ws, _, _ = context(args)
    config = dict(ws.config.get("governance") or {})
    log = AuditLog(
        config.get("audit_root") or (ws.root / ".assay" / "audit"),
        retention_days=int(config.get("retention_days", 190)),
    )

    if args.action == "stats":
        stats = log.stats()
        emit(args, stats)
        if not args.json:
            heading("Audit log")
            for key in ("records", "artifacts", "total_cost_usd", "oldest", "newest",
                        "retention_days", "path"):
                kv(key, stats.get(key))
            if not stats["records"]:
                output.dim(
                    "\nNothing logged yet. Auditing is off unless assay.yaml sets "
                    "governance.audit: true — an audit log nobody asked for is a "
                    "surprise file in someone's repository."
                )
        return EXIT_OK

    if args.action == "log":
        records = log.read(artifact_id=args.id, limit=args.limit)
        emit(args, {"count": len(records), "records": records})
        if not args.json:
            if not records:
                print("No audit records.")
            else:
                table([{**r, "timestamp": (r.get("timestamp") or "")[:19]} for r in records],
                      ["timestamp", "artifact_id", "kind", "outcome", "model",
                       "cost_usd", "environment"])
        return EXIT_OK

    if args.action == "verify":
        integrity = log.verify_chain()
        emit(args, integrity)
        if not args.json:
            heading("Audit integrity")
            kv("status", integrity["status"])
            kv("hashed records", integrity["hashed_records"])
            kv("legacy unsealed", integrity["legacy_unsealed_records"])
            kv("head", integrity["head_hash"])
            for error in integrity["errors"]:
                output.fail(error)
            output.dim("\n" + integrity["note"])
        return EXIT_OK if integrity["valid"] is True else EXIT_VALIDATION

    if args.action == "aggregate":
        sources: dict[str, AuditLog] = {}
        if args.source:
            for raw in args.source:
                label, separator, path = raw.partition("=")
                if not separator or not label.strip() or not path.strip():
                    die("--source must be LABEL=PATH", EXIT_USAGE)
                label = label.strip()
                if label in sources:
                    die(f"duplicate audit source label: {label}", EXIT_USAGE)
                sources[label] = AuditLog(Path(path.strip()).expanduser())
        else:
            sources["local"] = log
        result = aggregate_audit_logs(sources)
        emit(args, result)
        if not args.json:
            heading("Cross-deployment audit aggregation")
            for key in ("sources", "records", "identified_deployments",
                        "unattributed_records", "total_cost_usd"):
                kv(key, result[key])
            kv("integrity", result["integrity"]["status"])
            if result["duplicate_run_ids"]:
                output.warn(f"{len(result['duplicate_run_ids'])} duplicate run id(s)")
            output.dim("\n" + result["note"])
        return EXIT_OK if result["integrity"]["valid"] is not False else EXIT_VALIDATION

    if args.action == "report":
        report = control_report(ws, log)
        emit(args, report)
        if not args.json:
            heading("Regulatory control mapping")
            kv("generated", report["generated_at"][:19])
            kv("summary", ", ".join(f"{k}: {v}" for k, v in sorted(report["summary"].items())))
            for entry in report["controls"]:
                mark = {"supported": output.PASS, "partial": output.WARN}.get(
                    entry["status"], output.FAIL)
                print(f"\n  {mark}  {entry['control']}")
                print(f"       evidence: {entry['evidence']}")
                print(f"       gap:      {entry['gap']}")
            output.dim("\n" + report["disclaimer"])
        return EXIT_OK

    if args.action == "dossier":
        dossier = annex_iv_dossier(ws, log)
        if args.out:
            target = Path(args.out).expanduser()
            if target.exists() and not args.yes:
                die(f"{target} exists; pass --yes to replace it", EXIT_USAGE)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(dossier, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        emit(args, dossier)
        if not args.json:
            heading("Annex IV evidence dossier")
            kv("workspace", dossier["workspace"])
            kv("artifacts", len(dossier["artifact_inventory"]))
            kv("coverage", ", ".join(
                f"{key}: {value}" for key, value in sorted(dossier["coverage"].items())
            ))
            if args.out:
                kv("written", str(target))
            for item in dossier["sections"]:
                print(f"  {item['annex_item']}. {item['status']:<7} {item['title']}")
            output.dim("\n" + dossier["disclaimer"])
        return EXIT_OK

    if args.action == "prune":
        if not args.yes:
            die("prune deletes audit evidence; pass --yes to confirm", EXIT_USAGE)
        removed = log.prune()
        emit(args, {"files_removed": removed})
        if not args.json:
            output.ok(f"removed {removed} expired monthly log file(s)")
        return EXIT_OK

    return EXIT_USAGE


def cmd_redteam(args):
    """Replay an injection corpus against a harness and report the attack success rate."""
    from assay_core import AgentRuntime, redteam
    from assay_core.redteam import RedTeamError

    _, store, rt = context(args)
    harness = resolve_prompt(store, args.id)
    if not harness.is_harness:
        die(f"{harness.id!r} is kind {harness.kind!r}; red-teaming applies to harnesses.",
            EXIT_USAGE)

    live = (not args.json) and (not args.quiet)
    try:
        report = redteam.run_corpus(
            AgentRuntime(rt), harness,
            corpus=args.corpus,
            variables={**load_vars_file(args.vars_file), **parse_vars(args.var)},
            model=args.model,
            sandbox_root=args.sandbox,
            categories=args.category,
            strategies=args.strategy,
            on_result=(lambda r: output.render_attack(r)) if live else None,
        )
    except RedTeamError as exc:
        die(exc.message, EXIT_USAGE)

    if args.json:
        emit(args, report.to_dict())
    else:
        output.render_redteam_summary(report)

    if not report.usable:
        # No attack executed. Failing loudly beats reporting a flattering 0%.
        return EXIT_EVAL
    if args.max_asr is not None and report.attack_success_rate > args.max_asr:
        return EXIT_EVAL
    return EXIT_OK if report.passed else EXIT_EVAL


def cmd_judge(args):
    """Calibrate an LLM judge against human labels, and certify it — or refuse to."""
    from assay_core import calibration
    from assay_core.calibration import CalibrationError

    ws, store, rt = context(args)

    if args.action == "check":
        prompt = resolve_prompt(store, args.id)
        ok, reason = calibration.is_certified(prompt, max_age_days=args.max_age_days)
        emit(args, {"id": prompt.id, "certified": ok, "reason": reason})
        if not args.json:
            (output.ok if ok else output.fail)(f"{prompt.id}: {reason}")
        return EXIT_OK if ok else EXIT_VALIDATION

    if args.action != "calibrate":
        return EXIT_USAGE

    try:
        cases = calibration.load_labels(args.labels)
    except CalibrationError as exc:
        die(exc.message, EXIT_USAGE)

    judge_prompt = None
    judge_fn = None
    if args.id:
        # Score the cases live with a judge prompt from the library. Without --id, scores
        # are read from the label file, which lets calibration run fully offline.
        judge_prompt = resolve_prompt(store, args.id)
        criteria = judge_prompt.body or judge_prompt.data.get("description", "")
        ask = rt._make_judge(args.model)

        def judge_fn(case):  # noqa: F811
            import json as _json
            import re as _re

            raw = ask(calibration.build_judge_prompt(criteria, case.output))
            cleaned = _re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw.strip())
            payload = _json.loads(cleaned)
            return float(payload.get("score", 0)), str(payload.get("reasoning", ""))[:400]

    try:
        report = calibration.calibrate(
            cases,
            judge=judge_fn,
            judge_id=args.id or "(scores from label file)",
            thresholds=calibration.Thresholds.from_config(
                (ws.config.get("judge") or {}).get("thresholds")
            ),
            resamples=args.resamples,
        )
    except CalibrationError as exc:
        die(exc.message, EXIT_VALIDATION)

    if args.json:
        emit(args, report.to_dict())
    else:
        output.render_calibration(report)

    if args.write and judge_prompt is not None:
        judge_prompt.data["calibration"] = report.certificate()
        store.put(judge_prompt, message=f"calibrate {judge_prompt.id}")
        if not args.json:
            output.dim(f"\ncertificate written to {judge_prompt.path}")

    return EXIT_OK if report.certified else EXIT_VALIDATION


def cmd_memory(args):
    """Inspect, search and prune what agents have remembered.

    Memory a user cannot inspect is memory a user cannot trust, so this is a first-class
    command rather than a debugging aid.
    """
    ws, _, rt = context(args)
    store = rt.registry.get("assay.memory", args.backend)

    if args.action == "stats":
        stats = store.stats(namespace=args.namespace)
        if args.json:
            emit(args, stats)
            return EXIT_OK
        if not stats["namespaces"]:
            print("No memory recorded yet.")
            return EXIT_OK
        rows = [
            {"namespace": name, "records": info["records"],
             "kinds": ", ".join(f"{k}:{v}" for k, v in sorted(info["kinds"].items())),
             "newest": (info["newest"] or "")[:19]}
            for name, info in sorted(stats["namespaces"].items())
        ]
        table(rows, ["namespace", "records", "kinds", "newest"])
        output.dim(f"\n{stats['total']} record(s) total")
        return EXIT_OK

    if args.action == "search":
        if not args.query:
            die("search needs a query: assay memory search 'what happened with X'", EXIT_USAGE)
        hits = store.recall(args.query, namespace=args.namespace or "default",
                            kind=args.kind, limit=args.limit)
        if args.json:
            # `count` for consistency with ls / models / redteam corpus — scripts
            # should not need a different shape per command.
            emit(args, {"query": args.query, "namespace": args.namespace or "default",
                        "count": len(hits),
                        "results": [{**h.to_dict(), "score": h.score} for h in hits]})
            return EXIT_OK
        if not hits:
            print("No matching memories.")
            return EXIT_OK
        for hit in hits:
            heading(f"{hit.kind} · {hit.score:.2f} · {(hit.created_at or '')[:19]}")
            if hit.outcome:
                kv("outcome", hit.outcome)
            if hit.entities:
                kv("entities", ", ".join(hit.entities[:6]))
            print(f"  {hit.content.strip()}")
        return EXIT_OK

    if args.action == "forget":
        if not args.namespace and not args.id and not args.yes:
            die("refusing to wipe every namespace without --yes", EXIT_USAGE)
        removed = store.forget(namespace=args.namespace or "default", record_id=args.id)
        emit(args, {"removed": removed})
        if not args.json:
            output.ok(f"removed {removed} record(s)")
        return EXIT_OK

    return EXIT_USAGE


def cmd_tokens(args):
    """Report what this library costs a client's context, tier by tier."""
    from assay_core import disclosure

    ws, store, _ = context(args)
    budget = disclosure.DisclosureBudget.from_config(
        {**(ws.config.get("disclosure") or {}),
         **({"max_tokens": args.budget} if args.budget else {})}
    )
    prompts = []
    for prompt_id in store.list():
        try:
            prompts.append(store.get(prompt_id))
        except Exception:
            continue

    report = disclosure.workspace_report(prompts, budget=budget)
    if args.json:
        emit(args, report)
        return EXIT_OK

    index = report["index"]
    heading("Context cost")
    kv("prompts", report["prompts"])
    kv("tier-1 index", f"{index['index_tokens']:,} tokens ({index['included']} listed)")
    kv("without tiering", f"{index['full_tokens']:,} tokens")
    kv("saved", f"{index['saved_tokens']:,} tokens ({index['saving_ratio']:.0%})")
    kv("per prompt", f"{index['tokens_per_entry']} tokens")
    kv("budget", f"{index['budget_tokens']:,} tokens")

    if index.get("namespaces"):
        kv("namespaces", ", ".join(f"{k} ({v})" for k, v in sorted(index["namespaces"].items())))
    if index["omitted"]:
        output.warn(
            f"{len(index['omitted'])} prompt(s) omitted from the tier-1 index — budget "
            f"reached. Clients see the namespace map above and reach the rest via search. "
            f"Raise the budget with --budget or 'disclosure.max_tokens' in assay.yaml."
        )
    if index["truncated_summaries"]:
        output.warn(
            f"{len(index['truncated_summaries'])} description(s) truncated at "
            f"{budget.max_summary_chars} chars: {', '.join(index['truncated_summaries'][:5])}"
        )
    if report["heaviest"]:
        heading("Heaviest prompts (tier-2)")
        table(report["heaviest"], ["id", "tier1_tokens", "tier2_tokens"])
    output.dim(
        "\nEstimates at ~4 chars/token. Exact counts need a provider tokenizer; "
        "this errs high on purpose."
    )
    return EXIT_OK


def cmd_plugins(args):
    ws, _, _ = context(args)
    inventory = ws.registry().describe()
    if args.json:
        emit(args, inventory)
        return EXIT_OK
    for group, records in inventory.items():
        if not records:
            continue
        heading(group)
        table(records, ["name", "target", "source", "distribution", "error"])
    return EXIT_OK


def cmd_optimize(args):
    """Generate, independently evaluate, and optionally promote one prompt rewrite."""
    _, store, rt = context(args)
    prompt = resolve_prompt(store, args.id)
    if prompt.kind != "prompt":
        die("reflective optimization currently supports kind: prompt", EXIT_USAGE)

    baseline = rt.evaluate(prompt, model=args.model)
    optimizer = rt.registry.get("assay.optimizers", args.optimizer)
    rewrite_model = args.rewrite_model or args.model or rt.default_model
    rewrite_cost = 0.0

    def rewrite(request: str):
        nonlocal rewrite_cost
        rewrite_prompt = PromptFile(
            data={
                "promptfile": 1,
                "id": "system/reflective-optimizer",
                "engine": {"template": "none"},
                "model": {"primary": rewrite_model, "params": {"temperature": 0}},
            },
            body=request,
        )
        result = rt.run(rewrite_prompt, {}, model=rewrite_model)
        rewrite_cost += result.cost_usd
        return result.text, result.cost_usd

    optimized = optimizer.optimize(
        prompt,
        dataset=baseline.get("cases") or [],
        budget={"rewrite": rewrite},
    )
    candidate = optimized["candidate"]
    candidate_report = rt.evaluate(candidate, model=args.model)
    baseline_score = baseline.get("score")
    candidate_score = candidate_report.get("score")
    usable = bool(baseline.get("usable") and candidate_report.get("usable"))
    improved = (
        candidate_score > baseline_score
        if usable and baseline_score is not None and candidate_score is not None
        else None
    )

    written = False
    if args.write and improved is True:
        store.put(candidate, message=f"optimize {prompt.id} with {args.optimizer}")
        written = True

    report = {
        "id": prompt.id,
        "optimizer": args.optimizer,
        "rewrite_model": rewrite_model,
        "baseline": {
            "score": baseline_score,
            "score_ci": baseline.get("score_ci"),
            "usable": baseline.get("usable"),
            "failed_assertions": baseline.get("failed_assertions"),
            "cost_usd": baseline.get("total_cost_usd", 0.0),
        },
        "candidate": {
            "score": candidate_score,
            "score_ci": candidate_report.get("score_ci"),
            "usable": candidate_report.get("usable"),
            "failed_assertions": candidate_report.get("failed_assertions"),
            "cost_usd": candidate_report.get("total_cost_usd", 0.0),
            "version": candidate.version,
            "body": candidate.body,
        },
        "improved": improved,
        "score_delta": (
            round(candidate_score - baseline_score, 6)
            if improved is not None else None
        ),
        "rationale": optimized.get("rationale", ""),
        "rewrite_cost_usd": round(rewrite_cost, 8),
        "total_cost_usd": round(
            float(baseline.get("total_cost_usd", 0.0))
            + float(candidate_report.get("total_cost_usd", 0.0))
            + rewrite_cost,
            8,
        ),
        "written": written,
        "write_note": (
            "promoted because the measured score improved"
            if written else
            "not written: before/after evaluation was not usable"
            if improved is None else
            "not written: candidate did not improve the measured score"
            if args.write else
            "dry run; pass --write to promote an improving candidate"
        ),
    }
    if args.json:
        emit(args, report)
    else:
        heading(f"Optimize {prompt.id}")
        kv("baseline", "not measured" if baseline_score is None else f"{baseline_score:.1%}")
        kv("candidate", "not measured" if candidate_score is None else f"{candidate_score:.1%}")
        kv("delta", "withheld" if report["score_delta"] is None
           else f"{report['score_delta']:+.1%}")
        kv("total cost", f"${report['total_cost_usd']:.6f}")
        (output.ok if written else output.warn)(report["write_note"])

    if args.write and improved is not True:
        return EXIT_EVAL
    if args.require_improvement and improved is not True:
        return EXIT_EVAL
    return EXIT_OK


def cmd_tools(args):
    """Pin or verify the exact tool metadata offered to an agent harness."""
    from assay_core import AgentRuntime, provenance

    _, store, rt = context(args)
    harness = resolve_prompt(store, args.id)
    if not harness.is_harness:
        die(f"{harness.id!r} is not an agent harness", EXIT_USAGE)

    harness_config = dict(harness.data.get("harness") or {})
    declarations, _ = AgentRuntime(rt)._resolve_tools(harness, harness_config)
    control = dict(harness_config.get("control") or {})

    if args.check:
        pinned = control.get("pin_tools")
        problems, current = provenance.verify_tools(
            declarations, pinned if isinstance(pinned, dict) else {}, strict=True
        )
        report = {
            "id": harness.id,
            "checked": True,
            "updated": False,
            "valid": not problems,
            "fingerprints": current,
            "problems": problems,
        }
        if args.json:
            emit(args, report)
        elif problems:
            output.fail(f"tool pins for {harness.id}")
            for problem in problems:
                print(f"     {problem}")
        else:
            output.ok(f"tool pins for {harness.id} ({len(current)} tool(s))")
        return EXIT_OK if not problems else EXIT_POLICY

    problems, current = provenance.verify_tools(declarations, None)
    if problems and not args.allow_suspicious:
        report = {
            "id": harness.id,
            "checked": True,
            "updated": False,
            "valid": False,
            "fingerprints": current,
            "problems": problems,
        }
        if args.json:
            emit(args, report)
        else:
            output.fail(f"refusing to pin suspicious tool metadata for {harness.id}")
            for problem in problems:
                print(f"     {problem}")
            output.warn("Review the declarations, or explicitly use --allow-suspicious.")
        return EXIT_POLICY

    control["pin_tools"] = current
    harness_config["control"] = control
    harness.data["harness"] = harness_config
    store.put(harness)
    report = {
        "id": harness.id,
        "checked": True,
        "updated": True,
        "valid": not problems,
        "fingerprints": current,
        "problems": problems,
    }
    if args.json:
        emit(args, report)
    else:
        output.ok(f"pinned {len(current)} tool(s) for {harness.id}")
        for name, fingerprint in sorted(current.items()):
            print(f"     {name}: {fingerprint}")
    return EXIT_OK


def cmd_spec(args):
    if args.action == "show":
        from assay_core.promptfile import load_schema

        emit(args, load_schema(), force=True)
        return EXIT_OK
    failures = []
    for target in args.files:
        for path in ([Path(target)] if Path(target).is_file() else discover(target)):
            try:
                errs = PromptFile.load(path).validate()
            except AssayError as exc:
                errs = [exc.message]
            if errs:
                failures.append({"path": str(path), "errors": errs})
                if not args.json:
                    output.fail(str(path))
                    for e in errs:
                        print(f"     {e}")
            elif not args.json:
                output.ok(str(path))
    if args.json:
        emit(args, {"valid": not failures, "failures": failures})
    return EXIT_VALIDATION if failures else EXIT_OK


def cmd_mcp(args):
    try:
        from assay_mcp.server import main as mcp_main
    except ImportError:
        die("MCP server not installed. Run: pip install assay-mcp", EXIT_FAIL)
    return mcp_main(transport=args.transport, host=args.host, port=args.port) or EXIT_OK


def cmd_serve(args):
    try:
        import uvicorn
        from assay_cli.proxy import create_proxy_app
    except ImportError:
        die("HTTP proxy dependencies not installed. Run: pip install 'assay-cli[serve]'", EXIT_FAIL)

    try:
        loopback = args.host.lower() == "localhost" or ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = False
    if not loopback and not os.getenv("ASSAY_PROXY_TOKEN"):
        die(
            "Refusing a non-loopback proxy without ASSAY_PROXY_TOKEN. "
            "Set a bearer token or bind to 127.0.0.1.",
            EXIT_USAGE,
        )
    uvicorn.run(create_proxy_app(workspace=args.workspace), host=args.host, port=args.port)
    return EXIT_OK


def cmd_version(args):
    payload = {"cli": CLI_VERSION, "core": CORE_VERSION, "spec": "promptfile-v1",
               "python": sys.version.split()[0]}
    emit(args, payload, force=True)
    return EXIT_OK


def cmd_agents(args):
    """Write AGENTS.md so coding agents can discover this workspace's prompts.

    AGENTS.md is stewarded by the Agentic AI Foundation and read natively by Codex,
    Cursor, Copilot, Gemini CLI, Aider, goose, Zed, Windsurf and others. A workspace full
    of tested prompts is invisible to an agent that does not know they exist, and a
    hand-written index goes stale the moment someone adds a file.
    """
    from assay_core import agentsmd

    ws, store, _ = context(args)
    artifacts = []
    for prompt_id in store.list():
        try:
            artifacts.append(store.get(prompt_id))
        except Exception:
            continue

    if args.action == "show" or args.stdout:
        block = agentsmd.generate(
            artifacts,
            workspace_name=ws.config.get("name") or ws.root.name,
            prompts_dir=str(ws.config.get("prompts") or "prompts").lstrip("./"),
        )
        if args.json:
            emit(args, {"content": block})
        else:
            print(block)
        return EXIT_OK

    written = agentsmd.write(
        ws.root,
        artifacts,
        targets=args.target or ["agents"],
        workspace_name=ws.config.get("name") or ws.root.name,
        prompts_dir=str(ws.config.get("prompts") or "prompts").lstrip("./"),
    )

    if args.json:
        emit(args, {"written": written, "artifacts": len(artifacts)})
        return EXIT_OK

    for entry in written:
        verb = "created" if entry["created"] else "updated"
        print(f"  {verb} {entry['file']}  ({len(artifacts)} artifacts indexed)")
        if entry["preserved_existing"]:
            print("    existing content kept; the generated block was appended")
    print("\n  Coding agents that read AGENTS.md will now find these prompts.")
    print("  Re-run after adding or removing artifacts.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

SAMPLE_PROMPT = """---
promptfile: 1
id: demo/hello
name: Hello
description: A starter prompt. Delete me once you have your own.
version: 1
kind: prompt
status: draft
tags: [demo]
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required: [name]
    properties:
      name: { type: string }
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
  - id: greets
    input: { name: World }
    assert:
      - { type: contains, value: World }
---

Greet {{ name }} in one warm sentence.
"""


def build_parser() -> argparse.ArgumentParser:
    # Global flags live on a parent parser so they are accepted both before and
    # after the subcommand — `assay --json ls` and `assay ls --json` both work.
    # SUPPRESS defaults so a flag given before the subcommand is not clobbered by the
    # subparser's own default when it re-parses the same option.
    globals_parser = argparse.ArgumentParser(add_help=False)
    globals_parser.add_argument(
        "-W", "--workspace", default=argparse.SUPPRESS,
        help="workspace root (default: search upward)",
    )
    globals_parser.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS,
        help="machine-readable output",
    )
    globals_parser.add_argument(
        "--no-color", action="store_true", default=argparse.SUPPRESS,
        help="disable ANSI colour",
    )

    parser = argparse.ArgumentParser(
        prog="assay",
        description="Assay — git-native prompt engineering.",
        epilog="Docs: https://github.com/BaijayantaRoy/Assay",
        parents=[globals_parser],
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command")

    def add(name, func, help_text, **kwargs):
        kwargs.setdefault("parents", [globals_parser])
        p = sub.add_parser(name, help=help_text, **kwargs)
        p.set_defaults(func=func)
        return p

    p = add("init", cmd_init, "create a workspace here")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--name")
    p.add_argument("--from", dest="from_url",
                   help="HTTPS PromptFile or /v1/export URL")
    p.add_argument("--dry-run", action="store_true",
                   help="download, validate, and report conflicts without writing")
    p.add_argument("--force", action="store_true",
                   help="replace conflicting PromptFile ids after review")
    p.add_argument("--allow-local-url", action="store_true",
                   help="allow a controlled loopback/private test server")

    p = add("new", cmd_new, "scaffold a new prompt")
    p.add_argument("id")
    p.add_argument("--name")
    p.add_argument("--description")
    p.add_argument("--kind", default="prompt")
    p.add_argument("--model")
    p.add_argument("--body")
    p.add_argument("--tag", action="append")
    p.add_argument("--force", action="store_true")

    p = add("import", cmd_import, "migrate a foreign prompt/eval configuration")
    p.add_argument(
        "source",
        help="foreign file, langfuse://prompt-name, or promptlayer://prompt-name",
    )
    p.add_argument("--format", dest="import_format", help="importer id (auto-detected by default)")
    p.add_argument("--prefix", default="imported", help="PromptFile id prefix")
    p.add_argument("--dry-run", action="store_true", help="validate and report without writing")
    p.add_argument("--force", action="store_true", help="overwrite colliding PromptFile ids")
    selector = p.add_mutually_exclusive_group()
    selector.add_argument("--label", help="remote registry deployment/release label")
    selector.add_argument(
        "--version", dest="registry_version", type=int, help="remote registry version"
    )
    p.add_argument("--base-url", help="HTTPS registry origin (or HTTP loopback for testing)")

    p = add("ls", cmd_ls, "list prompts")
    p.add_argument("--prefix")
    p.add_argument("--tag", action="append")
    p.add_argument("--status")

    p = add("show", cmd_show, "show one prompt")
    p.add_argument("id")
    p.add_argument("--raw", action="store_true", help="print the file verbatim")

    p = add("render", cmd_render, "render without calling a model")
    p.add_argument("id")
    p.add_argument("-v", "--var", action="append", metavar="K=V")
    p.add_argument("-f", "--vars-file")
    p.add_argument("-m", "--model")

    p = add("run", cmd_run, "render and execute against a model")
    p.add_argument("id")
    p.add_argument("-v", "--var", action="append", metavar="K=V")
    p.add_argument("-f", "--vars-file")
    p.add_argument("-m", "--model")
    p.add_argument("-p", "--param", action="append", metavar="K=V")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument(
        "--stream", action="store_true",
        help="stream text deltas; with --json, emit newline-delimited stream events",
    )
    p.add_argument("--no-guardrails", action="store_true")

    p = add("agent", cmd_agent, "run a harness and show its trajectory")
    p.add_argument("id")
    p.add_argument("-v", "--var", action="append", metavar="K=V")
    p.add_argument("-f", "--vars-file")
    p.add_argument("-g", "--goal", help="the goal for this run")
    p.add_argument("-m", "--model")
    p.add_argument("--sandbox", help="root directory tools are confined to")
    p.add_argument("--dry-run", action="store_true",
                   help="add the read_only controller: show what it would do")
    p.add_argument("--yes", action="store_true", help="auto-approve gated tool calls")
    p.add_argument("--approver-id", help="identity recorded beside approval decisions")
    p.add_argument("-q", "--quiet", action="store_true", help="summary only, no live steps")

    p = add("loop", cmd_loop, "run an outer loop until its goal verifies")
    p.add_argument("id")
    p.add_argument("-v", "--var", action="append", metavar="K=V")
    p.add_argument("-f", "--vars-file")
    p.add_argument("-g", "--goal")
    p.add_argument("-m", "--model")
    p.add_argument("-n", "--max-cycles", type=int)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")

    p = add("test", cmd_test, "run embedded evals for prompts, harnesses and loops (CI gate)")
    p.add_argument("id", nargs="?")
    p.add_argument("--prefix")
    p.add_argument("-m", "--model")
    p.add_argument("--judge-model")
    p.add_argument(
        "--max-workers", type=bounded_workers, default=1, metavar="N",
        help="bounded concurrent eval cases for kind: prompt (1-32; default: 1)",
    )
    p.add_argument("-q", "--quiet", action="store_true",
                   help="hide per-case trajectory lines on success")
    p.add_argument("--require-evals", action="store_true",
                   help="fail prompts that define no eval cases")

    p = add("optimize", cmd_optimize, "rewrite a prompt and gate promotion on measured gain")
    p.add_argument("id")
    p.add_argument("--optimizer", default="reflective")
    p.add_argument("-m", "--model", help="model override for before/after evaluation")
    p.add_argument("--rewrite-model", help="model used to propose the strict JSON rewrite")
    p.add_argument("--write", action="store_true",
                   help="promote only when the independently measured score improves")
    p.add_argument("--require-improvement", action="store_true",
                   help="exit 4 unless a usable positive score delta was measured")

    p = add("lint", cmd_lint, "validate schema, style, and workspace policy")
    p.add_argument("path", nargs="?")
    p.add_argument("--strict", action="store_true", help="treat warnings as errors")
    p.add_argument("--schema-only", action="store_true")
    p.add_argument("--policy", action="store_true", help="enforce assay.yaml policy block")

    p = add("diff", cmd_diff, "diff two prompts or versions")
    p.add_argument("left")
    p.add_argument("right", nargs="?")

    p = add("history", cmd_history, "git history for a prompt")
    p.add_argument("id")

    p = add("models", cmd_models, "list or sync the model catalogue")
    p.add_argument("action", nargs="?", default="ls", choices=["ls", "sync"])
    p.add_argument("--provider")
    p.add_argument("--source", help="catalogue URL for 'sync'")

    p = add("audit", cmd_audit, "run log and regulatory control mapping")
    p.add_argument("action", nargs="?", default="stats",
                   choices=["stats", "log", "verify", "aggregate", "report", "dossier", "prune"])
    p.add_argument("--id", help="filter the log to one artifact")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--source", action="append", metavar="LABEL=PATH",
                   help="audit root to aggregate; repeatable")
    p.add_argument("--out", help="write a dossier JSON file")
    p.add_argument("--yes", action="store_true",
                   help="confirm a destructive prune or replace an existing dossier")

    p = add("redteam", cmd_redteam, "replay an injection corpus against a harness")
    p.add_argument("id")
    p.add_argument("-c", "--corpus", help="path to a corpus jsonl (default: shipped v1)")
    p.add_argument("--category", action="append",
                   help="restrict to a category, repeatable")
    p.add_argument("--strategy", action="append",
                   choices=["static", "sequence", "adaptive"],
                   help="restrict to a delivery strategy, repeatable")
    p.add_argument("-v", "--var", action="append", metavar="K=V")
    p.add_argument("-f", "--vars-file")
    p.add_argument("-m", "--model", help="use a real model to test susceptibility, not just defences")
    p.add_argument("--sandbox")
    p.add_argument("--max-asr", type=float,
                   help="fail above this attack success rate (0.0 = any success fails)")
    p.add_argument("-q", "--quiet", action="store_true")

    p = add("judge", cmd_judge, "calibrate an LLM judge against human labels")
    p.add_argument("action", choices=["calibrate", "check"])
    p.add_argument("id", nargs="?", help="judge prompt id (omit to use scores in the label file)")
    p.add_argument("-l", "--labels", help="path to a *.labels.jsonl file")
    p.add_argument("-m", "--model")
    p.add_argument("--resamples", type=int, default=1000, help="bootstrap resamples")
    p.add_argument("--write", action="store_true",
                   help="write the certificate back into the judge PromptFile")
    p.add_argument("--max-age-days", type=int, default=180,
                   help="certificate expiry for 'check'")

    p = add("memory", cmd_memory, "inspect what agents have remembered")
    p.add_argument("action", nargs="?", default="stats", choices=["stats", "search", "forget"])
    p.add_argument("query", nargs="?")
    p.add_argument("-n", "--namespace")
    p.add_argument("--kind", choices=["episodic", "semantic"])
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--id", help="record id, for 'forget'")
    p.add_argument("--backend", default="jsonl")
    p.add_argument("--yes", action="store_true", help="confirm a destructive forget")

    p = add("tokens", cmd_tokens, "report the context cost of this library")
    p.add_argument("--budget", type=int, help="override the tier-1 token budget")

    p = add("plugins", cmd_plugins, "inventory installed plugins")
    p.add_argument("action", nargs="?", default="ls", choices=["ls"])

    p = add("tools", cmd_tools, "pin or verify an agent harness's tool metadata")
    p.add_argument("action", choices=["pin"])
    p.add_argument("id", help="agent harness id or PromptFile path")
    p.add_argument("--check", action="store_true", help="verify pins without writing")
    p.add_argument(
        "--allow-suspicious", action="store_true",
        help="pin metadata flagged as injection-shaped after explicit review",
    )

    p = add("spec", cmd_spec, "validate files against the PromptFile schema")
    p.add_argument("action", choices=["validate", "show"])
    p.add_argument("files", nargs="*", default=["."])

    p = add("agents", cmd_agents, "write AGENTS.md so coding agents can find your prompts")
    p.add_argument("action", choices=["init", "show"], nargs="?", default="init")
    p.add_argument(
        "--target", action="append", choices=sorted(agentsmd.TARGETS),
        help="which file to write; repeatable. Default: agents (AGENTS.md). "
             "Use --target claude for Claude Code, which reads CLAUDE.md instead.",
    )
    p.add_argument("--stdout", action="store_true",
                   help="print the block instead of writing any file")

    p = add("mcp", cmd_mcp, "run the MCP server")
    p.add_argument("--transport", default="stdio", choices=["stdio", "http"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)

    p = add("serve", cmd_serve, "run the OpenAI-compatible PromptFile proxy")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument(
        "--proxy", action="store_true",
        help="explicit compatibility flag; the packaged server is the bounded prompt proxy",
    )

    add("version", cmd_version, "print version information")
    return parser


def main(argv: list[str] | None = None) -> int:
    output.configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    # Normalise the SUPPRESS-defaulted globals so command functions can rely on them.
    for flag, default in (("json", False), ("no_color", False), ("workspace", None)):
        if not hasattr(args, flag):
            setattr(args, flag, default)

    if args.no_color or os.getenv("NO_COLOR"):
        output.disable_color()
    if args.version:
        return cmd_version(args)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE

    try:
        return args.func(args) or EXIT_OK
    except AssayError as exc:
        if args.json:
            print(json.dumps({"error": exc.to_dict()}, indent=2))
        else:
            output.fail(f"{exc.code}: {exc}")
        return EXIT_PROVIDER if exc.code.startswith("assay.provider") else EXIT_FAIL
    except KeyboardInterrupt:
        output.warn("interrupted")
        return 130
    except BrokenPipeError:  # e.g. `assay ls | head`
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
