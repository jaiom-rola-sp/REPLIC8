#!/usr/bin/perl
# Prints what is on hand for a part id given on the command line.
use strict;
my ($part, $site) = @ARGV;
die "usage: lookup.pl PART [SITE]\n" unless defined $part;
print "part=$part\n";
print "on_hand=", ($part =~ /^P/ ? 12 : 0), "\n";
print "site=", (defined $site ? $site : "MAIN"), "\n";
