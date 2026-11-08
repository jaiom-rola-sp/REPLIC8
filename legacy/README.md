# Demo legacy systems (FR-10)

Three small stand-ins for the subsidiaries' old software. REPLIC8 treats them as untrusted legacy code: it compiles and runs them only in the sandbox.

| Folder | Company | Language | Operations |
|--------|---------|----------|------------|
| `b-maintenance-cobol/` | B: oilfield services | COBOL (GnuCOBOL, fixed format) | 9 read-only paragraphs |
| `c-inventory-java/` | C: logistics/manufacturing | Java, J2SE 1.4 style (no generics; `Vector`, `Hashtable`) | 9 read-only methods |
| `d-mrp400-java/` | D: Midwest Precision Parts (pump manufacturing) | Java, JDK 1.4 style | 14 read-only transactions + 1 write |

Data lives in fixed-width files under each `data/` folder. The Java sources are compiled together into one jar in the sandbox; COBOL compiles to a native program. B and C are written to look like code that several people changed over 20 years (see "Messy on purpose" below). Every B and C operation is read-only, and none uses the clock (B's "today" is a fixed batch date, `2026-11-08`), so replayed answers stay identical.

## B: Field Maintenance System (COBOL, `src/MAINT.cbl`)

| Command | Inputs | Returns |
|---------|--------|---------|
| `GET-REQUEST` | `REQUEST-ID` | One maintenance request: well, part, site, quantity, priority, status, opened |
| `LIST-OPEN-REQUESTS` | `WELL-ID` | Open requests for one well |
| `LIST-SITE-REQUESTS` | `SITE`, optional `STATUS` | All requests at a site (OPEN, CLOSED or HOLD) |
| `GET-WELL` | `WELL-ID` | Well name, site, status, barrels/day, last service, open request count |
| `GET-SERVICE-HISTORY` | `WELL-ID` | Event count, failures, total downtime hours, then each event (date, type, part, technician) |
| `GET-TECHNICIAN` | `TECH-ID` | Name, site, skill, cert level, availability, hourly rate |
| `FIND-AVAILABLE-TECHS` | `SITE`, optional `SKILL` | Technicians free now at that site |
| `CALC-DOWNTIME-COST` | `WELL-ID`, `DAYS` (1 to 365) | Lost barrels and dollars: barrels/day x $88.00 x days |
| `GET-WELL-RISK` | `WELL-ID`, optional `AS-OF-DATE` (YYYY-MM-DD) | Risk score 0 to 100 and level (LOW, MEDIUM, HIGH, CRITICAL), with the factors |

Risk score: shut in +40, each open HIGH request +20, each other open request +5, each failure in the last 365 days +10, no service in 180 days +10. 70+ is CRITICAL, 40+ HIGH, 20+ MEDIUM.

Data files: `requests.dat` (R-1001 to R-1013), `wells.dat`, `techs.dat`, `history.dat`.

## C: Parts Inventory and Logistics (Java, `src/com/subc/pil/Inventory.java`)

| Command | Inputs | Returns |
|---------|--------|---------|
| `checkStock` | `PART-ID` | On hand and warehouse (the part's first stock row) |
| `getShippingOptions` | `PART-ID`, `DESTINATION` | Lanes from that warehouse to the region |
| `getWarehouse` | `WAREHOUSE` | Part lines, units, stock value, and outbound lanes |
| `listLowStock` | optional `WAREHOUSE` | Stock rows below their reorder point, with shortfall and open PO quantity |
| `getSupplier` | `SUPPLIER-ID` | Name, city, lead days, on-time %, freight, parts supplied, open POs |
| `getPartSourcing` | `PART-ID` | Unit cost, supplier, total on hand, open PO quantity and next date, stock by warehouse |
| `listPoLines` | optional `PART-ID`, optional `STATUS` | Purchase orders (OPEN, RECEIVED, CANCELED) |
| `getCheapestShipping` | `PART-ID`, `DESTINATION` | Cheapest lane from any warehouse that has the part |
| `quoteDelivery` | `PART-ID`, `DESTINATION`, `QUANTITY` (1 to 9999) | Cheapest delivered option (stock + lane, or direct from the supplier), plus every option. Days = transit + 1 handling day, or the supplier lead time |

Source files: `Inventory.java` (2003 code and the dispatcher), `PilRecs.java` (shared helpers), `Sourcing.java`, `WhseRpt.java`, `Purch.java`.

Data files: `stock.dat` (now also an ODESSA warehouse), `lanes.dat` (new lanes all leave from ODESSA), `catalog.dat`, `suppliers.dat`, `purchase_orders.dat`.

## Shared keys (how B and C connect)

- **Part ID**, for example `PMP-2210`: a B maintenance request names the part; C stocks it.
- **Site region**, for example `PERMIAN`: a B request's well is in a region; C ships to regions.

Original demo chain (answers unchanged): B `GET-REQUEST R-1001` gives part `PMP-2210` at site `PERMIAN`. Then C `checkStock PMP-2210` shows 12 on hand in Houston, and C `getShippingOptions PMP-2210 PERMIAN` gives two carriers.

New demo story (one agent question, both systems):

1. B `GET-WELL-RISK W-44`: shut in, open HIGH request, 2 failures this year, score 80, **CRITICAL**.
2. B `CALC-DOWNTIME-COST W-44 DAYS=7`: 720 bbl/day x $88 x 7 = **$443,520.00** lost.
3. B `LIST-SITE-REQUESTS PERMIAN STATUS=OPEN`: R-1006 needs 2 x `CBL-0500` cable for W-44.
4. B `FIND-AVAILABLE-TECHS PERMIAN SKILL=ELECTRICAL`: **Maria Alvarez (T-101)** is free.
5. C `quoteDelivery CBL-0500 PERMIAN QUANTITY=2`: from ODESSA by BASINEXPRESS, **5 days, $20,325.50** ($19,700 parts + $625.50 freight). Faster (2 days, $21,680) and supplier-direct (21 days, $20,420) options are listed too.

The original records and lanes were not changed, so the four original operations give byte-identical output.

## Messy on purpose (B and C)

Real legacy code is untidy, and REPLIC8 should cope with it. B and C were rewritten to look like code many people touched over the years. **Every answer is byte-identical** to the clean version (391 recorded calls compared).

- **B (COBOL):** change log with initials and change requests; the release 2 commands bolted on behind `WHEN OTHER` in their own `R2-DISPATCH` with `GO TO`; `PERFORM ... THRU ...-EXIT` paragraphs; 88-level flags; nested `IF`s instead of `EVALUATE`; commented-out old formulas; unused fields left "for record sizes"; a dead report paragraph nothing calls.
- **C (Java):** the 2004 methods split across `Sourcing`, `WhseRpt` and `Purch`, all extending a "utility base class" (`PilRecs`); helpers copy-pasted between `Inventory` and `PilRecs` (two `openData`s); a catalog cache; a deprecated money formatter kept for audit; dispatch through constants; a debug flag; commented-out removed commands.
- The `GET-REQUEST` to `FETCH-REQUEST` rename still works.

## D: MRP/400 (Java, `legacy/d-mrp400-java`)

Krish's MRP/400 shop floor system (from `krishthapa-portfolio/mrp400-legacy`), extended. Its original command-line mode is unchanged (73 recorded calls identical). REPLIC8 calls it through a new **batch queue mode**: with no arguments it reads the line protocol on stdin, accepts method names (`getPart`) or transaction codes (`GET-PART`), and prints lists as `BEGIN-ITEMS` blocks. Each class has an `ENTRY` table naming its commands.

| Command | Inputs | Returns |
|---------|--------|---------|
| `getPart` | `PART-ID` | Description, stock, reorder point, lead time, cost |
| `listReorder` | none | Active parts below reorder point |
| `getBom` | `PART-ID` | One level of components |
| `calcMaterialNeeds` | `PART-ID`, `QTY` | Needed, on hand and shortage per component, `CAN-BUILD` |
| `getWorkOrder` | `WORK-ORDER-ID` | Part, quantity, due date, status, machine |
| `listOpenWorkOrders` | none | Open and on-hold work orders |
| `getMachineStatus` | `MACHINE-ID` | Up, down or maintenance |
| `createWorkOrder` | 5 fields | **Write.** REPLIC8 locks it |
| `getRouting` (new) | `PART-ID` | Each operation's machine, its state, setup and run minutes |
| `calcMachineHours` (new) | `MACHINE-ID` | Hours of open work queued on a machine, per order, and shifts of work |
| `checkWoReadiness` (new) | `WORK-ORDER-ID` | `READY` Y/N and every blocker: hold, component shortage, machine not up |
| `explodeBom` (new) | `PART-ID`, optional `QTY` | Every component at every level, with extended quantity and make/buy |
| `whereUsed` (new) | `PART-ID` | Assemblies that use the part |
| `calcRolledCost` (new) | `PART-ID` | Material rolled up through the tree + machine labor, against standard cost |
| `planReplenishment` (new) | `PART-ID`, `QTY` | What to make and buy, netting stock level by level, total buy cost and critical-path lead time |

New data: `ROUTING.DAT`, and a pump skid (`SKID-77` = `PUMP-77` + `FRAME-S1` + `CTRL-PNL` + bolts) so the BOM is three levels deep. New parts sit above their reorder points, so `listReorder` is unchanged.

Example answers: `checkWoReadiness WO100481` is not ready (drill DRILL3 is down); `calcRolledCost PUMP-77` is $1,448.84 against $1,845.00 standard; `planReplenishment SKID-77 QTY=6` makes 5 skids, 2 pumps and 3 frames, buys 2 control panels ($2,250.00), 31 days end to end.

**Write-guard note:** REPLIC8 treats any name containing a write verb as a write. `getWorkOrder` contains "order", so it is locked as a write although it only reads. Three new names were chosen to avoid this (`listPoLines`, `calcMachineHours`, `checkWoReadiness`).

D is not in `deploy/vm/onboard-demo.sh`; import it from the dashboard or add a third `onboard` line (`"repo_url":"local://d-mrp400-java"`).

## Line protocol

Both programs read a command on the first stdin line (Java matches it case-insensitively), then `KEY=VALUE` lines, then `END`. They print `KEY=VALUE` lines; `BEGIN-ITEMS` starts a list and `--` closes each item. REPLIC8's shim (`backend/runtime/shim.py`) converts JSON to and from this.

## Self-heal rehearsal

The live break is in COBOL: rename the paragraph `GET-REQUEST` (and its `WHEN "GET-REQUEST"` line) to `FETCH-REQUEST`. The old wrapper then fails its contract test, and REPLIC8 should re-point `maintenance.get_request` at the new paragraph without changing what agents see.

## Note

For the real demo, each folder should be its own GitHub repo so REPLIC8 can ingest it by URL (FR-1). See the PRD open questions.
