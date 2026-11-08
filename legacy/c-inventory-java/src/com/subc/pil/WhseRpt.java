package com.subc.pil;

import java.io.IOException;
import java.util.Vector;

/*
 * WhseRpt - warehouse reports (screen PIL-W2 and the low stock run).
 *
 * CHANGE LOG
 *   2004-04-01  MKB  getWarehouse.
 *   2004-04-19  MKB  listLowStock (replaces the COBOL LOWSTK job).
 *   2006-08-08  TQ   Stock value uses catalog cost, not last PO cost.
 */
public class WhseRpt extends PilRecs {

    static final String TX_WAREHOUSE = "getWarehouse";
    static final String TX_LOWSTOCK = "listLowStock";
    static int lastLowCount = 0;   // was read by the old PIL-W2 screen


    /** One warehouse: stock lines, units, stock value and outbound lanes. */
    static void getWarehouse(String warehouse) throws IOException {
        warehouse = up(warehouse);
        Vector stock = readRecords(STOCK_FILE, 39);
        int lines = 0;
        int units = 0;
        long value = 0;
        for (int i = 0; i < stock.size(); i++) {
            String rec = (String) stock.elementAt(i);
            if (field(rec, 39, 49).equals(warehouse)) {
                lines++;
                int qty = onHand(rec);
                units += qty;
                String cat = findCatalog(field(rec, 0, 10));
                if (cat != null) {
                    value += impliedCents(field(cat, 10, 18)) * qty;
                }
            }
        }
        Vector lanes = readRecords(LANES_FILE, 43);
        Vector out = new Vector();
        for (int i = 0; i < lanes.size(); i++) {
            String rec = (String) lanes.elementAt(i);
            if (field(rec, 0, 10).equals(warehouse)) {
                out.addElement(rec);
            }
        }
        if (lines == 0 && out.size() == 0) {
            System.out.println("FOUND=N");
            System.out.println("WAREHOUSE=" + warehouse);
            return;
        }
        System.out.println("FOUND=Y");
        System.out.println("WAREHOUSE=" + warehouse);
        System.out.println("PART-LINES=" + lines);
        System.out.println("TOTAL-UNITS=" + units);
        System.out.println("STOCK-VALUE-USD=" + money(value));
        System.out.println("BEGIN-ITEMS");
        for (int i = 0; i < out.size(); i++) {
            String rec = (String) out.elementAt(i);
            System.out.println("DESTINATION=" + field(rec, 10, 20));
            System.out.println("CARRIER=" + field(rec, 20, 32));
            System.out.println("TRANSIT-DAYS=" + Integer.parseInt(field(rec, 32, 35)));
            System.out.println("COST-USD=" + money(decimalCents(field(rec, 35, 43))));
            System.out.println("--");
        }
        System.out.println("COUNT=" + out.size());
    }

    /** Stock rows below their reorder point, optionally for one warehouse. */
    static void listLowStock(String warehouse) throws IOException {
        warehouse = up(warehouse);
        Vector stock = readRecords(STOCK_FILE, 39);
        System.out.println("WAREHOUSE=" + (warehouse.length() == 0 ? "ALL" : warehouse));
        System.out.println("BEGIN-ITEMS");
        int count = 0;
        for (int i = 0; i < stock.size(); i++) {
            String rec = (String) stock.elementAt(i);
            String wh = field(rec, 39, 49);
            if (warehouse.length() > 0 && !wh.equals(warehouse)) {
                continue;
            }
            String part = field(rec, 0, 10);
            String cat = findCatalog(part);
            if (cat == null) {
                continue;
            }
            int reorder = Integer.parseInt(field(cat, 23, 27));
            int qty = onHand(rec);
            if (qty < reorder) {
                count++;
                System.out.println("PART-ID=" + part);
                System.out.println("DESCRIPTION=" + field(rec, 10, 34));
                System.out.println("WAREHOUSE=" + wh);
                System.out.println("ON-HAND=" + qty);
                System.out.println("REORDER-POINT=" + reorder);
                System.out.println("SHORTFALL=" + (reorder - qty));
                System.out.println("OPEN-PO-QTY=" + openPurchaseOrders(part)[0]);
                System.out.println("--");
            }
        }
        System.out.println("COUNT=" + count);
    }
}
