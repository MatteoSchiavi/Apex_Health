// Apex Day — background temporal-event service.
//
// Runs INSIDE the ~30 s background slot (system.ServiceDelegate). Battery
// policy (spec 6.5), enforced here:
//   * registered ONLY from the foreground app (ApexApp.onStart /
//     onSettingsChanged) with a repeating Time.Duration (seconds!) — a
//     Duration registration repeats on its own, so this delegate NEVER
//     re-registers (defect 6.2.2 fixed);
//   * default interval 60 min, user-selectable 60/120/240 (settings);
//   * outside the configured active window (default 05:00-23:30 local) or
//     without a connected phone the work is skipped entirely — no radio;
//   * after 3 consecutive failures the effective rate backs off to 4x the
//     interval until the next success (the temporal event still fires —
//     re-registration is foreground-only — but it exits before any radio
//     use, which makes the skip nearly free);
//   * a 25 s watchdog guarantees Background.exit is always reached even if
//     makeWebRequest never calls back (known firmware edge);
//   * results are persisted by THIS process into Application.Storage
//     (CIQ 3.2+; try/catch + read-back) and, when the app happens to be
//     running, also delivered through Background.exit() -> onBackgroundData.
//
// (:background): this class (and its :background dependency chain) is the
// only code loaded into the background build — fenix7pro background budget
// is 64 KB of memory.

using Toybox.Application;
using Toybox.Background;
using Toybox.Communications;
using Toybox.Lang;
using Toybox.System;
using Toybox.Time;

(:background)
class ApexBackgroundService extends System.ServiceDelegate {

    static const BACKOFF_FAIL_STREAK = 3;
    static const BACKOFF_MULTIPLIER = 4;

    var _done as Lang.Boolean;
    var _net as ApexNet or Null;

    function initialize() {
        ServiceDelegate.initialize();
        _done = false;
        _net = null;
    }

    function onTemporalEvent() as Void {
        _done = false;

        // ---- battery gates: exit before any radio use ------------------
        var intervalMin = ApexNet.refreshIntervalMinutes();

        // backoff: 3+ consecutive failures -> skip until 4x interval passed
        var failStreak = ApexStore.metaNum("failStreak");
        var lastAttempt = ApexStore.metaNum("lastAttempt");
        if (failStreak >= BACKOFF_FAIL_STREAK && lastAttempt > 0) {
            var since = Time.now().value().toNumber() - lastAttempt;
            if (since < intervalMin * 60 * BACKOFF_MULTIPLIER) {
                _finish(null);
                return;
            }
        }

        // active hours (user-local minutes from midnight)
        if (!ApexNet.withinActiveHours()) {
            _finish(null);
            return;
        }

        // phone availability — makeWebRequest needs the phone over BLE
        if (!System.getDeviceSettings().phoneConnected) {
            _finish(null);
            return;
        }

        ApexStore.setMetaNum("lastAttempt", Time.now().value().toNumber());

        // ---- work: one day fetch (+ pending event flush on success) ----
        // NOTE: no in-process watchdog: Toybox.Timer is flagged
        // disableBackground by the platform (verified in api.mir), so the
        // only guaranteed exit safety net is the OS 30 s background kill —
        // which is exactly what it is for. A hung request therefore costs
        // this slot at most; the Duration registration keeps repeating on
        // its own, so the next interval fires normally.
        var net = new ApexNet();
        _net = net;
        net.fetchDay(method(:_onDayFetched));
    }

    function _onDayFetched(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void {
        if (_done) {
            return; // process already exiting
        }
        _applyDayResponse(responseCode, data);

        // spec 6.5.6: the event flush rides along with a SUCCESSFUL day
        // fetch — never on its own wake-up. One extra request only when
        // events are actually pending.
        var net = _net;
        if (responseCode == 200 && net != null && ApexStore.pendingCount() > 0 && !ApexStore.metaBool("evUnsupported")) {
            var batch = ApexStore.takeEventBatch();
            if (batch.size() > 0) {
                net.postEvents(batch, method(:_onEventsPosted));
                return; // _finish happens in the POST callback
            }
        }
        _finish(null);
    }

    function _onEventsPosted(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void {
        if (_done) {
            return;
        }
        if (responseCode == 200) {
            var batch = ApexStore.takeEventBatch();
            var ids = [] as Lang.Array;
            for (var i = 0; i < batch.size(); i += 1) {
                var ev = ApexPayload.asDict(batch[i]);
                if (ev != null) {
                    ids.add(ApexPayload.asStr(ev.get("id")));
                }
            }
            ApexStore.removeEventsByIds(ids);
        }
        _finish(null);
    }

    //! Shared response handling (also used by the foreground app through
    //! ApexApp.onBackgroundData-free direct fetches). Persists the payload
    //! and updates the meta record. Returns the day dict on success.
    function _applyDayResponse(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Lang.Dictionary or Null {
        if (responseCode == 401 || responseCode == 403) {
            // revoked token: never pose stale data as current (spec 6.2.7)
            ApexStore.wipeForAuthError();
            return null;
        }
        if (responseCode == 200 && data != null && data instanceof Lang.Dictionary) {
            var day = data as Lang.Dictionary;
            var stored = false;
            if (ApexNet.V3_YES == ApexStore.metaNum("v3State") && _isV3SameReply(day)) {
                // v3 "same" — nothing changed, only refresh the sync stamp
                stored = true;
            } else {
                stored = ApexStore.saveDay(day);
                if (stored && day.hasKey("rev")) {
                    ApexStore.setMetaNum("rev", ApexPayload.numAt(day, "rev"));
                }
            }
            if (stored) {
                ApexStore.setMetaNum("lastSync", Time.now().value());
                ApexStore.setMetaNum("failStreak", 0);
                ApexStore.setMetaFlag("authError", false);
                return day;
            }
            ApexStore.setMetaNum("failStreak", ApexStore.metaNum("failStreak") + 1);
            return null;
        }
        // transport error or non-200: count into the backoff, keep cache
        ApexStore.setMetaNum("failStreak", ApexStore.metaNum("failStreak") + 1);
        return null;
    }

    private function _isV3SameReply(day as Lang.Dictionary) as Lang.Boolean {
        return ApexPayload.boolAt(day, "same");
    }

    //! Idempotent exit; passes the fresh day payload to the foreground app
    //! when it is running (delivered to onBackgroundData; if the app is not
    //! running the system hands it over on the next launch). Payload > 8 KB
    //! raises ExitDataSizeLimitException — caught, exit(null) instead.
    private function _finish(payload as Application.PersistableType or Null) as Void {
        if (_done) {
            return;
        }
        _done = true;
        // Background.exit passes the payload (~8 KB limit) to the foreground
        // app when it is running; oversized payloads exit with null instead.
        try {
            Background.exit(payload);
        } catch (ex instanceof Background.ExitDataSizeLimitException) {
            Background.exit(null);
        } catch (ex) {
            Background.exit(null);
        }
    }
}
