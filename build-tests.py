#!/usr/bin/python

# tz.js - Library for working with timezones in JavaScript

# Written in 2011 by L. David Baron <dbaron@dbaron.org>

# To the extent possible under law, the author(s) have dedicated all
# copyright and related and neighboring rights to this software to the
# public domain worldwide.  This software is distributed without any
# warranty.
#
# You should have received a copy of the CC0 Public Domain Dedication
# along with this software.  If not, see
# <http://creativecommons.org/publicdomain/zero/1.0/>.

# This script converts the compiled time zone data from the Olson time
# zone database (http://www.twinsun.com/tz/tz-link.htm), which is
# generated from the tzdata* data using the tzcode* code, and
# distributed on many Unix-ish operating systems in /usr/share/zoneinfo,
# into a JSON format suitable for inclusion in the tz.js JavaScript
# library.

import sys
import imp
import os.path
import subprocess
import re
import math

__all__ = [
    "output_tests"
]

STOP_YEAR = 2050
STOP_SECS = 2524608000 # 2050, in seconds since the epoch

os.environ["LC_ALL"] = "C"
os.environ["LC_TIME"] = "C"

generate_zones = imp.load_source("compiled_to_json",
                                 os.path.join(os.path.dirname(__file__),
                                              "compiled-to-json.py")
                                 ).generate_zones
all_zones = list(generate_zones())

