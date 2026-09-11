// Apex Health — the GLANCE (MASTER_SPEC §23 Phase 10 acceptance criterion).
//
// "glance shows today's readiness / recovery / strain".
//
// Renders straight from Application.Storage — the 30-minute background
// temporal event is what talks to the network, so the glance paints in
// milliseconds and works with the last sync even when the phone is away.
// A "$" prefix in the Storage key marks it as app-managed data.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.System;
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
        var cached = ApexTodayService.cached();

        var rows = 3;
        var rowH = h / rows;
        var pad = w / 24;
        var labelFont = Graphics.FONT_XTINY;
        var valueFont = (rowH >= 30) ? Graphics.FONT_SMALL : Graphics.FONT_TINY;

        var readiness  = (cached == null) ? null : cached.get("readiness");
        var recovery   = (cached == null) ? null : cached.get("recovery");
        var strain     = (cached == null) ? null : cached.get("strain");
        var asOf       = (cached == null) ? null : cached.get("asOfDate");

        // Column layout: labels left, values right-aligned — glance-safe on
        // every supported rectangle (28px and up).
        var items = [
            { "label" => "READY",    "value" => readiness, "goodHigh" => true  },
            { "label" => "RECOVERY", "value" => recovery,  "goodHigh" => true  },
            { "label" => "STRAIN",   "value" => strain,    "goodHigh" => false }
        ];

        for (var i = 0; i < items.size(); i += 1) {
            var top = i * rowH;
            var item = items[i];
            var value = item.get("value");

            dc.setColor(Graphics.COLOR_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(pad, top + rowH / 2, labelFont, item.get("label"),
                        Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);

            dc.setColor(ApexScore.color(value, item.get("goodHigh")), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w - pad, top + rowH / 2, valueFont, ApexScore.format(value),
                        Graphics.TEXT_JUSTIFY_RIGHT | Graphics.TEXT_JUSTIFY_VCENTER);
        }

        // One-pixel separator above the as-of footer keeps "is this today?"
        // answerable at a glance (the server's `stale` flag decides content,
        // the date itself decides honesty).
        if (asOf != null) {
            dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(w - pad, h, Graphics.FONT_XTINY, asOf, Graphics.TEXT_JUSTIFY_RIGHT);
        }
    }
}
