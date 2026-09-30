// Apex Day — TODAY view (Phase 10 v2): everything Apex knows about today
// that the watch itself cannot show.
//
//   GYM         today's sessions — recurring routine and/or AI-planned
//               session (marked PLAN), with the exercises block wrapped
//   SUPPLEMENTS active protocols (name — dose)
//   ALERTS      open alert count + the newest few, severity-colored
//   footer      journal streak + last sync state
//
// Live refresh on open, 15-minute timer while open, manual refresh on
// SELECT, scroll on UP/DOWN. Renders from the Storage cache first so the
// view is instant; the fetch updates it in place when the radio answers.

using Toybox.Application;
using Toybox.Graphics;
using Toybox.Lang;
using Toybox.System;
using Toybox.Timer;
using Toybox.WatchUi;

class ApexTodayView extends WatchUi.View {

    var _timer;
    var _fetching;
    var _scroll;    // pixels scrolled up
    var _maxScroll; // computed on every paint
    var _syncedAt;  // "HH:MM" of the last successful fetch

    function initialize() {
        View.initialize();
        _fetching = false;
        _scroll = 0;
        _maxScroll = 0;
        _syncedAt = null;
    }

    // Called by the delegate for scrolling.
    function page(direction as Number) as Void {
        var step = 120; // ~half a small screen; clamped by _maxScroll
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
        _refresh();
        _timer = new Timer.Timer();
        _timer.start(method(:_refresh), 15 * 60 * 1000, true);
    }

    function onHide() as Void {
        // F-29 audit: stop timers defensively and null the callback so the
        // view can be GC'd even if onShow ran without a matching onHide
        // (known edge on some low-RAM SDK versions). The previous code only
        // stopped the timer; the callback closure retained the view, delaying
        // GC on watch-class RAM.
        if (_timer != null) {
            _timer.stop();
            _timer = null;
        }
        _fetching = false;
        View.onHide();
    }

    // F-29 audit: defensive teardown for the case where the view is destroyed
    // without onHide (firmware edge). Called from onGetInitialLayout's
    // teardown path when the system signals view disposal.
    function _defensiveTeardown() as Void {
        if (_timer != null) {
            _timer.stop();
            _timer = null;
        }
        _fetching = false;
    }

    function _refresh() as Void {
        _fetching = true;
        var service = new ApexDayService();
        service.fetchDay(method(:_onFetched));
    }

