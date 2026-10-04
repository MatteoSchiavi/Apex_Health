// Apex Day — defensive payload access + event constructors.
//
// ONE place that knows how to read the server payload. Every accessor is
// null-safe and type-coercing: views never crash on missing/renamed keys
// (spec: "never crash on missing keys"), and the app is additive-ready for
// the v3 watch contract (docs/WATCH_API_V3.md): when the server starts
// sending the compact v3 blocks (wo / sup / al / gym / gear / don / ev / wx)
// they win over the v2 blocks automatically.
//
// v2 contract (backend/app/api/watch.py — read-only for this app):
//   {date, weekday, sessions[{title,source,start,duration,notes}],
//    supplements[{name,dose,schedule}], alerts{count,items[{message,severity}]},
//    journal_streak, gym_plan{...exercises[{gym_day_exercise_id,name,sets,
//    reps_min,reps_max,rest_seconds,notes,sets_done,complete}]...},
//    safety{verdict,intensity_ceiling,reasons[]}}
// v3 blocks (future, additive): wo{t,min,st,hint}, sup[{n,dose,done}],
//   al{n,top[]}, gym{...}, verdict{v,c,r[]}, gear[{n,h,lim}], don{days},
//   ev{t,days,taper}, wx{tmin,tmax,wind,rain}, streak.
//
// Annotated (:background) AND (:glance): the background service and the
// glance build both need these accessors (glance memory budget: 64 KB).

using Toybox.Lang;
using Toybox.Math;
using Toybox.Time;

(:background, :glance)
class ApexPayload {

    // ------------------------------------------------------------ coercions

    static function asStr(value) as Lang.String {
        if (value == null) {
            return "";
        }
        if (value instanceof Lang.String) {
            return value;
        }
        if (value instanceof Lang.Boolean) {
            return value ? "1" : "0";
        }
        return value.toString();
    }

    static function asNum(value) as Lang.Number {
        if (value == null) {
            return 0;
        }
        if (value instanceof Lang.Boolean) {
            return value ? 1 : 0;
        }
        if (value instanceof Lang.String) {
            return value.toNumber();
        }
        // Float/Long/Double are Number subtypes; plain Numbers pass through
        if (value instanceof Lang.Number) {
            return value as Lang.Number;
        }
        return 0;
    }

    static function asBool(value) as Lang.Boolean {
        if (value == null) {
            return false;
        }
        if (value instanceof Lang.Boolean) {
            return value;
        }
        if (value instanceof Lang.Number) {
            return value != 0;
        }
        if (value instanceof Lang.String) {
            return value.equals("true") || value.equals("1");
        }
        return false;
    }

    static function asDict(value) as Lang.Dictionary or Null {
        return (value != null && value instanceof Lang.Dictionary) ? value : null;
    }

    static function asArr(value) as Lang.Array or Null {
        return (value != null && value instanceof Lang.Array) ? value : null;
    }

    // ------------------------------------------------------- key accessors

    static function strAt(dict as Lang.Dictionary or Null, key as Lang.String) as Lang.String {
        if (dict == null) {
            return "";
        }
        return asStr(dict.get(key));
    }

    static function numAt(dict as Lang.Dictionary or Null, key as Lang.String) as Lang.Number {
        if (dict == null) {
            return 0;
        }
        return asNum(dict.get(key));
    }

    static function boolAt(dict as Lang.Dictionary or Null, key as Lang.String) as Lang.Boolean {
        if (dict == null) {
            return false;
        }
        return asBool(dict.get(key));
    }

    static function dictAt(dict as Lang.Dictionary or Null, key as Lang.String) as Lang.Dictionary or Null {
        if (dict == null) {
            return null;
        }
        return asDict(dict.get(key));
    }

    static function arrAt(dict as Lang.Dictionary or Null, key as Lang.String) as Lang.Array or Null {
        if (dict == null) {
            return null;
        }
        return asArr(dict.get(key));
    }

    // --------------------------------------------------------- day blocks
    // v3 short blocks win when present; v2 blocks are the fallback.

    //! safety verdict: v3 "verdict"{v,c,r[]} or v2 "safety"{verdict,...}
    static function verdictBlock(day as Lang.Dictionary or Null) as Lang.Dictionary or Null {
        var v3 = dictAt(day, "verdict");
        if (v3 != null) {
            return v3;
        }
        return dictAt(day, "safety");
    }

    static function verdictOf(day as Lang.Dictionary or Null) as Lang.String {
        var block = verdictBlock(day);
        if (block == null) {
            return "";
        }
        var v = strAt(block, "v");
        if (v.equals("")) {
            v = strAt(block, "verdict");
        }
        return v;
    }

    static function verdictReasons(day as Lang.Dictionary or Null) as Lang.Array or Null {
        var block = verdictBlock(day);
        if (block == null) {
            return null;
        }
        var r = arrAt(block, "r");
        if (r == null) {
            r = arrAt(block, "reasons");
        }
        return r;
    }

    static function verdictCeiling(day as Lang.Dictionary or Null) as Lang.String {
        var block = verdictBlock(day);
        if (block == null) {
            return "";
        }
        var c = strAt(block, "c");
        if (c.equals("")) {
            c = strAt(block, "intensity_ceiling");
        }
        return c;
    }

