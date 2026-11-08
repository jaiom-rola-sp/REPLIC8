/*
 * Routing.java
 *
 * Routings (which machines a part goes through), machine load and
 * work order readiness for the morning production meeting.
 *
 * ROUTING.DAT record layout (51 bytes):
 *   01-10  PART-ID
 *   11-13  OPERATION-SEQ     9(3)
 *   14-19  MACHINE-ID
 *   20-23  SETUP-MINUTES     9(4)
 *   24-27  RUN-MINUTES       9(4)   per unit
 *   28-51  DESCRIPTION
 *
 * CHANGE LOG
 *   2005-02-14  DJS  Original version (routing inquiry).
 *   2005-08-03  DJS  CALC-MACHINE-HOURS for the shop board.
 *   2006-01-19  KLM  CHECK-WO-READINESS: holds, shortages, machines down.
 *   2006-05-02  KLM  Machine rates moved here from the cost sheet (TEMP).
 */
package com.mpp.mrp;

import java.io.IOException;
import java.util.Hashtable;
import java.util.Vector;

public class Routing {

    /** Line-protocol names (see Main.runQueue). */
    static final String[][] ENTRY = {
        { "getRouting", "GET-ROUTING" },
        { "calcMachineHours", "CALC-MACHINE-HOURS" },
        { "checkWoReadiness", "CHECK-WO-READINESS" },
    };

    /** Hours in one shift. Second shift was cut in 2003. */
    static final int SHIFT_HOURS = 8;

    /** Machine labor+burden rates in cents per hour. TEMP until the cost sheet is online (2006). */
    static Hashtable rates() {
        Hashtable r = new Hashtable();
        r.put("LATHE1", new Integer(9500));
        r.put("MILL02", new Integer(11000));
        r.put("DRILL3", new Integer(6500));
        r.put("WELD01", new Integer(8000));
        return r;
    }

    static int rateFor(String machineId) {
        Integer r = (Integer) rates().get(machineId);
        return r == null ? 7500 : r.intValue();   // shop average
    }

