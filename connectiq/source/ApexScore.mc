// Apex Health — score display helpers shared by the glance and the view:
// null-safe formatting ("--" beats "0" for unscored days) and the semantic
// color bands (§7 composites are 0..100, higher-is-better except strain,
// where extremes are the warning — mirrors the Grafana thresholds).

using Toybox.Graphics;
using Toybox.Lang;

class ApexScore {

    static function toFloat(value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Lang.Float) {
            return value;
        }
        return value.toFloat();
    }

    static function format(value) as String {
        if (value == null) {
            return "--";
        }
        var v = toFloat(value);
        if (v == null) {
            return "--";
        }
        return Lang.format("%.1f", [ v ]);
    }

    static function color(value, goodHigh as Boolean) as ColorType {
        var v = toFloat(value);
        if (v == null) {
            return Graphics.COLOR_GRAY;
        }
        if (goodHigh) {
            // readiness / recovery — higher is better
            return (v >= 70.0) ? Graphics.COLOR_GREEN
                 : (v >= 40.0) ? Graphics.COLOR_YELLOW
                 :               Graphics.COLOR_RED;
        }
        // strain — moderate is fine, extremes warn
        return (v <= 13.0) ? Graphics.COLOR_GREEN
             : (v <= 18.0) ? Graphics.COLOR_YELLOW
             :               Graphics.COLOR_RED;
    }
}