    //! published workout status: v3 "wo"{t,min,st,hint} — absent in v2.
    static function workoutBlock(day as Lang.Dictionary or Null) as Lang.Dictionary or Null {
        return dictAt(day, "wo");
    }

    //! concrete gym plan: v2 "gym_plan" or v3 "gym".
    static function gymBlock(day as Lang.Dictionary or Null) as Lang.Dictionary or Null {
        var v3 = dictAt(day, "gym");
        if (v3 != null) {
            return v3;
        }
        return dictAt(day, "gym_plan");
    }

    //! supplements: v3 "sup"[{n,dose,done}] or v2 "supplements"[{name,dose}].
    static function supplementList(day as Lang.Dictionary or Null) as Lang.Array or Null {
        var v3 = arrAt(day, "sup");
        if (v3 != null) {
            return v3;
        }
        return arrAt(day, "supplements");
    }

    static function supplementName(supp as Lang.Dictionary) as Lang.String {
        var n = strAt(supp, "n");
        if (n.equals("")) {
            n = strAt(supp, "name");
        }
        return n;
    }

    static function supplementDose(supp as Lang.Dictionary) as Lang.String {
        var d = strAt(supp, "dose");
        return d;
    }

    static function supplementDone(supp as Lang.Dictionary) as Lang.Boolean {
        return boolAt(supp, "done");
    }

    //! alerts: v3 "al"{n,top[]} or v2 "alerts"{count,items[]}.
    static function alertCount(day as Lang.Dictionary or Null) as Lang.Number {
        var v3 = dictAt(day, "al");
        if (v3 != null) {
            return numAt(v3, "n");
        }
        var alerts = dictAt(day, "alerts");
        if (alerts == null) {
            return 0;
        }
        var count = alerts.get("count");
        if (count == null) {
            var items = arrAt(alerts, "items");
            return (items == null) ? 0 : items.size();
        }
        return asNum(count);
    }

    static function alertItems(day as Lang.Dictionary or Null) as Lang.Array or Null {
        var v3 = dictAt(day, "al");
        if (v3 != null) {
            return arrAt(v3, "top");
        }
        var alerts = dictAt(day, "alerts");
        return (alerts == null) ? null : arrAt(alerts, "items");
    }

    static function alertMessage(alert as Lang.Dictionary) as Lang.String {
        var m = strAt(alert, "m");
        if (m.equals("")) {
            m = strAt(alert, "message");
        }
        return m;
    }

    static function alertSeverity(alert as Lang.Dictionary) as Lang.String {
        var s = strAt(alert, "s");
        if (s.equals("")) {
            s = strAt(alert, "severity");
        }
        return s;
    }

    //! journal streak: v3 "streak" or v2 "journal_streak".
    static function streak(day as Lang.Dictionary or Null) as Lang.Number {
        if (day == null) {
            return 0;
        }
        var s = day.get("streak");
        if (s == null) {
            s = day.get("journal_streak");
        }
        return asNum(s);
    }

    //! weekday 0=Mon..6=Sun (v2 "weekday"; v3 "wd").
    static function weekday(day as Lang.Dictionary or Null) as Lang.Number {
        if (day == null) {
            return -1;
        }
        var wd = day.get("wd");
        if (wd == null) {
            wd = day.get("weekday");
        }
        return asNum(wd);
    }

    //! local date string (v2 "date"; v3 "d").
    static function dateOf(day as Lang.Dictionary or Null) as Lang.String {
        if (day == null) {
            return "";
        }
        var d = strAt(day, "d");
        if (d.equals("")) {
            d = strAt(day, "date");
        }
        return d;
    }

    // -------------------------------------------------------- event queue
    // Client events are queued in Application.Storage and flushed together
    // with the next fetch (never their own radio wake-up), except
    // post-workout feedback which may flush once immediately.

    static const EVENT_SET_LOG = "set_log";
    static const EVENT_FEEDBACK = "feedback";
    static const EVENT_SUPPLEMENT = "supplement";
    static const EVENT_MOOD = "mood";

    //! Pseudo-unique client event id (the server dedupes by id). No UUID API
    //! in Monkey C — epoch seconds + Math.rand() hex is unique enough for a
    //! single-device queue.
    static function newEventId() as Lang.String {
        var ts = Time.now().value().toNumber();
        var rnd = Math.rand() & 0xFFFF;
        return Lang.format("$1$-$2$", [ts.format("%08x"), rnd.format("%04x")]);
    }

    static function makeEvent(eventType as Lang.String, data as Lang.Dictionary) as Lang.Dictionary {
        return { "id" => newEventId(), "type" => eventType,
                 "at" => Time.now().value().toNumber(), "d" => data } as Lang.Dictionary;
    }

    //! Minutes since the given epoch-seconds timestamp (clamped >= 0).
    static function minutesSince(epochSeconds as Lang.Number) as Lang.Number {
        if (epochSeconds <= 0) {
            return -1;  // never synced
        }
        var now = Time.now().value();
        var delta = (now - epochSeconds) / 60;
        return (delta < 0) ? 0 : delta;
    }
}
