// Apex Health — app entry (MASTER_SPEC §23 Phase 10).
//
// Three faces of the same app:
//   * glance  — ApexGlanceView, drawn from Application.Storage (instant, no
//               network on the wrist); today's readiness / recovery / strain.
//   * app     — ApexView, opens with a live refresh and shows fetch status.
//   * service — ApexBackgroundService, temporal event every 30 minutes that
//               fetches /watch/today and parks it in Storage for the glance.

using Toybox.Application;
using Toybox.Background;
using Toybox.Time;

class ApexApp extends Application.AppBase {

    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() {
        return [ new ApexView(), new ApexViewDelegate() ];
    }

    function getGlanceView() {
        return new ApexGlanceView();
    }

    function getServiceDelegate() {
        return [ new ApexBackgroundService() ];
    }

    function onStart(state) {
        AppBase.onStart(state);
        // Keep the refresh loop alive: register the next 30-minute temporal
        // event. The service re-registers after every run; this covers the
        // first one and re-arming after settings changes.
        if (state == null || state.get("returnData") == null) {
            Background.registerForTemporalEvent(new Time.Duration(30 * 60 * 1000L));
        }
    }

    function onStop(state) {
        AppBase.onStop(state);
    }
}
