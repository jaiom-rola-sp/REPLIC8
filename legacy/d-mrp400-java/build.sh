#!/bin/sh
# Builds MRP/400 with plain javac and runs a quick smoke test.
set -e
mkdir -p classes
javac -d classes src/com/mpp/mrp/*.java
java -cp classes com.mpp.mrp.Main GET-PART PART_ID=PUMP-77
