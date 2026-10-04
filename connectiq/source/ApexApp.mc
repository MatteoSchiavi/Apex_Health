// Apex Day — app entry.
//
// Three faces of the same app:
//   * glance  — ApexGlanceView: verdict + workout + counts, painted from
//               Application.Storage in milliseconds, zero radio;
//   * app     — menu (Today / Workout status / Gym / Feedback / Supplements /
//               Alerts / Body & upkeep / Conditions / Mood / Week);
//   * service — ApexBackgroundService (:background build), a repeating
//               temporal event that refreshes the cache for the glance.
//
// Defects of the previous revision fixed here:
//   * the temporal event is registered ONLY here, in the FOREGROUND
//     (onStart / onSettingsChanged), with a Duration in SECONDS that the
//     platform repeats automatically — the service never re-registers;
//   * interval comes from settings (60/120/240 min), clamped to the 5 min
//     platform minimum, 60 min default (the old code passed 30*60*1000
//     "seconds" = 20.8 DAYS between refreshes);
//   * background results arrive through onBackgroundData() and are
//     persisted with a read-back check;
//   * 401 handling keeps wiping all cached data (revoked tokens can never
//     pose stale data as current).
//
// Battery: the app never polls. Views fetch once on open (and on SELECT);
// the only repeating UI timer in the whole app is the rest-timer tick while
// that screen is visible.

using Toybox.Application;
using Toybox.Background;
using Toybox.Lang;
using Toybox.System;
using Toybox.Time;
using Toybox.WatchUi;

// (:background) on the AppBase mirrors Garmin's BackgroundTimer sample: the
// entry point is intentionally part of the background/glance builds, and the
// foreground-only view references inside the entry methods are exempt from
// the cross-scope check (verified against the official sample).
(:background)
class ApexApp extends Application.AppBase {

    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() as [WatchUi.Views] or [WatchUi.Views, WatchUi.InputDelegates] {
        return [new ApexMainMenu(), new ApexMenuDelegate()];
    }

    //! Glance: wired by presence of this method (manifest v3 has no
    //! <iq:glances> element) + minSdkVersion >= 4.0.0.
    function getGlanceView() as [WatchUi.GlanceView] or [WatchUi.GlanceView, WatchUi.GlanceViewDelegate] or Null {
        return [new ApexGlanceView()];
    }

    //! The background process delegate. Class is (:background)-annotated so
    //! only it + its dependency chain load into the 64 KB background build.
    function getServiceDelegate() as [System.ServiceDelegate] {
        return [new ApexBackgroundService()];
    }

    function onStart(state as Lang.Dictionary or Null) as Void {
        AppBase.onStart(state);
        // (Re-)arm the repeating temporal event from the FOREGROUND. This is
        // the only registration point; it overwrites any prior registration
        // (platform allows exactly one temporal event per app). A Duration
        // >= 5 minutes repeats by itself.
        _registerTemporalEvent();
    }

    function onStop(state as Lang.Dictionary or Null) as Void {
        AppBase.onStop(state);
    }

    //! Settings changed from the phone while running: re-arm with the new
    //! interval (and let views pick up units etc. on next paint).
    function onSettingsChanged() as Void {
        AppBase.onSettingsChanged();
        _registerTemporalEvent();
    }

    //! Data from a finished background process: persist (idempotent — the
    //! service already wrote Storage; this re-verifies with a read-back) and
    //! refresh the UI if we are the live foreground app.
    function onBackgroundData(data as Application.PersistableType) as Void {
        var day = ApexPayload.asDict(data);
        if (day != null && !ApexPayload.boolAt(day, "same")) {
            if (ApexStore.saveDay(day)) {
                ApexStore.setMetaNum("lastSync", Time.now().value());
                if (day.hasKey("rev")) {
                    ApexStore.setMetaNum("rev", ApexPayload.numAt(day, "rev"));
                }
            }
        }
        WatchUi.requestUpdate();
    }

    private function _registerTemporalEvent() as Void {
        var minutes = ApexNet.refreshIntervalMinutes();
        Background.registerForTemporalEvent(new Time.Duration(minutes * 60));
    }
}

// ---------------------------------------------------------------------------
// Main menu: the Apex-only surfaces, priority-ordered (P0 first).

class ApexMainMenu extends WatchUi.Menu2 {

    function initialize() {
        Menu2.initialize({:title => WatchUi.loadResource(Rez.Strings.AppTitle) as Lang.String});
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuToday) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubToday) as Lang.String,
            :it_today, null));
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuWorkout) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubWorkout) as Lang.String,
            :it_workout, null));
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuGym) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubGym) as Lang.String,
            :it_gym, null));
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuFeedback) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubFeedback) as Lang.String,
            :it_feedback, null));
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuSupplements) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubSupplements) as Lang.String,
            :it_supplements, null));
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuAlerts) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubAlerts) as Lang.String,
            :it_alerts, null));
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuBody) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubBody) as Lang.String,
            :it_body, null));
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuConditions) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubConditions) as Lang.String,
            :it_conditions, null));
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuMood) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubMood) as Lang.String,
            :it_mood, null));
        addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuWeek) as Lang.String,
            WatchUi.loadResource(Rez.Strings.SubWeek) as Lang.String,
            :it_week, null));
    }
}

class ApexMenuDelegate extends WatchUi.Menu2InputDelegate {

    function initialize() {
        Menu2InputDelegate.initialize();
    }

    //! Menu2 delivers the chosen MenuItem here (NOT onMenuItem — that is
    //! the legacy Menu1 hook; the old app overrode the wrong method, so its
    //! menu could never navigate).
    function onSelect(item as WatchUi.MenuItem) as Void {
        var id = item.getId();
        if (id == null) {
            return;
        }
        if (id.equals(:it_week)) {
            var weekView = new ApexWeekView();
            WatchUi.switchToView(weekView, new ApexWeekDelegate(weekView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else if (id.equals(:it_workout)) {
            var workoutView = new ApexWorkoutView();
            WatchUi.switchToView(workoutView, new ApexWorkoutDelegate(workoutView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else if (id.equals(:it_gym)) {
            var gymView = new ApexGymView();
            WatchUi.switchToView(gymView, new ApexGymDelegate(gymView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else if (id.equals(:it_feedback)) {
            var feedbackView = new ApexFeedbackView();
            WatchUi.switchToView(feedbackView, new ApexFeedbackDelegate(feedbackView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else if (id.equals(:it_supplements)) {
            var supView = new ApexSupplementsView();
            WatchUi.switchToView(supView, new ApexSupplementsDelegate(supView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else if (id.equals(:it_alerts)) {
            var alertsView = new ApexAlertsView();
            WatchUi.switchToView(alertsView, new ApexAlertsDelegate(alertsView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else if (id.equals(:it_body)) {
            var bodyView = new ApexBodyView();
            WatchUi.switchToView(bodyView, new ApexBodyDelegate(bodyView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else if (id.equals(:it_conditions)) {
            var condView = new ApexConditionsView();
            WatchUi.switchToView(condView, new ApexConditionsDelegate(condView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else if (id.equals(:it_mood)) {
            var moodView = new ApexMoodView();
            WatchUi.switchToView(moodView, new ApexMoodDelegate(moodView),
                                 WatchUi.SLIDE_IMMEDIATE);
        } else {
            var todayView = new ApexTodayView();
            WatchUi.switchToView(todayView, new ApexTodayDelegate(todayView),
                                 WatchUi.SLIDE_IMMEDIATE);
        }
    }
}
