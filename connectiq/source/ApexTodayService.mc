// Apex Health — today service: fetches GET /watch/today from the server and
// caches the result in Application.Storage under $ApexToday.
//
// Auth: the user pastes their Funnel URL and a watch token (minted from
// Settings in the web API) into the app's Connect IQ settings screen; the
// token rides in the Authorization header — the same 22.2-grade secret the
// server only ever stores hashed.
//
// The response is shaped by app/api/watch.py:
//   { "readiness": 82.5, "recovery": 61.0, "strain": 14.2,
//     "as_of_date": "2026-09-11", "stale": false, "data_completeness": "full" }

using Toybox.Application;
using Toybox.Background;
using Toybox.Communications;
using Toybox.Lang;
using Toybox.System;

const STORAGE_KEY = "$ApexToday";

class ApexTodayService {

    var _callback;

    function initialize() {
    }

    // callback(responseCode as Number, data as Dictionary or Null)
    function fetch(callback as Method(_, _, _)) as Void {
        _callback = callback;
        var url = ((Application.Properties.getValue("server_url") as String) + "/watch/today");
        var token = Application.Properties.getValue("api_token") as String;
        var headers = { "Authorization" => "Bearer " + token };
        var options = {
            method => Communications.HTTP_REQUEST_METHOD_GET,
            headers => headers,
            responseTypes => [ Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON ]
        };
        var code = Communications.makeWebRequest(url, null, options, method(:onResponse));
        if (code != Communications.NETWORK_REQUEST_OK) {
            // makeWebRequest refused to even start (no phone, no BLE, bad URL).
            _finish(code, null);
        }
    }

    function onResponse(responseCode as Number, data as Dictionary or Null) as Void {
        _finish(responseCode, data);
    }

    function _finish(responseCode as Number, data as Dictionary or Null) as Void {
        if (responseCode == 200 && data != null) {
            var cached = {
                "readiness"  => _toFloat(data.get("readiness")),
                "recovery"   => _toFloat(data.get("recovery")),
                "strain"     => _toFloat(data.get("strain")),
                "asOfDate"   => data.get("as_of_date"),
                "stale"      => data.get("stale"),
                "completeness" => data.get("data_completeness"),
                "fetchedAt"  => System.getClockTime().hour * 60 + System.getClockTime().min
            };
            Application.Storage.setValue(STORAGE_KEY, cached);
        } else if (responseCode == 401) {
            // Token revoked server-side — drop the cache so the glance shows
            // "sign in" instead of yesterday's numbers pretending to be today's.
            Application.Storage.deleteValue(STORAGE_KEY);
        }
        if (_callback != null) {
            _callback.invoke(responseCode, data);
        }
    }

    function _toFloat(value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Lang.Float) {
            return value;
        }
        return value.toFloat();
    }

    // Read what the glance will render — shared by glance, view and tests.
    static function cached() as Dictionary or Null {
        return Application.Storage.getValue(STORAGE_KEY);
    }

    static function clearCache() as Void {
        Application.Storage.deleteValue(STORAGE_KEY);
    }
}
