      *> ============================================================
      *> SUBSIDIARY B - FIELD MAINTENANCE SYSTEM (FMS)
      *> Oilfield services: maintenance requests for well equipment.
      *> Demo stand-in for replic8 (FR-10). Read-only lookups.
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
       WORKING-STORAGE SECTION.
       01  WS-REQ-STATUS       PIC XX.
       01  WS-EOF              PIC X VALUE "N".
       01  WS-FOUND            PIC X VALUE "N".
       01  WS-CMD              PIC X(40).
       01  WS-LINE             PIC X(80).
       01  WS-KEY              PIC X(30).
       01  WS-VAL              PIC X(40).
       01  WS-GUARD            PIC 99 VALUE 0.
       01  WS-IN-REQ-ID        PIC X(8) VALUE SPACES.
       01  WS-IN-WELL-ID       PIC X(8) VALUE SPACES.
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
                   DISPLAY "ERROR=UNKNOWN-COMMAND"
                   MOVE 2 TO RETURN-CODE
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
