/*
 * Machines.java
 *
 * Machine status inquiry for the shop floor board.
 *
 * MACHINES.DAT record layout (39 bytes):
 *   01-06  MACHINE-ID
 *   07-30  MACHINE-NAME
 *   31     STATUS            U = up, D = down, M = maintenance
 *   32-39  LAST-PM-DATE      YYYYMMDD
 *
 * CHANGE LOG
 *   2001-04-04  DJS  Original version.
 */
package com.mpp.mrp;

import java.io.IOException;
import java.util.Vector;

public class Machines {

    /** Line-protocol names (see Main.runQueue). */
    static final String[][] ENTRY = {
        { "getMachineStatus", "GET-MACHINE-STATUS" },
    };

    /**
     * GET-MACHINE-STATUS: whether a machine is up, down or in maintenance.
     */
    public static String getMachineStatus(String machineId) throws IOException {
        Vector recs = RecordFile.readAll("MACHINES.DAT");
        for (int i = 0; i < recs.size(); i++) {
            String rec = (String) recs.elementAt(i);
            if (RecordFile.field(rec, 1, 6).equals(machineId)) {
                String st = RecordFile.field(rec, 31, 31);
                String name = "U".equals(st) ? "UP" : "D".equals(st) ? "DOWN"
                            : "M".equals(st) ? "MAINTENANCE" : "UNKNOWN";
                return "STATUS=OK\n"
                    + "MACHINE_ID=" + RecordFile.field(rec, 1, 6) + "\n"
                    + "MACHINE_NAME=" + RecordFile.field(rec, 7, 30) + "\n"
                    + "MACHINE_STATUS=" + name + "\n"
                    + "LAST_PM_DATE=" + WorkOrders.isoDate(RecordFile.field(rec, 32, 39)) + "\n";
            }
        }
        return "STATUS=NOT-FOUND\nMACHINE_ID=" + machineId + "\n";
    }
}