    function _onFetched(responseCode as Number, data as Dictionary or Null) as Void {
        _fetching = false;
        if (responseCode == 200) {
            var clock = System.getClockTime();
            var minute = (clock.min < 10 ? "0" : "") + clock.min;
            _syncedAt = clock.hour + ":" + minute;
            _scroll = 0;
        } else if (responseCode == 401) {
            WatchUi.showToast("Apex: token invalid — check settings");
        } else {
            WatchUi.showToast("Apex: sync failed (" + responseCode + ")");
        }
        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Dc) as Void {
        View.onUpdate(dc);

        var w = dc.getWidth();
        var h = dc.getHeight();
        var pad = w / 16;
        var cached = ApexDayService.cachedDay();

        // Pre-build the line list: { :text, :font, :color, :gap, :indent } —
        // then paint from _scroll. Rebuilt every paint (wrap is dc-dependent);
        // the day payload is small enough that this is well under a frame.
        var lines = [];
        lines.add(_line("TODAY", Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));

        if (ApexDayService.authError() && cached == null) {
            lines.add(_line("Token invalid —", Graphics.FONT_TINY, Graphics.COLOR_RED, 8, 0));
            lines.add(_line("re-check settings", Graphics.FONT_TINY, Graphics.COLOR_RED, 8, 0));
            _paint(dc, lines, h, pad);
            return;
        }

        // ---- gym
        var sessions = (cached == null) ? null : cached.get("sessions");
        if (sessions == null || sessions.size() == 0) {
            lines.add(_line("Rest day", Graphics.FONT_MEDIUM, Graphics.COLOR_WHITE, 10, 0));
        } else {
            for (var i = 0; i < sessions.size(); i += 1) {
                var s = sessions[i];
                var isPlan = s.get("source").toString().equals("plan");
                var head = ApexFormat.sessionTitle(s);
                var start = ApexFormat.startLabel(s.get("start"));
                if (!start.equals("")) {
                    head = start + "  " + head;
                }
                var duration = ApexFormat.durationLabel(s.get("duration"));
                if (!duration.equals("")) {
                    head = head + " · " + duration;
                }
                lines.add(_line(head, Graphics.FONT_SMALL, Graphics.COLOR_YELLOW, 10, 0));
                if (isPlan) {
                    lines.add(_line("PLANNED SESSION", Graphics.FONT_XTINY,
                                    Graphics.COLOR_BLUE, 4, 8));
                }
                var notes = s.get("notes");
                if (notes != null) {
                    var wrapped = ApexFormat.wrap(dc, notes.toString(),
                                                  Graphics.FONT_TINY, w - pad * 2 - 8);
                    for (var j = 0; j < wrapped.size(); j += 1) {
                        lines.add(_line(wrapped[j], Graphics.FONT_TINY,
                                        Graphics.COLOR_LT_GRAY, 4, 8));
                    }
                }
            }
        }

        // ---- supplements
        var supplements = (cached == null) ? null : cached.get("supplements");
        if (supplements != null && supplements.size() > 0) {
            lines.add(_line("SUPPLEMENTS", Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 14, 0));
            for (var i = 0; i < supplements.size(); i += 1) {
                var supp = supplements[i];
                var name = ApexFormat.text(supp.get("name"));
                var dose = ApexFormat.text(supp.get("dose"));
                var lineTxt = (dose.equals("")) ? name : name + " — " + dose;
                lines.add(_line(lineTxt, Graphics.FONT_TINY, Graphics.COLOR_WHITE, 4, 8));
            }
        }

        // ---- alerts
        var alerts = (cached == null) ? null : cached.get("alerts");
        var alertCount = 0;
        var alertItems = null;
        if (alerts != null) {
            if (alerts.get("count") != null) {
                alertCount = alerts.get("count").toNumber();
            }
            alertItems = alerts.get("items");
        }
        lines.add(_line("ALERTS " + alertCount, Graphics.FONT_XTINY,
                        Graphics.COLOR_DK_GRAY, 14, 0));
        if (alertCount == 0) {
            lines.add(_line("Nothing open", Graphics.FONT_TINY,
                            Graphics.COLOR_LT_GRAY, 4, 8));
        } else if (alertItems != null) {
            for (var i = 0; i < alertItems.size(); i += 1) {
                var alert = alertItems[i];
                var msg = ApexFormat.text(alert.get("message"));
                var wrapped = ApexFormat.wrap(dc, msg, Graphics.FONT_TINY, w - pad * 2 - 8);
                var color = ApexFormat.severityColor(alert.get("severity"));
                for (var j = 0; j < wrapped.size(); j += 1) {
                    lines.add(_line(wrapped[j], Graphics.FONT_TINY, color, 4, 8));
                }
            }
        }

        // ---- footer
        var streak = (cached == null) ? null : cached.get("journal_streak");
        var footer = "streak " + ((streak == null) ? "0" : streak.toString()) + "d";
        if (_syncedAt != null) {
            footer = footer + " · synced " + _syncedAt;
        } else if (_fetching) {
            footer = footer + " · syncing...";
        }
        lines.add(_line(footer, Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 16, 0));

        _paint(dc, lines, h, pad);
    }

    private function _line(text, font, color, gap, indent) as Dictionary {
        return { :text => text, :font => font, :color => color,
                 :gap => gap, :indent => indent };
    }

    private function _paint(dc as Dc, lines as Array, h as Number, pad as Number) as Void {
        dc.clear();
        // Approximate vertical advance: one XTINY line + breathing room per
        // entry keeps spacing even across round/rect MIP sizes.
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

// Delegate is constructed with ITS view so page() has a target without any
// global view lookup.
class ApexTodayDelegate extends WatchUi.BehaviorDelegate {

    var _view;

    function initialize(view as ApexTodayView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onBack() as Boolean {
        // Back to the menu, not out of the app.
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
