// Apex Day — background service (30-minute temporal event, Phase 10 v2).
//
// Connect IQ pattern for glance data: the PROCESS (not the glance) talks to
// the network, so the wrist stays cool and the glance paints instantly from
// Storage. Refreshes GET /watch/day (gym sessions, supplements, alerts,
// streak — everything the glance needs). After each run we re-register the
// next temporal event and exit — a background process that forgets to exit
// drains batteries and gets killed by the OS.
//
// F-30 audit: watchdog timer guarantees Background.exit(null) is reached
// even if the network layer never calls back (known firmware edge on some
// devices where makeWebRequest silently drops the callback). Without the
// watchdog the temporal slot is burned until the OS kill timeout.

using Toybox.Application;
using Toybox.Background;
using Toybox.Lang;
using Toybox.System;
using Toybox.Time;
using Toybox.Timer;

class ApexBackgroundService extends Application.ServiceDelegate {

    var _watchdog;
    var _done;

    function initialize() {
        ServiceDelegate.initialize();
        _watchdog = null;
        _done = false;
    }

    function onTemporalEvent() as Void {
        _done = false;
        // F-30: watchdog — force Background.exit(null) after 25s if the
        // network layer never calls back. The temporal slot is 30s; without
        // this the slot is burned until the OS kill timeout.
        _watchdog = new Timer.Timer();
        _watchdog.start(method(:_watchdogFire), 25000, false);
        var service = new ApexDayService();
        service.fetchDay(method(:_onFetched));
    }

    function _watchdogFire() as Void {
        if (!_done) {
            System.println("Apex background sync: watchdog fired — network callback never came");
            _finish();
        }
    }

    function _onFetched(responseCode as Number, data as Dictionary or Null) as Void {
        System.println("Apex background sync: " + responseCode);
        _finish();
    }

    function _finish() as Void {
        if (_done) {
            return;  // idempotent — watchdog + callback race is benign
        }
        _done = true;
        if (_watchdog != null) {
            _watchdog.stop();
            _watchdog = null;
        }
        // Arm the next run before exiting (30 minutes).
        Background.registerForTemporalEvent(new Time.Duration(30 * 60 * 1000L));
        Background.exit(null);
    }
}
