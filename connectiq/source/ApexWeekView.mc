// Apex Day — WEEK view (spec 6.6 #10): the 7-day plan, Monday-anchored on
// the owner's local week, today highlighted. Fetched from /watch/week on
// open (cached copy paints instantly first). Simplified on purpose — no
// per-step details, the day payload owns that.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

class ApexWeekView extends ApexBaseView {

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

    function refresh() as Void {
        setFetching(true);
        var net = new ApexNet();
        net.fetchWeek(method(:_onFetched));
    }

    function _onFetched(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void {
        setFetching(false);
        if (responseCode == 200) {
            setSyncedAt(ApexBaseView.clockStamp());
            var week = ApexPayload.asDict(data);
            if (week != null) {
                ApexStore.saveWeek(week); // cache for the next open; over-size is caught
            }
        } else if (responseCode == 401 || responseCode == 403) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.TokenInvalidHint), null);
        }
        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        View.onUpdate(dc);
        var lines = [];
        var day = ApexStore.loadDay();
        var week = ApexStore.loadWeek();

        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.MenuWeek).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));

        if (week == null) {
            lines.add(ApexBaseView.line(
                (_fetching) ? WatchUi.loadResource(Rez.Strings.Syncing).toString()
                            : WatchUi.loadResource(Rez.Strings.NoDataYet).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_LT_GRAY, 6, 0));
            paintLines(dc, lines);
            return;
        }

        var today = ApexPayload.weekday(day);
        var days = ApexPayload.arrAt(week, "days");
        if (days != null) {
            for (var i = 0; i < days.size(); i += 1) {
                var dayEntry = ApexPayload.asDict(days[i]);
                if (dayEntry == null) {
                    continue;
                }
                var wd = ApexPayload.weekday(dayEntry);
                var name = ApexFormat.weekdayName(wd);
                var sessions = ApexPayload.arrAt(dayEntry, "sessions");
                if (sessions == null || sessions.size() == 0) {
                    lines.add(ApexBaseView.line(name + " — " +
                        WatchUi.loadResource(Rez.Strings.WeekRest).toString(),
                        Graphics.FONT_TINY, Graphics.COLOR_DK_GRAY, 4, 0));
                } else {
                    for (var j = 0; j < sessions.size(); j += 1) {
                        var s = ApexPayload.asDict(sessions[j]);
                        if (s == null) {
                            continue;
                        }
                        var start = ApexPayload.strAt(s, "start");
                        var when = start.equals("") ? "" : start + " ";
                        var row = name + "  " + when + ApexPayload.strAt(s, "title");
                        lines.add(ApexBaseView.line(row, Graphics.FONT_TINY,
                                 (wd == today) ? Graphics.COLOR_YELLOW : Graphics.COLOR_WHITE,
                                 4, (j > 0) ? 12 : 0));
                    }
                }
            }
        }
        lines.add(footerLine());
        paintLines(dc, lines);
    }
}

class ApexWeekDelegate extends ApexDelegate {

    function initialize(view as ApexWeekView) {
        ApexDelegate.initialize(view);
    }

    function onSelect() as Lang.Boolean {
        var view = _view as ApexWeekView;
        if (view != null) {
            view.refresh();
        }
        return true;
    }
}
