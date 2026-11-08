/*
 * ============================================================
 * SUBSIDIARY C - PARTS INVENTORY AND LOGISTICS (PIL)
 * Industrial logistics: replacement-part stock and shipping lanes.
 * Written 2003 for J2SE 1.4 (no generics). Demo stand-in for
 * REPLIC8 (FR-10). Read-only lookups.
 * CHANGE LOG
 *   2003-05-12  GDH  Original: checkStock, getShippingOptions.
 *   2003-09-02  GDH  Guard of 20 input lines (batch reader hung, PIL-031).
 *   2004-03-08  MKB  Release 2 commands moved to Sourcing, WhseRpt, Purch.
 *   2004-03-08  MKB  NOTE: helpers here are duplicated in PilRecs (PIL-140).
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
    /** Set -Dpil.debug=Y to trace commands on stderr (never on stdout - the batch reader parses it). */
    static final boolean DEBUG = "Y".equals(System.getProperty("pil.debug"));

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
        } else if (runRelease2(cmd, partId, destination, warehouse, supplierId, status, quantity)) {
            // handled by a release 2 class (2004)
        } else {
            System.out.println("ERROR=UNKNOWN-COMMAND");
            System.exit(2);
        }
    }

    /**
     * Release 2 commands (MKB 2004). Returns false if the command is not one of ours.
     * Order matters: PIL-150 had getCheapestShipping shadowed by a prefix check.
     */
    static boolean runRelease2(String cmd, String partId, String destination, String warehouse,
                               String supplierId, String status, String quantity) throws IOException {
        if (DEBUG) {
            System.err.println("PIL R2 CMD=" + cmd);
        }
        if (WhseRpt.TX_WAREHOUSE.equalsIgnoreCase(cmd)) {
            WhseRpt.getWarehouse(warehouse);
            return true;
        }
        if (WhseRpt.TX_LOWSTOCK.equalsIgnoreCase(cmd)) {
            WhseRpt.listLowStock(warehouse);
            return true;
        }
        if (Purch.TX_SUPPLIER.equalsIgnoreCase(cmd)) {
            Purch.getSupplier(supplierId);
            return true;
        }
        if (Sourcing.TX_SOURCING.equalsIgnoreCase(cmd)) {
            Sourcing.getPartSourcing(partId);
            return true;
        }
        if (Purch.TX_POS.equalsIgnoreCase(cmd)) {
            Purch.listPoLines(partId, status);
            return true;
        }
        if (Sourcing.TX_CHEAPEST.equalsIgnoreCase(cmd)) {
            Sourcing.getCheapestShipping(partId, destination);
            return true;
        }
        if (Sourcing.TX_QUOTE.equalsIgnoreCase(cmd)) {
            Sourcing.quoteDelivery(partId, destination, quantity);
            return true;
        }
        // if ("getBackorders".equalsIgnoreCase(cmd)) { ... }   removed 2006, PIL-205
        return false;
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
}
