// Apex Day — GYM views (spec 6.6 #3, P0): log sets without the phone.
//
//   ApexGymView          — today's plan: progress + exercise list;
//                          SELECT opens the Menu2 picker of exercises
//   ApexGymExerciseView  — current exercise, target "4 × 6–8", set dots,
//                          reps/weight steppers, LOG SET, rest-timer launch,
//                          next-exercise preview
//
// Defaults: reps = the plan's target (reps_max or reps_min), weight falls
// back to the last value used in THIS launch session (in-memory) — the v2
// payload carries no per-exercise history.
//
// Logging a set queues an idempotent client event (type "set_log", carrying
// gym_day_exercise_id, set number, reps, kg) in Application.Storage; the
// queue flushes with the next fetch — never on its own radio wake-up.
// Local progress (sets_done) is incremented immediately so the UI stays
// truthful while offline; the next server sync reconciles.

using Toybox.Application;
using Toybox.Graphics;
using Toybox.Lang;
using Toybox.WatchUi;

// ---------------------------------------------------------------------------
// Shared per-launch session state for the gym flow (last weights, local
// progress) — one place, no scattered globals.

class ApexGymExercises {

    static var _exercises as Lang.Array or Null;
    static var _lastWeights as Lang.Dictionary or Null;

    static function reset() as Void {
        _exercises = null;
        _lastWeights = {};
    }

    //! Snapshot the exercise list from the cached day (call once per view
    //! entry; the cached payload stays authoritative).
    static function current() as Lang.Dictionary or Null {
        if (_exercises == null) {
            var day = ApexStore.loadDay();
            var gym = ApexPayload.gymBlock(day);
            if (gym == null) {
                return null;
            }
            _exercises = ApexPayload.arrAt(gym, "exercises");
        }
        var day2 = ApexStore.loadDay();
        return ApexPayload.gymBlock(day2);
    }

    static function exerciseAt(index as Lang.Number) as Lang.Dictionary or Null {
        if (_exercises == null) {
            current();
        }
        if (_exercises == null || index < 0 || index >= _exercises.size()) {
            return null;
        }
        return ApexPayload.asDict(_exercises[index]);
    }

    static function lastWeight(index as Lang.Number) as Lang.Float {
        if (_lastWeights == null) {
            _lastWeights = {};
        }
        var value = _lastWeights.get(index.toString());
        if (value == null || !(value instanceof Lang.Float)) {
            return 0.0;
        }
        return value as Lang.Float;
    }

    static function setLastWeight(index as Lang.Number, kg as Lang.Float) as Void {
        _lastWeights.put(index.toString(), kg);
    }

    //! Local, optimistic sets_done bump; also reflected into the cached day
    //! so the list view stays truthful.
    static function bumpSetsDone(index as Lang.Number) as Void {
        var ex = exerciseAt(index);
        if (ex == null) {
            return;
        }
        ex.put("sets_done", ApexPayload.numAt(ex, "sets_done") + 1);
        ex.put("complete", ApexPayload.numAt(ex, "sets_done") >= ApexPayload.numAt(ex, "sets"));
        var day = ApexStore.loadDay();
        var gym = ApexPayload.gymBlock(day);
        if (gym != null) {
            var progress = ApexPayload.dictAt(gym, "progress");
            if (progress != null) {
                progress.put("sets_done", ApexPayload.numAt(progress, "sets_done") + 1);
            }
            gym.put("exercises", _exercises);
            day.put("gym_plan", gym);
            ApexStore.saveDay(day);
        }
    }

    static function nextExerciseName(fromIndex as Lang.Number) as Lang.String {
        var i = fromIndex + 1;
        for (var guard = 0; guard < 50; guard += 1) {
            var ex = exerciseAt(i);
            if (ex == null) {
                return "";
            }
            if (!ApexPayload.boolAt(ex, "complete")) {
                return ApexPayload.strAt(ex, "name");
            }
            i += 1;
        }
        return "";
    }
}

// ---------------------------------------------------------------------------
// Exercise list

class ApexGymView extends ApexBaseView {

