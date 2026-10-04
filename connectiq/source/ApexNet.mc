// Apex Day — network transport (the ONLY code that calls makeWebRequest).
//
// Endpoints (bearer device token; HTTPS only; token never logged):
//   GET  /watch/day         — v2 day payload (gym, supplements, alerts,
//                             streak, gym_plan, safety) — EXISTS today.
//   GET  /watch/v3/day?rev= — compact v3 day payload with revision check
//                             ({"v":3,"rev":n,"same":true} when unchanged) —
//                             DOES NOT EXIST yet; probed once, then the app
//                             falls back to /watch/day until the backend
//                             ships it (re-probe at most every 24 h).
//   POST /watch/events      — batched, idempotent event upload (set logs,
//                             feedback, supplement doses, mood) — probed the
//                             same way; while unsupported the queue stays in
//                             Storage and the UI shows the pending count.
//
// Battery rules implemented here (spec 6.5.4/6.5.5):
//   * revision check first (v3): a "same" reply is ~100 bytes and the
//     common case once the backend supports it;
//   * one request per wake-up in the background (the ONLY exception: a
//     pending event batch rides along with a successful day fetch);
//   * no retries inside the same wake-up — failures count into the
//     background backoff (failStreak in the meta record).
//
// makeWebRequest facts used (verified against the API docs + forums):
//   * options key is :responseType (SINGULAR) + HTTP_RESPONSE_CONTENT_TYPE_JSON;
//   * responseCode is the HTTP status, or 0 / a negative BLE_* error for
//     transport-level failures (0 = UNKNOWN_ERROR);
//   * JSON responses arrive as Lang.Dictionary;
//   * POST bodies: a parameters Dictionary + "Content-Type: application/json"
//     header makes the system serialize the dictionary as JSON.
//
// (:background): shared by the background service and the main app.

using Toybox.Application;
using Toybox.Communications;
using Toybox.Lang;
using Toybox.System;
using Toybox.Time;

(:background)
class ApexNet {

    // v3 capability probe states (stored in meta as "v3State")
    static const V3_PROBE = 0;      // probe on next fetch
    static const V3_YES = 1;        // /watch/v3/day answered
    static const V3_NO = 2;         // fell back to v2

    static const REPROBE_SECONDS = 24 * 60 * 60; // re-probe v3 once per day

