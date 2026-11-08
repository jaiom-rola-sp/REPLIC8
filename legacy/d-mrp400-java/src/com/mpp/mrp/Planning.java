/*
 * Planning.java
 *
 * Multi-level bill of materials, cost roll-up and the MRP net requirements
 * run. BillOfMaterials.java only ever did one level; this walks the whole
 * tree (pump skid -> pump -> motor ...).
 *
 * CHANGE LOG
 *   2005-09-12  RTH  EXPLODE-BOM and WHERE-USED (indented BOM report).
 *   2006-03-27  KLM  CALC-ROLLED-COST for the yearly standard cost update.
 *   2006-11-08  KLM  PLAN-REPLENISHMENT: nets stock level by level, so a
 *                    component used twice is only counted once.
 *   2007-02-01  DJS  Loop guard after a bad BOM entry hung the night run.
 */
package com.mpp.mrp;

import java.io.IOException;
import java.util.Hashtable;
import java.util.Vector;

public class Planning {

    /** Line-protocol names (see Main.runQueue). */
    static final String[][] ENTRY = {
        { "explodeBom", "EXPLODE-BOM" },
        { "whereUsed", "WHERE-USED" },
        { "calcRolledCost", "CALC-ROLLED-COST" },
        { "planReplenishment", "PLAN-REPLENISHMENT" },
    };

    /** Deepest BOM we accept. Anything deeper is a loop in BOM.DAT. */
    static final int MAX_LEVELS = 10;
    /** Standard lot size: setup minutes are spread over this many units. */
    static final int STD_LOT = 10;

    static class BomLoop extends RuntimeException {
        BomLoop() {
            super("BOM-LOOP");
        }
    }

