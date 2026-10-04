// Apex Day — POST-SESSION FEEDBACK view (spec 6.6 #4, P0): the 5-second
// check-in that feeds the coach's next plan.
//
//   RPE 1-10, soreness 1-5, pain/injury toggle, one confirm.
//   MENU moves to the next field; UP/DOWN adjust; SELECT on the confirm
//   field queues the event.
//
// Exception to the "no radio on its own" rule (spec 6.5.6): post-workout
// feedback may flush ONCE immediately when the phone is connected — a
// failed flush simply stays queued for the next fetch.

using Toybox.Application;
using Toybox.Graphics;
using Toybox.Lang;
using Toybox.System;
using Toybox.WatchUi;

class ApexFeedbackView extends WatchUi.View {

    var _rpe as Lang.Number;       // 1..10
    var _soreness as Lang.Number;  // 1..5
    var _injury as Lang.Boolean;
    var _field as Lang.Number;     // 0=rpe 1=soreness 2=injury 3=confirm
    var _sent as Lang.Boolean;

    function initialize() {
        View.initialize();
        _rpe = 6;
        _soreness = 2;
        _injury = false;
        _field = 0;
        _sent = false;
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        View.onUpdate(dc);
        dc.clear();
        var w = dc.getWidth();
        var h = dc.getHeight();
        var pad = w / 16;

        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(pad, (h * 10) / 100, Graphics.FONT_XTINY,
                    WatchUi.loadResource(Rez.Strings.MenuFeedback),
                    Graphics.TEXT_JUSTIFY_LEFT);

        _row(dc, pad, (h * 26) / 100, WatchUi.loadResource(Rez.Strings.FbRpe),
             _rpe.toString(), _field == 0);
        _row(dc, pad, (h * 40) / 100, WatchUi.loadResource(Rez.Strings.FbSoreness),
             _soreness.toString(), _field == 1);
        _row(dc, pad, (h * 54) / 100, WatchUi.loadResource(Rez.Strings.FbInjury),
             WatchUi.loadResource(_injury ? Rez.Strings.FbYes : Rez.Strings.FbNo).toString(),
             _field == 2);

        // confirm row
        var confirmColor = (_field == 3) ? Graphics.COLOR_YELLOW : Graphics.COLOR_DK_GRAY;
        dc.setColor(confirmColor, Graphics.COLOR_TRANSPARENT);
        dc.drawText(pad, (h * 72) / 100, Graphics.FONT_SMALL,
                    (_field == 3 ? "> " : "  ") +
                    WatchUi.loadResource(Rez.Strings.FbConfirm).toString(),
                    Graphics.TEXT_JUSTIFY_LEFT);

        if (_sent) {
            dc.setColor(Graphics.COLOR_DK_GREEN, Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, (h * 86) / 100, Graphics.FONT_XTINY,
                        WatchUi.loadResource(Rez.Strings.FbQueued),
                        Graphics.TEXT_JUSTIFY_LEFT);
        }
    }

    private function _row(dc as Graphics.Dc, x as Lang.Number, y as Lang.Number, label as Lang.Object, value as Lang.String, focused as Lang.Boolean) as Void {
        dc.setColor(focused ? Graphics.COLOR_WHITE : Graphics.COLOR_LT_GRAY,
                    Graphics.COLOR_TRANSPARENT);
        dc.drawText(x, y, Graphics.FONT_SMALL,
                    (focused ? "> " : "  ") + label + ": " + value,
                    Graphics.TEXT_JUSTIFY_LEFT);
    }

    //! MENU: next field.
    function nextField() as Void {
        _field = (_field >= 3) ? 0 : _field + 1;
        WatchUi.requestUpdate();
    }

    //! UP/DOWN: adjust the focused field.
    function step(direction as Lang.Number) as Void {
        if (_field == 0) {
            _rpe = ApexFormat.clamp(_rpe + direction, 1, 10);
        } else if (_field == 1) {
            _soreness = ApexFormat.clamp(_soreness + direction, 1, 5);
        } else if (_field == 2) {
            if (direction != 0) {
                _injury = !_injury;
            }
        }
        WatchUi.requestUpdate();
    }

    //! SELECT: on the confirm field queue the feedback event; otherwise
    //! advance one field (button-first ergonomics).
    function confirm() as Void {
        if (_field < 3 || _sent) {
            nextField();
            return;
        }
        var data = {
            "rpe" => _rpe,
            "soreness" => _soreness,
            "injury" => _injury,
            "source" => "watch"
        };
        var event = ApexPayload.makeEvent(ApexPayload.EVENT_FEEDBACK, data);
        var result = ApexStore.addEvent(event);
        if (result.equals("failed")) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.SyncFailed), null);
            return;
        }
        if (result.equals("dropped")) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.QueueFull), null);
        }
        _sent = true;
        WatchUi.requestUpdate();
        WatchUi.showToast(WatchUi.loadResource(Rez.Strings.FbQueued), null);

        // spec exception: post-workout feedback may flush immediately ONCE
        if (System.getDeviceSettings().phoneConnected) {
            var batch = ApexStore.takeEventBatch();
            if (batch.size() > 0) {
                var net = new ApexNet();
                net.postEvents(batch, method(:_onFlushed));
            }
        }
    }

    function _onFlushed(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void {
        if (responseCode == 200) {
            var batch = ApexStore.takeEventBatch();
            var ids = [];
            for (var i = 0; i < batch.size(); i += 1) {
                var ev = ApexPayload.asDict(batch[i]);
                if (ev != null) {
                    ids.add(ApexPayload.asStr(ev.get("id")));
                }
            }
            ApexStore.removeEventsByIds(ids);
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.QueueSent), null);
        }
        // anything else: stay queued for the next fetch — never retry here
    }
}

class ApexFeedbackDelegate extends WatchUi.BehaviorDelegate {

    var _view as ApexFeedbackView or Null;

    function initialize(view as ApexFeedbackView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onNextPage() as Lang.Boolean {
        if (_view != null) {
            _view.step(1);
        }
        return true;
    }

    function onPreviousPage() as Lang.Boolean {
        if (_view != null) {
            _view.step(-1);
        }
        return true;
    }

    function onSelect() as Lang.Boolean {
        if (_view != null) {
            _view.confirm();
        }
        return true;
    }

    function onMenu() as Lang.Boolean {
        if (_view != null) {
            _view.nextField();
        }
        return true;
    }

    function onBack() as Lang.Boolean {
        WatchUi.switchToView(new ApexMainMenu(), new ApexMenuDelegate(),
                             WatchUi.SLIDE_IMMEDIATE);
        return true;
    }
}