    var _callback as Method(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void or Null;
    var _kind as Lang.String;      // "day" | "week" | "events"
    var _isV3 as Lang.Boolean;     // this request went to /watch/v3/day
    var _fallbackDone as Lang.Boolean; // the one-shot v3->v2 fallback for this wake-up

    function initialize() {
        _callback = null;
        _kind = "day";
        _isV3 = false;
        _fallbackDone = false;
    }

    // ------------------------------------------------------------ config

    static function baseUrl() as Lang.String {
        var url = ApexPayload.asStr(Application.Properties.getValue("server_url"));
        while (url.length() > 0 && url.substring(url.length() - 1, url.length()).equals("/")) {
            url = url.substring(0, url.length() - 1);
        }
        return url;
    }

    static function hasToken() as Lang.Boolean {
        var token = ApexPayload.asStr(Application.Properties.getValue("api_token"));
        return token.length() > 0;
    }

    static function refreshIntervalMinutes() as Lang.Number {
        var m = 60;
        var raw = Application.Properties.getValue("refresh_interval");
        if (raw instanceof Lang.Number) {
            m = (raw as Lang.Number).toNumber();
        }
        if (m < 5) {
            m = 5;   // platform minimum for temporal events
        }
        return m;
    }

    //! True when the wall clock is inside the configured active window
    //! (minutes from midnight, user-local). Spec 6.5.3: skip background work
    //! outside 05:00-23:30 by default.
    static function withinActiveHours() as Lang.Boolean {
        var startMin = 300;
        var endMin = 1410;
        var rawStart = Application.Properties.getValue("active_start_min");
        var rawEnd = Application.Properties.getValue("active_end_min");
        if (rawStart instanceof Lang.Number) {
            startMin = rawStart as Lang.Number;
        }
        if (rawEnd instanceof Lang.Number) {
            endMin = rawEnd as Lang.Number;
        }
        var clock = System.getClockTime();
        var nowMin = clock.hour * 60 + clock.min;
        return nowMin >= startMin && nowMin < endMin;
    }

    // ------------------------------------------------------------- fetch

    //! Fetch the day payload. callback(responseCode as Number,
    //! data as Dictionary or String or Null). Exactly ONE request is made in
    //! the common case; the one-time v3 probe may issue a same-wake-up v2
    //! fallback (documented, happens at most once per day).
    function fetchDay(callback as Method(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void) as Void {
        _callback = callback;
        _kind = "day";
        _fallbackDone = false;

        var v3State = ApexStore.metaNum("v3State");
        var lastProbe = ApexStore.metaNum("lastProbe");
        var now = Time.now().value();

        _isV3 = (v3State == V3_YES)
             || (v3State == V3_PROBE)
             || (v3State == V3_NO && (lastProbe == 0 || now - lastProbe > REPROBE_SECONDS));

        var path = _isV3 ? "/watch/v3/day" : "/watch/day";
        var url = baseUrl() + path;
        if (_isV3) {
            url = url + "?rev=" + ApexStore.metaNum("rev");
        }
        _get(url);
    }

    //! Fetch the 7-day schedule (v2; no v3 revision endpoint exists for the
    //! week yet). Same callback contract as fetchDay.
    function fetchWeek(callback as Method(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void) as Void {
        _callback = callback;
        _kind = "week";
        _isV3 = false;
        _fallbackDone = false;
        _get(baseUrl() + "/watch/week");
    }

    private function _get(url as Lang.String) as Void {
        var headers = {} as Lang.Dictionary;
        var token = ApexPayload.asStr(Application.Properties.getValue("api_token"));
        headers.put("Authorization", "Bearer " + token);
        var options = {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :headers => headers,
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        };
        Communications.makeWebRequest(url, null, options, method(:_onResponse));
    }

    //! Upload a batch of queued events. Same callback contract as fetchDay.
    function postEvents(batch as Lang.Array, callback as Method(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void) as Void {
        _callback = callback;
        _kind = "events";
        _isV3 = false;
        var body = { "events" => batch } as Lang.Dictionary;
        var headers = { "Authorization" => "Bearer " + ApexPayload.asStr(Application.Properties.getValue("api_token")),
                        "Content-Type" => "application/json" } as Lang.Dictionary;
        var options = {
            :method => Communications.HTTP_REQUEST_METHOD_POST,
            :headers => headers,
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        };
        Communications.makeWebRequest(baseUrl() + "/watch/events", body, options, method(:_onResponse));
    }

    function _onResponse(responseCode as Lang.Number, data as Lang.Dictionary or Lang.String or Null) as Void {
        // ---- v3 capability bookkeeping
        if (_kind == "day" && _isV3) {
            if (responseCode == 404) {
                // endpoint missing: mark unsupported, remember probe time
                ApexStore.setMetaNum("v3State", V3_NO);
                ApexStore.setMetaNum("lastProbe", Time.now().value());
                if (!_fallbackDone) {
                    // one-shot same-wake-up fallback to the v2 endpoint so
                    // the wake-up is not wasted; this happens at most once
                    // per probe (probe is throttled to daily).
                    _fallbackDone = true;
                    _isV3 = false;
                    _get(baseUrl() + "/watch/day");
                    return;
                }
            } else if (responseCode == 200) {
                ApexStore.setMetaNum("v3State", V3_YES);
                ApexStore.setMetaNum("lastProbe", Time.now().value());
            }
        }
        if (_kind == "events" && responseCode == 404) {
            // events endpoint not shipped yet — keep the queue, back off
            ApexStore.setMetaFlag("evUnsupported", true);
            ApexStore.setMetaNum("evProbe", Time.now().value());
        } else if (_kind == "events" && responseCode == 200) {
            ApexStore.setMetaFlag("evUnsupported", false);
        }
        if (_callback != null) {
            _callback.invoke(responseCode, data);
        }
    }
}
