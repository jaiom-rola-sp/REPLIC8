/*
 * RecordFile.java
 *
 * Midwest Precision Parts - MRP/400 shop floor system (legacy-style demo)
 *
 * Reads fixed-width record files from the data directory.
 * The data directory is taken from the system property "mrp.data",
 * or defaults to "data" relative to the working directory.
 *
 * CHANGE LOG
 *   1999-03-02  RTH  Original version for JDK 1.1 port of RPG system.
 *   2003-07-18  KLM  Added field() helper, removed StringTokenizer use.
 */
package com.mpp.mrp;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.util.Vector;

public class RecordFile {

    public static String dataDir() {
        String dir = System.getProperty("mrp.data");
        if (dir == null || dir.length() == 0) {
            dir = "data";
        }
        return dir;
    }

    /** Returns every non-blank line of the file as a Vector of Strings. */
    public static Vector readAll(String fileName) throws IOException {
        Vector lines = new Vector();
        BufferedReader in = new BufferedReader(new FileReader(new File(dataDir(), fileName)));
        try {
            String line;
            while ((line = in.readLine()) != null) {
                if (line.trim().length() > 0) {
                    lines.addElement(line);
                }
            }
        } finally {
            in.close();
        }
        return lines;
    }

    /** Cuts a fixed-width field (1-based start, inclusive end) and trims it. */
    public static String field(String rec, int from, int to) {
        if (rec.length() < from) {
            return "";
        }
        int end = Math.min(to, rec.length());
        return rec.substring(from - 1, end).trim();
    }

    /** Numeric field with leading zeros removed. Non-numeric becomes 0. */
    public static int num(String rec, int from, int to) {
        try {
            return Integer.parseInt(field(rec, from, to));
        } catch (NumberFormatException e) {
            return 0;
        }
    }
}
