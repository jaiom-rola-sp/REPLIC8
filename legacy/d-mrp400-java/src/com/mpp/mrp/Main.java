/*
 * Main.java
 *
 * Batch entry point. Runs one transaction and prints KEY=VALUE lines.
 *
 *   java -cp classes com.mpp.mrp.Main <TRANSACTION> [KEY=VALUE ...]
 *
 * Transactions:
 *   GET-PART              PART_ID
 *   LIST-REORDER
 *   GET-BOM               PART_ID
 *   CALC-MATERIAL-NEEDS   PART_ID QTY
 *   GET-WORK-ORDER        WORK_ORDER_ID
 *   LIST-OPEN-WORK-ORDERS
 *   GET-MACHINE-STATUS    MACHINE_ID
 *   CREATE-WORK-ORDER     WORK_ORDER_ID PART_ID QTY DUE_DATE MACHINE_ID   (writes)
 *   GET-ROUTING           PART_ID
 *   CALC-MACHINE-HOURS    MACHINE_ID
 *   CHECK-WO-READINESS    WORK_ORDER_ID
 *   EXPLODE-BOM           PART_ID [QTY, default 1]
 *   WHERE-USED            PART_ID
 *   CALC-ROLLED-COST      PART_ID
 *   PLAN-REPLENISHMENT    PART_ID QTY
 *
 * BATCH QUEUE MODE (no arguments): the transaction comes on stdin instead,
 * the way the job scheduler feeds it:
 *   line 1      transaction, or its method name (getPart, explodeBom ...)
 *   then        KEY=VALUE lines (PART-ID and PART_ID both work)
 *   then        END
 * Output is the same data as KEY=VALUE lines with '-' in the keys; lists are
 * BEGIN-ITEMS, one block per item closed by "--", then COUNT=n.
 * Failures print ERROR=<code>. Empty stdin behaves like before (NO-TRANSACTION).
 *
 * CHANGE LOG
 *   1999-06-21  RTH  Original version, replaced green-screen menu.
 *   2004-10-12  KLM  KEY=VALUE arguments instead of positional ones.
 *   2005-02-14  DJS  Routing transactions.
 *   2005-09-12  RTH  Multi-level BOM, where-used.
 *   2006-11-08  KLM  Cost roll-up, replenishment plan.
 *   2007-05-21  KLM  Batch queue mode on stdin for the job scheduler.
 */
package com.mpp.mrp;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.Hashtable;
import java.util.Vector;

public class Main {

    public static void main(String[] args) {
        if (args.length == 0) {
            runQueue();
            return;
        }
        Hashtable p = new Hashtable();
        for (int i = 1; i < args.length; i++) {
            int eq = args[i].indexOf('=');
            if (eq > 0) {
                p.put(args[i].substring(0, eq).toUpperCase(), args[i].substring(eq + 1));
            }
        }
        try {
            System.out.print(run(args[0].toUpperCase(), p));
        } catch (Exception e) {
            System.out.print("STATUS=ERROR\n");
            System.exit(1);
        }
    }

    static String run(String tx, Hashtable p) throws Exception {
        if ("GET-PART".equals(tx)) {
            return PartMaster.getPart(get(p, "PART_ID"));
        }
        if ("LIST-REORDER".equals(tx)) {
            return PartMaster.listReorder();
        }
        if ("GET-BOM".equals(tx)) {
            return BillOfMaterials.getBom(get(p, "PART_ID"));
        }
        if ("CALC-MATERIAL-NEEDS".equals(tx)) {
            return BillOfMaterials.calcMaterialNeeds(get(p, "PART_ID"), toInt(get(p, "QTY")));
        }
        if ("GET-WORK-ORDER".equals(tx)) {
            return WorkOrders.getWorkOrder(get(p, "WORK_ORDER_ID"));
        }
        if ("LIST-OPEN-WORK-ORDERS".equals(tx)) {
            return WorkOrders.listOpenWorkOrders();
        }
        if ("GET-MACHINE-STATUS".equals(tx)) {
            return Machines.getMachineStatus(get(p, "MACHINE_ID"));
        }
        if ("CREATE-WORK-ORDER".equals(tx)) {
            return WorkOrders.createWorkOrder(get(p, "WORK_ORDER_ID"), get(p, "PART_ID"),
                toInt(get(p, "QTY")), get(p, "DUE_DATE"), get(p, "MACHINE_ID"));
        }
        if ("GET-ROUTING".equals(tx)) {
            return Routing.getRouting(get(p, "PART_ID"));
        }
        if ("CALC-MACHINE-HOURS".equals(tx)) {
            return Routing.calcMachineHours(get(p, "MACHINE_ID"));
        }
        if ("CHECK-WO-READINESS".equals(tx)) {
            return Routing.checkWoReadiness(get(p, "WORK_ORDER_ID"));
        }
        if ("EXPLODE-BOM".equals(tx)) {
            return Planning.explodeBom(get(p, "PART_ID"), qtyOrOne(get(p, "QTY")));
        }
        if ("WHERE-USED".equals(tx)) {
            return Planning.whereUsed(get(p, "PART_ID"));
        }
        if ("CALC-ROLLED-COST".equals(tx)) {
            return Planning.calcRolledCost(get(p, "PART_ID"));
        }
        if ("PLAN-REPLENISHMENT".equals(tx)) {
            return Planning.planReplenishment(get(p, "PART_ID"), toInt(get(p, "QTY")));
        }
        return "STATUS=UNKNOWN-TRANSACTION\n";
    }