    /** BOM rows whose parent is partId. */
    static Vector children(String partId) throws IOException {
        Vector recs = RecordFile.readAll("BOM.DAT");
        Vector out = new Vector();
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (RecordFile.field(rec, 1, 10).equals(partId)) {
                out.addElement(rec);
            }
        }
        return out;
    }

    static String money(long cents) {
        String sign = cents < 0 ? "-" : "";
        long c = Math.abs(cents);
        long frac = c % 100;
        return sign + (c / 100) + "." + (frac < 10 ? "0" : "") + frac;
    }

    // ------------------------------------------------------------------
    // EXPLODE-BOM
    // ------------------------------------------------------------------

    /**
     * EXPLODE-BOM: every component at every level needed to build QTY units,
     * parents before their components (indented BOM order).
     */
    public static String explodeBom(String partId, int qty) throws IOException {
        if (qty <= 0 || qty > 9999) {
            return "STATUS=INVALID-QTY\nQTY=" + qty + "\n";
        }
        if (PartMaster.findRecord(partId) == null) {
            return "STATUS=NOT-FOUND\nPART_ID=" + partId + "\n";
        }
        StringBuffer items = new StringBuffer();
        int[] count = new int[1];
        int[] deepest = new int[1];
        try {
            explode(partId, qty, 1, items, count, deepest);
        } catch (BomLoop e) {
            return "STATUS=BOM-LOOP\nPART_ID=" + partId + "\n";
        }
        return "STATUS=OK\nPART_ID=" + partId + "\nQTY=" + qty
            + "\nLEVELS=" + deepest[0]
            + "\nCOUNT=" + count[0] + "\n" + items.toString();
    }

    static void explode(String parent, int qty, int level, StringBuffer items, int[] count, int[] deepest)
            throws IOException {
        if (level > MAX_LEVELS) {
            throw new BomLoop();
        }
        Vector kids = children(parent);
        for (int i = 0; i < kids.size(); i++) {
            String rec = (String) kids.elementAt(i);
            String comp = RecordFile.field(rec, 11, 20);
            int per = RecordFile.num(rec, 21, 25);
            int ext = per * qty;
            String pr = PartMaster.findRecord(comp);
            boolean make = children(comp).size() > 0;
            int n = ++count[0];
            if (level > deepest[0]) {
                deepest[0] = level;
            }
            items.append("ITEM_").append(n).append("_LEVEL=").append(level).append("\n");
            items.append("ITEM_").append(n).append("_PARENT_ID=").append(parent).append("\n");
            items.append("ITEM_").append(n).append("_COMPONENT_ID=").append(comp).append("\n");
            items.append("ITEM_").append(n).append("_DESCRIPTION=")
                 .append(pr == null ? "*** NOT IN PART MASTER ***" : RecordFile.field(pr, 11, 40)).append("\n");
            items.append("ITEM_").append(n).append("_QTY_PER=").append(per).append("\n");
            items.append("ITEM_").append(n).append("_QTY_EXTENDED=").append(ext).append("\n");
            items.append("ITEM_").append(n).append("_MAKE_OR_BUY=").append(make ? "MAKE" : "BUY").append("\n");
            if (make) {
                explode(comp, ext, level + 1, items, count, deepest);
            }
        }
    }

    // ------------------------------------------------------------------
    // WHERE-USED
    // ------------------------------------------------------------------

    /**
     * WHERE-USED: every assembly that uses this part directly.
     */
    public static String whereUsed(String partId) throws IOException {
        if (PartMaster.findRecord(partId) == null) {
            return "STATUS=NOT-FOUND\nPART_ID=" + partId + "\n";
        }
        Vector recs = RecordFile.readAll("BOM.DAT");
        StringBuffer items = new StringBuffer();
        int count = 0;
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (!RecordFile.field(rec, 11, 20).equals(partId)) {
                continue;
            }
            String parent = RecordFile.field(rec, 1, 10);
            String pr = PartMaster.findRecord(parent);
            count++;
            items.append("ITEM_").append(count).append("_PARENT_ID=").append(parent).append("\n");
            items.append("ITEM_").append(count).append("_DESCRIPTION=")
                 .append(pr == null ? "" : RecordFile.field(pr, 11, 40)).append("\n");
            items.append("ITEM_").append(count).append("_QTY_PER=").append(RecordFile.num(rec, 21, 25)).append("\n");
        }
        return "STATUS=OK\nPART_ID=" + partId + "\nCOUNT=" + count + "\n" + items.toString();
    }

    // ------------------------------------------------------------------
    // CALC-ROLLED-COST
    // ------------------------------------------------------------------

    /** Standard unit cost from the part master, in cents. */
    static long standardCents(String partId) throws IOException {
        String pr = PartMaster.findRecord(partId);
        return pr == null ? 0 : RecordFile.num(pr, 61, 69);
    }

    /** Labor for one unit, in cents: (setup / STD_LOT + run) minutes at the machine rate. */
    static long laborCents(String partId) throws IOException {
        Vector steps = Routing.stepsFor(partId);
        long scaled = 0;   // cents x 60 x STD_LOT
        for (int i = 0; i < steps.size(); i++) {
            String rec = (String) steps.elementAt(i);
            int setup = RecordFile.num(rec, 20, 23);
            int run = RecordFile.num(rec, 24, 27);
            scaled += (long) (setup + run * STD_LOT) * Routing.rateFor(RecordFile.field(rec, 14, 19));
        }
        long div = 60L * STD_LOT;
        return (scaled + div / 2) / div;
    }

    /** Rolled-up cost of one unit: bought parts at standard, made parts = components + labor. */
    static long rolledCents(String partId, int level) throws IOException {
        if (level > MAX_LEVELS) {
            throw new BomLoop();
        }
        Vector kids = children(partId);
        if (kids.size() == 0) {
            return standardCents(partId);
        }
        long total = laborCents(partId);
        for (int i = 0; i < kids.size(); i++) {
            String rec = (String) kids.elementAt(i);
            total += RecordFile.num(rec, 21, 25) * rolledCents(RecordFile.field(rec, 11, 20), level + 1);
        }
        return total;
    }

    /**
     * CALC-ROLLED-COST: what one unit really costs (materials rolled up through
     * every level, plus machine labor) against the standard cost on file.
     */
    public static String calcRolledCost(String partId) throws IOException {
        if (PartMaster.findRecord(partId) == null) {
            return "STATUS=NOT-FOUND\nPART_ID=" + partId + "\n";
        }
        Vector kids = children(partId);
        StringBuffer items = new StringBuffer();
        long material = 0;
        try {
            for (int i = 0; i < kids.size(); i++) {
                String rec = (String) kids.elementAt(i);
                String comp = RecordFile.field(rec, 11, 20);
                int per = RecordFile.num(rec, 21, 25);
                long unit = rolledCents(comp, 2);
                material += unit * per;
                int n = i + 1;
                items.append("ITEM_").append(n).append("_COMPONENT_ID=").append(comp).append("\n");
                items.append("ITEM_").append(n).append("_QTY_PER=").append(per).append("\n");
                items.append("ITEM_").append(n).append("_UNIT_COST=").append(money(unit)).append("\n");
                items.append("ITEM_").append(n).append("_EXTENDED_COST=").append(money(unit * per)).append("\n");
            }
        } catch (BomLoop e) {
            return "STATUS=BOM-LOOP\nPART_ID=" + partId + "\n";
        }
        long labor = kids.size() == 0 ? 0 : laborCents(partId);
        long rolled = kids.size() == 0 ? standardCents(partId) : material + labor;
        long std = standardCents(partId);
        return "STATUS=OK\nPART_ID=" + partId
            + "\nMAKE_OR_BUY=" + (kids.size() == 0 ? "BUY" : "MAKE")
            + "\nMATERIAL_COST=" + money(material)
            + "\nLABOR_COST=" + money(labor)
            + "\nROLLED_COST=" + money(rolled)
            + "\nSTANDARD_COST=" + money(std)
            + "\nVARIANCE=" + money(rolled - std)
            + "\nCOUNT=" + kids.size() + "\n" + items.toString();
    }

    // ------------------------------------------------------------------
    // PLAN-REPLENISHMENT
    // ------------------------------------------------------------------

    /**
     * PLAN-REPLENISHMENT: to have QTY units of a part, what must be made and
     * what must be bought. Stock is used up level by level (a part that
     * appears twice is netted once). The total lead time is the longest
     * chain of lead times through the parts that need action.
     */
    public static String planReplenishment(String partId, int qty) throws IOException {
        if (qty <= 0 || qty > 9999) {
            return "STATUS=INVALID-QTY\nQTY=" + qty + "\n";
        }
        if (PartMaster.findRecord(partId) == null) {
            return "STATUS=NOT-FOUND\nPART_ID=" + partId + "\n";
        }
        Hashtable avail = new Hashtable();
        Vector lines = new Vector();
        long[] buyCost = new long[1];
        int lead;
        try {
            lead = plan(partId, qty, 0, avail, lines, buyCost);
        } catch (BomLoop e) {
            return "STATUS=BOM-LOOP\nPART_ID=" + partId + "\n";
        }
        StringBuffer items = new StringBuffer();
        int makes = 0;
        int buys = 0;
        for (int i = 0; i < lines.size(); i++) {
            String[] l = (String[]) lines.elementAt(i);
            int n = i + 1;
            if ("MAKE".equals(l[2])) makes++; else buys++;
            items.append("ITEM_").append(n).append("_PART_ID=").append(l[0]).append("\n");
            items.append("ITEM_").append(n).append("_LEVEL=").append(l[1]).append("\n");
            items.append("ITEM_").append(n).append("_ACTION=").append(l[2]).append("\n");
            items.append("ITEM_").append(n).append("_QTY=").append(l[3]).append("\n");
            items.append("ITEM_").append(n).append("_LEAD_TIME_DAYS=").append(l[4]).append("\n");
        }
        return "STATUS=OK\nPART_ID=" + partId + "\nQTY=" + qty
            + "\nMAKE_LINES=" + makes
            + "\nBUY_LINES=" + buys
            + "\nBUY_COST=" + money(buyCost[0])
            + "\nTOTAL_LEAD_DAYS=" + lead
            + "\nCOUNT=" + lines.size() + "\n" + items.toString();
    }

    /** Nets one requirement; returns the lead days this branch adds. */
    static int plan(String partId, int gross, int level, Hashtable avail, Vector lines, long[] buyCost)
            throws IOException {
        if (level > MAX_LEVELS) {
            throw new BomLoop();
        }
        String pr = PartMaster.findRecord(partId);
        if (!avail.containsKey(partId)) {
            avail.put(partId, new Integer(pr == null ? 0 : RecordFile.num(pr, 44, 50)));
        }
        int have = ((Integer) avail.get(partId)).intValue();
        int use = Math.min(have, gross);
        avail.put(partId, new Integer(have - use));
        int net = gross - use;
        if (net == 0) {
            return 0;
        }
        int own = pr == null ? 0 : RecordFile.num(pr, 58, 60);
        Vector kids = children(partId);
        String action = kids.size() > 0 ? "MAKE" : "BUY";
        lines.addElement(new String[] { partId, String.valueOf(level), action,
                                        String.valueOf(net), String.valueOf(own) });
        if (kids.size() == 0) {
            buyCost[0] += (long) net * (pr == null ? 0 : RecordFile.num(pr, 61, 69));
            return own;
        }
        int longest = 0;
        for (int i = 0; i < kids.size(); i++) {
            String rec = (String) kids.elementAt(i);
            int sub = plan(RecordFile.field(rec, 11, 20), net * RecordFile.num(rec, 21, 25),
                           level + 1, avail, lines, buyCost);
            if (sub > longest) {
                longest = sub;
            }
        }
        return own + longest;
    }
}
