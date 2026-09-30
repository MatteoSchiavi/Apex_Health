// Apex Day — ALERTS view (Phase 10 v2): the open Apex alerts (§17) on the
// wrist. Severity-colored, newest first (server-ordered, max 3 shipped to
// the watch — the full inbox with ack buttons stays in Telegram/web).
//
// Reads the cached /watch/day payload; SELECT re-fetches the day.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

class ApexAlertsView extends WatchUi.View {

    var _scroll;
    var _maxScroll;
    var _fetching;

    function initialize() {
        View.initialize();
        _scroll = 0;
        _maxScroll = 0;
        _fetching = false;
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
        var service = new ApexDayService();
        _fetching = true;
        service.fetchDay(method(:_onFetched));
    }

    function _onFetched(responseCode as Number, data as Dictionary or Null) as Void {
        _fetching = false;
        if (responseCode == 401) {
            WatchUi.showToast("Apex: token invalid — check settings");
        }
        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Dc) as Void {
        View.onUpdate(dc);

        var w = dc.getWidth();
        var h = dc.getHeight();
        var pad = w / 16;
        var cached = ApexDayService.cachedDay();

        var lines = [];
        lines.add(_line("ALERTS", Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));

        var alerts = (cached == null) ? null : cached.get("alerts");
        var alertCount = 0;
        var alertItems = null;
        if (alerts != null) {
            if (alerts.get("count") != null) {
                alertCount = alerts.get("count").toNumber();
            }
            alertItems = alerts.get("items");
        }

        if (alertCount == 0) {
            lines.add(_line(_fetching ? "Checking..." : "Nothing open",
                            Graphics.FONT_SMALL, Graphics.COLOR_WHITE, 8, 0));
        } else {
            lines.add(_line(alertCount + " open", Graphics.FONT_SMALL,
                            Graphics.COLOR_YELLOW, 8, 0));
            if (alertItems != null) {
                for (var i = 0; i < alertItems.size(); i += 1) {
                    var alert = alertItems[i];
                    var msg = ApexFormat.text(alert.get("message"));
                    var wrapped = ApexFormat.wrap(dc, msg, Graphics.FONT_TINY,
                                                  w - pad * 2 - 8);
                    var color = ApexFormat.severityColor(alert.get("severity"));
                    for (var j = 0; j < wrapped.size(); j += 1) {
                        lines.add(_line(wrapped[j], Graphics.FONT_TINY, color, 4, 8));
                    }
                }
            }
            lines.add(_line("(ack in Telegram / web)", Graphics.FONT_XTINY,
                            Graphics.COLOR_DK_GRAY, 10, 0));
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

class ApexAlertsDelegate extends WatchUi.BehaviorDelegate {

    var _view;

    function initialize(view as ApexAlertsView) {
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
        service.fetchDay(method(:_noop));
        return true;
    }

    function _noop(responseCode as Number, data as Dictionary or Null) as Void {
        WatchUi.requestUpdate();
    }
}
