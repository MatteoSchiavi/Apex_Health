// Apex Day — shared formatting helpers.
//
// Static-only classes: weekday names (localized via Rez), severity/verdict
// colors, null-safe text, word-wrap, unit conversion and data-age labels.
// (:glance): the glance build uses the color + label helpers too.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;
(:background, :glance)
class ApexFormat {

    // -------------------------------------------------------------- text

    static function text(value) as Lang.String {
        if (value == null) {
            return "";
        }
        if (value instanceof Lang.String) {
            return value;
        }
        return value.toString();
    }

    static function pad2(n as Lang.Number) as Lang.String {
        return (n >= 0 && n < 10) ? "0" + n : n.toString();
    }

    //! Weekday short name from the payload's 0=Mon..6=Sun index (localized).
    static function weekdayName(dayIndex as Lang.Number) as Lang.String {
        if (dayIndex < 0 || dayIndex > 6) {
            return "";
        }
        var ids = [Rez.Strings.Wd0, Rez.Strings.Wd1, Rez.Strings.Wd2,
                   Rez.Strings.Wd3, Rez.Strings.Wd4, Rez.Strings.Wd5, Rez.Strings.Wd6];
        return WatchUi.loadResource(ids[dayIndex]).toString();
    }

    //! "$1$ h ago"-style label from minutes (localized units).
    static function ageLabel(minutes as Lang.Number) as Lang.String {
        if (minutes < 0) {
            return WatchUi.loadResource(Rez.Strings.Never).toString();
        }
        var unit;
        var value;
        if (minutes < 60) {
            unit = WatchUi.loadResource(Rez.Strings.MinShort).toString();
            value = minutes;
        } else if (minutes < 60 * 48) {
            unit = WatchUi.loadResource(Rez.Strings.HourShort).toString();
            value = (minutes / 60).toNumber();
        } else {
            unit = WatchUi.loadResource(Rez.Strings.DayShort).toString();
            value = (minutes / (60 * 24)).toNumber();
        }
        return value + " " + unit;
    }

    //! Weight in the user's unit: payload/queues are always kg (SI); only
    //! the DISPLAY converts (imperial property). Returns "80.0 kg"/"176.4 lb".
    static function weightLabel(kg as Lang.Float, imperial as Lang.Boolean) as Lang.String {
        var unit = imperial
            ? WatchUi.loadResource(Rez.Strings.GymLb).toString()
            : WatchUi.loadResource(Rez.Strings.GymKg).toString();
        var shown = imperial ? kg * 2.20462 : kg;
        return shown.format("%.1f") + " " + unit;
    }

    //! kg -> displayed number in the user's unit (for steppers).
    static function weightToDisplay(kg as Lang.Float, imperial as Lang.Boolean) as Lang.Float {
        return imperial ? kg * 2.20462 : kg;
    }

    //! Displayed weight number -> kg for the queued event (SI on the wire).
    static function displayToWeight(displayValue as Lang.Float, imperial as Lang.Boolean) as Lang.Float {
        return imperial ? displayValue / 2.20462 : displayValue;
    }

    static function clamp(n as Lang.Number, lo as Lang.Number, hi as Lang.Number) as Lang.Number {
        if (n < lo) {
            return lo;
        }
        if (n > hi) {
            return hi;
        }
        return n;
    }

    // ------------------------------------------------------------- colors
    // MIP 64-color palette standard constants only.

    //! Alerts severity -> color: red strictly for "act now", yellow warning,
    //! gray informational.
    static function severityColor(severity as Lang.String) as Graphics.ColorType {
        if (severity.equals("critical") || severity.equals("error")) {
            return Graphics.COLOR_RED;
        }
        if (severity.equals("warning")) {
            return Graphics.COLOR_YELLOW;
        }
        return Graphics.COLOR_LT_GRAY;
    }

    //! Safety verdict -> color: green go, orange modify, red rest.
    static function verdictColor(verdict as Lang.String) as Graphics.ColorType {
        if (verdict.equals("rest")) {
            return Graphics.COLOR_RED;
        }
        if (verdict.equals("modify")) {
            return Graphics.COLOR_ORANGE;
        }
        if (verdict.equals("go")) {
            return Graphics.COLOR_DK_GREEN;
        }
        return Graphics.COLOR_LT_GRAY;
    }

    static function verdictLabel(verdict as Lang.String) as Lang.String {
        if (verdict.equals("rest")) {
            return WatchUi.loadResource(Rez.Strings.VerdictRest).toString();
        }
        if (verdict.equals("modify")) {
            return WatchUi.loadResource(Rez.Strings.VerdictModify).toString();
        }
        if (verdict.equals("go")) {
            return WatchUi.loadResource(Rez.Strings.VerdictGo).toString();
        }
        return "—";
    }

    // -------------------------------------------------------------- wrap
    // Word-wrap into lines no wider than maxWidth in font. A single word
    // longer than the line is emitted as-is (honest truncation at draw time
    // via clip). Unit-tested (ApexTests).
    //
    // NOTE: Monkey C has NO String.split() — the tokenizer below is manual
    // (find/substring), which also makes it allocation-lean.
    static function wrap(dc as Graphics.Dc, text as Lang.String, font as Graphics.FontType, maxWidth as Lang.Number) as Lang.Array {
        var lines = [];
        if (text == null || text.length() == 0 || maxWidth <= 0) {
            return lines;
        }
        var words = _words(text);
        var current = "";
        for (var i = 0; i < words.size(); i += 1) {
            var word = words[i] as Lang.String;
            var candidate = (current.equals("")) ? word : current + " " + word;
            if (dc.getTextWidthInPixels(candidate, font) <= maxWidth) {
                current = candidate;
            } else {
                if (!current.equals("")) {
                    lines.add(current);
                }
                current = word;
            }
        }
        if (!current.equals("")) {
            lines.add(current);
        }
        return lines;
    }

    //! Split on single spaces ( Monkey C lacks String.split() ).
    static function _words(text as Lang.String) as Lang.Array {
        var words = [];
        var len = text.length();
        var start = 0;
        for (var i = 0; i < len; i += 1) {
            if (text.substring(i, i + 1).equals(" ")) {
                if (i > start) {
                    words.add(text.substring(start, i));
                }
                start = i + 1;
            }
        }
        if (start < len) {
            words.add(text.substring(start, len));
        }
        return words;
    }
}
