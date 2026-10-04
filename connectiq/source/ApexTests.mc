// Apex Day — Run No Evil unit tests (Toybox.Test).
//
// Build with --unit-test and run in the simulator:
//   monkeyc -f monkey.jungle -y devkey.der -w -o bin/ApexDay-test.prg \
//           -d fenix7pro --unit-test
//   monkeydo bin/ApexDay-test.prg fenix7pro -t
//
// Test code is automatically stripped from release/device builds by the
// compiler (:test annotation), so these functions cost nothing on the watch.
// Scope: pure logic that can be proven in the simulator — formatters, the
// defensive payload accessors, the event queue policy, revision/id helpers.
// What CANNOT be proven here (needs the owner's watch) is listed in README.

using Toybox.Lang;
using Toybox.Test;
using Toybox.Time;

(:test)
function testAsNumCoercions(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(0, ApexPayload.asNum(null));
    Test.assertEqual(5, ApexPayload.asNum(5));
    Test.assertEqual(7, ApexPayload.asNum(7.9));
    Test.assertEqual(42, ApexPayload.asNum("42"));
    Test.assertEqual(1, ApexPayload.asNum(true));
    Test.assertEqual(0, ApexPayload.asNum(false));
    return true;
}

(:test)
function testAsStrCoercions(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual("", ApexPayload.asStr(null));
    Test.assertEqual("abc", ApexPayload.asStr("abc"));
    Test.assertEqual("12", ApexPayload.asStr(12));
    return true;
}

(:test)
function testDefensiveAccessors(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual("", ApexPayload.strAt(null, "k"));
    Test.assertEqual(0, ApexPayload.numAt(null, "k"));
    Test.assertEqual(false, ApexPayload.boolAt(null, "k"));

    var dict = { "a" => "x", "b" => 3, "c" => true };
    Test.assertEqual("x", ApexPayload.strAt(dict, "a"));
    Test.assertEqual("", ApexPayload.strAt(dict, "missing"));
    Test.assertEqual(3, ApexPayload.numAt(dict, "b"));
    Test.assertEqual(0, ApexPayload.numAt(dict, "missing"));
    Test.assertEqual(true, ApexPayload.boolAt(dict, "c"));
    Test.assertEqual(false, ApexPayload.boolAt(dict, "missing"));
    return true;
}

(:test)
function testVerdictAccessorsV2(logger as Test.Logger) as Lang.Boolean {
    var day = {
        "safety" => { "verdict" => "rest", "intensity_ceiling" => "rest",
                      "reasons" => [ "HRV -18%" ] }
    };
    Test.assertEqual("rest", ApexPayload.verdictOf(day));
    Test.assertEqual("rest", ApexPayload.verdictCeiling(day));
    var reasons = ApexPayload.verdictReasons(day);
    Test.assertEqual(1, (reasons == null) ? 0 : reasons.size());
    // absent block -> empty verdict, no crash
    Test.assertEqual("", ApexPayload.verdictOf({}));
    Test.assertEqual("", ApexPayload.verdictOf(null));
    return true;
}

(:test)
function testVerdictAccessorsV3(logger as Test.Logger) as Lang.Boolean {
    var day = {
        "verdict" => { "v" => "modify", "c" => "low", "r" => [ "ACWR 1.6" ] },
        "wo" => { "t" => "Z2 ride", "min" => 90, "st" => "scheduled",
                  "hint" => "Cycling > Training > Workouts" },
        "sup" => [ { "n" => "Magnesium", "dose" => "400 mg", "done" => false } ],
        "al" => { "n" => 2, "top" => [ { "m" => "Low ferritin", "s" => "warning" } ] },
        "streak" => 6, "wd" => 3, "d" => "2026-10-05"
    };
    Test.assertEqual("modify", ApexPayload.verdictOf(day));
    Test.assertEqual("low", ApexPayload.verdictCeiling(day));
    var wo = ApexPayload.workoutBlock(day);
    Test.assertEqual("Z2 ride", ApexPayload.strAt(wo, "t"));
    Test.assertEqual(1, ApexPayload.supplementList(day).size());
    Test.assertEqual(2, ApexPayload.alertCount(day));
    Test.assertEqual(6, ApexPayload.streak(day));
    Test.assertEqual(3, ApexPayload.weekday(day));
    Test.assertEqual("2026-10-05", ApexPayload.dateOf(day));
    return true;
}

(:test)
function testAlertCountFallbacks(logger as Test.Logger) as Lang.Boolean {
    // v2 shape
    var v2 = { "alerts" => { "count" => 3, "items" => [ { "message" => "a", "severity" => "info" } ] } };
    Test.assertEqual(3, ApexPayload.alertCount(v2));
    // count missing -> derive from items
    var noCount = { "alerts" => { "items" => [ { "message" => "a" }, { "message" => "b" } ] } };
    Test.assertEqual(2, ApexPayload.alertCount(noCount));
    // absent -> 0
    Test.assertEqual(0, ApexPayload.alertCount({}));
    return true;
}