    /** All routing steps for a part, in file order (file is kept in sequence order). */
    static Vector stepsFor(String partId) throws IOException {
        Vector recs = RecordFile.readAll("ROUTING.DAT");
        Vector out = new Vector();
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (RecordFile.field(rec, 1, 10).equals(partId)) {
                out.addElement(rec);
            }
        }
        return out;
    }

    /** UP, DOWN, MAINTENANCE or UNKNOWN. */
    static String machineState(String machineId) throws IOException {
        Vector recs = RecordFile.readAll("MACHINES.DAT");
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (RecordFile.field(rec, 1, 6).equals(machineId)) {
                String st = RecordFile.field(rec, 31, 31);
                return "U".equals(st) ? "UP" : "D".equals(st) ? "DOWN"
                     : "M".equals(st) ? "MAINTENANCE" : "UNKNOWN";
            }
        }
        return "UNKNOWN";
    }

    /** Minutes to tenths of an hour, rounded half up: "12.5". */
    static String hours(int minutes) {
        int tenths = (minutes * 10 + 30) / 60;
        return (tenths / 10) + "." + (tenths % 10);
    }

    /**
     * GET-ROUTING: the operations a part goes through and each machine's state.
     */
    public static String getRouting(String partId) throws IOException {
        if (PartMaster.findRecord(partId) == null) {
            return "STATUS=NOT-FOUND\nPART_ID=" + partId + "\n";
        }
        Vector steps = stepsFor(partId);
        StringBuffer items = new StringBuffer();
        int setup = 0;
        int run = 0;
        for (int i = 0; i < steps.size(); i++) {
            String rec = (String) steps.elementAt(i);
            int n = i + 1;
            String mach = RecordFile.field(rec, 14, 19);
            setup += RecordFile.num(rec, 20, 23);
            run += RecordFile.num(rec, 24, 27);
            items.append("ITEM_").append(n).append("_SEQ=").append(RecordFile.num(rec, 11, 13)).append("\n");
            items.append("ITEM_").append(n).append("_MACHINE_ID=").append(mach).append("\n");
            items.append("ITEM_").append(n).append("_MACHINE_STATUS=").append(machineState(mach)).append("\n");
            items.append("ITEM_").append(n).append("_DESCRIPTION=").append(RecordFile.field(rec, 28, 51)).append("\n");
            items.append("ITEM_").append(n).append("_SETUP_MIN=").append(RecordFile.num(rec, 20, 23)).append("\n");
            items.append("ITEM_").append(n).append("_RUN_MIN=").append(RecordFile.num(rec, 24, 27)).append("\n");
        }
        return "STATUS=OK\nPART_ID=" + partId
            + "\nMAKE_OR_BUY=" + (steps.size() > 0 ? "MAKE" : "BUY")
            + "\nTOTAL_SETUP_MIN=" + setup
            + "\nRUN_MIN_PER_UNIT=" + run
            + "\nCOUNT=" + steps.size() + "\n" + items.toString();
    }

    /**
     * CALC-MACHINE-HOURS: hours of open work queued on one machine.
     * Load per order = setup + run x qty for every routing step on that machine.
     */
    public static String calcMachineHours(String machineId) throws IOException {
        String state = machineState(machineId);
        if ("UNKNOWN".equals(state)) {
            return "STATUS=NOT-FOUND\nMACHINE_ID=" + machineId + "\n";
        }
        Vector wos = RecordFile.readAll("WORKORD.DAT");
        StringBuffer items = new StringBuffer();
        int count = 0;
        int totalMin = 0;
        for (int i = 0; i < wos.size(); i++) {
            String wo = (String) wos.elementAt(i);
            String st = RecordFile.field(wo, 33, 33);
            if (!"O".equals(st) && !"H".equals(st)) {
                continue;
            }
            String part = RecordFile.field(wo, 9, 18);
            int qty = RecordFile.num(wo, 19, 24);
            Vector steps = stepsFor(part);
            int min = 0;
            for (int s = 0; s < steps.size(); s++) {
                String rec = (String) steps.elementAt(s);
                if (RecordFile.field(rec, 14, 19).equals(machineId)) {
                    min += RecordFile.num(rec, 20, 23) + RecordFile.num(rec, 24, 27) * qty;
                }
            }
            if (min == 0) {
                continue;
            }
            count++;
            totalMin += min;
            items.append("ITEM_").append(count).append("_WORK_ORDER_ID=").append(RecordFile.field(wo, 1, 8)).append("\n");
            items.append("ITEM_").append(count).append("_PART_ID=").append(part).append("\n");
            items.append("ITEM_").append(count).append("_QTY=").append(qty).append("\n");
            items.append("ITEM_").append(count).append("_WO_STATUS=").append(WorkOrders.statusName(st)).append("\n");
            items.append("ITEM_").append(count).append("_DUE_DATE=")
                 .append(WorkOrders.isoDate(RecordFile.field(wo, 25, 32))).append("\n");
            items.append("ITEM_").append(count).append("_LOAD_HOURS=").append(hours(min)).append("\n");
        }
        int shiftMin = SHIFT_HOURS * 60;
        int days = (totalMin + shiftMin - 1) / shiftMin;
        return "STATUS=OK\nMACHINE_ID=" + machineId
            + "\nMACHINE_STATUS=" + state
            + "\nLOAD_HOURS=" + hours(totalMin)
            + "\nSHIFT_HOURS=" + SHIFT_HOURS
            + "\nSHIFTS_OF_WORK=" + days
            + "\nCOUNT=" + count + "\n" + items.toString();
    }

    /**
     * CHECK-WO-READINESS: can this work order start today? Lists every blocker:
     * the order's own status, component shortages, and machines that are not up.
     */
    public static String checkWoReadiness(String woId) throws IOException {
        Vector wos = RecordFile.readAll("WORKORD.DAT");
        String wo = null;
        for (int i = 0; i < wos.size(); i++) {
            String rec = (String) wos.elementAt(i);
            if (RecordFile.field(rec, 1, 8).equals(woId)) {
                wo = rec;
                break;
            }
        }
        if (wo == null) {
            return "STATUS=NOT-FOUND\nWORK_ORDER_ID=" + woId + "\n";
        }
        String part = RecordFile.field(wo, 9, 18);
        int qty = RecordFile.num(wo, 19, 24);
        String st = RecordFile.field(wo, 33, 33);
        StringBuffer items = new StringBuffer();
        int n = 0;
        if (!"O".equals(st)) {
            n++;
            items.append(blocker(n, "ORDER", woId, WorkOrders.statusName(st)));
        }
        Vector bom = RecordFile.readAll("BOM.DAT");
        for (int i = 0; i < bom.size(); i++) {
            String rec = (String) bom.elementAt(i);
            if (!RecordFile.field(rec, 1, 10).equals(part)) {
                continue;
            }
            String comp = RecordFile.field(rec, 11, 20);
            int needed = RecordFile.num(rec, 21, 25) * qty;
            String pr = PartMaster.findRecord(comp);
            int onHand = pr == null ? 0 : RecordFile.num(pr, 44, 50);
            if (needed > onHand) {
                n++;
                items.append(blocker(n, "SHORTAGE", comp, "SHORT " + (needed - onHand)));
            }
        }
        Vector steps = stepsFor(part);
        Hashtable seen = new Hashtable();
        for (int i = 0; i < steps.size(); i++) {
            String mach = RecordFile.field((String) steps.elementAt(i), 14, 19);
            if (seen.containsKey(mach)) {
                continue;
            }
            seen.put(mach, mach);
            String ms = machineState(mach);
            if (!"UP".equals(ms)) {
                n++;
                items.append(blocker(n, "MACHINE", mach, ms));
            }
        }
        return "STATUS=OK\nWORK_ORDER_ID=" + woId
            + "\nPART_ID=" + part
            + "\nQTY=" + qty
            + "\nWO_STATUS=" + WorkOrders.statusName(st)
            + "\nREADY=" + (n == 0 ? "Y" : "N")
            + "\nCOUNT=" + n + "\n" + items.toString();
    }

    static String blocker(int n, String type, String id, String detail) {
        return "ITEM_" + n + "_BLOCKER_TYPE=" + type + "\n"
             + "ITEM_" + n + "_BLOCKER_ID=" + id + "\n"
             + "ITEM_" + n + "_DETAIL=" + detail + "\n";
    }
}
