# Demo script

How to run the REPLIC8 demo on stage, about 4 minutes. Everything here is built and was rehearsed on 2026-11-08 against the real backend, live Nemotron and the COBOL and Java systems. Hosting: the Azure VM in [deploy](../deploy/README.md), frontend on Vercel.

## Before the demo

**The day before**

- [ ] The VM is running (Azure portal, VM, **Start**) and `curl https://<backend hostname>/health` prints `{"status":"ok"}`.
- [ ] Load the systems once: `sudo bash /opt/replic8/deploy/vm/onboard-demo.sh`. It prints the four tools: `maintenance.get_request`, `maintenance.list_open_requests`, `inventory.check_stock`, `inventory.get_shipping_options`.
- [ ] The sandbox image is pinned by digest: `sudo grep SANDBOX_IMAGES /etc/replic8/replic8.env` shows `replic8-legacy-runtime:1@sha256:...` (setup does this after every build).
- [ ] `REPLIC8_CORS_ORIGINS` is `https://www.replic8.work` (the Vercel site), and the dashboard connects from it.
- [ ] Rehearse the whole script below once, then reset (see the end).
- [ ] Download the fallback video and have it open on the presenting laptop.

**One hour before**

- [ ] Health check again. Open the Vercel dashboard, Settings: gateway address `https://<backend hostname>`, the gateway token, **Connect gateway**. Overview shows 2 systems and 4 operations.
- [ ] In a terminal: `REPLIC8_TOKEN=<gateway token> python backend/scripts/mcp_demo.py --url https://<backend hostname>/mcp` answers with "Fastest: LONESTARHOT, 1 day(s), $1525.50".
- [ ] An SSH session to the VM is open, ready for the live break.
- [ ] The admin token is in a password manager or a note that isn't on screen.

## The script

**1. The problem (30 s).** Company A bought two companies. Their software is decades old: B's maintenance system is COBOL, C's inventory is Java from 2003. No APIs, so A's AI agents can't use them.

**2. REPLIC8 reads the code (45 s).** Dashboard, **Overview**: "REPLIC8 read both repos, compiled them in a locked sandbox, and Nemotron picked the real functions." Point at the graph: the gateway, both systems, four read-only tools, and the dashed `part_id` link found in real data. Open **Operations**: every tool shows its source file and line (`src/MAINT.cbl:95`), version and "read". Nothing is guessed: each tool passed contract tests against the real program.

**3. An agent uses it over MCP (45 s).** In the terminal, run `mcp_demo.py` (or ask Claude Code with the MCP server added; see `backend/README.md`). It looks up pump request R-1001 in the COBOL system, checks stock for that part in the Java system, then finds shipping to the well's region: 12 in Houston, fastest LONESTARHOT, 1 day. Each step shows which file and version answered.

**4. The legacy code changes (60 s).** "Someone renames a function in the COBOL." In the SSH session:

```bash
sudo sed -i 's/GET-REQUEST/FETCH-REQUEST/g' /opt/replic8/legacy/b-maintenance-cobol/src/MAINT.cbl
```

Agents are unaffected: the published version is pinned to the tested code. In the dashboard, open the **maintenance** system, enter the admin token, click **Check for changes**. Switch to **Activity** and narrate: change detected, `get_request` broke (FunctionMissing), Nemotron repairs only that tool, the recorded answers replay identically, **v2 saved**. About 6 to 10 seconds. Run `mcp_demo.py` again: the same answer, now from v2.

**5. Safe by design (30 s).** Everything is read-only (writes are blocked), every call needs a scoped token, legacy code runs offline in a locked container, and the model never writes code. Back in the system panel, **Roll back** to v1 to show any version can be restored instantly.

**6. Close (15 s).** "Old software, ready for AI agents today, and it keeps working when the old code changes."

## If something fails

- **Repair takes longer than 30 s or fails:** Nemotron may be slow or rate-limited. Say so, switch to the fallback video at the repair step, and continue.
- **Dashboard can't connect:** check the gateway address has no trailing slash, and that `REPLIC8_CORS_ORIGINS` matches the Vercel address exactly.
- **The VM is down:** use the laptop-plus-tunnel fallback in [deploy](../deploy/README.md), or the video.

## Reset after a rehearsal

```bash
sudo sed -i 's/FETCH-REQUEST/GET-REQUEST/g' /opt/replic8/legacy/b-maintenance-cobol/src/MAINT.cbl
```

Then, in the dashboard, **Roll back** maintenance to v1 (if you didn't already). The code now matches v1 again, so **Check for changes** finds nothing to repair and the next run starts clean.
