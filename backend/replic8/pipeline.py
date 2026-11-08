"""Onboarding (F1) and self-healing (F2): the steps that turn legacy code into published tools.

onboard:  fetch code -> build in sandbox -> extract symbols -> Nemotron proposes ->
          contract tests in sandbox -> publish passing operations
heal:     fetch new code -> build -> diff -> Nemotron repairs -> replay recorded
          contract cases (identical outputs required) -> save new version

Every legacy run goes through Sandbox.run (via Executor or Sandbox.build) (PRD
section 7). Progress is reported through the event log, which the dashboard reads.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator

from .config import Settings
from .contracts import replay_contract, run_contract
from .events import EventLog
from .executor import Executor, repo_key
from .extract import extract_symbols, language_of, program_symbols
from .generate import JsonModel, heal as model_heal, propose
from .guard import Symbol
from .ingest import Checkout, IngestError
from .models import MODES, NAME, Access, ContractCase, ContractTestResult, Operation, Tier, WrapperVersion
from .prompts import source_diff
from .registry import Registry, RegistryError
from .runtimes import RUNTIMES, argv_for, callable_symbols, cli_exe
from .sandbox import FunctionMissing, OutputSchemaError, Sandbox
from .sources import SourceError, canonical_url, fetch, latest_commit

log = logging.getLogger("replic8.pipeline")
HEAL_TRIGGERS = (OutputSchemaError, FunctionMissing)


class PipelineError(Exception):
    """Safe to show to an admin: no code, stderr, or model output."""


@dataclass
class HealOutcome:
    status: str               # "saved", "failed", "skipped"
    version: int | None
    detail: str


class Pipeline:
    def __init__(self, settings: Settings, registry: Registry, sandbox: Sandbox, executor: Executor,
                 model: JsonModel | None, events: EventLog,
                 heal_cooldown_s: float = 60.0):
        self.settings = settings
        self.registry = registry
        self.sandbox = sandbox
        self.executor = executor
        self.model = model
        self.events = events
        self.repos_root = settings.data_dir / "repos"
        self.builds_root = sandbox.builds_root
        self.heal_cooldown_s = heal_cooldown_s
        self._locks: dict[str, threading.Lock] = {}
        self._last_heal: dict[str, float] = {}
        self._guard = threading.Lock()

    # ---------- shared steps ----------

    def _lock(self, system: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(system, threading.Lock())

    def busy(self, system: str) -> bool:
        return self._lock(system).locked()

    def _fetch(self, url: str) -> Checkout:
        try:
            return fetch(url, self.repos_root, local_root=self.settings.local_repo_root,
                         max_bytes=self.settings.max_repo_bytes, max_files=self.settings.max_repo_files,
                         timeout_s=self.settings.clone_timeout_s)
        except IngestError as exc:
            raise PipelineError(str(exc)) from exc

    def _runtime(self, checkout: Checkout):
        supported = [lang for lang in checkout.languages if lang in RUNTIMES]
        if not supported:
            found = ", ".join(checkout.languages) or "none"
            raise PipelineError(f"no supported language yet (found: {found[:80]})")
        return RUNTIMES[supported[0]]

    def _build(self, checkout: Checkout, runtime) -> None:
        out = self.builds_root / repo_key(checkout.url) / checkout.commit
        if out.is_dir() and any(out.iterdir()):
            return
        try:
            result = self.sandbox.build(runtime.image, checkout.path, out, list(runtime.build_argv))
        except FileNotFoundError:
            raise PipelineError("the sandbox is unavailable (is Docker installed and running?)") from None
        if not result.ok:
            raise PipelineError("legacy code did not compile in the sandbox")

    def _symbols(self, checkout: Checkout, system: str, mode: str = "auto") -> list[Symbol]:
        """What the model may wrap: functions, command-line programs, or both (mode "auto" takes whatever exists)."""
        symbols, partial = extract_symbols(checkout.path)
        if partial:
            log.info("partly parsed files: %s", ", ".join(partial[:10]))
        funcs = callable_symbols(checkout.path, symbols) if mode != "programs" else []
        progs = self._programs(checkout) if mode != "functions" else []
        found = funcs + progs
        if not found:
            hint = ""
            if mode == "functions" and program_symbols(checkout.path):
                hint = " (it has command-line programs; change the mode)"
            if mode == "programs" and callable_symbols(checkout.path, symbols):
                hint = " (it has functions; change the mode)"
            what = {"functions": "callable functions", "programs": "command-line programs"}.get(
                mode, "callable functions or command-line programs")
            raise PipelineError(f"no {what} found in the legacy code{hint}")
        read_as = "functions and programs" if funcs and progs else "functions" if funcs else "programs"
        self.events.add("mode_detected", system=system, detail=f"{len(funcs)} functions, {len(progs)} programs: reading as {read_as}"
                        + (f" (mode: {mode})" if mode != "auto" else ""))
        return found

    def _programs(self, checkout: Checkout) -> list[Symbol]:
        """Command-line programs, each with what it prints for --help (run in the sandbox, shown to the model as data)."""
        programs = []
        build = self.executor.builds_root / repo_key(checkout.url) / checkout.commit
        for sym in program_symbols(checkout.path):
            exe = cli_exe(sym.file)
            help_text = ""
            if exe:
                try:
                    res = self.sandbox.run(RUNTIMES[language_of(PurePosixPath(sym.file))].image, checkout.path,
                                           exe + ["--help"], b"", build_dir=build if build.is_dir() else None)
                    raw = (res.stdout or b"")[:2000].decode("utf-8", "replace")
                    help_text = "".join(c for c in raw if c in "\n\t" or " " <= c < "\x7f").strip()
                except Exception:  # noqa: BLE001 - help is optional context; the contract tests are the real gate
                    log.info("could not read --help for %s", sym.file)
            programs.append(replace(sym, help=help_text))
        return programs

    def _model(self) -> JsonModel:
        if self.model is None:
            raise PipelineError("Nemotron is not configured (NVIDIA_API_KEY, REPLIC8_NEMOTRON_MODEL)")
        return self.model

    # ---------- onboarding ----------

    def onboard(self, system: str, repo_url: str,
                examples: dict[str, list[dict[str, Any]]] | None = None,
                known_values: dict[str, list[str]] | None = None, mode: str = "auto") -> WrapperVersion:
        """Turn a legacy repo into published, tested operations under namespace `system`."""
        if not NAME.match(system):
            raise PipelineError("system name must match ^[a-z][a-z0-9_]{0,31}$")
        if mode not in MODES:
            raise PipelineError("mode must be auto, functions or programs")
        try:
            canonical_url(repo_url, self.settings.local_repo_root)
        except IngestError as exc:
            raise PipelineError(str(exc)) from exc
        if not self._lock(system).acquire(blocking=False):
            raise PipelineError(f"{system} is already being processed")
        try:
            self.events.add("onboard_started", system=system)
            try:
                version = self._onboard(system, repo_url, examples or {}, known_values or {}, mode)
            except (PipelineError, RegistryError) as exc:
                self.events.add("onboard_failed", system=system, detail=str(exc))
                raise PipelineError(str(exc)) from exc
            except Exception as exc:  # noqa: BLE001 - the dashboard must never wait on a silent failure
                log.exception("onboarding %s hit an unexpected error", system)
                self.events.add("onboard_failed", system=system, detail="unexpected error, see the gateway log")
                raise PipelineError("unexpected error") from exc
            self.events.add("onboarded", system=system, version=version.version)
            self.events.add("published", system=system, version=version.version,
                            operations=len(version.operations), rejected=len(version.rejected))
            return version
        finally:
            self._lock(system).release()

    def _onboard(self, system: str, repo_url: str, examples: dict[str, list[dict[str, Any]]],
                 known_values: dict[str, list[str]], mode: str) -> WrapperVersion:
        def stage(name: str) -> None:  # the dashboard shows where an import is, or stopped
            self.events.add("onboard_stage", system=system, detail=name)

        stage("fetch")
        checkout = self._fetch(repo_url)
        stage("detect")
        runtime = self._runtime(checkout)
        stage("build")
        self._build(checkout, runtime)
        stage("extract")
        symbols = self._symbols(checkout, system, mode)
        stage("propose")
        gen = propose(self._model(), namespace=system, tier=Tier.parsed, repo_root=checkout.path,
                      image=runtime.image, argv_for=argv_for, symbols=symbols)

        candidates: list[Operation] = []
        tests: dict[str, ContractTestResult] = {}
        cases: dict[str, list[ContractCase]] = {}
        rejected = dict(gen.rejected)
        stage("test")
        for op in gen.accepted:
            if op.access is Access.write and op.tool not in self.settings.write_allowlist:
                rejected[op.tool] = "write operation: not tested or published in v1 (FR-13)"
                continue
            known = _usable_known_inputs(op, known_values)
            given = known + [e for e in examples.get(op.name, []) + examples.get(op.tool, []) if isinstance(e, dict)]
            fitted = fit_input_schema(op.input_schema, given)
            if fitted is None:
                rejected[op.tool] = "input schema does not fit the supplied example inputs (type or fields differ)"
                continue
            if fitted != op.input_schema:
                op = op.model_copy(update={"input_schema": fitted})
                self.events.add("schema_adjusted", system=system, tool=op.tool,
                                detail="model input rules rejected real examples; loosened to fit them")
            inputs = given + _valid_inputs(op, gen.examples.get(op.tool, []))
            run = run_contract(self.executor, op, checkout.url, checkout.commit, inputs, learn_schema=True)
            tests[op.tool], cases[op.tool] = run.result, run.cases
            if run.output_schema is not None:
                # Publish what the legacy program really returns, not the model's guess.
                op = op.model_copy(update={"output_schema": run.output_schema})
            candidates.append(op)
            if not run.result.passed:
                self.events.add("contract_failed", system=system, tool=op.tool, detail=run.result.detail)
        stage("publish")
        return self.registry.publish(system, checkout.url, checkout.commit, candidates, tests, cases,
                                     rejected=rejected, reason="onboarded", mode=mode)

    # ---------- self-heal ----------

    def trigger_heal(self, tool_name: str, error_info: Exception) -> bool:
        """PRD section 7: called by the gateway's error handler on OutputSchemaError or
        FunctionMissing. Starts a background repair for the tool's system. Returns
        True if a repair was started (not if one is running or ran recently)."""
        system = tool_name.split(".", 1)[0]
        self.events.add("call_failed", system=system, tool=tool_name, detail=type(error_info).__name__)
        if not isinstance(error_info, HEAL_TRIGGERS) or self.model is None:
            return False
        with self._guard:
            last = self._last_heal.get(system, 0.0)
            if time.monotonic() - last < self.heal_cooldown_s:
                return False
            self._last_heal[system] = time.monotonic()
        threading.Thread(target=self._heal_quietly, args=(system, type(error_info).__name__),
                         name=f"heal-{system}", daemon=True).start()
        return True

    def _heal_quietly(self, system: str, reason: str) -> None:
        try:
            self.heal(system, reason=reason)
        except Exception:  # noqa: BLE001 - a background repair must never crash the gateway
            log.exception("background heal crashed for %s", system)

    def check_for_changes(self, system: str) -> bool:
        """Has the legacy repo moved past the published commit? If so, start a repair."""
        current = self.registry.current(system)
        if current is None:
            return False
        try:
            latest = latest_commit(current.repo_url, local_root=self.settings.local_repo_root)
        except SourceError:
            return False
        if latest == current.source_commit:
            return False
        self.events.add("change_detected", system=system, version=current.version)
        threading.Thread(target=self._heal_quietly, args=(system, "change_detected"), daemon=True).start()
        return True

    def heal(self, system: str, reason: str = "manual") -> HealOutcome:
        current = self.registry.current(system)
        if current is None:
            raise PipelineError(f"{system} has no published version")
        lock = self._lock(system)
        if not lock.acquire(blocking=False):
            return HealOutcome("skipped", None, "a repair is already running")
        try:
            return self._heal(system, current, reason)
        except (PipelineError, RegistryError) as exc:
            self.events.add("heal_failed", system=system, version=current.version, detail=str(exc))
            return HealOutcome("failed", None, str(exc))
        finally:
            lock.release()

    def _heal(self, system: str, current: WrapperVersion, reason: str) -> HealOutcome:
        checkout = self._fetch(current.repo_url)
        if checkout.commit == current.source_commit:
            # Same code: the failure isn't from a legacy change, so there is nothing to diff.
            self.events.add("heal_skipped", system=system, version=current.version,
                            detail="legacy code unchanged")
            return HealOutcome("skipped", None, "legacy code unchanged")

        runtime = self._runtime(checkout)
        self._build(checkout, runtime)
        symbols = self._symbols(checkout, system, current.mode)
        by_name = {s.name: s for s in symbols}

        # 1. Replay every recorded contract against the new code, unchanged.
        tests: dict[str, ContractTestResult] = {}
        cases: dict[str, list[ContractCase]] = {}
        kept: dict[str, Operation] = {}
        broken: list[Operation] = []
        for old in current.operations:
            op = _relocated(old, by_name)
            run = replay_contract(self.executor, op, checkout.url, checkout.commit,
                                  current.cases.get(old.tool, [])) if op else None
            if run is not None and run.result.passed:
                kept[old.tool], tests[old.tool], cases[old.tool] = op, run.result, run.cases
            else:
                broken.append(old)
                detail = run.result.detail if run is not None else "FunctionMissing: function no longer found"
                self.events.add("contract_failed", system=system, tool=old.tool, detail=detail)

        rejected: dict[str, str] = {}
        if broken:
            # 2. Ask Nemotron to repair only what broke, then replay those contracts too.
            self.events.add("heal_started", system=system, version=current.version, detail=reason,
                            broken=len(broken))
            old_dir = self.repos_root / repo_key(current.repo_url) / current.source_commit
            diff = source_diff(old_dir, checkout.path) if old_dir.is_dir() else ""
            gen = model_heal(self._model(), namespace=system, tier=Tier.parsed, previous=current.operations,
                             diff=diff, repo_root=checkout.path, image=runtime.image, argv_for=argv_for,
                             symbols=symbols)
            repaired = {op.tool: op for op in gen.accepted}
            for old in broken:
                op = repaired.get(old.tool)
                if op is None:
                    rejected[old.tool] = gen.rejected.get(old.tool, "no repair proposed")
                    continue
                if op.access is not old.access:
                    rejected[old.tool] = "repair changed read/write access"
                    continue
                run = replay_contract(self.executor, op, checkout.url, checkout.commit,
                                      current.cases.get(old.tool, []))
                tests[op.tool], cases[op.tool] = run.result, run.cases
                if run.result.passed:
                    kept[op.tool] = op
                else:
                    rejected[op.tool] = f"repair failed its recorded contract: {run.result.detail}"[:300]

        if not kept:
            detail = "no operation passed its recorded contract on the new code"
            self.events.add("heal_failed", system=system, version=current.version, detail=detail)
            return HealOutcome("failed", None, detail)
        label = f"self-heal ({reason})" if broken else "code changed; contracts still pass"
        version = self.registry.publish(system, checkout.url, checkout.commit, list(kept.values()),
                                        tests, cases, rejected=rejected, reason=label, mode=current.mode)
        self.events.add("heal_saved", system=system, version=version.version,
                        operations=len(version.operations), rejected=len(version.rejected),
                        repaired=len(broken) - len(rejected))
        return HealOutcome("saved", version.version, f"saved v{version.version}")

    # ---------- history ----------

    def rollback(self, system: str, version: int) -> WrapperVersion:
        loaded = self.registry.rollback(system, version)
        self.events.add("rolled_back", system=system, version=loaded.version)
        return loaded

    def poll_forever(self, interval_s: float, stop: threading.Event) -> None:
        """Scheduled change detection (F2 step 1). Runs in a background thread."""
        while not stop.wait(interval_s):
            for system in self.registry.systems():
                try:
                    self.check_for_changes(system)
                except Exception:  # noqa: BLE001
                    log.exception("change check failed for %s", system)


def _known_inputs(op: Operation, known: dict[str, list[str]], limit: int = 3) -> list[dict[str, Any]]:
    """Inputs built from the operator's known-good values, for operations where every field has some."""
    fields = list(op.input_schema.get("properties", {}))
    if not fields or any(f not in known for f in fields):
        return []
    rounds = min(limit, max(len(known[f]) for f in fields))
    return [{f: known[f][i % len(known[f])] for f in fields} for i in range(rounds)]


