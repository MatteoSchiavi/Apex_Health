// Apex Day — app entry (Phase 10 v2, the rethought watch app).
//
// WHY THE RETHINK: readiness / recovery / strain are already native on every
// supported device (Training Readiness, Recovery Time, Body Battery/Load) —
// duplicating them on a data page was a worse copy of what the watch already
// shows. Apex's value on the wrist is the data ONLY Apex holds:
//   * the gym schedule (recurring routine + AI-planned overrides)
//   * active supplements
//   * Apex alerts (low ferritin, sync failures, gear service due, ...)
//   * the journal streak
//
// Three faces of the same app:
//   * glance  — ApexGlanceView: today's gym session + counts, from Storage.
//   * app     — menu (Today / Week / Alerts), each a scrollable view that
//               refreshes live on open.
//   * service — ApexBackgroundService, a 30-minute temporal event that
//               refreshes the day cache for the glance.

using Toybox.Application;
using Toybox.Background;
using Toybox.Lang;
using Toybox.Time;
using Toybox.WatchUi;

class ApexApp extends Application.AppBase {

    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() {
        return [ new ApexMainMenu(), new ApexMenuDelegate() ];
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

// ---------------------------------------------------------------------------
// Main menu: the three Apex-only surfaces.

class ApexMainMenu extends WatchUi.Menu2 {

    function initialize() {
        Menu2.initialize({ :title => "Apex Day" });
        addItem(new WatchUi.MenuItem("Today", "gym · supplements · alerts", null, 1));
        addItem(new WatchUi.MenuItem("Week", "gym schedule", null, 2));
        addItem(new WatchUi.MenuItem("Alerts", "open alerts", null, 3));
    }
}

class ApexMenuDelegate extends WatchUi.Menu2InputDelegate {

    function initialize() {
        Menu2InputDelegate.initialize();
    }

    function onMenuItem(id) as Boolean {
        if (id == 2) {
            var weekView = new ApexWeekView();
            WatchUi.switchToView(weekView, new ApexWeekDelegate(weekView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else if (id == 3) {
            var alertsView = new ApexAlertsView();
            WatchUi.switchToView(alertsView, new ApexAlertsDelegate(alertsView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else {
            var todayView = new ApexTodayView();
            WatchUi.switchToView(todayView, new ApexTodayDelegate(todayView),
                                 WatchUi.SLIDE_IMMEDIATE);
        }
        return true;
    }
}
