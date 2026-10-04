// Apex Day — BODY & UPKEEP view (spec 6.6 #7, P1): the things Garmin never
// tells you — gear service-due counters (enduro hours!), blood-donation
// eligibility countdown, event countdown + taper window.
//
// These come from the v3 blocks (gear / don / ev). Against the v2 backend
// the view says honestly that the data needs Apex server v3 — no fake
// zeros. The blocks render automatically once the backend ships them.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

class ApexBodyView extends ApexBaseView {

    function initialize() {
        ApexBaseView.initialize();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        View.onUpdate(dc);
        var lines = [];
        var day = ApexStore.loadDay();

        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.MenuBody).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));

        if (day == null) {
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.NoDataYet).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_LT_GRAY, 6, 0));
            paintLines(dc, lines);
            return;
        }

        var any = false;

        // ---- gear: [{n, h, lim}]
        var gear = ApexPayload.arrAt(day, "gear");
        if (gear != null && gear.size() > 0) {
            any = true;
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.GearLabel).toString(),
                Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 4, 0));
            for (var i = 0; i < gear.size() && i < 4; i += 1) {
                var g = ApexPayload.asDict(gear[i]);
                if (g == null) {
                    continue;
                }
                var hours = ApexPayload.numAt(g, "h");
                var lim = ApexPayload.numAt(g, "lim");
                var due = (lim > 0 && hours >= lim * 9 / 10);
                var color = due ? Graphics.COLOR_RED
                          : (lim > 0 && hours >= lim * 3 / 4)
                              ? Graphics.COLOR_YELLOW : Graphics.COLOR_WHITE;
                var label = ApexPayload.strAt(g, "n") + " " + Lang.format(
                    WatchUi.loadResource(Rez.Strings.GearHours).toString(), [hours, lim]);
                if (due) {
                    label = label + " · " +
                        WatchUi.loadResource(Rez.Strings.GearDue).toString();
                }
                lines.add(ApexBaseView.line(label, Graphics.FONT_TINY, color, 4, 8));
            }
        }

        // ---- donation: {days}
        var don = ApexPayload.dictAt(day, "don");
        if (don != null) {
            any = true;
            var days = ApexPayload.numAt(don, "days");
            var donLabel = (days <= 0)
                ? WatchUi.loadResource(Rez.Strings.DonReady).toString()
                : Lang.format(WatchUi.loadResource(Rez.Strings.DonDays).toString(), [days]);
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.DonLabel).toString() + ": " + donLabel,
                Graphics.FONT_TINY, (days <= 0) ? Graphics.COLOR_DK_GREEN : Graphics.COLOR_WHITE,
                6, 0));
        }

        // ---- event: {t, days, taper}
        var ev = ApexPayload.dictAt(day, "ev");
        if (ev != null && !ApexPayload.strAt(ev, "t").equals("")) {
            any = true;
            var evName = ApexPayload.strAt(ev, "t");
            var evDays = ApexPayload.numAt(ev, "days");
            var taper = ApexPayload.numAt(ev, "taper");
            lines.add(ApexBaseView.line(Lang.format(
                WatchUi.loadResource(Rez.Strings.EventIn).toString(), [evDays, evName]),
                Graphics.FONT_TINY, Graphics.COLOR_WHITE, 4, 0));
            if (taper > 0 && evDays <= taper) {
                lines.add(ApexBaseView.line(Lang.format(
                    WatchUi.loadResource(Rez.Strings.TaperLabel).toString(), [taper]),
                    Graphics.FONT_XTINY, Graphics.COLOR_YELLOW, 4, 8));
            }
        }

        if (!any) {
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.BodyNone).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_LT_GRAY, 6, 0));
        }
        lines.add(footerLine());
        paintLines(dc, lines);
    }
}

class ApexBodyDelegate extends ApexDelegate {

    function initialize(view as ApexBodyView) {
        ApexDelegate.initialize(view);
    }
}
