// Apex Day — SUPPLEMENTS view (spec 6.6 #5, P1): one-tap adherence.
//
// Lists today's active protocols with a checkbox; SELECT marks a dose as
// taken (queues a timestamped "supplement" event; local mark kept for the
// day so the checkbox survives re-paints). Marks reset when the server date
// changes (new day = new doses).

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

class ApexSupplementsView extends ApexBaseView {

    var _cursor as Lang.Number;
    var _rows as Lang.Array or Null; // resolved [{name, dose, done}]

    function initialize() {
        ApexBaseView.initialize();
        _cursor = 0;
        _rows = null;
    }

    function onShow() as Void {
        View.onShow();
        refresh();
    }

    function onHide() as Void {
        setFetching(false);
        View.onHide();
    }

    function refresh() as Void {
        setFetching(true);
        var net = new ApexNet();
        net.fetchDay(method(:_onFetched));
    }

    function _onFetched(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void {
        setFetching(false);
        if (responseCode == 200) {
            setSyncedAt(ApexBaseView.clockStamp());
        } else if (responseCode == 401 || responseCode == 403) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.TokenInvalidHint), null);
        }
        WatchUi.requestUpdate();
    }

    //! Resolve the visible rows from the payload + local marks.
    private function _resolve() as Lang.Array {
        var rows = [];
        var day = ApexStore.loadDay();
        var sup = ApexPayload.supplementList(day);
        if (sup != null) {
            for (var i = 0; i < sup.size(); i += 1) {
                var s = ApexPayload.asDict(sup[i]);
                if (s == null) {
                    continue;
                }
                var name = ApexPayload.supplementName(s);
                var done = ApexPayload.supplementDone(s)
                        || ApexStore.supplementTakenAt(name) > 0;
                rows.add({ "name" => name, "dose" => ApexPayload.supplementDose(s),
                           "done" => done });
            }
        }
        return rows;
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        View.onUpdate(dc);
        var lines = [];
        var day = ApexStore.loadDay();

        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.MenuSupplements).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));

        if (day == null) {
            lines.add(ApexBaseView.line(
                (_fetching) ? WatchUi.loadResource(Rez.Strings.Syncing).toString()
                            : WatchUi.loadResource(Rez.Strings.NoDataYet).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_LT_GRAY, 6, 0));
            paintLines(dc, lines);
            return;
        }

        _rows = _resolve();
        if (_rows.size() == 0) {
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.SupNone).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_WHITE, 6, 0));
            lines.add(footerLine());
            paintLines(dc, lines);
            return;
        }
        if (_cursor >= _rows.size()) {
            _cursor = _rows.size() - 1;
        }
        for (var i = 0; i < _rows.size(); i += 1) {
            var row = ApexPayload.asDict(_rows[i]);
            if (row == null) {
                continue;
            }
            var mark = ApexPayload.boolAt(row, "done") ? "[x] " : "[ ] ";
            var name = ApexPayload.strAt(row, "name");
            var dose = ApexPayload.strAt(row, "dose");
            var text = mark + name + ((dose.equals("")) ? "" : " — " + dose);
            lines.add(ApexBaseView.line(text, Graphics.FONT_TINY,
                     (i == _cursor) ? Graphics.COLOR_YELLOW
                                    : (ApexPayload.boolAt(row, "done")
                                        ? Graphics.COLOR_DK_GREEN : Graphics.COLOR_WHITE),
                     4, 0));
        }
        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.SupMarkHint).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));
        lines.add(footerLine());
        paintLines(dc, lines);
    }

    //! SELECT: toggle the cursor row's taken mark + queue the event.
    function markTaken() as Void {
        if (_rows == null || _cursor < 0 || _cursor >= _rows.size()) {
            return;
        }
        var row = ApexPayload.asDict(_rows[_cursor]);
        if (row == null) {
            return;
        }
        var name = ApexPayload.strAt(row, "name");
        if (ApexPayload.boolAt(row, "done")) {
            return; // already taken today
        }
        var day = ApexStore.loadDay();
        ApexStore.markSupplementTaken(ApexPayload.dateOf(day), name);
        var data = { "supplement" => name, "dose" => ApexPayload.strAt(row, "dose") };
        var result = ApexStore.addEvent(ApexPayload.makeEvent(ApexPayload.EVENT_SUPPLEMENT, data));
        if (result.equals("failed")) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.SyncFailed), null);
            return;
        }
        if (result.equals("dropped")) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.QueueFull), null);
        }
        WatchUi.requestUpdate();
    }

    function moveCursor(direction as Lang.Number) as Void {
        _cursor += direction;
        if (_cursor < 0) {
            _cursor = 0;
        }
        WatchUi.requestUpdate();
    }
}

class ApexSupplementsDelegate extends ApexDelegate {

    function initialize(view as ApexSupplementsView) {
        ApexDelegate.initialize(view);
    }

    function onNextPage() as Lang.Boolean {
        var view = _view as ApexSupplementsView;
        if (view != null) {
            view.moveCursor(1);
        }
        WatchUi.requestUpdate();
        return true;
    }

    function onPreviousPage() as Lang.Boolean {
        var view = _view as ApexSupplementsView;
        if (view != null) {
            view.moveCursor(-1);
        }
        WatchUi.requestUpdate();
        return true;
    }

    function onSelect() as Lang.Boolean {
        var view = _view as ApexSupplementsView;
        if (view != null) {
            view.markTaken();
        }
        return true;
    }
}
