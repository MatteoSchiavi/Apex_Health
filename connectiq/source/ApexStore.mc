// Apex Day — Application.Storage wrapper (the ONLY code that touches Storage).
//
// Battery architecture: the wrist never blocks on the radio to paint. The
// background temporal event fetches and persists; the glance and the views
// render from this cache in milliseconds.
//
// Platform facts this code relies on (see README "Platform facts"):
//   * Storage values <= 8 KB each, ~128 KB total (conservative documented
//     bounds) — the day payload is <= 4 KB by contract, the week payload can
//     exceed 8 KB in the worst case, so a failed week write is caught and
//     flagged instead of crashing.
//   * Writing Storage from a background process needs CIQ 3.2+ (fenix7pro is
//     CIQ 4.x). A firmware bug was reported around Storage.setValue() on some
//     models — every setValue is therefore wrapped in try/catch AND verified
//     by a read-back.
//   * Background processes may READ properties but never write them.
//
// (:background): shared by the background service and the main app.
// The glance reads via loadDay()/loadMeta() — it is (:glance)-annotated and
// this class is compiled into that build too.

using Toybox.Application;
using Toybox.Lang;
using Toybox.Time;

(:background, :glance)
class ApexStore {

    static const KEY_DAY = "$ApexDay";
    static const KEY_WEEK = "$ApexWeek";
    static const KEY_EVENTS = "$ApexEvents";
    static const KEY_META = "$ApexMeta";
    static const KEY_SUP_TAKEN = "$ApexSupTaken";

    static const MAX_EVENTS = 100;   // spec 6.5.6: max 100 queued events
    static const MAX_EVENT_BATCH = 50; // spec 6.3: max 50 events per POST

    // ------------------------------------------------------------ raw pairs

    static function _put(key as Lang.String, value as Application.PersistableType) as Lang.Boolean {
        var ok = false;
        try {
            Application.Storage.setValue(key, value);
            // read-back check: guards the known firmware setValue bug
            ok = (Application.Storage.getValue(key) != null);
        } catch (ex) {
            ok = false;
        }
        return ok;
    }

    static function _get(key as Lang.String) {
        var value = null;
        try {
            value = Application.Storage.getValue(key);
        } catch (ex) {
            value = null;
        }
        return value;
    }

    static function _del(key as Lang.String) as Void {
        try {
            Application.Storage.deleteValue(key);
        } catch (ex) {
            // nothing to do — deleting a missing key is fine
        }
    }

    // ----------------------------------------------------------- day cache

    static function saveDay(day as Lang.Dictionary or Null) as Lang.Boolean {
        if (day == null) {
            return false;
        }
        return _put(KEY_DAY, day);
    }

    static function loadDay() as Lang.Dictionary or Null {
        return ApexPayload.asDict(_get(KEY_DAY));
    }

    // ---------------------------------------------------------- week cache

    static function saveWeek(week as Lang.Dictionary or Null) as Lang.Boolean {
        if (week == null) {
            return false;
        }
        var ok = _put(KEY_WEEK, week);
        if (!ok) {
            // payload too large for one Storage value — flag, don't crash
            setMetaFlag("weekSkip", true);
        }
        return ok;
    }

    static function loadWeek() as Lang.Dictionary or Null {
        return ApexPayload.asDict(_get(KEY_WEEK));
    }

    // ---------------------------------------------------------------- meta

    static function loadMeta() as Lang.Dictionary {
        var meta = ApexPayload.asDict(_get(KEY_META));
        if (meta == null) {
            meta = {};
        }
        return meta;
    }

    static function saveMeta(meta as Lang.Dictionary) as Lang.Boolean {
        return _put(KEY_META, meta);
    }

    static function metaNum(key as Lang.String) as Lang.Number {
        return ApexPayload.numAt(loadMeta(), key);
    }

    static function metaBool(key as Lang.String) as Lang.Boolean {
        return ApexPayload.boolAt(loadMeta(), key);
    }

    static function setMetaNum(key as Lang.String, value as Lang.Number) as Void {
        var meta = loadMeta();
        meta.put(key, value);
        saveMeta(meta);
    }

