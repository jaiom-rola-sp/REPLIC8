# Deep dive: how REPLIC8 works

Plain-language tour of what the backend does and where the code lives. Paths are under `backend/replic8/` unless noted. For the plan see the [PRD](prd.md); for threats see [security](security.md).

## The whole path in one picture

```
GitHub repo
  -> fetch      clone the code at one exact commit        sources.py, ingest.py
  -> detect     which language(s)?                        ingest.py, runtimes.py
  -> build      compile / syntax-check in the sandbox     runtime/build.py
  -> extract    list the real functions and programs      extract.py
  -> propose    Nemotron drafts tools from that list      prompts.py, generate.py
  -> guard      reject anything that is not real/safe     guard.py
  -> test       run every tool on the real code, record   contracts.py
  -> publish    save a version, serve it                  registry.py, gateway.py
```

Each step is one `onboard_stage` event, which is what the dashboard's import screen shows (`pipeline.py`, `_onboard`).

## 1. Fetch: one exact commit

- GitHub URLs must be `https://github.com/owner/repo`. Anything else is refused.
- The clone uses safe git flags and is checked for symlinks and size.
- Every version is tied to the commit it was built from. The demo's local folders get a hash of their files instead of a commit, so a code change still gives a new version.

## 2. Detect and build

- The language comes from file extensions. Eight languages can run (see the README table).
- Building happens in the sandbox, not on the host:
  - COBOL, Fortran, Java, C and Pascal are compiled.
  - Python, Perl and PHP are only syntax-checked.
- If the code does not build, the import stops with a clear message.

## 3. Extract: facts, not guesses

- A tree-sitter parser reads each file and lists the real function names and line numbers. Python also gets its parameter names. C, Pascal, Perl, PHP and Python programs are found by their entry point (`main`, `program`, `$argv`, and so on).
- Each file is parsed in its own process with a time limit. Some grammars hang on garbage input, so a hostile repo cannot freeze an import.
- If a parser only half understands a file, a symbol is kept only when its name really appears on its reported line.
- This list is the only thing the model may pick from.

## 4. Propose: Nemotron drafts, REPLIC8 decides

The model gets the extracted list plus the source files (secrets are redacted first) and returns one JSON object. For each tool it gives:

- a name, the function, the file and line
- `read` or `write`
- a description
- input and output rules (JSON Schema)
- a few example inputs

It also gets a **how replic8 calls this** section, so its rules match what the callers really do:

| Kind | How a call happens | Code |
|------|--------------------|------|
| COBOL, Fortran, Java function | JSON becomes `KEY=VALUE` lines on stdin; `KEY=VALUE` output lines become JSON | `runtime/shim.py` |
| Python function | JSON becomes keyword arguments; the return value becomes JSON | `runtime/call_python.py` |
| Command-line program | The model fills in a small form; each caller value becomes one argument | `runtime/call_cli.py` |

The model never writes code or a command. Text inside the legacy files is marked as untrusted data, so instructions planted in comments are ignored.

## 5. Guard: nothing is trusted yet

`guard.validate_proposal` checks every proposed tool:

- The function, file and line must match something extracted. The model cannot invent a function.
- A Python tool's inputs must be the function's real parameter names, and every parameter without a default must be required.
- A command-line form may only use short literal arguments and `{field}` slots for string or number inputs. Anything that looks like shell syntax is rejected.
- A function with a write-sounding name (`update`, `send`, `delete`...) is forced to `write`, even if the model says `read`. v1 serves reads only.
- REPLIC8 picks the image and builds the command. The model's proposal contains neither.
- At most 20 tools per system. When a repo has both functions and programs, each gets half.

What is left are **candidates**, not tools.

## 6. Test: real answers are recorded, output rules are learned

This is `contracts.py`. For each candidate:

1. **Pick inputs.** Real IDs you typed at import come first (`known_values`), then the model's examples. Examples that do not fit the input rules are dropped. If the model's rules reject a real ID (it guessed a letters-and-digits pattern, say), the rules are loosened to fit the real value, never the other way round (`fit_input_schema`, with a `schema_adjusted` event).
2. **Run each input on the real legacy code** in the sandbox, up to 5 cases.
3. **Record** every input and the output it really gave.
4. **Repeat the first input.** If the answer differs, the tool is unstable and fails.
5. **Learn the output rules** from the recorded outputs (`observed_schema`):
   - a field seen in every output is required;
   - a field seen in only some is optional;
   - types come from the real values (a number stays a number);
   - the model's guessed output rules are thrown away.

Example. Two recorded outputs for a lookup:

```
{"found": "Y", "part_id": "PMP-2210", "qty": 4}
{"found": "N"}
```

