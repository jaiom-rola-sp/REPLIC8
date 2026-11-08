package com.subc.pil;

import java.io.IOException;
import java.util.Vector;

/*
 * Sourcing - where to get a part and what it costs delivered.
 *
 * CHANGE LOG
 *   2004-03-15  MKB  getPartSourcing, getCheapestShipping.
 *   2004-11-02  MKB  quoteDelivery for the field desk (PIL-183).
 *   2005-06-30  JRS  Supplier-direct option added to quotes.
 *   2008-02-11  JRS  Tie on cost now goes to the faster option (PIL-231).
 */
public class Sourcing extends PilRecs {

    // command names the Inventory dispatcher matches on
    static final String TX_SOURCING = "getPartSourcing";
    static final String TX_CHEAPEST = "getCheapestShipping";
    static final String TX_QUOTE = "quoteDelivery";


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
