<?php
// Prints a JSON object for the sku given on the command line.
if ($argc < 2) { fwrite(STDERR, "usage: stock.php SKU\n"); exit(1); }
echo json_encode(["sku" => $argv[1], "price" => 4.5]), "\n";
