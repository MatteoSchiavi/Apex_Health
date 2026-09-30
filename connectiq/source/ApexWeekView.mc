// Apex Day — WEEK view (Phase 10 v2): the 7-day gym schedule, Monday-
// anchored on the owner's local week (the server resolves each date:
// planned sessions override the recurring template, per app/queries/gym.py).
//
// One row per day: "Mon 18:00 Push Day" or "Tue — rest". Today's row is
// highlighted yellow. Fetched on open; cached copy paints instantly first.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.System;
using Toybox.Timer;
using Toybox.WatchUi;

class ApexWeekView extends WatchUi.View {

    var _timer;
    var _fetching;
    var _scroll;
    var _maxScroll;
    var _todayWeekday;

    function initialize() {
        View.initialize();
        _fetching = false;
        _scroll = 0;
        _maxScroll = 0;
        _todayWeekday = -1;
    }

    function page(direction as Number) as Void {
        var step = 120;
        _scroll = _scroll + direction * step;
        if (_scroll < 0) {
            _scroll = 0;
        }
        if (_scroll > _maxScroll) {
            _scroll = _maxScroll;
        }
    }

    function onShow() as Void {
        View.onShow();
        var day = ApexDayService.cachedDay();
        if (day != null && day.get("weekday") != null) {
            _todayWeekday = day.get("weekday").toNumber();
        }
        _refresh();
        _timer = new Timer.Timer();
        _timer.start(method(:_refresh), 15 * 60 * 1000, true);
    }

    function onHide() as Void {
        if (_timer != null) {
            _timer.stop();
        }
        View.onHide();
    }

    function _refresh() as Void {
        _fetching = true;
        var service = new ApexDayService();
        service.fetchWeek(method(:_onFetched));
    }

    function _onFetched(responseCode as Number, data as Dictionary or Null) as Void {
        _fetching = false;
        if (responseCode == 401) {
            WatchUi.showToast("Apex: token invalid — check settings");
        } else if (responseCode != 200) {
            WatchUi.showToast("Apex: sync failed (" + responseCode + ")");
        }
        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Dc) as Void {
        View.onUpdate(dc);

        var w = dc.getWidth();
        var h = dc.getHeight();
        var pad = w / 16;
        var week = ApexDayService.cachedWeek();

        var lines = [];
        lines.add(_line("WEEK", Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));

        if (week == null) {
            var msg = _fetching ? "Syncing..." : "No data yet";
            lines.add(_line(msg, Graphics.FONT_TINY, Graphics.COLOR_LT_GRAY, 8, 0));
            _paint(dc, lines, h, pad);
            return;
        }

        var days = week.get("days");
        if (days != null) {
            for (var i = 0; i < days.size(); i += 1) {
                var dayEntry = days[i];
                var weekday = dayEntry.get("weekday").toNumber();
                var name = ApexFormat.weekdayName(weekday);
                var sessions = dayEntry.get("sessions");
                if (sessions == null || sessions.size() == 0) {
                    lines.add(_line(name + " — rest", Graphics.FONT_TINY,
                                    Graphics.COLOR_DK_GRAY, 4, 0));
                } else {
                    for (var j = 0; j < sessions.size(); j += 1) {
                        var s = sessions[j];
                        var start = ApexFormat.startLabel(s.get("start"));
                        var when = (start.equals("")) ? "" : start + " ";
                        var row = name + "  " + when + ApexFormat.sessionTitle(s);
                        var color = (weekday == _todayWeekday)
                            ? Graphics.COLOR_YELLOW
                            : Graphics.COLOR_WHITE;
                        lines.add(_line(row, Graphics.FONT_TINY, color, 4,
                                        (j > 0) ? 12 : 0));
                    }
                }
            }
        }
        _paint(dc, lines, h, pad);
    }

    private function _line(text, font, color, gap, indent) as Dictionary {
        return { :text => text, :font => font, :color => color,
                 :gap => gap, :indent => indent };
    }

    private function _paint(dc as Dc, lines as Array, h as Number, pad as Number) as Void {
        dc.clear();
        var lineHeight = h / 14;
        var y = pad - _scroll;
        for (var i = 0; i < lines.size(); i += 1) {
            var line = lines[i];
            if (y + lineHeight > 0 && y < h) {
                dc.setColor(line.get("color"), Graphics.COLOR_TRANSPARENT);
                dc.drawText(pad + line.get("indent").toNumber(), y,
                            line.get("font"), line.get("text"),
                            Graphics.TEXT_JUSTIFY_LEFT);
            }
            y += lineHeight + line.get("gap").toNumber();
        }
        _maxScroll = (y > h) ? (y - h) : 0;
        if (_scroll > _maxScroll) {
            _scroll = _maxScroll;
        }
    }
}

class ApexWeekDelegate extends WatchUi.BehaviorDelegate {

    var _view;

    function initialize(view as ApexWeekView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onBack() as Boolean {
        WatchUi.switchToView(new ApexMainMenu(), new ApexMenuDelegate(),
                             WatchUi.SLIDE_IMMEDIATE);
        return true;
    }

    function onNextPage() as Boolean {
        _view.page(1);
        WatchUi.requestUpdate();
        return true;
    }

    function onPreviousPage() as Boolean {
        _view.page(-1);
        WatchUi.requestUpdate();
        return true;
    }

    function onSelect() as Boolean {
        var service = new ApexDayService();
        service.fetchWeek(method(:_noop));
        return true;
    }

    function _noop(responseCode as Number, data as Dictionary or Null) as Void {
        WatchUi.requestUpdate();
    }
}
