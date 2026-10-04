// Apex Day — shared UI plumbing: base view (scroll state + painting) and
// base delegate (paging + back navigation) used by every screen.
//
// Round-screen safety: pad derives from dc.getWidth() (never hard-coded
// pixels), so the same code fits fenix7pro today and any future round
// MIP/AMOLED target. Battery: no animations; WatchUi.requestUpdate() only
// after data or input changes.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.System;
using Toybox.WatchUi;

//! Common base for all scrollable Apex views: holds scroll state and the
//! line-model painter. Subclasses build their line list in onUpdate.
class ApexBaseView extends WatchUi.View {

    var _scroll as Lang.Number;
    var _maxScroll as Lang.Number;
    var _fetching as Lang.Boolean;
    var _syncedAt as Lang.String;   // "HH:MM" of the last successful fetch

    function initialize() {
        View.initialize();
        _scroll = 0;
        _maxScroll = 0;
        _fetching = false;
        _syncedAt = "";
    }

    //! Called by ApexDelegate for UP/DOWN paging.
    function page(direction as Lang.Number) as Void {
        var step = dcHeight() * 2 / 3;
        _scroll = _scroll + direction * step;
        if (_scroll < 0) {
            _scroll = 0;
        }
        if (_scroll > _maxScroll) {
            _scroll = _maxScroll;
        }
    }

    //! Freshly fetched -> jump back to the top of the payload.
    function resetScroll() as Void {
        _scroll = 0;
    }

    function setFetching(flag as Lang.Boolean) as Void {
        _fetching = flag;
    }

    function setSyncedAt(label as Lang.String) as Void {
        _syncedAt = label;
    }

    //! One drawable row ({text, font, color, gap, indent}).
    static function line(text as Lang.String, font as Graphics.FontType, color as Graphics.ColorType, gap as Lang.Number, indent as Lang.Number) as Lang.Dictionary {
        return { "text" => text, "font" => font, "color" => color,
                 "gap" => gap, "indent" => indent };
    }

    //! Paint rows from the scroll offset; updates _maxScroll (clamped).
    function paintLines(dc as Graphics.Dc, lines as Lang.Array) as Void {
        dc.clear();
        var h = dc.getHeight();
        var pad = dc.getWidth() / 16;
        var y = pad - _scroll;
        for (var i = 0; i < lines.size(); i += 1) {
            var line = ApexPayload.asDict(lines[i]);
            if (line == null) {
                continue;
            }
            var font = line.get("font") as Graphics.FontType;
            var rowH = dc.getFontHeight(font) + ApexPayload.asNum(line.get("gap"));
            if (y + rowH > 0 && y < h) {
                dc.setColor(line.get("color") as Graphics.ColorType, Graphics.COLOR_TRANSPARENT);
                dc.drawText(pad + ApexPayload.asNum(line.get("indent")), y, font,
                            line.get("text"), Graphics.TEXT_JUSTIFY_LEFT);
            }
            y += rowH;
        }
        _maxScroll = (y > h) ? (y - h) : 0;
        if (_scroll > _maxScroll) {
            _scroll = _maxScroll;
        }
    }

    //! Standard "synced HH:MM" footer stamp after a successful fetch.
    static function clockStamp() as Lang.String {
        var clock = System.getClockTime();
        return clock.hour + ":" + ApexFormat.pad2(clock.min);
    }

    //! Human "Synced $1$ ago" label from the stored meta (or never/syncing).
    function footerLine() as Lang.String {
        var lastSync = ApexStore.metaNum("lastSync");
        var age = ApexPayload.minutesSince(lastSync);
        var label;
        if (_fetching && (age < 0)) {
            label = WatchUi.loadResource(Rez.Strings.Syncing).toString();
        } else {
            label = Lang.format(WatchUi.loadResource(Rez.Strings.SyncedAge).toString(),
                                [ApexFormat.ageLabel(age)]);
        }
        var pending = ApexStore.pendingCount();
        if (pending > 0) {
            label = label + " · " + Lang.format(
                WatchUi.loadResource(Rez.Strings.QueuePending).toString(), [pending]);
        }
        return label;
    }

    //! Screen height via the last drawn dc — unavailable before onLayout, so
    //! paging falls back to a conservative constant until then.
    private function dcHeight() as Lang.Number {
        return 260;
    }
}

//! Base delegate for scrollable Apex views: UP/DOWN (and swipes) page the
//! view, BACK returns to the main menu, SELECT stays abstract.
class ApexDelegate extends WatchUi.BehaviorDelegate {

    var _view as ApexBaseView;

    function initialize(view as ApexBaseView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onNextPage() as Lang.Boolean {
        if (_view != null) {
            _view.page(1);
        }
        WatchUi.requestUpdate();
        return true;
    }

    function onPreviousPage() as Lang.Boolean {
        if (_view != null) {
            _view.page(-1);
        }
        WatchUi.requestUpdate();
        return true;
    }

    function onBack() as Lang.Boolean {
        WatchUi.switchToView(new ApexMainMenu(), new ApexMenuDelegate(),
                             WatchUi.SLIDE_IMMEDIATE);
        return true;
    }
}
