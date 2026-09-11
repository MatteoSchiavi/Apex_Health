// Apex Day — the GLANCE (Phase 10 v2 acceptance surface).
//
// The glance answers ONE question in the two seconds the wrist is up:
//   "what does Apex have for me today?"
//   top zone    — today's gym session (title + time), or "Rest day"
//   bottom zone — the counts: supplements · open alerts · journal streak
//
// Deliberately NOT readiness/recovery/strain: those are native (Training
// Readiness / Recovery Time / Body Battery). Renders straight from
// Application.Storage — the 30-minute background temporal event is what
// talks to the network, so this paints in milliseconds even with the phone
// away. An auth-error flag blanks the numbers instead of faking them.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

class ApexGlanceView extends WatchUi.GlanceView {

    function initialize() {
        GlanceView.initialize();
    }

    function onUpdate(dc as Dc) as Void {
        GlanceView.onUpdate(dc);
        dc.clear();

        var w = dc.getWidth();
        var h = dc.getHeight();
        var pad = w / 20;
        var cached = ApexDayService.cachedDay();

        if (ApexDayService.authError() && cached == null) {
            dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, h / 2, Graphics.FONT_TINY, "Token invalid",
                        Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
            return;
        }

        // ---- top zone: today's first session (or rest day)
        var titleFont = (h >= 100) ? Graphics.FONT_SMALL : Graphics.FONT_TINY;
        var subFont = Graphics.FONT_XTINY;
        var topY = h * 0.12;

        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(pad, topY, subFont, "TODAY", Graphics.TEXT_JUSTIFY_LEFT);

        var sessions = (cached == null) ? null : cached.get("sessions");
        if (sessions == null || sessions.size() == 0) {
            dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, topY + h * 0.22, titleFont, "Rest day",
                        Graphics.TEXT_JUSTIFY_LEFT);
        } else {
            var first = sessions[0];
            var title = ApexFormat.sessionTitle(first);
            var start = ApexFormat.startLabel(first.get("start"));
            var extra = (sessions.size() > 1)
                ? " +" + (sessions.size() - 1) : "";
            dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, topY + h * 0.22, titleFont, title + extra,
                        Graphics.TEXT_JUSTIFY_LEFT);
            if (!start.equals("")) {
                dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
                dc.drawText(w - pad, topY + h * 0.22, titleFont, start,
                            Graphics.TEXT_JUSTIFY_RIGHT);
            }
        }

        // ---- bottom zone: counts that Garmin cannot show
        var supplements = (cached == null) ? null : cached.get("supplements");
        var alerts = (cached == null) ? null : cached.get("alerts");
        var streak = (cached == null) ? null : cached.get("journal_streak");

        var suppCount = (supplements == null) ? 0 : supplements.size();
        var alertCount = 0;
        if (alerts != null && alerts.get("count") != null) {
            alertCount = alerts.get("count").toNumber();
        }
        var streakText = (streak == null) ? "0" : streak.toString();

        var line = "supp " + suppCount + "  alert " + alertCount
                 + "  streak " + streakText + "d";
        dc.setColor((alertCount > 0) ? Graphics.COLOR_YELLOW : Graphics.COLOR_DK_GRAY,
                    Graphics.COLOR_TRANSPARENT);
        dc.drawText(pad, h - h * 0.22, subFont, line, Graphics.TEXT_JUSTIFY_LEFT);
    }
}
