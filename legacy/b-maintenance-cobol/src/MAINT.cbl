      *> ============================================================
      *> SUBSIDIARY B - FIELD MAINTENANCE SYSTEM (FMS)
      *> Oilfield services: maintenance requests for well equipment.
      *> Demo stand-in for REPLIC8 (FR-10). Read-only lookups.
      *> CHANGE LOG
      *>   1991-04-02  RJM  ORIGINAL VERSION (REQUEST LOOKUP).
      *>   1993-11-19  RJM  LIST-OPEN-REQUESTS FOR FIELD SUPERVISORS.
      *>   1998-08-30  TKW  Y2K - OPENED DATE NOW CCYY-MM-DD.
      *>   2004-02-11  DLP  RELEASE 2 - WELLS, TECHS, SERVICE HISTORY.
      *>   2006-07-25  DLP  CR-4471 DOWNTIME COST FOR FINANCE.
      *>   2009-03-03  SAB  CR-5120 WELL RISK SCORE (SEE MEMO 09-14).
      *>   2011-10-17  SAB  CR-5388 OIL PRICE WAS 65.00, NOW 88.00.
      *> Line protocol: command on line 1, KEY=VALUE lines, END.
      *> ============================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINT.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT REQ-FILE ASSIGN TO "data/requests.dat"
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-REQ-STATUS.
           SELECT WELL-FILE ASSIGN TO "data/wells.dat"
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-WELL-STATUS.
           SELECT TECH-FILE ASSIGN TO "data/techs.dat"
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-TECH-STATUS.
           SELECT HIST-FILE ASSIGN TO "data/history.dat"
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-HIST-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  REQ-FILE.
       01  REQ-REC.
           05 RQ-ID            PIC X(8).
           05 RQ-WELL          PIC X(8).
           05 RQ-PART          PIC X(10).
           05 RQ-SITE          PIC X(10).
           05 RQ-QTY           PIC 9(3).
           05 RQ-PRIORITY      PIC X(6).
           05 RQ-STATUS        PIC X(6).
           05 RQ-OPENED        PIC X(10).
       FD  WELL-FILE.
       01  WELL-REC.
           05 WL-ID            PIC X(8).
           05 WL-NAME          PIC X(20).
           05 WL-SITE          PIC X(10).
           05 WL-STATUS        PIC X(8).
           05 WL-BBL-DAY       PIC 9(5).
           05 WL-LAST-SVC      PIC X(10).
       FD  TECH-FILE.
       01  TECH-REC.
           05 TC-ID            PIC X(6).
           05 TC-NAME          PIC X(20).
           05 TC-SITE          PIC X(10).
           05 TC-SKILL         PIC X(10).
           05 TC-CERT          PIC 9.
           05 TC-STATUS        PIC X(9).
           05 TC-RATE          PIC 9(3)V99.
       FD  HIST-FILE.
       01  HIST-REC.
           05 HS-WELL          PIC X(8).
           05 HS-DATE          PIC X(10).
           05 HS-EVENT         PIC X(8).
           05 HS-PART          PIC X(10).
           05 HS-DOWNTIME      PIC 9(3)V9.
           05 HS-TECH          PIC X(6).
       WORKING-STORAGE SECTION.
       01  WS-REQ-STATUS       PIC XX.
       01  WS-WELL-STATUS      PIC XX.
       01  WS-TECH-STATUS      PIC XX.
       01  WS-HIST-STATUS      PIC XX.
       01  WS-EOF2             PIC X VALUE "N".
           88 AUX-AT-END       VALUE "Y".
           88 AUX-MORE         VALUE "N".
       01  WS-EOF              PIC X VALUE "N".
           88 REQ-AT-END       VALUE "Y".
       01  WS-FOUND            PIC X VALUE "N".
       01  WS-CMD              PIC X(40).
       01  WS-LINE             PIC X(80).
       01  WS-KEY              PIC X(30).
       01  WS-VAL              PIC X(40).
       01  WS-GUARD            PIC 99 VALUE 0.
       01  WS-CMD-R2           PIC X(40) VALUE SPACES.
      *> NO LONGER USED AFTER 1998 - LEAVE IN PLACE (TKW)
       01  WS-OLD-YY           PIC 99 VALUE 0.
       01  WS-PAGE-CTR         PIC 9(3) VALUE 0.
       01  WS-LINE-CTR         PIC 9(3) VALUE 60.
       01  W-CTR1              PIC 9(4) VALUE 0.
       01  SAVE-AREA-2         PIC X(61) VALUE SPACES.
       01  WS-RPT-HDR          PIC X(40)
               VALUE "FMS WELL STATUS REPORT    PAGE ".
       01  WS-IN-REQ-ID        PIC X(8) VALUE SPACES.
       01  WS-IN-WELL-ID       PIC X(8) VALUE SPACES.
       01  WS-IN-SITE          PIC X(10) VALUE SPACES.
       01  WS-IN-STATUS        PIC X(8) VALUE SPACES.
       01  WS-IN-TECH-ID       PIC X(6) VALUE SPACES.
       01  WS-IN-SKILL         PIC X(10) VALUE SPACES.
       01  WS-IN-DAYS          PIC X(10) VALUE SPACES.
       01  WS-IN-AS-OF         PIC X(10) VALUE SPACES.
       01  WS-COUNT            PIC 9(4) VALUE 0.
       01  WS-COUNT-OUT        PIC Z(3)9.
       01  WS-QTY-OUT          PIC ZZ9.
       01  WS-MATCH.
           05 WM-ID            PIC X(8).
           05 WM-WELL          PIC X(8).
           05 WM-PART          PIC X(10).
           05 WM-SITE          PIC X(10).
           05 WM-QTY           PIC 9(3).
           05 WM-PRIORITY      PIC X(6).
           05 WM-STATUS        PIC X(6).
           05 WM-OPENED        PIC X(10).
       01  WS-WELL-SAVE.
           05 WV-ID            PIC X(8).
           05 WV-NAME          PIC X(20).
           05 WV-SITE          PIC X(10).
           05 WV-STATUS        PIC X(8).
           05 WV-BBL-DAY       PIC 9(5).
           05 WV-LAST-SVC      PIC X(10).
      *> Batch run date. Fixed so that replayed answers stay identical.
       01  WS-RUN-DATE         PIC X(10) VALUE "2026-11-08".
       01  WS-OIL-PRICE        PIC 9(3)V99 VALUE 88.00.
       01  WS-NUM-OUT          PIC Z(5)9.
       01  WS-HRS-OUT          PIC Z(4)9.9.
       01  WS-MONEY-OUT        PIC Z(8)9.99.
       01  WS-RATE-OUT         PIC ZZ9.99.
       01  WS-OPEN-CNT         PIC 9(4) VALUE 0.
       01  WS-HIGH-CNT         PIC 9(4) VALUE 0.
       01  WS-FAIL-CNT         PIC 9(4) VALUE 0.
       01  WS-FAIL-12M         PIC 9(4) VALUE 0.
       01  WS-DOWN-HRS         PIC 9(5)V9 VALUE 0.
       01  WS-DAYS             PIC 9(3) VALUE 0.
       01  WS-LOST-BBL         PIC 9(7) VALUE 0.
       01  WS-DAILY-LOSS       PIC 9(7)V99 VALUE 0.
       01  WS-TOTAL-LOSS       PIC 9(9)V99 VALUE 0.
       01  WS-SCORE            PIC 9(3) VALUE 0.
       01  WS-RISK             PIC X(8) VALUE SPACES.
       01  WS-SHUT-IN          PIC X VALUE "N".
       01  WS-SVC-STALE        PIC X VALUE "N".
       01  WS-DATE-IN          PIC X(10).
       01  WS-DATE-PARTS.
           05 WS-DP-YYYY       PIC X(4).
           05 WS-DP-MM         PIC X(2).
           05 WS-DP-DD         PIC X(2).
       01  WS-DATE-NUM REDEFINES WS-DATE-PARTS PIC 9(8).
       01  WS-DATE-OK          PIC X VALUE "N".
       01  WS-DAY-NUM          PIC 9(7) VALUE 0.
       01  WS-ASOF-DAY         PIC 9(7) VALUE 0.
       01  WS-AGE-DAYS         PIC S9(7) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-LOGIC.
           ACCEPT WS-CMD
           PERFORM READ-INPUT
           EVALUATE FUNCTION TRIM(WS-CMD)
               WHEN "GET-REQUEST"
                   PERFORM GET-REQUEST
               WHEN "LIST-OPEN-REQUESTS"
                   PERFORM LIST-OPEN-REQUESTS
               WHEN OTHER
                   PERFORM R2-DISPATCH THRU R2-DISPATCH-EXIT
           END-EVALUATE
           STOP RUN.

       READ-INPUT.
           PERFORM UNTIL WS-GUARD > 20
               ADD 1 TO WS-GUARD
               MOVE SPACES TO WS-LINE
               ACCEPT WS-LINE
               IF FUNCTION TRIM(WS-LINE) = "END" OR WS-LINE = SPACES
                   EXIT PERFORM
               END-IF
               MOVE SPACES TO WS-KEY WS-VAL
               UNSTRING WS-LINE DELIMITED BY "="
                   INTO WS-KEY WS-VAL
               END-UNSTRING
               EVALUATE FUNCTION TRIM(WS-KEY)
                   WHEN "REQUEST-ID"
                       MOVE WS-VAL TO WS-IN-REQ-ID
                   WHEN "WELL-ID"
                       MOVE WS-VAL TO WS-IN-WELL-ID
                   WHEN "SITE"
                       MOVE WS-VAL TO WS-IN-SITE
                   WHEN "STATUS"
                       MOVE WS-VAL TO WS-IN-STATUS
                   WHEN "TECH-ID"
                       MOVE WS-VAL TO WS-IN-TECH-ID
                   WHEN "SKILL"
                       MOVE WS-VAL TO WS-IN-SKILL
                   WHEN "DAYS"
                       MOVE WS-VAL TO WS-IN-DAYS
                   WHEN "AS-OF-DATE"
                       MOVE WS-VAL TO WS-IN-AS-OF
               END-EVALUATE
           END-PERFORM.

       OPEN-REQUESTS-FILE.
           OPEN INPUT REQ-FILE
           IF WS-REQ-STATUS NOT = "00"
               DISPLAY "ERROR=DATA-FILE-UNAVAILABLE"
               MOVE 3 TO RETURN-CODE
               STOP RUN
           END-IF
           MOVE "N" TO WS-EOF.

      *> Look up one maintenance request by its ID.
       GET-REQUEST.
           PERFORM OPEN-REQUESTS-FILE
           PERFORM UNTIL WS-EOF = "Y"
               READ REQ-FILE
                   AT END
                       MOVE "Y" TO WS-EOF
                   NOT AT END
                       IF RQ-ID = WS-IN-REQ-ID
                           MOVE REQ-REC TO WS-MATCH
                           MOVE "Y" TO WS-FOUND
                           MOVE "Y" TO WS-EOF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE REQ-FILE
           IF WS-FOUND = "Y"
               MOVE WM-QTY TO WS-QTY-OUT
               DISPLAY "FOUND=Y"
               DISPLAY "REQUEST-ID=" FUNCTION TRIM(WM-ID)
               DISPLAY "WELL-ID=" FUNCTION TRIM(WM-WELL)
               DISPLAY "PART-ID=" FUNCTION TRIM(WM-PART)
               DISPLAY "SITE=" FUNCTION TRIM(WM-SITE)
               DISPLAY "QUANTITY=" FUNCTION TRIM(WS-QTY-OUT)
               DISPLAY "PRIORITY=" FUNCTION TRIM(WM-PRIORITY)
               DISPLAY "STATUS=" FUNCTION TRIM(WM-STATUS)
               DISPLAY "OPENED=" FUNCTION TRIM(WM-OPENED)
           ELSE
               DISPLAY "FOUND=N"
               DISPLAY "REQUEST-ID=" FUNCTION TRIM(WS-IN-REQ-ID)
           END-IF.

      *> List open maintenance requests for one well.
       LIST-OPEN-REQUESTS.
           PERFORM OPEN-REQUESTS-FILE
           DISPLAY "WELL-ID=" FUNCTION TRIM(WS-IN-WELL-ID)
           DISPLAY "BEGIN-ITEMS"
           PERFORM UNTIL WS-EOF = "Y"
               READ REQ-FILE
                   AT END
                       MOVE "Y" TO WS-EOF
                   NOT AT END
                       IF RQ-WELL = WS-IN-WELL-ID
                          AND RQ-STATUS = "OPEN"
                           ADD 1 TO WS-COUNT
                           MOVE RQ-QTY TO WS-QTY-OUT
                           DISPLAY "REQUEST-ID=" FUNCTION TRIM(RQ-ID)
                           DISPLAY "PART-ID=" FUNCTION TRIM(RQ-PART)
                           DISPLAY "QUANTITY=" FUNCTION TRIM(WS-QTY-OUT)
                           DISPLAY "PRIORITY="
                               FUNCTION TRIM(RQ-PRIORITY)
                           DISPLAY "--"
                       END-IF
               END-READ
           END-PERFORM
           CLOSE REQ-FILE
           MOVE WS-COUNT TO WS-COUNT-OUT
           DISPLAY "COUNT=" FUNCTION TRIM(WS-COUNT-OUT).


      *> ------------------------------------------------------------
      *> RELEASE 2 COMMANDS (DLP 2004). KEPT OUT OF THE MAIN EVALUATE
      *> SO THE 1991 PROGRAM DID NOT NEED RE-CERTIFICATION.
      *> ------------------------------------------------------------
       R2-DISPATCH.
           MOVE FUNCTION TRIM(WS-CMD) TO WS-CMD-R2
           IF WS-CMD-R2 = "LIST-SITE-REQUESTS"
               PERFORM LIST-SITE-REQUESTS
               GO TO R2-DISPATCH-EXIT.
           IF WS-CMD-R2 = "GET-WELL"
               PERFORM GET-WELL THRU GET-WELL-EXIT
               GO TO R2-DISPATCH-EXIT.
           IF WS-CMD-R2 = "GET-SERVICE-HISTORY"
               PERFORM GET-SERVICE-HISTORY THRU GSH-EXIT
               GO TO R2-DISPATCH-EXIT.
           IF WS-CMD-R2 = "GET-TECHNICIAN"
               PERFORM GET-TECHNICIAN
               GO TO R2-DISPATCH-EXIT.
           IF WS-CMD-R2 = "FIND-AVAILABLE-TECHS"
               PERFORM FIND-AVAILABLE-TECHS
               GO TO R2-DISPATCH-EXIT.
      *>   CR-4471
           IF WS-CMD-R2 = "CALC-DOWNTIME-COST"
               PERFORM CALC-DOWNTIME-COST THRU CDC-EXIT
               GO TO R2-DISPATCH-EXIT.
      *>   CR-5120
           IF WS-CMD-R2 = "GET-WELL-RISK"
               PERFORM GET-WELL-RISK THRU GWR-EXIT
               GO TO R2-DISPATCH-EXIT.
      *>   IF WS-CMD-R2 = "PRINT-WELL-RPT"
      *>       PERFORM OLD-PRINT-WELL-RPT
      *>       GO TO R2-DISPATCH-EXIT.
           DISPLAY "ERROR=UNKNOWN-COMMAND"
           MOVE 2 TO RETURN-CODE.
       R2-DISPATCH-EXIT.
           EXIT.

      *> ------------------------------------------------------------
      *> RELEASE 2 FILE HANDLING AND OPERATIONS
      *> ------------------------------------------------------------

       OPEN-WELLS-FILE.
           OPEN INPUT WELL-FILE
           IF WS-WELL-STATUS NOT = "00"
               DISPLAY "ERROR=DATA-FILE-UNAVAILABLE"
               MOVE 3 TO RETURN-CODE
               STOP RUN
           END-IF
           SET AUX-MORE TO TRUE.

       OPEN-TECHS-FILE.
           OPEN INPUT TECH-FILE
           IF WS-TECH-STATUS NOT = "00"
               DISPLAY "ERROR=DATA-FILE-UNAVAILABLE"
               MOVE 3 TO RETURN-CODE
               STOP RUN
           END-IF
           SET AUX-MORE TO TRUE.

       OPEN-HISTORY-FILE.
           OPEN INPUT HIST-FILE
           IF WS-HIST-STATUS NOT = "00"
               DISPLAY "ERROR=DATA-FILE-UNAVAILABLE"
               MOVE 3 TO RETURN-CODE
               STOP RUN
           END-IF
           SET AUX-MORE TO TRUE.

      *> Turn YYYY-MM-DD in WS-DATE-IN into a day number.
       CONVERT-DATE.
           MOVE "N" TO WS-DATE-OK
           MOVE 0 TO WS-DAY-NUM
           IF WS-DATE-IN(5:1) = "-" AND WS-DATE-IN(8:1) = "-"
               MOVE WS-DATE-IN(1:4) TO WS-DP-YYYY
               MOVE WS-DATE-IN(6:2) TO WS-DP-MM
               MOVE WS-DATE-IN(9:2) TO WS-DP-DD
               IF WS-DATE-PARTS IS NUMERIC
                   IF FUNCTION TEST-DATE-YYYYMMDD(WS-DATE-NUM) = 0
                       MOVE "Y" TO WS-DATE-OK
                       COMPUTE WS-DAY-NUM =
                           FUNCTION INTEGER-OF-DATE(WS-DATE-NUM)
                   END-IF
               END-IF
           END-IF.

      *> Find one well by WS-IN-WELL-ID; copy it to WS-WELL-SAVE.
       FIND-WELL.
           MOVE "N" TO WS-FOUND
           PERFORM OPEN-WELLS-FILE
           PERFORM UNTIL AUX-AT-END
               READ WELL-FILE
                   AT END
                       SET AUX-AT-END TO TRUE
                   NOT AT END
                       IF WL-ID = WS-IN-WELL-ID
                           MOVE WELL-REC TO WS-WELL-SAVE
                           MOVE "Y" TO WS-FOUND
                           SET AUX-AT-END TO TRUE
                       END-IF
               END-READ
           END-PERFORM
           CLOSE WELL-FILE.

      *> Count open requests (and HIGH ones) for WS-IN-WELL-ID.
       COUNT-WELL-REQUESTS.
           MOVE 0 TO WS-OPEN-CNT WS-HIGH-CNT
           PERFORM OPEN-REQUESTS-FILE
           PERFORM UNTIL WS-EOF = "Y"
               READ REQ-FILE
                   AT END
                       MOVE "Y" TO WS-EOF
                   NOT AT END
                       IF RQ-WELL = WS-IN-WELL-ID
                          AND RQ-STATUS = "OPEN"
                           ADD 1 TO WS-OPEN-CNT
                           IF RQ-PRIORITY = "HIGH"
                               ADD 1 TO WS-HIGH-CNT
                           END-IF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE REQ-FILE.

       WELL-NOT-FOUND.
           DISPLAY "FOUND=N"
           DISPLAY "WELL-ID=" FUNCTION TRIM(WS-IN-WELL-ID).

      *> All requests at one site, optionally one status.
       LIST-SITE-REQUESTS.
           PERFORM OPEN-REQUESTS-FILE
           DISPLAY "SITE=" FUNCTION TRIM(WS-IN-SITE)
           DISPLAY "BEGIN-ITEMS"
           PERFORM UNTIL WS-EOF = "Y"
               READ REQ-FILE
                   AT END
                       MOVE "Y" TO WS-EOF
                   NOT AT END
                       IF RQ-SITE = WS-IN-SITE
                          AND (WS-IN-STATUS = SPACES
                               OR RQ-STATUS = WS-IN-STATUS)
                           ADD 1 TO WS-COUNT
                           MOVE RQ-QTY TO WS-QTY-OUT
                           DISPLAY "REQUEST-ID=" FUNCTION TRIM(RQ-ID)
                           DISPLAY "WELL-ID=" FUNCTION TRIM(RQ-WELL)
                           DISPLAY "PART-ID=" FUNCTION TRIM(RQ-PART)
                           DISPLAY "QUANTITY=" FUNCTION TRIM(WS-QTY-OUT)
                           DISPLAY "PRIORITY="
                               FUNCTION TRIM(RQ-PRIORITY)
                           DISPLAY "STATUS=" FUNCTION TRIM(RQ-STATUS)
                           DISPLAY "OPENED=" FUNCTION TRIM(RQ-OPENED)
                           DISPLAY "--"
                       END-IF
               END-READ
           END-PERFORM
           CLOSE REQ-FILE
           MOVE WS-COUNT TO WS-COUNT-OUT
           DISPLAY "COUNT=" FUNCTION TRIM(WS-COUNT-OUT).

      *> One well: site, status, output and open request counts.
       GET-WELL.
           PERFORM FIND-WELL
           IF WS-FOUND NOT = "Y"
               PERFORM WELL-NOT-FOUND
               GO TO GET-WELL-EXIT
           END-IF
           PERFORM COUNT-WELL-REQUESTS
           DISPLAY "FOUND=Y"
           DISPLAY "WELL-ID=" FUNCTION TRIM(WV-ID)
           DISPLAY "WELL-NAME=" FUNCTION TRIM(WV-NAME)
           DISPLAY "SITE=" FUNCTION TRIM(WV-SITE)
           DISPLAY "STATUS=" FUNCTION TRIM(WV-STATUS)
           MOVE WV-BBL-DAY TO WS-NUM-OUT
           DISPLAY "BBL-PER-DAY=" FUNCTION TRIM(WS-NUM-OUT)
           DISPLAY "LAST-SERVICE=" FUNCTION TRIM(WV-LAST-SVC)
           MOVE WS-OPEN-CNT TO WS-COUNT-OUT
           DISPLAY "OPEN-REQUESTS=" FUNCTION TRIM(WS-COUNT-OUT).

       GET-WELL-EXIT.
           EXIT.
      *> Service and failure events for one well, newest last.
       GET-SERVICE-HISTORY.
           PERFORM FIND-WELL
           IF WS-FOUND NOT = "Y"
               PERFORM WELL-NOT-FOUND
               GO TO GSH-EXIT
           END-IF
           MOVE 0 TO WS-FAIL-CNT WS-DOWN-HRS
           PERFORM OPEN-HISTORY-FILE
           PERFORM UNTIL AUX-AT-END
               READ HIST-FILE
                   AT END
                       SET AUX-AT-END TO TRUE
                   NOT AT END
                       IF HS-WELL = WS-IN-WELL-ID
                           ADD 1 TO WS-COUNT
                           ADD HS-DOWNTIME TO WS-DOWN-HRS
                           IF HS-EVENT = "FAILURE"
                               ADD 1 TO WS-FAIL-CNT
                           END-IF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE HIST-FILE
           DISPLAY "FOUND=Y"
           DISPLAY "WELL-ID=" FUNCTION TRIM(WV-ID)
           MOVE WS-COUNT TO WS-COUNT-OUT
           DISPLAY "EVENTS=" FUNCTION TRIM(WS-COUNT-OUT)
           MOVE WS-FAIL-CNT TO WS-COUNT-OUT
           DISPLAY "FAILURES=" FUNCTION TRIM(WS-COUNT-OUT)
           MOVE WS-DOWN-HRS TO WS-HRS-OUT
           DISPLAY "DOWNTIME-HOURS=" FUNCTION TRIM(WS-HRS-OUT)
           DISPLAY "BEGIN-ITEMS"
           PERFORM OPEN-HISTORY-FILE
           PERFORM UNTIL AUX-AT-END
               READ HIST-FILE
                   AT END
                       SET AUX-AT-END TO TRUE
                   NOT AT END
                       IF HS-WELL = WS-IN-WELL-ID
                           DISPLAY "DATE=" FUNCTION TRIM(HS-DATE)
                           DISPLAY "EVENT=" FUNCTION TRIM(HS-EVENT)
                           DISPLAY "PART-ID=" FUNCTION TRIM(HS-PART)
                           MOVE HS-DOWNTIME TO WS-HRS-OUT
                           DISPLAY "DOWNTIME-HOURS="
                               FUNCTION TRIM(WS-HRS-OUT)
                           DISPLAY "TECH-ID=" FUNCTION TRIM(HS-TECH)
                           DISPLAY "--"
                       END-IF
               END-READ
           END-PERFORM
           CLOSE HIST-FILE
           MOVE WS-COUNT TO WS-COUNT-OUT
           DISPLAY "COUNT=" FUNCTION TRIM(WS-COUNT-OUT).

       GSH-EXIT.
           EXIT.
      *> One field technician by ID.
       GET-TECHNICIAN.
           MOVE "N" TO WS-FOUND
           PERFORM OPEN-TECHS-FILE
           PERFORM UNTIL AUX-AT-END
               READ TECH-FILE
                   AT END
                       SET AUX-AT-END TO TRUE
                   NOT AT END
                       IF TC-ID = WS-IN-TECH-ID
                           MOVE "Y" TO WS-FOUND
                           SET AUX-AT-END TO TRUE
                       END-IF
               END-READ
           END-PERFORM
           IF WS-FOUND = "Y"
               DISPLAY "FOUND=Y"
               DISPLAY "TECH-ID=" FUNCTION TRIM(TC-ID)
               DISPLAY "NAME=" FUNCTION TRIM(TC-NAME)
               DISPLAY "SITE=" FUNCTION TRIM(TC-SITE)
               DISPLAY "SKILL=" FUNCTION TRIM(TC-SKILL)
               DISPLAY "CERT-LEVEL=" TC-CERT
               DISPLAY "AVAILABILITY=" FUNCTION TRIM(TC-STATUS)
               MOVE TC-RATE TO WS-RATE-OUT
               DISPLAY "HOURLY-RATE=" FUNCTION TRIM(WS-RATE-OUT)
           ELSE
               DISPLAY "FOUND=N"
               DISPLAY "TECH-ID=" FUNCTION TRIM(WS-IN-TECH-ID)
           END-IF
           CLOSE TECH-FILE.

      *> Technicians free now at a site, optionally with one skill.
       FIND-AVAILABLE-TECHS.
           PERFORM OPEN-TECHS-FILE
           DISPLAY "SITE=" FUNCTION TRIM(WS-IN-SITE)
           DISPLAY "BEGIN-ITEMS"
           PERFORM UNTIL AUX-AT-END
               READ TECH-FILE
                   AT END
                       SET AUX-AT-END TO TRUE
                   NOT AT END
                       IF TC-SITE = WS-IN-SITE
                          AND TC-STATUS = "AVAILABLE"
                          AND (WS-IN-SKILL = SPACES
                               OR TC-SKILL = WS-IN-SKILL)
                           ADD 1 TO WS-COUNT
                           DISPLAY "TECH-ID=" FUNCTION TRIM(TC-ID)
                           DISPLAY "NAME=" FUNCTION TRIM(TC-NAME)
                           DISPLAY "SKILL=" FUNCTION TRIM(TC-SKILL)
                           DISPLAY "CERT-LEVEL=" TC-CERT
                           MOVE TC-RATE TO WS-RATE-OUT
                           DISPLAY "HOURLY-RATE="
                               FUNCTION TRIM(WS-RATE-OUT)
                           DISPLAY "--"
                       END-IF
               END-READ
           END-PERFORM
           CLOSE TECH-FILE
           MOVE WS-COUNT TO WS-COUNT-OUT
           DISPLAY "COUNT=" FUNCTION TRIM(WS-COUNT-OUT).

      *> Lost production while a well is down: BBL/DAY x PRICE x DAYS.
       CALC-DOWNTIME-COST.
           IF FUNCTION TRIM(WS-IN-DAYS) = SPACES
              OR FUNCTION TEST-NUMVAL(WS-IN-DAYS) NOT = 0
               DISPLAY "ERROR=BAD-DAYS"
               GO TO CDC-EXIT
           END-IF
           IF FUNCTION NUMVAL(WS-IN-DAYS) < 1
              OR FUNCTION NUMVAL(WS-IN-DAYS) > 365
              OR FUNCTION NUMVAL(WS-IN-DAYS) NOT =
                 FUNCTION INTEGER(FUNCTION NUMVAL(WS-IN-DAYS))
               DISPLAY "ERROR=BAD-DAYS"
               GO TO CDC-EXIT
           END-IF
           COMPUTE WS-DAYS = FUNCTION NUMVAL(WS-IN-DAYS)
           PERFORM FIND-WELL
           IF WS-FOUND NOT = "Y"
               PERFORM WELL-NOT-FOUND
               GO TO CDC-EXIT
           END-IF
           COMPUTE WS-LOST-BBL = WV-BBL-DAY * WS-DAYS
      *>   COMPUTE WS-DAILY-LOSS = WV-BBL-DAY * 65.00
      *>   ^^^ PRE CR-5388. KEEP FOR AUDIT.
           COMPUTE WS-DAILY-LOSS ROUNDED = WV-BBL-DAY * WS-OIL-PRICE
           COMPUTE WS-TOTAL-LOSS ROUNDED = WS-DAILY-LOSS * WS-DAYS
           DISPLAY "FOUND=Y"
           DISPLAY "WELL-ID=" FUNCTION TRIM(WV-ID)
           DISPLAY "STATUS=" FUNCTION TRIM(WV-STATUS)
           MOVE WS-DAYS TO WS-NUM-OUT
           DISPLAY "DAYS=" FUNCTION TRIM(WS-NUM-OUT)
           MOVE WV-BBL-DAY TO WS-NUM-OUT
           DISPLAY "BBL-PER-DAY=" FUNCTION TRIM(WS-NUM-OUT)
           MOVE WS-OIL-PRICE TO WS-RATE-OUT
           DISPLAY "OIL-PRICE-USD=" FUNCTION TRIM(WS-RATE-OUT)
           MOVE WS-LOST-BBL TO WS-NUM-OUT
           DISPLAY "LOST-BBL=" FUNCTION TRIM(WS-NUM-OUT)
           MOVE WS-DAILY-LOSS TO WS-MONEY-OUT
           DISPLAY "DAILY-LOSS-USD=" FUNCTION TRIM(WS-MONEY-OUT)
           MOVE WS-TOTAL-LOSS TO WS-MONEY-OUT
           DISPLAY "TOTAL-LOSS-USD=" FUNCTION TRIM(WS-MONEY-OUT).

       CDC-EXIT.
           EXIT.
      *> Risk score for one well (0-100):
      *>   shut in +40, each open HIGH request +20, other open +5,
      *>   each failure in the 365 days before AS-OF-DATE +10,
      *>   no service in 180 days +10.
      *>   70+ CRITICAL, 40+ HIGH, 20+ MEDIUM, else LOW.
       GET-WELL-RISK.
           IF WS-IN-AS-OF = SPACES
               MOVE WS-RUN-DATE TO WS-IN-AS-OF
           END-IF
           MOVE WS-IN-AS-OF TO WS-DATE-IN
           PERFORM CONVERT-DATE
           IF WS-DATE-OK NOT = "Y"
               DISPLAY "ERROR=BAD-AS-OF-DATE"
               GO TO GWR-EXIT
           END-IF
           MOVE WS-DAY-NUM TO WS-ASOF-DAY
           PERFORM FIND-WELL
           IF WS-FOUND NOT = "Y"
               PERFORM WELL-NOT-FOUND
               GO TO GWR-EXIT
           END-IF
           PERFORM COUNT-WELL-REQUESTS
           MOVE 0 TO WS-SCORE WS-FAIL-12M
           MOVE "N" TO WS-SHUT-IN WS-SVC-STALE
           IF WV-STATUS = "SHUTIN"
               MOVE "Y" TO WS-SHUT-IN
               ADD 40 TO WS-SCORE
           END-IF
           COMPUTE WS-SCORE = WS-SCORE + WS-HIGH-CNT * 20
               + (WS-OPEN-CNT - WS-HIGH-CNT) * 5
           PERFORM OPEN-HISTORY-FILE
           PERFORM UNTIL AUX-AT-END
               READ HIST-FILE
                   AT END
                       SET AUX-AT-END TO TRUE
                   NOT AT END
                       IF HS-WELL = WS-IN-WELL-ID
                          AND HS-EVENT = "FAILURE"
                           MOVE HS-DATE TO WS-DATE-IN
                           PERFORM CONVERT-DATE
                           COMPUTE WS-AGE-DAYS =
                               WS-ASOF-DAY - WS-DAY-NUM
                           IF WS-DATE-OK = "Y"
                              AND WS-AGE-DAYS >= 0
                              AND WS-AGE-DAYS < 365
                               ADD 1 TO WS-FAIL-12M
                           END-IF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE HIST-FILE
           COMPUTE WS-SCORE = WS-SCORE + WS-FAIL-12M * 10
           MOVE WV-LAST-SVC TO WS-DATE-IN
           PERFORM CONVERT-DATE
           COMPUTE WS-AGE-DAYS = WS-ASOF-DAY - WS-DAY-NUM
           IF WS-DATE-OK NOT = "Y" OR WS-AGE-DAYS > 180
               MOVE "Y" TO WS-SVC-STALE
               ADD 10 TO WS-SCORE
           END-IF
           IF WS-SCORE > 100
               MOVE 100 TO WS-SCORE
           END-IF
      *>   BANDS PER MEMO 09-14. DO NOT CHANGE WITHOUT OPS SIGN-OFF.
           IF WS-SCORE NOT < 70
               MOVE "CRITICAL" TO WS-RISK
           ELSE
               IF WS-SCORE NOT < 40
                   MOVE "HIGH" TO WS-RISK
               ELSE
                   IF WS-SCORE NOT < 20
                       MOVE "MEDIUM" TO WS-RISK
                   ELSE
                       MOVE "LOW" TO WS-RISK
                   END-IF
               END-IF
           END-IF
           DISPLAY "FOUND=Y"
           DISPLAY "WELL-ID=" FUNCTION TRIM(WV-ID)
           DISPLAY "AS-OF-DATE=" FUNCTION TRIM(WS-IN-AS-OF)
           MOVE WS-SCORE TO WS-NUM-OUT
           DISPLAY "RISK-SCORE=" FUNCTION TRIM(WS-NUM-OUT)
           DISPLAY "RISK-LEVEL=" FUNCTION TRIM(WS-RISK)
           DISPLAY "SHUT-IN=" WS-SHUT-IN
           MOVE WS-OPEN-CNT TO WS-COUNT-OUT
           DISPLAY "OPEN-REQUESTS=" FUNCTION TRIM(WS-COUNT-OUT)
           MOVE WS-HIGH-CNT TO WS-COUNT-OUT
           DISPLAY "HIGH-PRIORITY-OPEN=" FUNCTION TRIM(WS-COUNT-OUT)
           MOVE WS-FAIL-12M TO WS-COUNT-OUT
           DISPLAY "FAILURES-12M=" FUNCTION TRIM(WS-COUNT-OUT)
           DISPLAY "SERVICE-OVERDUE=" WS-SVC-STALE.
       GWR-EXIT.
           EXIT.

      *> ------------------------------------------------------------
      *> OLD 132-COLUMN WELL REPORT. REPLACED BY THE FMS SCREENS IN
      *> 1998. NOT CALLED. DO NOT DELETE - BATCH JCL STILL NAMES IT.
      *> ------------------------------------------------------------
       OLD-PRINT-WELL-RPT.
           ADD 1 TO WS-PAGE-CTR
           MOVE 0 TO WS-LINE-CTR
           PERFORM OPEN-WELLS-FILE
           PERFORM UNTIL AUX-AT-END
               READ WELL-FILE
                   AT END
                       SET AUX-AT-END TO TRUE
                   NOT AT END
                       ADD 1 TO W-CTR1 WS-LINE-CTR
                       IF WS-LINE-CTR > 55
                           ADD 1 TO WS-PAGE-CTR
                           MOVE 0 TO WS-LINE-CTR
                       END-IF
                       MOVE WELL-REC TO SAVE-AREA-2
               END-READ
           END-PERFORM
           CLOSE WELL-FILE.
