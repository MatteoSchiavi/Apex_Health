// Apex Day — shared formatting helpers (Phase 10 v2).
//
// Weekday names (the server sends weekday as 0=Mon..6=Sun), severity colors,
// null-safe strings and a word-wrap used by every view. Static-only class —
// no state, so nothing to initialize.

using Toybox.Graphics;
using Toybox.Lang;

class ApexFormat {

    static function weekdayName(dayIndex) as String {
        if (dayIndex == null || dayIndex < 0 || dayIndex > 6) {
            return "";
        }
        var names = [ "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun" ];
        return names[dayIndex];
    }

    static function text(value) as String {
        if (value == null) {
            return "";
        }
        return value.toString();
    }

    // Alerts severity -> color (§17 semantic: red strictly for alerts that
    // need the user to act, yellow = warning, gray = informational).
    static function severityColor(severity) as ColorType {
        if (severity == null) {
            return Graphics.COLOR_GRAY;
        }
        var s = severity.toString();
        if (s.equals("critical") || s.equals("error")) {
            return Graphics.COLOR_RED;
        }
        if (s.equals("warning")) {
            return Graphics.COLOR_YELLOW;
        }
        return Graphics.COLOR_GRAY;
    }

    static function durationLabel(minutes) as String {
        if (minutes == null || minutes <= 0) {
            return "";
        }
        return minutes.toString() + " min";
    }

    // "start" is either null (plan session — date-anchored, no clock time)
    // or "HH:MM" from the recurring schedule.
    static function startLabel(start) as String {
        return (start == null) ? "" : start.toString();
    }

    static function sessionTitle(session as Dictionary) as String {
        var title = session.get("title");
        return (title == null) ? "Session" : title.toString();
    }

    // Word-wrap `text` into lines no wider than maxWidth in `font`.
    // Splits on spaces; a single word longer than the line is emitted as-is
    // (truncation happens at draw time, which is honest enough for notes).
    static function wrap(dc as Dc, text as String, font as FontType, maxWidth as Number) as Array {
        var lines = [];
        if (text == null || text.length() == 0) {
            return lines;
        }
        var words = text.split(" ");
        var current = "";
        for (var i = 0; i < words.size(); i += 1) {
            var candidate = (current.equals("")) ? words[i] : current + " " + words[i];
            if (dc.getTextWidthInPixels(candidate, font) <= maxWidth) {
                current = candidate;
            } else {
                if (!current.equals("")) {
                    lines.add(current);
                }
                current = words[i];
            }
        }
        if (!current.equals("")) {
            lines.add(current);
        }
        return lines;
    }
}
