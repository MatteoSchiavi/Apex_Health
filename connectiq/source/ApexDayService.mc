// Apex Day — data service (Phase 10 v2, the rethought watch app).
//
// Fetches the Apex-only payload from the server:
//   GET /watch/day   -> gym sessions (recurring schedule, overridden by
//                       date-specific planned sessions), active supplements,
//                       open alerts, journal streak
//   GET /watch/week  -> the 7-day resolved schedule for the week view
//
// Auth: the user pastes their Funnel URL and a watch token (minted from the
// web API) into the app's Connect IQ settings screen; the token rides in the
// Authorization header. On 401 the cached data is DELETED and an auth-error
// flag is set — a revoked token can never pose stale data as current.
//
// Results are parked in Application.Storage under "$" keys (app-managed data),
// which is what the glance and the views render from — the wrist never blocks
// on the radio to paint.

using Toybox.Application;
using Toybox.Communications;
using Toybox.Lang;

const APEX_DAY_KEY = "$ApexDay";
const APEX_WEEK_KEY = "$ApexWeek";
const APEX_AUTH_KEY = "$ApexAuthError";

class ApexDayService {

    var _callback;
    var _isDay;

    function initialize() {
        _callback = null;
        _isDay = true;
    }

    function fetchDay(callback as Method(_, _, _)) as Void {
        _isDay = true;
        _fetch("/watch/day", callback);
    }

    function fetchWeek(callback as Method(_, _, _)) as Void {
        _isDay = false;
        _fetch("/watch/week", callback);
    }

    function _fetch(path as String, callback as Method(_, _, _)) as Void {
        _callback = callback;
        var base = Application.Properties.getValue("server_url") as String;
        var token = Application.Properties.getValue("api_token") as String;
        var url = base + path;
        var headers = { "Authorization" => "Bearer " + token };
        var options = {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :headers => headers,
            :responseTypes => [ Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON ]
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
        var store = Application.Storage;
        if (responseCode == 401) {
            store.deleteValue(APEX_DAY_KEY);
            store.deleteValue(APEX_WEEK_KEY);
            store.setValue(APEX_AUTH_KEY, true);
        } else if (responseCode == 200 && data != null) {
            store.setValue(APEX_AUTH_KEY, false);
            if (_isDay) {
                store.setValue(APEX_DAY_KEY, data);
            } else {
                store.setValue(APEX_WEEK_KEY, data);
            }
        }
        if (_callback != null) {
            _callback.invoke(responseCode, data);
        }
    }

    // ------------------------------------------------------------ cache reads

    static function cachedDay() as Dictionary or Null {
        return Application.Storage.getValue(APEX_DAY_KEY);
    }

    static function cachedWeek() as Dictionary or Null {
        return Application.Storage.getValue(APEX_WEEK_KEY);
    }

    static function authError() as Boolean {
        var flag = Application.Storage.getValue(APEX_AUTH_KEY);
        return flag != null && flag;
    }
}
