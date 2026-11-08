# Demo legacy systems (FR-10)

Two small stand-ins for the subsidiaries' old software. REPLIC8 treats them as untrusted legacy code: it compiles and runs them only in the sandbox.

| Folder | Company | Language | Operations (read-only) |
|--------|---------|----------|------------------------|
| `b-maintenance-cobol/` | B: oilfield services | COBOL (GnuCOBOL, fixed format) | `GET-REQUEST`, `LIST-OPEN-REQUESTS` |
| `c-inventory-java/` | C: logistics/manufacturing | Java, J2SE 1.4 style (no generics; `Vector`, `Hashtable`) | `checkStock`, `getShippingOptions` |

Data lives in fixed-width files under each `data/` folder. The Java sources are compiled together into one jar in the sandbox; COBOL compiles to a native program.

## Shared keys (how B and C connect)

- **Part ID**, for example `PMP-2210`: a B maintenance request names the part; C stocks it.
- **Site region**, for example `PERMIAN`: a B request's well is in a region; C ships to regions.

Demo chain: B `GET-REQUEST R-1001` gives part `PMP-2210` at site `PERMIAN`. Then C `checkStock PMP-2210` shows 12 on hand in Houston, and C `getShippingOptions PMP-2210 PERMIAN` gives two carriers.

## Line protocol

Both programs read a command on the first stdin line (Java matches it case-insensitively), then `KEY=VALUE` lines, then `END`. They print `KEY=VALUE` lines; `BEGIN-ITEMS` starts a list and `--` closes each item. REPLIC8's shim (`backend/runtime/shim.py`) converts JSON to and from this.

## Self-heal rehearsal

The live break is in COBOL: rename the paragraph `GET-REQUEST` (and its `WHEN "GET-REQUEST"` line) to `FETCH-REQUEST`. The old wrapper then fails its contract test, and REPLIC8 should re-point `maintenance.get_request` at the new paragraph without changing what agents see.

## Note

For the real demo, each folder should be its own GitHub repo so REPLIC8 can ingest it by URL (FR-1). See the PRD open questions.
