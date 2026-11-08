# Demo legacy systems (FR-10)

Two small stand-ins for the subsidiaries' old software. REPLIC8 treats them as untrusted legacy code: it compiles and runs them only in the sandbox.

| Folder | Company | Language | Operations |
|--------|---------|----------|------------|
| `b-maintenance-cobol/` | B: oilfield services | COBOL (GnuCOBOL, fixed format) | 9 read-only paragraphs |
| `c-inventory-java/` | C: logistics/manufacturing | Java, J2SE 1.4 style (no generics; `Vector`, `Hashtable`) | 9 read-only methods |

Data lives in fixed-width files under each `data/` folder. The Java sources are compiled together into one jar in the sandbox; COBOL compiles to a native program. Every operation is read-only, and none uses the clock (B's "today" is a fixed batch date, `2026-11-08`), so replayed answers stay identical.

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
| `listPurchaseOrders` | optional `PART-ID`, optional `STATUS` | Purchase orders (OPEN, RECEIVED, CANCELED) |
| `getCheapestShipping` | `PART-ID`, `DESTINATION` | Cheapest lane from any warehouse that has the part |
| `quoteDelivery` | `PART-ID`, `DESTINATION`, `QUANTITY` (1 to 9999) | Cheapest delivered option (stock + lane, or direct from the supplier), plus every option. Days = transit + 1 handling day, or the supplier lead time |

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

## Line protocol

Both programs read a command on the first stdin line (Java matches it case-insensitively), then `KEY=VALUE` lines, then `END`. They print `KEY=VALUE` lines; `BEGIN-ITEMS` starts a list and `--` closes each item. REPLIC8's shim (`backend/runtime/shim.py`) converts JSON to and from this.

## Self-heal rehearsal

The live break is in COBOL: rename the paragraph `GET-REQUEST` (and its `WHEN "GET-REQUEST"` line) to `FETCH-REQUEST`. The old wrapper then fails its contract test, and REPLIC8 should re-point `maintenance.get_request` at the new paragraph without changing what agents see.

## Note

For the real demo, each folder should be its own GitHub repo so REPLIC8 can ingest it by URL (FR-1). See the PRD open questions.
