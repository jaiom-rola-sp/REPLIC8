# MRP/400: Midwest Precision Parts shop floor system

A small, legacy-style Java manufacturing system for testing REPLIC8. It reads fixed-width data files that are committed in this repo, runs one transaction per call, and prints `KEY=VALUE` lines.

It is written in the style of early-2000s Java (JDK 1.4 era: `Vector`, `Hashtable`, `StringBuffer`, no generics, no libraries) so it builds with plain `javac` and runs fully offline. The company, the change logs and all data are fictional, created for the REPLIC8 hackathon demo.

## Why it fits REPLIC8

- **Plain Java, no dependencies:** builds with `javac` alone, with no Maven, Gradle or downloads.
- **Data is in the repo:** `data/*.DAT`, fixed-width records with layouts documented in each class.
- **Batch, not interactive:** one transaction in, `KEY=VALUE` lines out, no prompts.
- **Mostly read-only:** seven lookups and reports, plus one write (`CREATE-WORK-ORDER`) so the gateway's write-blocking can be shown.
- **Fails cleanly:** unknown IDs return `STATUS=NOT-FOUND`; errors return `STATUS=ERROR` with no stack trace.

## Build and run

```
mkdir -p classes
javac -d classes src/com/mpp/mrp/*.java
java -cp classes com.mpp.mrp.Main GET-PART PART_ID=PUMP-77
```

Or run `./build.sh`. The data folder defaults to `data`; override it with `-Dmrp.data=/path/to/data`.

## Transactions

| Transaction | Inputs | Access | What it returns |
|---|---|---|---|
| `GET-PART` | `PART_ID` | read | Description, stock on hand, reorder point, lead time, unit cost, below-reorder flag |
| `LIST-REORDER` | none | read | Active parts whose stock is below the reorder point |
| `GET-BOM` | `PART_ID` | read | Components and quantity per assembly |
| `CALC-MATERIAL-NEEDS` | `PART_ID`, `QTY` | read | For building QTY units: needed, on hand, and shortage per component, plus `CAN_BUILD` |
| `GET-WORK-ORDER` | `WORK_ORDER_ID` | read | Part, quantity, due date, status, machine |
| `LIST-OPEN-WORK-ORDERS` | none | read | Open and on-hold work orders |
| `GET-MACHINE-STATUS` | `MACHINE_ID` | read | Up, down or maintenance, and last preventive maintenance date |
| `CREATE-WORK-ORDER` | `WORK_ORDER_ID`, `PART_ID`, `QTY`, `DUE_DATE`, `MACHINE_ID` | **write** | Appends to `WORKORD.DAT` |
| `GET-ROUTING` | `PART_ID` | read | Operations, machines (with state), setup and run minutes |
| `CALC-MACHINE-HOURS` | `MACHINE_ID` | read | Hours of open work queued on the machine, per order |
| `CHECK-WO-READINESS` | `WORK_ORDER_ID` | read | `READY` Y/N plus every blocker (hold, shortage, machine down) |
| `EXPLODE-BOM` | `PART_ID`, `QTY` (default 1) | read | Multi-level BOM with extended quantities and make/buy |
| `WHERE-USED` | `PART_ID` | read | Assemblies that use the part |
| `CALC-ROLLED-COST` | `PART_ID` | read | Rolled-up material + machine labor vs standard cost |
| `PLAN-REPLENISHMENT` | `PART_ID`, `QTY` | read | Make/buy plan netted level by level, buy cost, critical-path lead time |

Lists come back as `COUNT=n` followed by `ITEM_1_...`, `ITEM_2_...` lines.

## Batch queue mode (how REPLIC8 calls it)

Run with no arguments and the transaction comes on stdin: the transaction (or its method name, like `getPart`) on line 1, then `KEY=VALUE` lines (`PART-ID` or `PART_ID`), then `END`. Output uses `-` in keys, and lists come back as `BEGIN-ITEMS`, one block per item ending in `--`, then `COUNT=n`. Errors print `ERROR=<code>`. Empty stdin still prints `STATUS=NO-TRANSACTION`.

```
$ printf 'checkWoReadiness\nWORK-ORDER-ID=WO100481\nEND\n' | java -cp classes com.mpp.mrp.Main
STATUS=OK
WORK-ORDER-ID=WO100481
...
READY=N
BEGIN-ITEMS
BLOCKER-TYPE=MACHINE
BLOCKER-ID=DRILL3
DETAIL=DOWN
--
COUNT=1
```

## Example

```
$ java -cp classes com.mpp.mrp.Main CALC-MATERIAL-NEEDS PART_ID=PUMP-77 QTY=5
STATUS=OK
PART_ID=PUMP-77
QTY=5
CAN_BUILD=N
COUNT=7
...
ITEM_3_COMPONENT_ID=HSG-C3
ITEM_3_QTY_NEEDED=5
ITEM_3_QTY_ON_HAND=4
ITEM_3_SHORTAGE=1
...
```

## Sample IDs to try

- Parts: `SKID-77` (3-level BOM), `PUMP-77`, `PUMP-90`, `MTR-3HP`, `IMP-08`, `HSG-C3`, `VLV-2B` (`PUMP-60` is obsolete)
- Work orders: `WO100481` (open), `WO100482` (on hold), `WO100477` (closed)
- Machines: `LATHE1` (up), `MILL02` (maintenance), `DRILL3` (down)

## Data files

| File | Record length | Contents |
|---|---|---|
| `PARTS.DAT` | 70 | Part master: stock, reorder point, lead time, cost, status |
| `BOM.DAT` | 25 | Bill of materials: parent, component, quantity per |
| `WORKORD.DAT` | 39 | Work orders: part, quantity, due date, status, machine |
| `MACHINES.DAT` | 39 | Machines: name, status, last preventive maintenance |

Field positions are documented at the top of each Java class.

## License

MIT. See `LICENSE`.
