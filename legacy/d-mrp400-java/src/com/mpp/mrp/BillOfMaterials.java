/*
 * BillOfMaterials.java
 *
 * Single-level bill of materials and material requirements.
 *
 * BOM.DAT record layout (25 bytes):
 *   01-10  PARENT-PART-ID
 *   11-20  COMPONENT-PART-ID
 *   21-25  QTY-PER-ASSEMBLY   9(5)
 *
 * CHANGE LOG
 *   2000-05-14  RTH  Original version (single level only).
 *   2002-09-30  DJS  Added shortage calculation for MRP run.
 */
package com.mpp.mrp;

import java.io.IOException;
import java.util.Vector;

public class BillOfMaterials {

    /** Line-protocol names (see Main.runQueue). Multi-level work is in Planning. */
    static final String[][] ENTRY = {
        { "getBom", "GET-BOM" },
        { "calcMaterialNeeds", "CALC-MATERIAL-NEEDS" },
    };

    /**
     * GET-BOM: the components needed to build one unit of a part.
     */
    public static String getBom(String partId) throws IOException {
        Vector recs = RecordFile.readAll("BOM.DAT");
        StringBuffer items = new StringBuffer();
        int count = 0;
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (RecordFile.field(rec, 1, 10).equals(partId)) {
                count++;
                items.append("ITEM_").append(count).append("_COMPONENT_ID=")
                     .append(RecordFile.field(rec, 11, 20)).append("\n");
                items.append("ITEM_").append(count).append("_QTY_PER=")
                     .append(RecordFile.num(rec, 21, 25)).append("\n");
            }
        }
        if (count == 0) {
            return "STATUS=NOT-FOUND\nPART_ID=" + partId + "\n";
        }
        return "STATUS=OK\nPART_ID=" + partId + "\nCOUNT=" + count + "\n" + items.toString();
    }

    /**
     * CALC-MATERIAL-NEEDS: for building QTY units of a part, how much of
     * each component is needed, how much is on hand, and the shortage.
     */
    public static String calcMaterialNeeds(String partId, int qty) throws IOException {
        if (qty <= 0 || qty > 9999) {
            return "STATUS=INVALID-QTY\nQTY=" + qty + "\n";
        }
        Vector recs = RecordFile.readAll("BOM.DAT");
        StringBuffer items = new StringBuffer();
        int count = 0;
        int shortLines = 0;
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (!RecordFile.field(rec, 1, 10).equals(partId)) {
                continue;
            }
            String comp = RecordFile.field(rec, 11, 20);
            int needed = RecordFile.num(rec, 21, 25) * qty;
            String partRec = PartMaster.findRecord(comp);
            int onHand = partRec == null ? 0 : RecordFile.num(partRec, 44, 50);
            int shortage = needed > onHand ? needed - onHand : 0;
            if (shortage > 0) {
                shortLines++;
            }
            count++;
            items.append("ITEM_").append(count).append("_COMPONENT_ID=").append(comp).append("\n");
            items.append("ITEM_").append(count).append("_QTY_NEEDED=").append(needed).append("\n");
            items.append("ITEM_").append(count).append("_QTY_ON_HAND=").append(onHand).append("\n");
            items.append("ITEM_").append(count).append("_SHORTAGE=").append(shortage).append("\n");
        }
        if (count == 0) {
            return "STATUS=NOT-FOUND\nPART_ID=" + partId + "\n";
        }
        return "STATUS=OK\nPART_ID=" + partId + "\nQTY=" + qty
            + "\nCAN_BUILD=" + (shortLines == 0 ? "Y" : "N")
            + "\nCOUNT=" + count + "\n" + items.toString();
    }
}