    function initialize() {
        ApexBaseView.initialize();
        ApexGymExercises.reset();
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
        var day = ApexStore.loadDay();
        var gym = ApexPayload.gymBlock(day);

        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.MenuGym).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));

        if (day == null) {
            lines.add(ApexBaseView.line(
                (_fetching) ? WatchUi.loadResource(Rez.Strings.Syncing).toString()
                            : WatchUi.loadResource(Rez.Strings.NoDataYet).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_LT_GRAY, 6, 0));
            paintLines(dc, lines);
            return;
        }

        if (gym == null) {
            var sessions = ApexPayload.arrAt(day, "sessions");
            if (sessions != null && sessions.size() > 0) {
                lines.add(ApexBaseView.line(
                    WatchUi.loadResource(Rez.Strings.WoNone).toString(),
                    Graphics.FONT_SMALL, Graphics.COLOR_WHITE, 6, 0));
                var first = ApexPayload.asDict(sessions[0]);
                if (first != null) {
                    lines.add(ApexBaseView.line(ApexPayload.strAt(first, "title"),
                             Graphics.FONT_TINY, Graphics.COLOR_YELLOW, 4, 0));
                }
            } else {
                lines.add(ApexBaseView.line(
                    WatchUi.loadResource(Rez.Strings.GymNoPlan).toString(),
                    Graphics.FONT_SMALL, Graphics.COLOR_WHITE, 6, 0));
            }
            lines.add(footerLine());
            paintLines(dc, lines);
            return;
        }

        // progress header
        var progress = ApexPayload.dictAt(gym, "progress");
        var done = (progress == null) ? 0 : ApexPayload.numAt(progress, "sets_done");
        var total = (progress == null) ? 0 : ApexPayload.numAt(progress, "sets_total");
        lines.add(ApexBaseView.line(
            Lang.format(WatchUi.loadResource(Rez.Strings.GymProgress).toString(), [done, total]),
            Graphics.FONT_SMALL, (total > 0 && done >= total)
                ? Graphics.COLOR_DK_GREEN : Graphics.COLOR_YELLOW, 6, 0));

        var exercises = ApexPayload.arrAt(gym, "exercises");
        if (exercises != null) {
            for (var i = 0; i < exercises.size(); i += 1) {
                var ex = ApexPayload.asDict(exercises[i]);
                if (ex == null) {
                    continue;
                }
                var complete = ApexPayload.boolAt(ex, "complete");
                var row = (i + 1) + ". " + ApexPayload.strAt(ex, "name")
                        + "  " + ApexPayload.numAt(ex, "sets_done")
                        + "/" + ApexPayload.numAt(ex, "sets");
                lines.add(ApexBaseView.line(row, Graphics.FONT_TINY,
                         complete ? Graphics.COLOR_DK_GREEN : Graphics.COLOR_WHITE,
                         4, 0));
            }
        }
        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.GymFieldMenu).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 6, 0));
        paintLines(dc, lines);
    }
}

class ApexGymDelegate extends ApexDelegate {

    function initialize(view as ApexGymView) {
        ApexDelegate.initialize(view);
    }

    //! SELECT opens the Menu2 exercise picker; identifiers are indexes.
    function onSelect() as Lang.Boolean {
        var gym = ApexGymExercises.current();
        var exercises = _exercisesList();
        if (gym == null || exercises == null || exercises.size() == 0) {
            return true;
        }
        var menu = new WatchUi.Menu2({:title => ApexPayload.strAt(gym, "title")});
        for (var i = 0; i < exercises.size(); i += 1) {
            var ex = ApexPayload.asDict(exercises[i]);
            if (ex == null) {
                continue;
            }
            var repsLabel = (ApexPayload.numAt(ex, "reps_max") > ApexPayload.numAt(ex, "reps_min"))
                ? (ApexPayload.numAt(ex, "reps_min") + "-" + ApexPayload.numAt(ex, "reps_max"))
                : ApexPayload.numAt(ex, "reps_min").toString();
            var sub = Lang.format(WatchUi.loadResource(Rez.Strings.GymTarget).toString(),
                                  [ApexPayload.numAt(ex, "sets"), repsLabel]);
            menu.addItem(new WatchUi.MenuItem(ApexPayload.strAt(ex, "name"), sub,
                                              i as Lang.Number, null));
        }
        WatchUi.pushView(menu, new ApexGymPickDelegate(), WatchUi.SLIDE_IMMEDIATE);
        return true;
    }

    private function _exercisesList() as Lang.Array or Null {
        // exercises were snapshotted by ApexGymExercises.current() above
        var day = ApexStore.loadDay();
        var gym = ApexPayload.gymBlock(day);
        return (gym == null) ? null : ApexPayload.arrAt(gym, "exercises");
    }
}

//! Menu2 pick delegate — identifiers are the exercise indexes.
class ApexGymPickDelegate extends WatchUi.Menu2InputDelegate {

    function initialize() {
        Menu2InputDelegate.initialize();
    }

