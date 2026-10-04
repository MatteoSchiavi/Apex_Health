// Apex Day — ALERTS view (spec 6.6 #6): the newest Apex alerts,
// severity-coloured. Acknowledging stays in web/Telegram — the watch is a
// read-only window on purpose (no accidental acks on the wrist).

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

class ApexAlertsView extends ApexBaseView {

    function initialize() {
        ApexBaseView.initialize();
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

    function onUpdate(dc as Graphics.Dc) as Void {
        View.onUpdate(dc);
        var lines = [];
        var w = dc.getWidth();
        var day = ApexStore.loadDay();

        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.MenuAlerts).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));

        if (day == null) {
            lines.add(ApexBaseView.line(
                (_fetching) ? WatchUi.loadResource(Rez.Strings.Syncing).toString()
                            : WatchUi.loadResource(Rez.Strings.NoDataYet).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_LT_GRAY, 6, 0));
            paintLines(dc, lines);
            return;
        }

        var count = ApexPayload.alertCount(day);
        if (count == 0) {
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.AlertsNone).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_WHITE, 6, 0));
            lines.add(footerLine());
            paintLines(dc, lines);
            return;
        }

        lines.add(ApexBaseView.line(Lang.format(
            WatchUi.loadResource(Rez.Strings.AlertsOpen).toString(), [count]),
            Graphics.FONT_SMALL, Graphics.COLOR_YELLOW, 6, 0));

        var items = ApexPayload.alertItems(day);
        if (items != null) {
            for (var i = 0; i < items.size() && i < 3; i += 1) { // newest 3 only
                var alert = ApexPayload.asDict(items[i]);
                if (alert == null) {
                    continue;
                }
                var msg = ApexPayload.alertMessage(alert);
                var color = ApexFormat.severityColor(ApexPayload.alertSeverity(alert));
                var wrapped = ApexFormat.wrap(dc, msg, Graphics.FONT_TINY,
                                              w - (w / 16) * 2 - 8);
                for (var j = 0; j < wrapped.size(); j += 1) {
                    lines.add(ApexBaseView.line(wrapped[j] as Lang.String, Graphics.FONT_TINY,
                             color, 4, 8));
                }
            }
        }
        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.AlertsAck).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 8, 0));
        lines.add(footerLine());
        paintLines(dc, lines);
    }
}

class ApexAlertsDelegate extends ApexDelegate {

    function initialize(view as ApexAlertsView) {
        ApexDelegate.initialize(view);
    }

    function onSelect() as Lang.Boolean {
        var view = _view as ApexAlertsView;
        if (view != null) {
            view.refresh();
        }
        return true;
    }
}