def _usable_known_inputs(op: Operation, known: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Known-good values as inputs, keeping only those that fit the operation's field types (the form
    sends text, so a value for a numeric field is skipped instead of rejecting the whole operation)."""
    return [k for k in _known_inputs(op, known) if fit_input_schema(op.input_schema, [k]) is not None]


LOOSENABLE = ("pattern", "maxLength", "minLength", "enum", "format", "const")


def fit_input_schema(schema: dict[str, Any], examples: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Make the model's input schema accept the operator's real example inputs.

    Operator examples are real values (e.g. part ID "PMP-2210"), so they win over
    the model's guessed constraints. Only per-field value rules are loosened;
    a wrong type, a missing required field or an unknown field means the schema
    doesn't describe this function, and None is returned.
    """
    fitted = json.loads(json.dumps(schema))
    for _ in range(20):
        errors = [e for ex in examples for e in Draft202012Validator(fitted).iter_errors(ex)]
        if not errors:
            return fitted
        changed = False
        for err in errors:
            if err.validator not in LOOSENABLE or len(err.absolute_path) != 1:
                return None
            prop = fitted.get("properties", {}).get(err.absolute_path[0])
            if isinstance(prop, dict) and err.validator in prop:
                del prop[err.validator]
                changed = True
        if not changed:
            return None
    return None


def _valid_inputs(op: Operation, inputs: list[Any]) -> list[dict[str, Any]]:
    validator = Draft202012Validator(op.input_schema)
    return [i for i in inputs if isinstance(i, dict) and not list(validator.iter_errors(i))]


def _relocated(old: Operation, symbols: dict[str, Symbol]) -> Operation | None:
    """The old operation pointed at its symbol's line in the new code, or None if it's gone."""
    symbol = old.invocation.argv[-1]
    found = symbols.get(symbol)
    if found is None or found.file != old.source.file:
        return None
    return old.model_copy(update={"source": old.source.model_copy(update={"line": found.line})})
