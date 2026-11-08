package com.subc.pil;

import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.Hashtable;
import java.util.Vector;

/*
 * PilRecs - shared record helpers for PIL release 2.
 *
 * Every R2 class extends this so the helpers can be called without a prefix
 * (MKB 2004: "saves typing"). Inventory.java still has its own copies of
 * some of these from 2003; they were never merged. See PIL-140.
 *
 * CHANGE LOG
 *   2004-03-08  MKB  Pulled out of Inventory.java for release 2.
 *   2004-09-21  MKB  Catalog cache (PIL-177, nightly batch was slow).
 *   2007-01-15  JRS  money() rewritten with longs, fmtMoneyOld kept (PIL-212).
 */
public class PilRecs {

    // duplicated from Inventory (private there) - keep in step by hand
    protected static final String STOCK_FILE = "data/stock.dat";
    protected static final String LANES_FILE = "data/lanes.dat";
    protected static final String CATALOG_FILE = "data/catalog.dat";
    protected static final String SUPPLIERS_FILE = "data/suppliers.dat";
    protected static final String PO_FILE = "data/purchase_orders.dat";
    /** Days to pick and pack an order before the carrier collects it. */
    protected static final int HANDLING_DAYS = 1;
    protected static final int HANDLING_DAYS_HAZMAT = 3;   // PIL-190, never enabled

    /** PIL-177: catalog records by part id. One run = one process, so never stale. */
    private static Hashtable catCache = null;

    static BufferedReader openData(String path) {
        try {
            return new BufferedReader(new FileReader(path));
        } catch (FileNotFoundException e) {
            System.out.println("ERROR=DATA-FILE-UNAVAILABLE");
            System.exit(3);
            return null;
        }
    }

    static String up(String value) {
        return value == null ? "" : value.trim().toUpperCase();
    }

    static String field(String rec, int from, int to) {
        if (rec.length() <= from) {
            return "";
        }
        return rec.substring(from, Math.min(to, rec.length())).trim();
    }

    /** All records of a fixed-width file at least minLength long. */
    static Vector readRecords(String path, int minLength) throws IOException {
        Vector out = new Vector();
        BufferedReader reader = openData(path);
        try {
            String rec;
            while ((rec = reader.readLine()) != null) {
                if (rec.length() >= minLength) {
                    out.addElement(rec);
                }
            }
        } finally {
            reader.close();
        }
        return out;
    }

    /** Implied two-decimal field (9(n)V99) to cents. */
    static long impliedCents(String digits) {
        return Long.parseLong(digits.trim());
    }

    /** "625.50" to cents. */
    static long decimalCents(String text) {
        return Math.round(Double.parseDouble(text.trim()) * 100.0);
    }

    static String money(long cents) {
        long whole = cents / 100;
        long frac = cents % 100;
        return whole + "." + (frac < 10 ? "0" : "") + frac;
    }

    /** @deprecated PIL-212 - rounds 0.005 the wrong way. Use money(long). */
    static String fmtMoneyOld(double amt) {
        java.text.DecimalFormat df = new java.text.DecimalFormat("0.00");
        return df.format(amt);
    }

    /** Catalog: PART(10) UNIT-COST 9(6)V99 WEIGHT 9(5) REORDER 9(4) SUPPLIER(8) CATEGORY(10). */
    static String findCatalog(String partId) throws IOException {
        if (catCache == null) {
            catCache = new Hashtable();
            Vector recs = readRecords(CATALOG_FILE, 35);
            for (int i = 0; i < recs.size(); i++) {
                String rec = (String) recs.elementAt(i);
                String key = field(rec, 0, 10);
                if (!catCache.containsKey(key)) {   // first one wins, same as the old loop
                    catCache.put(key, rec);
                }
            }
        }
        return (String) catCache.get(partId);
        // OLD (pre PIL-177):
        // Vector recs = readRecords(CATALOG_FILE, 35);
        // for (int i = 0; i < recs.size(); i++) { ... }
    }

    /** Suppliers: ID(8) NAME(24) CITY(14) LEAD 9(3) ON-TIME 9(3) FREIGHT 9(5)V99. */
    static String findSupplier(String supplierId) throws IOException {
        Vector recs = readRecords(SUPPLIERS_FILE, 59);
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (field(rec, 0, 8).equals(supplierId)) {
                return rec;
            }
        }
        return null;
    }

    /** Every stock row for a part (a part can sit in several warehouses). */
    static Vector stockRows(String partId) throws IOException {
        Vector out = new Vector();
        Vector recs = readRecords(STOCK_FILE, 39);
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (field(rec, 0, 10).equals(partId)) {
                out.addElement(rec);
            }
        }
        return out;
    }

    static int onHand(String stockRec) {
        return Integer.parseInt(field(stockRec, 34, 39));
    }

    /** Open purchase-order quantity for a part, and the earliest expected date. */
    static String[] openPurchaseOrders(String partId) throws IOException {
        Vector recs = readRecords(PO_FILE, 59);
        int qty = 0;
        String next = "";
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (field(rec, 8, 18).equals(partId) && field(rec, 31, 39).equals("OPEN")) {
                qty += Integer.parseInt(field(rec, 26, 31));
                String expected = field(rec, 49, 59);
                if (next.length() == 0 || expected.compareTo(next) < 0) {
                    next = expected;
                }
            }
        }
        return new String[] { String.valueOf(qty), next };
    }
}
