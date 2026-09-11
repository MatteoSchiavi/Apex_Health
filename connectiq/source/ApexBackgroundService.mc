// Apex Day — background service (30-minute temporal event, Phase 10 v2).
//
// Connect IQ pattern for glance data: the PROCESS (not the glance) talks to
// the network, so the wrist stays cool and the glance paints instantly from
// Storage. Refreshes GET /watch/day (gym sessions, supplements, alerts,
// streak — everything the glance needs). After each run we re-register the
// next temporal event and exit — a background process that forgets to exit
// drains batteries and gets killed by the OS.

using Toybox.Application;
using Toybox.Background;
using Toybox.Lang;
using Toybox.System;
using Toybox.Time;

class ApexBackgroundService extends Application.ServiceDelegate {

    function initialize() {
        ServiceDelegate.initialize();
    }

    function onTemporalEvent() as Void {
        var service = new ApexDayService();
        service.fetchDay(method(:_onFetched));
    }

    function _onFetched(responseCode as Number, data as Dictionary or Null) as Void {
        System.println("Apex background sync: " + responseCode);
        // Arm the next run before exiting (30 minutes).
        Background.registerForTemporalEvent(new Time.Duration(30 * 60 * 1000L));
        Background.exit(null);
    }
}