    static function setMetaFlag(key as Lang.String, value as Lang.Boolean) as Void {
        var meta = loadMeta();
        meta.put(key, value);
        saveMeta(meta);
    }

    // -------------------------------------------------------- event queue
    // Oldest-drop policy: when MAX_EVENTS is reached the oldest event is
    // removed and a visible warning flag is set (spec 6.5.6). Returns
    // "ok" | "dropped" | "failed".

    static function addEvent(event as Lang.Dictionary) as Lang.String {
        var events = ApexPayload.asArr(_get(KEY_EVENTS));
        if (events == null) {
            events = [];
        }
        var result = "ok";
        if (events.size() >= MAX_EVENTS) {
            // drop the oldest without indexing (checker-safe)
            events = events.slice(1, events.size());
            setMetaFlag("queueWarned", true);
            result = "dropped";
        }
        events.add(event);
        return _put(KEY_EVENTS, events) ? result : "failed";
    }

    static function pendingEvents() as Lang.Array {
        var events = ApexPayload.asArr(_get(KEY_EVENTS));
        return (events == null) ? [] : events;
    }

    static function pendingCount() as Lang.Number {
        return pendingEvents().size();
    }

    //! Remove the given event dicts (matched by client id) — called after a
    //! successful POST /watch/events so retries never duplicate.
    static function removeEventsByIds(ids as Lang.Array) as Void {
        if (ids.size() == 0) {
            return;
        }
        var events = pendingEvents();
        var keep = [];
        for (var i = 0; i < events.size(); i += 1) {
            var ev = ApexPayload.asDict(events[i]);
            if (ev == null) {
                continue;
            }
            var id = ApexPayload.asStr(ev.get("id"));
            var drop = false;
            for (var j = 0; j < ids.size(); j += 1) {
                if (id.equals(ApexPayload.asStr(ids[j]))) {
                    drop = true;
                    break;
                }
            }
            if (!drop) {
                keep.add(ev);
            }
        }
        _put(KEY_EVENTS, keep);
    }

    //! Take up to MAX_EVENT_BATCH events for one POST (does not remove them;
    //! removal happens only after the server accepted the batch).
    static function takeEventBatch() as Lang.Array {
        var events = pendingEvents();
        var batch = [];
        var limit = (events.size() < MAX_EVENT_BATCH) ? events.size() : MAX_EVENT_BATCH;
        for (var i = 0; i < limit; i += 1) {
            batch.add(events[i]);
        }
        return batch;
    }

    // ---------------------------------------------------- supplement marks
    // Local adherence marks for today (name -> epoch). Reset when the server
    // date changes so yesterday's checks never pose as today's.

    static function supplementTakenDate() as Lang.String {
        var state = ApexPayload.asDict(_get(KEY_SUP_TAKEN));
        return (state == null) ? "" : ApexPayload.strAt(state, "date");
    }

    static function supplementTakenAt(name as Lang.String) as Lang.Number {
        var state = ApexPayload.asDict(_get(KEY_SUP_TAKEN));
        if (state == null) {
            return 0;
        }
        return ApexPayload.numAt(state, name);
    }

    static function markSupplementTaken(dayDate as Lang.String, name as Lang.String) as Void {
        var state = ApexPayload.asDict(_get(KEY_SUP_TAKEN));
        if (state == null || !ApexPayload.strAt(state, "date").equals(dayDate)) {
            state = { "date" => dayDate };
        }
        state.put(name, Time.now().value());
        _put(KEY_SUP_TAKEN, state);
    }

    // -------------------------------------------------------- 401 revocation
    // A revoked token must never pose stale data as current: wipe EVERYTHING
    // cached (day, week, queued events, marks) and keep only authError=true.

    static function wipeForAuthError() as Void {
        _del(KEY_DAY);
        _del(KEY_WEEK);
        _del(KEY_EVENTS);
        _del(KEY_SUP_TAKEN);
        var meta = {};
        meta.put("authError", true);
        saveMeta(meta);
    }
}
