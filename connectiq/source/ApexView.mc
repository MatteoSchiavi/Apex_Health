// Apex Health — foreground view: full values, live refresh on open and a
// 15-minute timer while open. The glance stays the primary surface; this
// view is for "open the app and look properly".

using Toybox.Application;
using Toybox.Graphics;
using Toybox.Lang;
using Toybox.System;
using Toybox.Timer;
using Toybox.WatchUi;

class ApexView extends WatchUi.View {

    var _timer;
    var _fetching;

    function initialize() {
        View.initialize();
        _fetching = false;
    }

    function onLayout(dc as Dc) as Void {
        View.onLayout(dc);
    }

    function onShow() as Void {
        View.onShow();
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
        var service = new ApexTodayService();
        service.fetch(method(:_onFetched));
    }

    function _onFetched(responseCode as Number, data as Dictionary or Null) as Void {
        _fetching = false;
        if (responseCode == 401) {
            WatchUi.showToast("Apex: token invalid — re-check settings");
        } else if (responseCode != 200) {
            WatchUi.showToast("Apex: sync failed (" + responseCode + ")");
        }
        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Dc) as Void {
        View.onUpdate(dc);
        dc.clear();

        var w = dc.getWidth();
        var h = dc.getHeight();
        var cached = ApexTodayService.cached();

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h / 8, Graphics.FONT_MEDIUM, "Apex Health",
                    Graphics.TEXT_JUSTIFY_CENTER);

        if (cached == null) {
            dc.setColor(Graphics.COLOR_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 2, h / 2, Graphics.FONT_SMALL, _fetching
                        ? "Syncing..." : "No data yet", Graphics.TEXT_JUSTIFY_CENTER);
            return;
        }

        var rows = [
            { "label" => "READINESS", "value" => cached.get("readiness"), "goodHigh" => true },
            { "label" => "RECOVERY",  "value" => cached.get("recovery"),  "goodHigh" => true },
            { "label" => "STRAIN",    "value" => cached.get("strain"),    "goodHigh" => false }
        ];

        var top = h * 0.28;
        var rowH = h * 0.2;
        for (var i = 0; i < rows.size(); i += 1) {
            var value = rows[i].get("value");
            dc.setColor(Graphics.COLOR_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 6, top + i * rowH, Graphics.FONT_TINY, rows[i].get("label"),
                        Graphics.TEXT_JUSTIFY_LEFT);
            dc.setColor(ApexScore.color(value, rows[i].get("goodHigh")), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w - w / 6, top + i * rowH, Graphics.FONT_LARGE,
                        ApexScore.format(value), Graphics.TEXT_JUSTIFY_RIGHT);
        }

        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h - h / 10, Graphics.FONT_XTINY,
                    "as of " + cached.get("asOfDate"), Graphics.TEXT_JUSTIFY_CENTER);
    }
}

class ApexViewDelegate extends WatchUi.BehaviorDelegate {

    function initialize() {
        BehaviorDelegate.initialize();
    }

    function onBack() as Boolean {
        // Let the system exit the app.
        return false;
    }

    function onSelect() as Boolean {
        // Button press = manual refresh.
        var view = new ApexTodayService();
        view.fetch(method(:_noop));
        return true;
    }

    function _noop(responseCode as Number, data as Dictionary or Null) as Void {
        WatchUi.requestUpdate();
    }
}