become the published rule: `found` is required, `part_id` and `qty` are optional. Agents get the true shape, including the not-found case.

A tool with no passing test is never published. The record (inputs and outputs) is saved with the version, because self-repair needs it.

## 7. Publish and serve

- `registry.py` saves a new version as a JSON file (`v1.json`, `v2.json`...) and moves a `current` pointer. Only tools that passed are inside.
- The gateway (`gateway.py`, `mcp_server.py`) serves the same tools as REST and MCP, and builds an OpenAPI file from them.
- Calls reach the tool named `system.tool`. There is no way to call anything that is not published.

### What happens on every call

1. The token is checked, and it must be scoped to that system (scopes are fail-closed: no scope, no tools).
2. The body is capped at 64 KB.
3. The input is checked against the tool's input rules (`executor.py`). Bad input is a 422 before any legacy code runs.
4. The call runs in the sandbox against the exact commit the version was tested on.
5. The output must be a JSON object that matches the learned output rules. If not, it is an error, not data.
6. The answer comes back with provenance: tool, tier, source `file:line`, version and commit.

## 8. The sandbox

Every legacy run is `docker run` with:

- no network
- a read-only disk (a small noexec scratch space only)
- all Linux capabilities dropped, no privilege gain
- a non-root user
- limits on memory, CPU, processes, time and output size
- an image pinned by digest, so a swapped image is refused

The code is mounted read-only. Anything the legacy program prints, or says in an error, never reaches the caller unchecked.

## 9. Many systems, one graph

`graph.py` draws the connections. A link from tool A to tool B exists when a field A really returns (from its output rules or its recorded outputs) has the same name and a compatible type as an input of B in another system. Example: the maintenance system returns `part_id`, and the inventory system takes `part_id`.

- Links come from real field names, never from model opinion.
- A link is marked `recorded` when the field was seen in a real answer.
- This is why the prompt tells the model to keep legacy field names: same data, same name, everywhere.
- Modern systems imported from an OpenAPI file appear in the graph too, but are never called (`established.py`).

## 10. Self-repair

A repair starts when a call fails with a changed-output or missing-function error, when you ask for one, or when a change check finds a new commit (`pipeline.py`, `_heal`).

1. Fetch the new commit, rebuild, extract again.
2. **Replay every recorded case on the new code.** Tools whose recorded outputs are identical are kept as they are, even if the code moved.
3. For the tools that broke, ask Nemotron for a repair, shown the code diff. A repair may only change where the function is. It cannot change the name, the inputs or read/write.
4. **Replay the same recorded cases on the repair.** Identical outputs, or it is rejected.
5. If anything passed, save a new version. The old one stays, and you can roll back to it.

Agents never see a half-finished repair: the old version keeps serving, pinned to its own commit, until the new one is saved.

## 11. Versions and rollback

- Every import and repair is a new numbered version with its reason (`onboarded`, `self-heal (...)`).
- Rollback is one admin call and just moves the `current` pointer.
- Each version also stores how the repo was read (`auto`, `functions` or `programs`), so a repair reads it the same way.

## 12. Reading a repo: functions, programs, or both

- `auto` (default) wraps whatever exists. A Python library gives functions; a C tool gives a program; a file that is both gives both.
- `functions` or `programs` forces one kind. If nothing of that kind exists, the error says what the repo does have.
- A `mode_detected` event reports what was found, for example "1 functions, 1 programs: reading as functions and programs".

## 13. Access and trust

- Gateway tokens call read tools, only inside their scopes.
- A separate admin token imports, repairs and rolls back. It must differ from every gateway token and never goes into an agent.
- Tools get a tier so you know how much to trust them: `parsed` (real function from a parser), `inferred` (model-proposed entry point) or `black-box` (a command-line program tested from the outside).

## 14. The activity feed

`events.py` writes an event for each step: import started, stage reached, published, contract failed, call failed, change detected, repair started or saved, rollback. Events carry only names, counts and fixed reason codes, never data from a call. The dashboard polls `/v1/events` for the live feed and per-system status.

## Where to look when something breaks

| Symptom | Look at |
|---------|---------|
| Import stops at build | the sandbox build log message; `runtime/build.py` |
| "does not match an extracted symbol" | the model named something the parser did not find (`guard.py`) |
| Tool rejected after test | `contract_failed` event detail (`contracts.py`) |
| 422 on a call | the input rules, or a value the caller refused (`executor.py`, `runtime/call_cli.py`) |
| 502 on a call | the legacy program failed or its output broke the rules; a repair may start |
| Dashboard shows no systems | the token's scopes (`REPLIC8_TOKEN_SCOPES`) |