    function onSelect(item as WatchUi.MenuItem) as Void {
        var index = item.getId();
        if (!(index instanceof Lang.Number)) {
            return;
        }
        var i = index as Lang.Number;
        if (ApexGymExercises.exerciseAt(i) == null) {
            return;
        }
        var exerciseView = new ApexGymExerciseView(i);
        WatchUi.pushView(exerciseView, new ApexGymExerciseDelegate(exerciseView),
                         WatchUi.SLIDE_IMMEDIATE);
    }
}

// ---------------------------------------------------------------------------
// Exercise tracker

class ApexGymExerciseView extends ApexBaseView {

    var _index as Lang.Number;
    var _focusReps as Lang.Boolean;   // false = weight focused
    var _reps as Lang.Number;
    var _weightKg as Lang.Float;
    var _flash as Lang.String;        // transient feedback line

    function initialize(index as Lang.Number) {
        ApexBaseView.initialize();
        _index = index;
        _focusReps = true;
        _flash = "";
        var ex = ApexGymExercises.exerciseAt(index);
        _reps = (ex == null) ? 8 : _defaultReps(ex);
        _weightKg = ApexGymExercises.lastWeight(index);
    }

    private function _defaultReps(ex as Lang.Dictionary) as Lang.Number {
        var rmax = ApexPayload.numAt(ex, "reps_max");
        var rmin = ApexPayload.numAt(ex, "reps_min");
        return (rmax > rmin) ? rmax : rmin;
    }

