// Apex Day — the GLANCE.
//
// Answers ONE question in the two seconds the wrist is up: "what does Apex
// have for me today?"
//   line 1 — safety verdict word, severity-coloured (GO / MODIFY / REST)
//   line 2 — today's workout name + a status dot (published or not)
//   line 3 — counts: supplements due · open alerts · journal streak
//   footer — data age ("3 h") so stale data is never posed as current
//
// Renders ONLY from Application.Storage — the background temporal event is
// what talks to the network. No request is ever made from the glance (the
// glance process is memory- and battery-budgeted). An auth-error flag blanks
// the payload instead of faking it.
//
// (:glance) — this class is what loads into the 64 KB glance build.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

(:glance)
class ApexGlanceView extends WatchUi.GlanceView {

    function initialize() {
        GlanceView.initialize();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        GlanceView.onUpdate(dc);
        dc.clear();

        var w = dc.getWidth();
        var h = dc.getHeight();
        var pad = w / 16;

        var day = ApexStore.loadDay();
        var meta = ApexStore.loadMeta();

        // ---- auth error (revoked token): say so, never fake data
        if (ApexPayload.boolAt(meta, "authError") && day == null) {
            dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, h / 2, Graphics.FONT_SMALL,
                        WatchUi.loadResource(Rez.Strings.TokenInvalid),
                        Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
            return;
        }

        // ---- line 1: verdict
        var verdict = ApexPayload.verdictOf(day);
        var y = (h * 10) / 100;
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(pad, y, Graphics.FONT_XTINY, "APEX", Graphics.TEXT_JUSTIFY_LEFT);

        if (day == null) {
            dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, (h * 30) / 100, Graphics.FONT_SMALL,
                        WatchUi.loadResource(Rez.Strings.NoDataYet),
                        Graphics.TEXT_JUSTIFY_LEFT);
            return;
        }

        y = (h * 26) / 100;
        if (!verdict.equals("")) {
            dc.setColor(ApexFormat.verdictColor(verdict), Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, y, Graphics.FONT_MEDIUM,
                        ApexFormat.verdictLabel(verdict), Graphics.TEXT_JUSTIFY_LEFT);
        }

        // ---- line 2: workout name + status dot
        y = (h * 48) / 100;
        var title = _workoutTitle(day);
        if (!title.equals("")) {
            dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, y, Graphics.FONT_TINY, title, Graphics.TEXT_JUSTIFY_LEFT);
            // status dot: green = published/on watch, gray = unknown
            var published = _workoutPublished(day);
            dc.setColor(published ? Graphics.COLOR_DK_GREEN : Graphics.COLOR_LT_GRAY,
                        Graphics.COLOR_TRANSPARENT);
            dc.fillCircle(w - pad - 6, y + 8, 5);
        }

        // ---- line 3: counts Garmin cannot show
        y = (h * 70) / 100;
        var suppCount = 0;
        var sup = ApexPayload.supplementList(day);
        if (sup != null) {
            suppCount = sup.size();
        }
        var alertCount = ApexPayload.alertCount(day);
        var streak = ApexPayload.streak(day);
        var lineText = Lang.format(
            WatchUi.loadResource(Rez.Strings.GlanceCounts).toString(),
            [suppCount, alertCount, streak]);
        dc.setColor((alertCount > 0) ? Graphics.COLOR_YELLOW : Graphics.COLOR_DK_GRAY,
                    Graphics.COLOR_TRANSPARENT);
        dc.drawText(pad, y, Graphics.FONT_XTINY, lineText, Graphics.TEXT_JUSTIFY_LEFT);

        // ---- footer: data age
        var age = ApexPayload.minutesSince(ApexPayload.numAt(meta, "lastSync"));
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(w - pad, (h * 88) / 100, Graphics.FONT_XTINY,
                    ApexFormat.ageLabel(age), Graphics.TEXT_JUSTIFY_RIGHT);
    }

    private function _workoutTitle(day as Lang.Dictionary or Null) as Lang.String {
        // v3 published workout wins
        var wo = ApexPayload.workoutBlock(day);
        if (wo != null) {
            var t = ApexPayload.strAt(wo, "t");
            if (!t.equals("")) {
                return t;
            }
        }
        // fallback: concrete gym plan / first session
        var gym = ApexPayload.gymBlock(day);
        if (gym != null) {
            var g = ApexPayload.strAt(gym, "title");
            if (!g.equals("")) {
                return g;
            }
        }
        var sessions = ApexPayload.arrAt(day, "sessions");
        if (sessions != null && sessions.size() > 0) {
            var first = ApexPayload.asDict(sessions[0]);
            if (first != null) {
                return ApexPayload.strAt(first, "title");
            }
        }
        return "";
    }

    private function _workoutPublished(day as Lang.Dictionary or Null) as Lang.Boolean {
        var wo = ApexPayload.workoutBlock(day);
        if (wo == null) {
            return false;
        }
        var st = ApexPayload.strAt(wo, "st");
        return st.equals("scheduled") || st.equals("published") || st.equals("on_watch");
    }
}
