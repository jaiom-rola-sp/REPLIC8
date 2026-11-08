/*
 * WorkOrders.java
 *
 * Shop floor work order inquiry and entry.
 *
 * WORKORD.DAT record layout (39 bytes):
 *   01-08  WORK-ORDER-ID
 *   09-18  PART-ID
 *   19-24  QTY-ORDERED       9(6)
 *   25-32  DUE-DATE          YYYYMMDD
 *   33     STATUS            O = open, H = on hold, C = closed
 *   34-39  MACHINE-ID
 *
 * CHANGE LOG
 *   1999-06-21  RTH  Original version.
 *   2003-01-08  DJS  Hold status added for quality holds.
 *   2004-10-12  KLM  createWorkOrder appends to WORKORD.DAT.
 */
package com.mpp.mrp;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.util.Vector;

public class WorkOrders {

    /** Line-protocol names (see Main.runQueue). createWorkOrder WRITES. */
    static final String[][] ENTRY = {
        { "getWorkOrder", "GET-WORK-ORDER" },
        { "listOpenWorkOrders", "LIST-OPEN-WORK-ORDERS" },
        { "createWorkOrder", "CREATE-WORK-ORDER" },
    };

    static String statusName(String code) {
        if ("O".equals(code)) return "OPEN";
        if ("H".equals(code)) return "ON-HOLD";
        if ("C".equals(code)) return "CLOSED";
        return "UNKNOWN";
    }

    static String isoDate(String yyyymmdd) {
        if (yyyymmdd.length() != 8) return yyyymmdd;
        return yyyymmdd.substring(0, 4) + "-" + yyyymmdd.substring(4, 6) + "-" + yyyymmdd.substring(6, 8);
    }

    /**
     * GET-WORK-ORDER: one work order with its part, quantity, due date and machine.
     */
    public static String getWorkOrder(String woId) throws IOException {
        Vector recs = RecordFile.readAll("WORKORD.DAT");
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (RecordFile.field(rec, 1, 8).equals(woId)) {
                return "STATUS=OK\n"
                    + "WORK_ORDER_ID=" + RecordFile.field(rec, 1, 8) + "\n"
                    + "PART_ID=" + RecordFile.field(rec, 9, 18) + "\n"
                    + "QTY_ORDERED=" + RecordFile.num(rec, 19, 24) + "\n"
                    + "DUE_DATE=" + isoDate(RecordFile.field(rec, 25, 32)) + "\n"
                    + "WO_STATUS=" + statusName(RecordFile.field(rec, 33, 33)) + "\n"
                    + "MACHINE_ID=" + RecordFile.field(rec, 34, 39) + "\n";
            }
        }
        return "STATUS=NOT-FOUND\nWORK_ORDER_ID=" + woId + "\n";
    }

    /**
     * LIST-OPEN-WORK-ORDERS: every work order that is open or on hold.
     */
    public static String listOpenWorkOrders() throws IOException {
        Vector recs = RecordFile.readAll("WORKORD.DAT");
        StringBuffer items = new StringBuffer();
        int count = 0;
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            String st = RecordFile.field(rec, 33, 33);
            if ("C".equals(st)) {
                continue;
            }
            count++;
            items.append("ITEM_").append(count).append("_WORK_ORDER_ID=")
                 .append(RecordFile.field(rec, 1, 8)).append("\n");
            items.append("ITEM_").append(count).append("_PART_ID=")
                 .append(RecordFile.field(rec, 9, 18)).append("\n");
            items.append("ITEM_").append(count).append("_DUE_DATE=")
                 .append(isoDate(RecordFile.field(rec, 25, 32))).append("\n");
            items.append("ITEM_").append(count).append("_WO_STATUS=")
                 .append(statusName(st)).append("\n");
        }
        return "STATUS=OK\nCOUNT=" + count + "\n" + items.toString();
    }

    /**
     * CREATE-WORK-ORDER: appends a new open work order to WORKORD.DAT.
     * This changes data. It exists so the gateway's write-blocking can be shown.
     */
    public static String createWorkOrder(String woId, String partId, int qty,
                                         String dueYyyymmdd, String machineId) throws IOException {
        if (PartMaster.findRecord(partId) == null) {
            return "STATUS=NOT-FOUND\nPART_ID=" + partId + "\n";
        }
        StringBuffer rec = new StringBuffer();
        rec.append(pad(woId, 8)).append(pad(partId, 10)).append(zeros(qty, 6))
           .append(pad(dueYyyymmdd, 8)).append("O").append(pad(machineId, 6)).append("\n");
        FileWriter out = new FileWriter(new File(RecordFile.dataDir(), "WORKORD.DAT"), true);
        try {
            out.write(rec.toString());
        } finally {
            out.close();
        }
        return "STATUS=OK\nWORK_ORDER_ID=" + woId + "\n";
    }

    static String pad(String s, int len) {
        StringBuffer b = new StringBuffer(s == null ? "" : s);
        if (b.length() > len) b.setLength(len);
        while (b.length() < len) b.append(' ');
        return b.toString();
    }

    static String zeros(int n, int len) {
        StringBuffer b = new StringBuffer(String.valueOf(n));
        while (b.length() < len) b.insert(0, '0');
        return b.toString();
    }
}