    function onHide() as Void {
        setFetching(false);
        View.onHide();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        View.onUpdate(dc);
        var ex = ApexGymExercises.exerciseAt(_index);
        var w = dc.getWidth();
        var lines = [];

        if (ex == null) {
            lines.add(ApexBaseView.line(
                WatchUi.loadResource(Rez.Strings.GymNoPlan).toString(),
                Graphics.FONT_SMALL, Graphics.COLOR_LT_GRAY, 6, 0));
            paintLines(dc, lines);
            return;
        }

        var name = ApexPayload.strAt(ex, "name");
        var sets = ApexPayload.numAt(ex, "sets");
        var setsDone = ApexPayload.numAt(ex, "sets_done");
        var rmin = ApexPayload.numAt(ex, "reps_min");
        var rmax = ApexPayload.numAt(ex, "reps_max");

        // exercise header + position
        var gym = ApexGymExercises.current();
        var count = 0;
        if (gym != null) {
            var all = ApexPayload.arrAt(gym, "exercises");
            count = (all == null) ? 0 : all.size();
        }
        lines.add(ApexBaseView.line(name, Graphics.FONT_SMALL,
                 Graphics.COLOR_YELLOW, 2, 0));
        lines.add(ApexBaseView.line(Lang.format(
            WatchUi.loadResource(Rez.Strings.GymExerciseOf).toString(),
            [_index + 1, count]), Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 4, 0));

        // target "4 × 6-8"
        var repsTarget = (rmax > rmin) ? (rmin + "-" + rmax) : rmin.toString();
        lines.add(ApexBaseView.line(Lang.format(
            WatchUi.loadResource(Rez.Strings.GymTarget).toString(),
            [sets, repsTarget]), Graphics.FONT_TINY, Graphics.COLOR_WHITE, 4, 0));

        // set dots: filled = done, outline = pending
        _paintSetDots(dc, w, sets, setsDone, 52);

        // steppers: reps (focused default) and weight
        var imperial = ApexPayload.asBool(Application.Properties.getValue("imperial"));
        var repsPrefix = _focusReps ? "> " : "  ";
        var weightPrefix = _focusReps ? "  " : "> ";
        lines.add(ApexBaseView.line(repsPrefix +
                 WatchUi.loadResource(Rez.Strings.GymReps).toString() + ": " + _reps,
                 Graphics.FONT_SMALL, Graphics.COLOR_WHITE, 2, 0));
        lines.add(ApexBaseView.line(weightPrefix +
                 WatchUi.loadResource(Rez.Strings.GymWeight).toString() + ": " +
                 ApexFormat.weightLabel(_weightKg, imperial),
                 Graphics.FONT_SMALL, Graphics.COLOR_WHITE, 4, 0));

        // transient feedback
        if (!_flash.equals("")) {
            lines.add(ApexBaseView.line(_flash, Graphics.FONT_XTINY,
                     Graphics.COLOR_DK_GREEN, 4, 0));
        }

        // next-up preview + key hints
        var next = ApexGymExercises.nextExerciseName(_index);
        if (!next.equals("")) {
            lines.add(ApexBaseView.line(Lang.format(
                WatchUi.loadResource(Rez.Strings.GymNext).toString(), [next]),
                Graphics.FONT_XTINY, Graphics.COLOR_LT_GRAY, 4, 0));
        }
        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.GymFieldMenu).toString(),
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 2, 0));
        lines.add(ApexBaseView.line(
            WatchUi.loadResource(Rez.Strings.GymLogSet).toString() + " (SELECT)",
            Graphics.FONT_XTINY, Graphics.COLOR_DK_GRAY, 2, 0));
        paintLines(dc, lines);
    }

    private function _paintSetDots(dc as Graphics.Dc, w as Lang.Number, sets as Lang.Number, done as Lang.Number, y as Lang.Number) as Void {
        if (sets <= 0) {
            return;
        }
        var radius = 5;
        var spacing = 2 * radius + 6;
        var totalW = sets * spacing - 6;
        var x = w / 2 - totalW / 2 + radius;
        for (var i = 0; i < sets; i += 1) {
            if (i < done) {
                dc.setColor(Graphics.COLOR_DK_GREEN, Graphics.COLOR_TRANSPARENT);
                dc.fillCircle(x, y, radius);
            } else {
                dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
                dc.drawCircle(x, y, radius);
            }
            x += spacing;
        }
    }

    //! UP/DOWN stepper on the focused field.
    function step(direction as Lang.Number) as Void {
        if (_focusReps) {
            _reps = ApexFormat.clamp(_reps + direction, 1, 50);
        } else {
            var imperial = ApexPayload.asBool(Application.Properties.getValue("imperial"));
            var shown = ApexFormat.weightToDisplay(_weightKg, imperial) + direction;
            if (shown < 0) {
                shown = 0.0;
            }
            _weightKg = ApexFormat.displayToWeight(shown, imperial);
        }
        WatchUi.requestUpdate();
    }

    //! MENU toggles the focused field.
    function toggleField() as Void {
        _focusReps = !_focusReps;
        WatchUi.requestUpdate();
    }

    //! SELECT logs the set: queue event + local progress + rest timer.
    function logSet() as Void {
        var ex = ApexGymExercises.exerciseAt(_index);
        if (ex == null) {
            return;
        }
        var data = {
            "gym_day_exercise_id" => ApexPayload.numAt(ex, "gym_day_exercise_id"),
            "set_no" => ApexPayload.numAt(ex, "sets_done") + 1,
            "reps" => _reps,
            "weight_kg" => _weightKg
        };
        var event = ApexPayload.makeEvent(ApexPayload.EVENT_SET_LOG, data);
        var result = ApexStore.addEvent(event);
        if (result.equals("failed")) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.SyncFailed), null);
            return;
        }
        if (result.equals("dropped")) {
            WatchUi.showToast(WatchUi.loadResource(Rez.Strings.QueueFull), null);
        }
        ApexGymExercises.setLastWeight(_index, _weightKg);
        ApexGymExercises.bumpSetsDone(_index);
        _flash = WatchUi.loadResource(Rez.Strings.GymLogged).toString();
        WatchUi.requestUpdate();

        var restSeconds = ApexPayload.numAt(ex, "rest_seconds");
        if (restSeconds > 0) {
            if (restSeconds > 600) {
                restSeconds = 600; // hard cap: bounded timer, bounded battery
            }
            var restView = new ApexRestView(restSeconds);
            WatchUi.pushView(restView, new ApexRestDelegate(restView),
                             WatchUi.SLIDE_IMMEDIATE);
        }
    }
}

class ApexGymExerciseDelegate extends WatchUi.BehaviorDelegate {

    var _view as ApexGymExerciseView or Null;

    function initialize(view as ApexGymExerciseView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onNextPage() as Lang.Boolean {
        if (_view != null) {
            _view.step(1);
        }
        return true;
    }

    function onPreviousPage() as Lang.Boolean {
        if (_view != null) {
            _view.step(-1);
        }
        return true;
    }

    function onSelect() as Lang.Boolean {
        if (_view != null) {
            _view.logSet();
        }
        return true;
    }

    function onMenu() as Lang.Boolean {
        if (_view != null) {
            _view.toggleField();
        }
        return true;
    }

    function onBack() as Lang.Boolean {
        var listView = new ApexGymView();
        WatchUi.switchToView(listView, new ApexGymDelegate(listView),
                             WatchUi.SLIDE_IMMEDIATE);
        return true;
    }
}
