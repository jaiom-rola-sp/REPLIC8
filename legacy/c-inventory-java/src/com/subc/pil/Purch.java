package com.subc.pil;

import java.io.IOException;
import java.util.Vector;

/*
 * Purch - supplier and purchase-order inquiry.
 *
 * CHANGE LOG
 *   2004-05-10  MKB  getSupplier, listPoLines (was listPurchaseOrders, renamed
 *                    so the name does not read like a purchase).
 *   2009-12-01  TQ   Status filter on listPoLines.
 */
public class Purch extends PilRecs {

    static final String TX_SUPPLIER = "getSupplier";
    static final String TX_POS = "listPoLines";


    /** One supplier with its terms. */
    static void getSupplier(String supplierId) throws IOException {
        supplierId = up(supplierId);
        String rec = findSupplier(supplierId);
        if (rec == null) {
            System.out.println("FOUND=N");
            System.out.println("SUPPLIER-ID=" + supplierId);
            return;
        }
        Vector catalog = readRecords(CATALOG_FILE, 35);
        int parts = 0;
        for (int i = 0; i < catalog.size(); i++) {
            if (field((String) catalog.elementAt(i), 27, 35).equals(supplierId)) {
                parts++;
            }
        }
        Vector pos = readRecords(PO_FILE, 59);
        int open = 0;
        for (int i = 0; i < pos.size(); i++) {
            String po = (String) pos.elementAt(i);
            if (field(po, 18, 26).equals(supplierId) && field(po, 31, 39).equals("OPEN")) {
                open++;
            }
        }
        System.out.println("FOUND=Y");
        System.out.println("SUPPLIER-ID=" + supplierId);
        System.out.println("NAME=" + field(rec, 8, 32));
        System.out.println("CITY=" + field(rec, 32, 46));
        System.out.println("LEAD-DAYS=" + Integer.parseInt(field(rec, 46, 49)));
        System.out.println("ON-TIME-PCT=" + Integer.parseInt(field(rec, 49, 52)));
        System.out.println("FREIGHT-USD=" + money(impliedCents(field(rec, 52, 59))));
        System.out.println("PARTS-SUPPLIED=" + parts);
        System.out.println("OPEN-POS=" + open);
    }

    /** Purchase orders, optionally for one part and/or one status. */
    static void listPoLines(String partId, String status) throws IOException {
        partId = up(partId);
        status = up(status);
        Vector recs = readRecords(PO_FILE, 59);
        System.out.println("BEGIN-ITEMS");
        int count = 0;
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (partId.length() > 0 && !field(rec, 8, 18).equals(partId)) {
                continue;
            }
            if (status.length() > 0 && !field(rec, 31, 39).equals(status)) {
                continue;
            }
            count++;
            System.out.println("PO-ID=" + field(rec, 0, 8));
            System.out.println("PART-ID=" + field(rec, 8, 18));
            System.out.println("SUPPLIER-ID=" + field(rec, 18, 26));
            System.out.println("QUANTITY=" + Integer.parseInt(field(rec, 26, 31)));
            System.out.println("STATUS=" + field(rec, 31, 39));
            System.out.println("ORDERED=" + field(rec, 39, 49));
            System.out.println("EXPECTED=" + field(rec, 49, 59));
            System.out.println("--");
        }
        System.out.println("COUNT=" + count);
    }
}
