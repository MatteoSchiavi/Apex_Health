// Apex Day — REST TIMER view (the battery-policy exception).
//
// After LOG SET the athlete gets a visible countdown for the exercise's
// rest_seconds with a vibration at the end and a skip button. This is the
// ONLY repeating timer in the whole app (spec 6.5.7: "a 1 Hz tick only on
// the rest-timer screen while it is visible, stopped on onHide").
//
// Additional guards because the platform has no View-level onEnterSleep
// (that API is watch-face-only):
//   * the timer is stopped in onHide();
//   * the countdown is hard-capped at 10 minutes (600 s) by the caller;
//   * the timer stops itself at zero.
//
// Vibration: Attention.vibrate(Array<VibeProfile>) — foreground only, which
// is exactly where this view runs. Guarded with `Attention has :vibrate`.

using Toybox.Attention;
using Toybox.Graphics;
using Toybox.Lang;
using Toybox.System;
using Toybox.Timer;
using Toybox.WatchUi;

class ApexRestView extends WatchUi.View {

    var _remaining as Lang.Number;
    var _total as Lang.Number;
    var _timer as Timer.Timer or Null;
    var _done as Lang.Boolean;

    function initialize(seconds as Lang.Number) {
        View.initialize();
        _total = seconds;
        _remaining = seconds;
        _timer = null;
        _done = false;
    }

    function onShow() as Void {
        View.onShow();
        _timer = new Timer.Timer();
        _timer.start(method(:_tick), 1000, true);
    }

    function onHide() as Void {
        _stopTimer();
        View.onHide();
    }

    private function _stopTimer() as Void {
        if (_timer != null) {
            _timer.stop();
            _timer = null;
        }
    }

    function _tick() as Void {
        if (_done) {
            return;
        }
        _remaining -= 1;
        if (_remaining <= 0) {
            _done = true;
            _stopTimer();
            _vibrate();
            // auto-return to the exercise view after the final buzz
            WatchUi.popView(WatchUi.SLIDE_IMMEDIATE);
            return;
        }
        WatchUi.requestUpdate();
    }

    private function _vibrate() as Void {
        if (Attention has :vibrate) {
            Attention.vibrate([
                new Attention.VibeProfile(80, 300),
                new Attention.VibeProfile(0, 200),
                new Attention.VibeProfile(80, 300)
            ] as Lang.Array);
        }
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        View.onUpdate(dc);
        dc.clear();
        var w = dc.getWidth();
        var h = dc.getHeight();

        // remaining seconds, big, centered
        dc.setColor((_remaining <= 5) ? Graphics.COLOR_YELLOW : Graphics.COLOR_WHITE,
                    Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, (h * 38) / 100, Graphics.FONT_LARGE,
                    _remaining.toString(),
                    Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        // progress ring hint as a thin bar
        var barW = w * 2 / 3;
        var fill = (_total > 0) ? (barW * _remaining / _total) : 0;
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawRectangle(w / 2 - barW / 2, (h * 62) / 100, barW, 4);
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.fillRectangle(w / 2 - barW / 2, (h * 62) / 100, fill, 4);

        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, (h * 80) / 100, Graphics.FONT_XTINY,
                    WatchUi.loadResource(Rez.Strings.GymRestSkip),
                    Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
    }
}

class ApexRestDelegate extends WatchUi.BehaviorDelegate {

    var _view as ApexRestView or Null;

    function initialize(view as ApexRestView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    //! SELECT skips the rest and returns to the exercise view.
    function onSelect() as Lang.Boolean {
        WatchUi.popView(WatchUi.SLIDE_IMMEDIATE);
        return true;
    }

    function onNextPage() as Lang.Boolean {
        return true; // no paging on the rest screen
    }

    function onPreviousPage() as Lang.Boolean {
        return true;
    }
}
