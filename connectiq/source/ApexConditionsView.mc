// Apex Day — CONDITIONS view (spec 6.6 #8, P1): today's weather window for
// planning the session (sailing / kite / wind / wake / surf / enduro care
// about this more than any native watch metric).
//
// Comes from the v3 `wx` block {tmin, tmax, wind (km/h), rain (%)}; against
// the v2 backend it says honestly that the data needs Apex server v3.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

class ApexConditionsView extends ApexBaseView {

    function initialize() {
        ApexBaseView.initialize();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        View.onUpdate(dc);
        dc.clear();
        var w = dc.getWidth();
        var h = dc.getHeight();
        var day = ApexStore.loadDay();
        var wx = ApexPayload.dictAt(day, "wx");

        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, (h * 12) / 100, Graphics.FONT_XTINY,
                    WatchUi.loadResource(Rez.Strings.MenuConditions),
                    Graphics.TEXT_JUSTIFY_CENTER);

        if (wx == null) {
            dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 2, h / 2, Graphics.FONT_SMALL,
                        (day == null)
                            ? WatchUi.loadResource(Rez.Strings.NoDataYet)
                            : WatchUi.loadResource(Rez.Strings.CondNone),
                        Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
            return;
        }

        var tmin = ApexPayload.numAt(wx, "tmin");
        var tmax = ApexPayload.numAt(wx, "tmax");
        var wind = ApexPayload.numAt(wx, "wind");
        var rain = ApexPayload.numAt(wx, "rain");

        // temperature range, big
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, (h * 34) / 100, Graphics.FONT_MEDIUM,
                    Lang.format(WatchUi.loadResource(Rez.Strings.CondTemp).toString(),
                                [tmin, tmax]),
                    Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        // wind + rain, one line each
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, (h * 52) / 100, Graphics.FONT_SMALL,
                    Lang.format(WatchUi.loadResource(Rez.Strings.CondWind).toString(), [wind]),
                    Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.drawText(w / 2, (h * 64) / 100, Graphics.FONT_SMALL,
                    Lang.format(WatchUi.loadResource(Rez.Strings.CondRain).toString(), [rain]),
                    Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        // wind flag for the water sports: >= 25 km/h highlighted
        if (wind >= 25) {
            dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 2, (h * 80) / 100, Graphics.FONT_XTINY, "> 25 km/h",
                        Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }
}

class ApexConditionsDelegate extends ApexDelegate {

    function initialize(view as ApexConditionsView) {
        ApexDelegate.initialize(view);
    }
}