(:test)
function testWrapTokenizer(logger as Test.Logger) as Lang.Boolean {
    // Monkey C has no String.split — ApexFormat._words is the tokenizer used
    // by wrap(); verify it directly (no dc needed for the pure logic).
    Test.assertEqual(3, ApexFormat._words("hello world foo").size());
    Test.assertEqual(0, ApexFormat._words("").size());
    Test.assertEqual(2, ApexFormat._words("a  b").size());   // double space
    Test.assertEqual(1, ApexFormat._words("solo").size());
    Test.assertEqual(0, ApexFormat._words("   ").size());    // spaces only
    return true;
}

(:test)
function testEventIdShape(logger as Test.Logger) as Lang.Boolean {
    var event = ApexPayload.makeEvent(ApexPayload.EVENT_SET_LOG, { "reps" => 8 });
    Test.assertEqual(ApexPayload.EVENT_SET_LOG, ApexPayload.asStr(event.get("type")));
    var id = ApexPayload.asStr(event.get("id"));
    Test.assertEqual(true, id.length() >= 13); // 8 hex + '-' + 4 hex
    Test.assertEqual(true, event.get("at") instanceof Lang.Number);
    return true;
}

(:test)
function testEventQueueDropPolicy(logger as Test.Logger) as Lang.Boolean {
    // fill the queue beyond MAX_EVENTS; oldest must be dropped with a flag
    for (var i = 0; i < ApexStore.MAX_EVENTS + 3; i += 1) {
        ApexStore.addEvent(ApexPayload.makeEvent("test", { "i" => i }));
    }
    Test.assertEqual(ApexStore.MAX_EVENTS, ApexStore.pendingCount());
    Test.assertEqual(true, ApexStore.metaBool("queueWarned"));
    // oldest (i=0..2) must be gone; newest present
    var events = ApexStore.pendingEvents();
    var first = ApexPayload.asDict(events[0]);
    Test.assertEqual(3, ApexPayload.numAt(ApexPayload.dictAt(first, "d"), "i"));
    // cleanup for other tests
    ApexStore.removeEventsByIds([ "all" ]);
    var after = ApexStore.pendingEvents();
    Test.assertEqual(ApexStore.MAX_EVENTS, after.size());
    return true;
}

(:test)
function testRemoveEventsByIds(logger as Test.Logger) as Lang.Boolean {
    var e1 = ApexPayload.makeEvent("test", { "x" => 1 });
    var e2 = ApexPayload.makeEvent("test", { "x" => 2 });
    ApexStore.addEvent(e1);
    ApexStore.addEvent(e2);
    var before = ApexStore.pendingCount();
    var ids = [ ApexPayload.asStr(e1.get("id")) ];
    ApexStore.removeEventsByIds(ids);
    Test.assertEqual(before - 1, ApexStore.pendingCount());
    return true;
}

(:test)
function testMinutesSince(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual(-1, ApexPayload.minutesSince(0));   // never synced
    Test.assertEqual(-1, ApexPayload.minutesSince(-5));
    var now = Time.now().value();
    Test.assertEqual(0, ApexPayload.minutesSince(now));  // clamped >= 0
    return true;
}

(:test)
function testPad2AndClamp(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual("05", ApexFormat.pad2(5));
    Test.assertEqual("42", ApexFormat.pad2(42));
    Test.assertEqual(5, ApexFormat.clamp(2, 5, 10));
    Test.assertEqual(10, ApexFormat.clamp(99, 5, 10));
    Test.assertEqual(7, ApexFormat.clamp(7, 5, 10));
    return true;
}

(:test)
function testWeekdayNameBounds(logger as Test.Logger) as Lang.Boolean {
    Test.assertEqual("", ApexFormat.weekdayName(-1));
    Test.assertEqual("", ApexFormat.weekdayName(7));
    Test.assertEqual(true, ApexFormat.weekdayName(0).length() >= 2);
    return true;
}

(:test)
function testSeverityColors(logger as Test.Logger) as Lang.Boolean {
    // red strictly for act-now severities
    Test.assertEqual(0xFF0000, ApexFormat.severityColor("critical"));
    Test.assertEqual(0xFF0000, ApexFormat.severityColor("error"));
    Test.assertEqual(0xFFFF00, ApexFormat.severityColor("warning"));
    Test.assertEqual(0xAAAAAA, ApexFormat.severityColor("info"));
    return true;
}
