// Apex Day — TODAY view: everything Apex knows about today that the watch
// itself does NOT show (spec 6.6 #1):
//   * safety verdict + first reason + intensity ceiling (Apex-only)
//   * workout card: title, minutes, status, "find it" hint
//   * next supplement due
//   * gear due / event countdown / weather window (v3 blocks when present)
//   * open alerts count, journal streak
//
// Readiness / recovery / Body Battery / HR / sleep are deliberately absent —
// the device shows those natively.
//
// Battery: fetch on open + on SELECT only. No timers while the view is open
// (the old 15-minute repeating timer is gone — defect 6.2.5).

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.System;
using Toybox.WatchUi;

class ApexTodayView extends ApexBaseView {

    function initialize() {
        ApexBaseView.initialize();
    }

    function onShow() as Void {
        View.onShow();
        refresh();
    }

    function onHide() as Void {
        setFetching(false);
        View.onHide();
    }

    //! Manual refresh (SELECT) — the only radio use besides onShow.
    function refresh() as Void {
        _refresh();
    }

    private function _refresh() as Void {
        setFetching(true);
        var net = new ApexNet();
        net.fetchDay(method(:_onFetched));
    }

    function _onFetched(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void {
        setFetching(false);
        if (responseCode == 200) {
            setSyncedAt(ApexBaseView.clockStamp());
            resetScroll();
        } else if (responseCode == 401 || responseCode == 403) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.TokenInvalidHint), null);
        } else if (responseCode >= 0) {
            WatchUi.showToast(Lang.format(
                WatchUi.loadResource(Rez.Strings.SyncFailedCode).toString(), [responseCode]), null);
        }
        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        View.onUpdate(dc);
        var lines = [];
        var day = ApexStore.loadDay();

        lines.add(ApexBaseView.line("APEX", Graphics.FONT_XTINY,
                 Graphics.COLOR_DK_GRAY, 4, 0));

        if (ApexStore.metaBool("authError") && day == null) {
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.TokenInvalid).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_RED, 6, 0));
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.CheckSettings).toString(),
                Graphics.FONT_TINY, Graphics.COLOR_LT_GRAY, 4, 0));
            paintLines(dc, lines);
            return;
        }

        if (day == null) {
            lines.add(ApexBaseView.line(
                fetchingLabel(), Graphics.FONT_SMALL, Graphics.COLOR_LT_GRAY, 6, 0));
            lines.add(footerLine());
            paintLines(dc, lines);
            return;
        }

        // ---- verdict banner
        var verdict = ApexPayload.verdictOf(day);
        if (!verdict.equals("")) {
            lines.add(ApexBaseView.line(ApexFormat.verdictLabel(verdict),
                     Graphics.FONT_MEDIUM, ApexFormat.verdictColor(verdict), 4, 0));
            var reasons = ApexPayload.verdictReasons(day);
            if (reasons != null && reasons.size() > 0) {
                lines.add(ApexBaseView.line(ApexFormat.text(reasons[0]),
                         Graphics.FONT_TINY, Graphics.COLOR_DK_GRAY, 4, 8));
            }
            var ceiling = ApexPayload.verdictCeiling(day);
            if (!ceiling.equals("")) {
                lines.add(ApexBaseView.line(Lang.format(
                    WatchUi.loadResource(Rez.Strings.Ceiling).toString(), [ceiling]),
                    Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 8));
            }
        }

        // ---- workout card (published workout wins, gym plan is fallback)
        var title = "";
        var minutes = 0;
        var wo = ApexPayload.workoutBlock(day);
        if (wo != null) {
            title = ApexPayload.strAt(wo, "t");
            minutes = ApexPayload.numAt(wo, "min");
        }
        if (title.equals("")) {
            var gym = ApexPayload.gymBlock(day);
            if (gym != null) {
                title = ApexPayload.strAt(gym, "title");
            }
        }
        if (title.equals("")) {
            var sessions = ApexPayload.arrAt(day, "sessions");
            if (sessions != null && sessions.size() > 0) {
                var first = ApexPayload.asDict(sessions[0]);
                if (first != null) {
                    title = ApexPayload.strAt(first, "title");
                    minutes = ApexPayload.numAt(first, "duration");
                }
            }
        }
        if (title.equals("")) {
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.GymRestDay).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_WHITE, 8, 0));
        } else {
            var head = title;
            if (minutes > 0) {
                head = head + " · " + minutes + " " +
                    WatchUi.loadResource(Rez.Strings.MinShortLabel).toString();
            }
            lines.add(ApexBaseView.line(head, Graphics.FONT_SMALL,
                     Graphics.COLOR_YELLOW, 4, 0));
            if (wo != null) {
                lines.add(ApexBaseView.line(
                    WatchUi.loadResource(_statusResId(ApexPayload.strAt(wo, "st"))).toString(),
                    Graphics.FONT_XTINY, Graphics.COLOR_WHITE, 4, 8));
            }
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.WoFindIt).toString() + " " +
                WatchUi.loadResource(Rez.Strings.WoFindHint).toString(),
                Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 8));
        }

        // ---- next supplement
        var sup = ApexPayload.supplementList(day);
        if (sup != null && sup.size() > 0) {
            var s0 = ApexPayload.asDict(sup[0]);
            if (s0 != null) {
                var dose = ApexPayload.supplementDose(s0);
                var name = ApexPayload.supplementName(s0);
                var supLine = (dose.equals("")) ? name : name + " — " + dose;
                if (sup.size() > 1) {
                    supLine = supLine + " (+" + (sup.size() - 1) + ")";
                }
                lines.add(ApexBaseView.line(supLine, Graphics.FONT_TINY,
                         Graphics.COLOR_WHITE, 6, 0));
            }
        }

        // ---- gear due (v3)
        var gear = ApexPayload.arrAt(day, "gear");
        if (gear != null && gear.size() > 0) {
            var g0 = ApexPayload.asDict(gear[0]);
            if (g0 != null) {
                var hours = ApexPayload.numAt(g0, "h");
                var lim = ApexPayload.numAt(g0, "lim");
                var over = (lim > 0 && hours >= lim * 9 / 10);
                lines.add(ApexBaseView.line(
                    ApexPayload.strAt(g0, "n") + " " + hours + "/" + lim + "h",
                    Graphics.FONT_XTINY, over ? Graphics.COLOR_RED : Graphics.COLOR_WHITE,
                    4, 0));
            }
        }

        // ---- event countdown (v3)
        var ev = ApexPayload.dictAt(day, "ev");
        if (ev != null) {
            var evName = ApexPayload.strAt(ev, "t");
            var evDays = ApexPayload.numAt(ev, "days");
            if (!evName.equals("")) {
                var evLine = Lang.format(
                    WatchUi.loadResource(Rez.Strings.EventIn).toString(),
                    [evDays, evName]);
                var taper = ApexPayload.numAt(ev, "taper");
                if (taper > 0 && evDays <= taper) {
                    evLine = evLine + " · " + Lang.format(
                        WatchUi.loadResource(Rez.Strings.TaperLabel).toString(), [taper]);
                }
                lines.add(ApexBaseView.line(evLine, Graphics.FONT_XTINY,
                         Graphics.COLOR_WHITE, 4, 0));
            }
        }

        // ---- weather window (v3)
        var wx = ApexPayload.dictAt(day, "wx");
        if (wx != null) {
            var tmin = ApexPayload.numAt(wx, "tmin");
            var tmax = ApexPayload.numAt(wx, "tmax");
            var wind = ApexPayload.numAt(wx, "wind");
            var rain = ApexPayload.numAt(wx, "rain");
            lines.add(ApexBaseView.line(
                Lang.format(WatchUi.loadResource(Rez.Strings.CondTemp).toString(), [tmin, tmax])
                + " · " + Lang.format(WatchUi.loadResource(Rez.Strings.CondWind).toString(), [wind])
                + " · " + Lang.format(WatchUi.loadResource(Rez.Strings.CondRain).toString(), [rain]),
                Graphics.FONT_XTINY, Graphics.COLOR_WHITE, 4, 0));
        }

        // ---- alerts + streak + footer
        var alertCount = ApexPayload.alertCount(day);
        if (alertCount > 0) {
            lines.add(ApexBaseView.line(Lang.format(
                WatchUi.loadResource(Rez.Strings.AlertsOpen).toString(), [alertCount]),
                Graphics.FONT_XTINY, Graphics.COLOR_YELLOW, 4, 0));
        }
        var streak = ApexPayload.streak(day);
        if (streak > 0) {
            lines.add(ApexBaseView.line(streak + "d", Graphics.FONT_XTINY,
                     Graphics.COLOR_DK_GRAY, 6, 0));
        }
        lines.add(footerLine());
        paintLines(dc, lines);
    }

    private function _statusResId(status as Lang.String) as Lang.ResourceId {
        if (status.equals("scheduled") || status.equals("published") || status.equals("on_watch")) {
            return Rez.Strings.WoPublished;
        }
        if (status.equals("removed")) {
            return Rez.Strings.WoRemoved;
        }
        if (status.equals("held")) {
            return Rez.Strings.WoHeld;
        }
        if (status.equals("failed")) {
            return Rez.Strings.WoFailed;
        }
        return Rez.Strings.WoUnknown;
    }

    private function fetchingLabel() as Lang.String {
        return (_fetching)
            ? WatchUi.loadResource(Rez.Strings.Syncing).toString()
            : WatchUi.loadResource(Rez.Strings.NoDataYet).toString();
    }
}

class ApexTodayDelegate extends ApexDelegate {

    function initialize(view as ApexTodayView) {
        ApexDelegate.initialize(view);
    }

    function onSelect() as Lang.Boolean {
        var todayView = _view as ApexTodayView;
        if (todayView != null) {
            todayView.refresh();
        }
        return true;
    }
}
