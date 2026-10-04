// Apex Day — QUICK MOOD view (spec 6.6 #9, P1): journal in three taps.
//
//   mood 1-5 · energy 1-5 · stress 1-5 -> one "mood" event.
//   MENU cycles fields, UP/DOWN adjusts, SELECT on the save field queues.
//   The event rides the normal queue (no own radio wake-up).

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

class ApexMoodView extends WatchUi.View {

    var _mood as Lang.Number;    // 1..5
    var _energy as Lang.Number;  // 1..5
    var _stress as Lang.Number;  // 1..5
    var _field as Lang.Number;   // 0=mood 1=energy 2=stress 3=save
    var _sent as Lang.Boolean;

    function initialize() {
        View.initialize();
        _mood = 3;
        _energy = 3;
        _stress = 3;
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
                    WatchUi.loadResource(Rez.Strings.MenuMood),
                    Graphics.TEXT_JUSTIFY_LEFT);

        _row(dc, pad, (h * 28) / 100, WatchUi.loadResource(Rez.Strings.MoodMood),
             _bar(_mood), _field == 0);
        _row(dc, pad, (h * 42) / 100, WatchUi.loadResource(Rez.Strings.MoodEnergy),
             _bar(_energy), _field == 1);
        _row(dc, pad, (h * 56) / 100, WatchUi.loadResource(Rez.Strings.MoodStress),
             _bar(_stress), _field == 2);

        dc.setColor((_field == 3) ? Graphics.COLOR_YELLOW : Graphics.COLOR_DK_GRAY,
                    Graphics.COLOR_TRANSPARENT);
        dc.drawText(pad, (h * 74) / 100, Graphics.FONT_SMALL,
                    (_field == 3 ? "> " : "  ") +
                    WatchUi.loadResource(Rez.Strings.MoodSave).toString(),
                    Graphics.TEXT_JUSTIFY_LEFT);

        if (_sent) {
            dc.setColor(Graphics.COLOR_DK_GREEN, Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, (h * 88) / 100, Graphics.FONT_XTINY,
                        WatchUi.loadResource(Rez.Strings.MoodQueued),
                        Graphics.TEXT_JUSTIFY_LEFT);
        }
    }

    //! 1..5 rendered as filled/empty dots (text-free, glyph-safe).
    private function _bar(value as Lang.Number) as Lang.String {
        var out = "";
        for (var i = 1; i <= 5; i += 1) {
            out = out + ((i <= value) ? "•" : "·");
        }
        return out;
    }

    private function _row(dc as Graphics.Dc, x as Lang.Number, y as Lang.Number, label as Lang.Object, value as Lang.String, focused as Lang.Boolean) as Void {
        dc.setColor(focused ? Graphics.COLOR_WHITE : Graphics.COLOR_LT_GRAY,
                    Graphics.COLOR_TRANSPARENT);
        dc.drawText(x, y, Graphics.FONT_SMALL,
                    (focused ? "> " : "  ") + label + " " + value,
                    Graphics.TEXT_JUSTIFY_LEFT);
    }

    function nextField() as Void {
        _field = (_field >= 3) ? 0 : _field + 1;
        WatchUi.requestUpdate();
    }

    function step(direction as Lang.Number) as Void {
        if (_field == 0) {
            _mood = ApexFormat.clamp(_mood + direction, 1, 5);
        } else if (_field == 1) {
            _energy = ApexFormat.clamp(_energy + direction, 1, 5);
        } else if (_field == 2) {
            _stress = ApexFormat.clamp(_stress + direction, 1, 5);
        }
        WatchUi.requestUpdate();
    }

    function confirm() as Void {
        if (_field < 3 || _sent) {
            nextField();
            return;
        }
        var data = { "mood" => _mood, "energy" => _energy, "stress" => _stress };
        var result = ApexStore.addEvent(ApexPayload.makeEvent(ApexPayload.EVENT_MOOD, data));
        if (result.equals("failed")) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.SyncFailed), null);
            return;
        }
        if (result.equals("dropped")) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.QueueFull), null);
        }
        _sent = true;
        WatchUi.requestUpdate();
        WatchUi.showToast(WatchUi.loadResource(Rez.Strings.MoodQueued), null);
    }
}

class ApexMoodDelegate extends WatchUi.BehaviorDelegate {

    var _view as ApexMoodView or Null;

    function initialize(view as ApexMoodView) {
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
