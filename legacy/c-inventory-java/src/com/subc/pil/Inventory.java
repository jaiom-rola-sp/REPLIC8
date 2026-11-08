/*
 * ============================================================
 * SUBSIDIARY C - PARTS INVENTORY AND LOGISTICS (PIL)
 * Industrial logistics: replacement-part stock and shipping lanes.
 * Written 2003 for J2SE 1.4 (no generics). Demo stand-in for
 * REPLIC8 (FR-10). Read-only lookups.
 * Release 2 (2004): catalog, suppliers, purchase orders,
 * multi-warehouse stock and delivered-cost quotes.
 * Line protocol: command on line 1, KEY=VALUE lines, END.
 * ============================================================
 */
package com.subc.pil;

import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.text.DecimalFormat;
import java.util.Hashtable;
import java.util.Vector;

public class Inventory {

    private static final String STOCK_FILE = "data/stock.dat";
    private static final String LANES_FILE = "data/lanes.dat";

    public static void main(String[] args) throws IOException {
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in));
        String cmd = in.readLine();
        if (cmd == null) {
            System.exit(1);
        }
        Hashtable params = new Hashtable();
        String line;
        int guard = 0;
        while ((line = in.readLine()) != null && guard++ < 20) {
            if (line.trim().equals("END") || line.trim().length() == 0) {
                break;
            }
            int eq = line.indexOf('=');
            if (eq <= 0) {
                continue;
            }
            params.put(line.substring(0, eq).trim(), line.substring(eq + 1).trim());
        }
        String partId = params.containsKey("PART-ID") ? (String) params.get("PART-ID") : "";
        String destination = params.containsKey("DESTINATION") ? (String) params.get("DESTINATION") : "";
        String warehouse = params.containsKey("WAREHOUSE") ? (String) params.get("WAREHOUSE") : "";
        String supplierId = params.containsKey("SUPPLIER-ID") ? (String) params.get("SUPPLIER-ID") : "";
        String status = params.containsKey("STATUS") ? (String) params.get("STATUS") : "";
        String quantity = params.containsKey("QUANTITY") ? (String) params.get("QUANTITY") : "";

        cmd = cmd.trim();
        if ("checkStock".equalsIgnoreCase(cmd)) {
            checkStock(partId);
        } else if ("getShippingOptions".equalsIgnoreCase(cmd)) {
            getShippingOptions(partId, destination);
        } else if ("getWarehouse".equalsIgnoreCase(cmd)) {
            getWarehouse(warehouse);
        } else if ("listLowStock".equalsIgnoreCase(cmd)) {
            listLowStock(warehouse);
        } else if ("getSupplier".equalsIgnoreCase(cmd)) {
            getSupplier(supplierId);
        } else if ("getPartSourcing".equalsIgnoreCase(cmd)) {
            getPartSourcing(partId);
        } else if ("listPurchaseOrders".equalsIgnoreCase(cmd)) {
            listPurchaseOrders(partId, status);
        } else if ("getCheapestShipping".equalsIgnoreCase(cmd)) {
            getCheapestShipping(partId, destination);
        } else if ("quoteDelivery".equalsIgnoreCase(cmd)) {
            quoteDelivery(partId, destination, quantity);
        } else {
            System.out.println("ERROR=UNKNOWN-COMMAND");
            System.exit(2);
        }
    }

    /**
     * Find a part in the stock file.
     * Returns { partId, description, onHand, warehouse } or null.
     */
    static String[] findPart(String partId) throws IOException {
        BufferedReader reader = openData(STOCK_FILE);
        try {
            String rec;
            while ((rec = reader.readLine()) != null) {
                if (rec.length() < 39) {
                    continue;
                }
                String part = rec.substring(0, 10).trim();
                if (part.equals(partId)) {
                    String warehouse = rec.length() > 39 ? rec.substring(39).trim() : "";
                    return new String[] { part, rec.substring(10, 34).trim(), rec.substring(34, 39).trim(), warehouse };
                }
            }
        } finally {
            reader.close();
        }
        return null;
    }

    /** How many of a part are on hand, and where. */
    static void checkStock(String partId) throws IOException {
        String[] part = findPart(partId);
        if (part == null) {
            System.out.println("FOUND=N");
            System.out.println("PART-ID=" + partId);
            return;
        }
        System.out.println("FOUND=Y");
        System.out.println("PART-ID=" + part[0]);
        System.out.println("DESCRIPTION=" + part[1]);
        System.out.println("ON-HAND=" + Integer.parseInt(part[2]));
        System.out.println("WAREHOUSE=" + part[3]);
    }

    /** Shipping lanes from the part's warehouse to a destination region. */
    static void getShippingOptions(String partId, String destination) throws IOException {
        String[] part = findPart(partId);
        if (part == null) {
            System.out.println("FOUND=N");
            System.out.println("BEGIN-ITEMS");
            System.out.println("COUNT=0");
            return;
        }
        String warehouse = part[3];
        System.out.println("FOUND=Y");
        System.out.println("WAREHOUSE=" + warehouse);
        System.out.println("DESTINATION=" + destination);
        System.out.println("BEGIN-ITEMS");

        Vector lanes = new Vector();
        BufferedReader reader = openData(LANES_FILE);
        try {
            String rec;
            while ((rec = reader.readLine()) != null) {
                if (rec.length() < 43) {
                    continue;
                }
                if (rec.substring(0, 10).trim().equals(warehouse)
                        && rec.substring(10, 20).trim().equals(destination)) {
                    lanes.addElement(rec);
                }
            }
        } finally {
            reader.close();
        }

        DecimalFormat money = new DecimalFormat("0.00");
        for (int i = 0; i < lanes.size(); i++) {
            String rec = (String) lanes.elementAt(i);
            StringBuffer out = new StringBuffer();
            out.append("CARRIER=").append(rec.substring(20, 32).trim()).append('\n');
            out.append("TRANSIT-DAYS=").append(Integer.parseInt(rec.substring(32, 35).trim())).append('\n');
            out.append("COST-USD=").append(money.format(Double.parseDouble(rec.substring(35, 43).trim()))).append('\n');
            out.append("--");
            System.out.println(out.toString());
        }
        System.out.println("COUNT=" + lanes.size());
    }

    private static BufferedReader openData(String path) {
        try {
            return new BufferedReader(new FileReader(path));
        } catch (FileNotFoundException e) {
            System.out.println("ERROR=DATA-FILE-UNAVAILABLE");
            System.exit(3);
            return null;
        }
    }

    /* ============================================================
     * Release 2 (2004): catalog, suppliers, purchase orders,
     * multi-warehouse stock and delivery quotes. Read-only.
     * ============================================================ */

    private static final String CATALOG_FILE = "data/catalog.dat";
    private static final String SUPPLIERS_FILE = "data/suppliers.dat";
    private static final String PO_FILE = "data/purchase_orders.dat";
    /** Days to pick and pack an order before the carrier collects it. */
    private static final int HANDLING_DAYS = 1;

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

    /** Catalog: PART(10) UNIT-COST 9(6)V99 WEIGHT 9(5) REORDER 9(4) SUPPLIER(8) CATEGORY(10). */
    static String findCatalog(String partId) throws IOException {
        Vector recs = readRecords(CATALOG_FILE, 35);
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (field(rec, 0, 10).equals(partId)) {
                return rec;
            }
        }
        return null;
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

    /** Where a part comes from: cost, supplier, stock by warehouse, open orders. */
    static void getPartSourcing(String partId) throws IOException {
        partId = up(partId);
        String cat = findCatalog(partId);
        if (cat == null) {
            System.out.println("FOUND=N");
            System.out.println("PART-ID=" + partId);
            return;
        }
        Vector rows = stockRows(partId);
        int total = 0;
        for (int i = 0; i < rows.size(); i++) {
            total += onHand((String) rows.elementAt(i));
        }
        int reorder = Integer.parseInt(field(cat, 23, 27));
        String supplierId = field(cat, 27, 35);
        String sup = findSupplier(supplierId);
        String[] po = openPurchaseOrders(partId);
        System.out.println("FOUND=Y");
        System.out.println("PART-ID=" + partId);
        if (rows.size() > 0) {
            System.out.println("DESCRIPTION=" + field((String) rows.elementAt(0), 10, 34));
        }
        System.out.println("CATEGORY=" + field(cat, 35, 45));
        System.out.println("UNIT-COST-USD=" + money(impliedCents(field(cat, 10, 18))));
        System.out.println("WEIGHT-LB=" + Integer.parseInt(field(cat, 18, 23)));
        System.out.println("REORDER-POINT=" + reorder);
        System.out.println("TOTAL-ON-HAND=" + total);
        System.out.println("BELOW-REORDER=" + (total < reorder ? "Y" : "N"));
        System.out.println("SUPPLIER-ID=" + supplierId);
        if (sup != null) {
            System.out.println("SUPPLIER-NAME=" + field(sup, 8, 32));
            System.out.println("LEAD-DAYS=" + Integer.parseInt(field(sup, 46, 49)));
        }
        System.out.println("OPEN-PO-QTY=" + po[0]);
        System.out.println("NEXT-PO-EXPECTED=" + (po[1].length() == 0 ? "NONE" : po[1]));
        System.out.println("BEGIN-ITEMS");
        for (int i = 0; i < rows.size(); i++) {
            String rec = (String) rows.elementAt(i);
            System.out.println("WAREHOUSE=" + field(rec, 39, 49));
            System.out.println("ON-HAND=" + onHand(rec));
            System.out.println("--");
        }
        System.out.println("COUNT=" + rows.size());
    }

    /** Purchase orders, optionally for one part and/or one status. */
    static void listPurchaseOrders(String partId, String status) throws IOException {
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

    /** Cheapest lane to a region from any warehouse that has the part. */
    static void getCheapestShipping(String partId, String destination) throws IOException {
        partId = up(partId);
        destination = up(destination);
        Vector rows = stockRows(partId);
        if (rows.size() == 0) {
            System.out.println("FOUND=N");
            System.out.println("PART-ID=" + partId);
            return;
        }
        Vector lanes = readRecords(LANES_FILE, 43);
        String best = null;
        int bestOnHand = 0;
        int checked = 0;
        for (int r = 0; r < rows.size(); r++) {
            String stock = (String) rows.elementAt(r);
            int qty = onHand(stock);
            if (qty <= 0) {
                continue;
            }
            String wh = field(stock, 39, 49);
            for (int i = 0; i < lanes.size(); i++) {
                String lane = (String) lanes.elementAt(i);
                if (!field(lane, 0, 10).equals(wh) || !field(lane, 10, 20).equals(destination)) {
                    continue;
                }
                checked++;
                if (best == null || cheaper(lane, best)) {
                    best = lane;
                    bestOnHand = qty;
                }
            }
        }
        System.out.println("FOUND=Y");
        System.out.println("PART-ID=" + partId);
        System.out.println("DESTINATION=" + destination);
        System.out.println("ROUTES-CHECKED=" + checked);
        if (best == null) {
            System.out.println("ROUTE=NONE");
            return;
        }
        System.out.println("ROUTE=FOUND");
        System.out.println("WAREHOUSE=" + field(best, 0, 10));
        System.out.println("ON-HAND=" + bestOnHand);
        System.out.println("CARRIER=" + field(best, 20, 32));
        System.out.println("TRANSIT-DAYS=" + Integer.parseInt(field(best, 32, 35)));
        System.out.println("COST-USD=" + money(decimalCents(field(best, 35, 43))));
    }

    static boolean cheaper(String lane, String than) {
        long a = decimalCents(field(lane, 35, 43));
        long b = decimalCents(field(than, 35, 43));
        if (a != b) {
            return a < b;
        }
        return Integer.parseInt(field(lane, 32, 35)) < Integer.parseInt(field(than, 32, 35));
    }

    /**
     * Full delivered quote for QUANTITY of a part to a region. Every warehouse
     * holding enough stock is priced over every lane, plus a direct order from
     * the supplier. The cheapest option wins (ties go to the faster one).
     * Delivery days = lane transit + HANDLING_DAYS, or the supplier lead time.
     */
    static void quoteDelivery(String partId, String destination, String quantityText) throws IOException {
        partId = up(partId);
        destination = up(destination);
        int quantity;
        try {
            quantity = Integer.parseInt(quantityText.trim());
        } catch (NumberFormatException e) {
            quantity = -1;
        }
        if (quantity < 1 || quantity > 9999) {
            System.out.println("ERROR=BAD-QUANTITY");
            return;
        }
        String cat = findCatalog(partId);
        if (cat == null) {
            System.out.println("FOUND=N");
            System.out.println("PART-ID=" + partId);
            return;
        }
        long unit = impliedCents(field(cat, 10, 18));
        long partCost = unit * quantity;

        // option = { source, shipFrom, carrier, days, freightCents }
        Vector options = new Vector();
        Vector rows = stockRows(partId);
        Vector lanes = readRecords(LANES_FILE, 43);
        for (int r = 0; r < rows.size(); r++) {
            String stock = (String) rows.elementAt(r);
            if (onHand(stock) < quantity) {
                continue;
            }
            String wh = field(stock, 39, 49);
            for (int i = 0; i < lanes.size(); i++) {
                String lane = (String) lanes.elementAt(i);
                if (field(lane, 0, 10).equals(wh) && field(lane, 10, 20).equals(destination)) {
                    options.addElement(new Object[] { "STOCK", wh, field(lane, 20, 32),
                        new Integer(Integer.parseInt(field(lane, 32, 35)) + HANDLING_DAYS),
                        new Long(decimalCents(field(lane, 35, 43))) });
                }
            }
        }
        String supplierId = field(cat, 27, 35);
        String sup = findSupplier(supplierId);
        if (sup != null) {
            options.addElement(new Object[] { "SUPPLIER", supplierId, "SUPPLIER-DIRECT",
                new Integer(Integer.parseInt(field(sup, 46, 49))),
                new Long(impliedCents(field(sup, 52, 59))) });
        }
        // insertion sort: cheapest first, then fastest
        for (int i = 1; i < options.size(); i++) {
            Object[] cur = (Object[]) options.elementAt(i);
            int j = i - 1;
            while (j >= 0 && better(cur, (Object[]) options.elementAt(j))) {
                options.setElementAt(options.elementAt(j), j + 1);
                j--;
            }
            options.setElementAt(cur, j + 1);
        }

        System.out.println("FOUND=Y");
        System.out.println("PART-ID=" + partId);
        System.out.println("DESTINATION=" + destination);
        System.out.println("QUANTITY=" + quantity);
        System.out.println("UNIT-COST-USD=" + money(unit));
        System.out.println("PART-COST-USD=" + money(partCost));
        if (options.size() == 0) {
            System.out.println("SOURCE=NONE");
        } else {
            Object[] best = (Object[]) options.elementAt(0);
            long freight = ((Long) best[4]).longValue();
            System.out.println("SOURCE=" + best[0]);
            System.out.println("SHIP-FROM=" + best[1]);
            System.out.println("CARRIER=" + best[2]);
            System.out.println("DELIVERY-DAYS=" + best[3]);
            System.out.println("FREIGHT-USD=" + money(freight));
            System.out.println("TOTAL-USD=" + money(partCost + freight));
        }
        System.out.println("BEGIN-ITEMS");
        for (int i = 0; i < options.size(); i++) {
            Object[] o = (Object[]) options.elementAt(i);
            long freight = ((Long) o[4]).longValue();
            System.out.println("SOURCE=" + o[0]);
            System.out.println("SHIP-FROM=" + o[1]);
            System.out.println("CARRIER=" + o[2]);
            System.out.println("DELIVERY-DAYS=" + o[3]);
            System.out.println("FREIGHT-USD=" + money(freight));
            System.out.println("TOTAL-USD=" + money(partCost + freight));
            System.out.println("--");
        }
        System.out.println("COUNT=" + options.size());
    }

    static boolean better(Object[] a, Object[] b) {
        long fa = ((Long) a[4]).longValue();
        long fb = ((Long) b[4]).longValue();
        if (fa != fb) {
            return fa < fb;
        }
        return ((Integer) a[3]).intValue() < ((Integer) b[3]).intValue();
    }
}