def output_tests(io):
    io.write("""<!DOCTYPE HTML>
<title>tz.js tests (generated by """ + __file__ + """)</title>
<script src="tz.js"></script>
<pre id="output"></pre>
<script>
var output_node = document.createTextNode("");
document.getElementById("output").appendChild(output_node);
function print(s)
{
    output_node.appendData(s + "\\n");
}

var pass_count = 0, fail_count = 0;

function assert(cond, description)
{
    if (cond) {
        ++pass_count;
    } else {
        ++fail_count;
        print("FAIL: " + description);
    }
}

function is(value, expected, description)
{
    assert(value == expected,
           description + ":  " + value + " should equal " + expected);
}

function check_offset(zone, d, utcoff, abbr)
{
    var z = tz.zoneAt(zone, new Date(d * 1000));
    is(z.offset, utcoff, zone + " at " + d);
    is(z.abbr, abbr, zone + " at " + d);
}

/*
 * Check a non-round-second values, since the tests below are largely round.
 *
 * The last two could become invalid in the future.
 */
check_offset("America/Los_Angeles", 1300010399.999, -28800, "PST");
check_offset("America/Los_Angeles", 1300010400.001, -25200, "PDT");
check_offset("America/Los_Angeles", 1308469553.734, -25200, "PDT");
check_offset("America/Los_Angeles", 2519888399.999, -25200, "PDT");
check_offset("America/Los_Angeles", 2519888400.001, -28800, "PST");
""")

    def output_check_offset(zone, d, utcoff, abbr):
        io.write("check_offset(\"{0}\", {1}, {2}, \"{3}\");\n" \
                   .format(zone, d, utcoff, abbr));

    date_zone_re = re.compile("^([^ ]*) ([+-])(\d{2}):(\d{2}):(\d{2})$")
    def expected_for(zone, time):
        date_process = subprocess.Popen(['date',
                                         '--date=@' + str(math.trunc(time)),
                                         '+%Z %::z'],
                                        stdout = subprocess.PIPE,
                                        env={"TZ": zone})
        (abbr, sign, hours, mins, secs) = date_zone_re.match(
            date_process.stdout.readline().rstrip("\n")).groups()
        date_process.stdout.close()
        utcoff = ((sign == "+") * 2 - 1) * \
                 (3600 * int(hours) + 60 * int(mins) + int(secs))
        return (utcoff, abbr)

    io.write("""
/*
 * Generate tests based on all the transitions shown by zdump for each zone.
 */
""")

    date_process = subprocess.Popen(['date', '--date=' + str(STOP_YEAR) +
                                     '-01-01 00:00:00 UTC', '+%s'],
                                    stdout = subprocess.PIPE)
    stop_d = int(date_process.stdout.read().rstrip("\n"))
    date_process.stdout.close()
    for zone in all_zones:
        def output_test(d, utcoff, abbr):
            output_check_offset(zone, d, utcoff, abbr)
        zdump = subprocess.Popen(['zdump', '-v', '-c', str(STOP_YEAR), zone],
                                 stdout=subprocess.PIPE)
        zdump_re = re.compile("^" + zone + "  ([^=]+) = ([^=]+) isdst=([01]) gmtoff=(-?\d+)$")
        first = True
        first_after_1970 = True
        prev_utcoff = None
        prev_abbr = None
        for line in zdump.stdout:
            line = line.rstrip("\n")
            if line.endswith(" = NULL"):
                continue
            (date_utc, date_loc, isdst, utcoff) = zdump_re.match(line).groups()
            isdst = bool(isdst) # not really needed
            utcoff = int(utcoff)
            date_process = subprocess.Popen(['date', '--date=' + date_utc,
                                             '+%s'],
                                            stdout = subprocess.PIPE)
            d = int(date_process.stdout.read().rstrip("\n"))
            date_process.stdout.close()
            abbr = date_loc.split(" ")[-1]
            if d >= 0:
                if first_after_1970 and d != 0 and not first:
                    output_test(0, prev_utcoff, prev_abbr)
                if first and d > 0:
                    output_test(0, utcoff, abbr)
                output_test(d, utcoff, abbr)
                first_after_1970 = False
            first = False
            prev_utcoff = utcoff
            prev_abbr = abbr
        zdump.stdout.close()
        if first:
            # This zone (Pacific/Johnston) has no transitions, but we
            # can still test it.
            (prev_utcoff, prev_abbr) = expected_for(zone, 0)
        if first_after_1970:
            output_test(0, prev_utcoff, prev_abbr)
        output_test(stop_d, prev_utcoff, prev_abbr)
    io.write("""

/*
 * Generate a fixed set of random tests using a linear-congruential
 * PRNG.  This does a good bit of testing of the space in a random way,
 * but uses a fixed random seed to always get the same set of tests.
 * See http://en.wikipedia.org/wiki/Linear_congruential_generator (using
 * the numbers from Numerical Recipes).
 */
""")
    def lc_prng(): # a generator
        # a randomly (once) generated number in [0,2^32)
        rand_state = 1938266273;
        while True:
            yield 1.0 * rand_state / 0x100000000 # value in [0,1)
            rand_state = ((rand_state * 1664525) + 1013904223) % 0x100000000

    prng = lc_prng()
    for i in range(50000):
        zone = all_zones[math.trunc(prng.next() * len(all_zones))]
        # pick a random time in 1970...STOP_SECS.  Use two random
        # numbers so we use the full space, random down to the
        # millisecond.
        time = (prng.next() * STOP_SECS) + (prng.next() * 0x100000000 / 1000)
        time = time % STOP_SECS
        time = math.floor(time * 1000) / 1000
        (utcoff, abbr) = expected_for(zone, time)
        output_check_offset(zone, time, utcoff, abbr)
    io.write("""
/*
 * Some fixed tests for window.tz.datesFor
 */
var df = window.tz.datesFor("America/Los_Angeles", 2011, 1, 1, 0, 0, 0);
is(df.length, 1, "datesFor (1) length");
is(df[0].offset, -28800, "datesFor(1) [0].offset");
is(df[0].abbr, "PST", "datesFor(1) [0].abbr");
is(df[0].date.valueOf(), 1293868800000, "datesFor(1) [0].date.valueOf()");
df = window.tz.datesFor("America/Los_Angeles", 2011, 3, 13, 2, 30, 0);
is(df.length, 0, "datesFor (2) length");
df = window.tz.datesFor("America/Los_Angeles", 2011, 11, 6, 1, 30, 0);
is(df.length, 2, "datesFor (3) length");
is(df[0].offset, -25200, "datesFor(3) [0].offset");
is(df[0].abbr, "PDT", "datesFor(3) [0].abbr");
is(df[0].date.valueOf(), 1320568200000, "datesFor(3) [0].date.valueOf()");
is(df[1].offset, -28800, "datesFor(3) [1].offset");
is(df[1].abbr, "PST", "datesFor(3) [1].abbr");
is(df[1].date.valueOf(), 1320571800000, "datesFor(3) [1].date.valueOf()");
""")

    io.write("""
print("Totals:  " + pass_count + " passed, " + fail_count + " failed.");
</script>
""")

if __name__ == '__main__':
    output_tests(sys.stdout)
