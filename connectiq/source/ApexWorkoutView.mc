// Apex Day — WORKOUT STATUS view (spec 6.6 #2): answers "did today's
// workout reach the watch?".
//
// With the v3 watch contract (`wo` block) this shows the publish state,
// workout name/minutes and the "find it" path. Against the current v2
// backend it says honestly that publish status is not available yet — it
// NEVER invents a state. If a structured workout is published it also
// surfaces "needs re-auth"/"held by safety" states from the server block.

using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

class ApexWorkoutView extends ApexBaseView {

    function initialize() {
        ApexBaseView.initialize();
    }

    function onShow() as Void {
        View.onShow();
        var net = new ApexNet();
        setFetching(true);
        net.fetchDay(method(:_onFetched));
    }

    function onHide() as Void {
        setFetching(false);
        View.onHide();
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
        var day = ApexStore.loadDay();

        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.WoTitle).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));

        if (day == null) {
            lines.add(ApexBaseView.line(fetchingLabel(), Graphics.FONT_SMALL,
                     Graphics.COLOR_LT_GRAY, 6, 0));
            lines.add(footerLine());
            paintLines(dc, lines);
            return;
        }

        var wo = ApexPayload.workoutBlock(day);
        if (wo == null) {
            // v2 backend: no publish status yet — be honest about it
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.WoUnknown).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_YELLOW, 4, 0));
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.WoUnknownHint).toString(),
                Graphics.FONT_TINY, Graphics.COLOR_LT_GRAY, 6, 0));
            // still show what today's plan is, as a fallback
            var gym = ApexPayload.gymBlock(day);
            var title = (gym == null) ? "" : ApexPayload.strAt(gym, "title");
            if (title.equals("")) {
                var sessions = ApexPayload.arrAt(day, "sessions");
                if (sessions != null && sessions.size() > 0) {
                    var first = ApexPayload.asDict(sessions[0]);
                    if (first != null) {
                        title = ApexPayload.strAt(first, "title");
                    }
                }
            }
            if (!title.equals("")) {
                lines.add(ApexBaseView.line(title, Graphics.FONT_TINY,
                         Graphics.COLOR_WHITE, 4, 0));
            }
        } else {
            var title = ApexPayload.strAt(wo, "t");
            var minutes = ApexPayload.numAt(wo, "min");
            var status = ApexPayload.strAt(wo, "st");
            lines.add(ApexBaseView.line(_statusLabel(status),
                     Graphics.FONT_MEDIUM, _statusColor(status), 4, 0));
            if (!title.equals("")) {
                var head = title;
                if (minutes > 0) {
                    head = head + " · " + minutes + " " +
                        WatchUi.loadResource(Rez.Strings.MinShortLabel).toString();
                }
                lines.add(ApexBaseView.line(head, Graphics.FONT_SMALL,
                         Graphics.COLOR_WHITE, 4, 0));
            }
            if (status.equals("scheduled") || status.equals("published") || status.equals("on_watch")) {
                lines.add(ApexBaseView.line(
                    WatchUi.loadResource(Rez.Strings.WoFindIt).toString() + " " +
                    WatchUi.loadResource(Rez.Strings.WoFindHint).toString(),
                    Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));
            }
            var hint = ApexPayload.strAt(wo, "hint");
            if (!hint.equals("")) {
                lines.add(ApexBaseView.line(hint, Graphics.FONT_XTINY,
                         Graphics.COLOR_DK_GRAY, 4, 0));
            }
        }
        lines.add(footerLine());
        paintLines(dc, lines);
    }

    private function _statusLabel(status as Lang.String) as Lang.String {
        if (status.equals("scheduled") || status.equals("published") || status.equals("on_watch")) {
            return WatchUi.loadResource(Rez.Strings.WoPublished).toString();
        }
        if (status.equals("none")) {
            return WatchUi.loadResource(Rez.Strings.WoNotPublished).toString();
        }
        if (status.equals("removed")) {
            return WatchUi.loadResource(Rez.Strings.WoRemoved).toString();
        }
        if (status.equals("held")) {
            return WatchUi.loadResource(Rez.Strings.WoHeld).toString();
        }
        if (status.equals("failed")) {
            return WatchUi.loadResource(Rez.Strings.WoFailed).toString();
        }
        if (status.equals("reauth")) {
            return WatchUi.loadResource(Rez.Strings.WoReauth).toString();
        }
        return WatchUi.loadResource(Rez.Strings.WoUnknown).toString();
    }

    private function _statusColor(status as Lang.String) as Graphics.ColorType {
        if (status.equals("scheduled") || status.equals("published") || status.equals("on_watch")) {
            return Graphics.COLOR_DK_GREEN;
        }
        if (status.equals("held") || status.equals("reauth")) {
            return Graphics.COLOR_YELLOW;
        }
        if (status.equals("failed")) {
            return Graphics.COLOR_RED;
        }
        return Graphics.COLOR_LT_GRAY;
    }

    private function fetchingLabel() as Lang.String {
        return (_fetching)
            ? WatchUi.loadResource(Rez.Strings.Syncing).toString()
            : WatchUi.loadResource(Rez.Strings.NoDataYet).toString();
    }
}

class ApexWorkoutDelegate extends ApexDelegate {

    function initialize(view as ApexWorkoutView) {
        ApexDelegate.initialize(view);
    }

    function onSelect() as Lang.Boolean {
        var view = _view as ApexWorkoutView;
        if (view != null) {
            view.onShow();
        }
        return true;
    }
}
