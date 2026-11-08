/*
 * PartMaster.java
 *
 * Part master lookups against PARTS.DAT.
 *
 * PARTS.DAT record layout (70 bytes):
 *   01-10  PART-ID
 *   11-40  DESCRIPTION
 *   41-43  UNIT-OF-MEASURE
 *   44-50  QTY-ON-HAND        9(7)
 *   51-57  REORDER-POINT      9(7)
 *   58-60  LEAD-TIME-DAYS     9(3)
 *   61-69  UNIT-COST-CENTS    9(9)
 *   70     STATUS             A = active, O = obsolete
 *
 * CHANGE LOG
 *   1999-03-02  RTH  Original version.
 *   2001-11-09  RTH  Added below-reorder flag for purchasing report.
 *   2004-02-23  KLM  Obsolete parts now reported instead of skipped.
 */
package com.mpp.mrp;

import java.io.IOException;
import java.util.Vector;

public class PartMaster {

    /** Line-protocol names (see Main.runQueue). */
    static final String[][] ENTRY = {
        { "getPart", "GET-PART" },
        { "listReorder", "LIST-REORDER" },
    };

    /** Finds one part record, or null if it does not exist. */
    public static String findRecord(String partId) throws IOException {
        Vector recs = RecordFile.readAll("PARTS.DAT");
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (RecordFile.field(rec, 1, 10).equals(partId)) {
                return rec;
            }
        }
        return null;
    }

    /**
     * GET-PART: part description, stock, reorder point, lead time and cost.
     */
    public static String getPart(String partId) throws IOException {
        StringBuffer out = new StringBuffer();
        String rec = findRecord(partId);
        if (rec == null) {
            out.append("STATUS=NOT-FOUND\n");
            out.append("PART_ID=").append(partId).append("\n");
            return out.toString();
        }
        int onHand = RecordFile.num(rec, 44, 50);
        int reorder = RecordFile.num(rec, 51, 57);
        int cents = RecordFile.num(rec, 61, 69);

        out.append("STATUS=OK\n");
        out.append("PART_ID=").append(RecordFile.field(rec, 1, 10)).append("\n");
        out.append("DESCRIPTION=").append(RecordFile.field(rec, 11, 40)).append("\n");
        out.append("UOM=").append(RecordFile.field(rec, 41, 43)).append("\n");
        out.append("QTY_ON_HAND=").append(onHand).append("\n");
        out.append("REORDER_POINT=").append(reorder).append("\n");
        out.append("LEAD_TIME_DAYS=").append(RecordFile.num(rec, 58, 60)).append("\n");
        out.append("UNIT_COST=").append(money(cents)).append("\n");
        out.append("PART_STATUS=").append(
            "O".equals(RecordFile.field(rec, 70, 70)) ? "OBSOLETE" : "ACTIVE").append("\n");
        out.append("BELOW_REORDER=").append(onHand < reorder ? "Y" : "N").append("\n");
        return out.toString();
    }

    /**
     * LIST-REORDER: active parts whose stock is below the reorder point.
     */
    public static String listReorder() throws IOException {
        Vector recs = RecordFile.readAll("PARTS.DAT");
        StringBuffer items = new StringBuffer();
        int count = 0;
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if ("O".equals(RecordFile.field(rec, 70, 70))) {
                continue;
            }
            int onHand = RecordFile.num(rec, 44, 50);
            int reorder = RecordFile.num(rec, 51, 57);
            if (onHand < reorder) {
                count++;
                items.append("ITEM_").append(count).append("_PART_ID=")
                     .append(RecordFile.field(rec, 1, 10)).append("\n");
                items.append("ITEM_").append(count).append("_QTY_ON_HAND=")
                     .append(onHand).append("\n");
                items.append("ITEM_").append(count).append("_REORDER_POINT=")
                     .append(reorder).append("\n");
            }
        }
        return "STATUS=OK\nCOUNT=" + count + "\n" + items.toString();
    }

    static String money(int cents) {
        String c = String.valueOf(cents % 100);
        if (c.length() < 2) {
            c = "0" + c;
        }
        return (cents / 100) + "." + c;
    }
}