    static String get(Hashtable p, String key) {
        String v = (String) p.get(key);
        return v == null ? "" : v.trim().toUpperCase();
    }

    static int qtyOrOne(String s) {
        return s.length() == 0 ? 1 : toInt(s);
    }

    // ------------------------------------------------------------------
    // Batch queue mode (KLM 2007)
    // ------------------------------------------------------------------

    /** Method name (upper case) -> transaction code, from each class's ENTRY table. */
    static Hashtable aliases() {
        String[][][] tables = { PartMaster.ENTRY, BillOfMaterials.ENTRY, WorkOrders.ENTRY,
                                Machines.ENTRY, Routing.ENTRY, Planning.ENTRY };
        Hashtable a = new Hashtable();
        for (int t = 0; t < tables.length; t++) {
            for (int i = 0; i < tables[t].length; i++) {
                a.put(tables[t][i][0].toUpperCase(), tables[t][i][1]);
            }
        }
        return a;
    }

    static void runQueue() {
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in));
        String cmd;
        Hashtable p = new Hashtable();
        try {
            cmd = in.readLine();
            if (cmd == null || cmd.trim().length() == 0) {
                System.out.print("STATUS=NO-TRANSACTION\n");
                System.exit(2);
            }
            String line;
            int guard = 0;
            while ((line = in.readLine()) != null && guard++ < 20) {
                if (line.trim().equals("END") || line.trim().length() == 0) {
                    break;
                }
                int eq = line.indexOf('=');
                if (eq > 0) {
                    p.put(line.substring(0, eq).trim().toUpperCase().replace('-', '_'),
                          line.substring(eq + 1));
                }
            }
        } catch (IOException e) {
            System.out.print("ERROR=INPUT-UNREADABLE\n");
            return;
        }
        String tx = cmd.trim().toUpperCase();
        String mapped = (String) aliases().get(tx);
        if (mapped != null) {
            tx = mapped;
        }
        String out;
        try {
            out = run(tx, p);
        } catch (Exception e) {
            System.out.print("ERROR=TRANSACTION-FAILED\n");
            return;
        }
        System.out.print(toQueueFormat(out));
    }

    /** STATUS=..., ITEM_n_X=... lines -> queue format (see header). */
    static String toQueueFormat(String out) {
        StringBuffer head = new StringBuffer();
        Vector items = new Vector();
        String count = null;
        int start = 0;
        while (start < out.length()) {
            int nl = out.indexOf('\n', start);
            if (nl < 0) {
                nl = out.length();
            }
            String line = out.substring(start, nl);
            start = nl + 1;
            int eq = line.indexOf('=');
            if (eq <= 0) {
                continue;
            }
            String key = line.substring(0, eq);
            String val = line.substring(eq + 1);
            if ("STATUS".equals(key) && "UNKNOWN-TRANSACTION".equals(val)) {
                return "ERROR=UNKNOWN-COMMAND\n";
            }
            if ("STATUS".equals(key) && "ERROR".equals(val)) {
                return "ERROR=TRANSACTION-FAILED\n";
            }
            if ("COUNT".equals(key)) {
                count = val;
                continue;
            }
            if (key.startsWith("ITEM_")) {
                int us = key.indexOf('_', 5);
                int n;
                try {
                    n = Integer.parseInt(key.substring(5, us));
                } catch (Exception e) {
                    continue;
                }
                while (items.size() < n) {
                    items.addElement(new StringBuffer());
                }
                ((StringBuffer) items.elementAt(n - 1))
                    .append(key.substring(us + 1).replace('_', '-')).append('=').append(val).append('\n');
                continue;
            }
            head.append(key.replace('_', '-')).append('=').append(val).append('\n');
        }
        if (count != null || items.size() > 0) {
            head.append("BEGIN-ITEMS\n");
            for (int i = 0; i < items.size(); i++) {
                head.append(items.elementAt(i)).append("--\n");
            }
            head.append("COUNT=").append(count == null ? String.valueOf(items.size()) : count).append('\n');
        }
        return head.toString();
    }

    static int toInt(String s) {
        try {
            return Integer.parseInt(s);
        } catch (NumberFormatException e) {
            return 0;
        }
    }
}
