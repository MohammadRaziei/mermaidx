"""What the QuickJS and V8 engines share lives in mermaidx/engines/_common.py (written once)."""
import json

import pytest
import quickjs

from mermaidx.engines import _common


def test_both_engines_raise_the_same_error_class():
    pytest.importorskip("py_mini_racer")
    from mermaidx.engines import quickjs_engine, v8_engine

    assert quickjs_engine.MermaidRenderError is _common.MermaidRenderError
    assert v8_engine.MermaidRenderError is _common.MermaidRenderError


def test_config_defaults_and_caller_wins():
    cfg = _common.mermaid_config(None, None)
    assert cfg["startOnLoad"] is False and cfg["theme"] == "default"
    assert cfg["flowchart"] == {"htmlLabels": True}
    assert cfg["journey"] == {"textPlacement": "fo"} and cfg["timeline"] == {"textPlacement": "fo"}

    cfg = _common.mermaid_config("dark", {"theme": "forest", "flowchart": {"htmlLabels": False}, "x": 1})
    assert cfg["theme"] == "forest" and cfg["flowchart"] == {"htmlLabels": False} and cfg["x"] == 1
    assert _common.mermaid_config("dark", None)["theme"] == "dark"


def test_context_scripts_load_geometry_before_the_shim_and_the_driver_last():
    scripts = _common.context_scripts()
    assert len(scripts) == 5
    bbox, shim, mermaid, alias, driver = scripts
    assert "__pathBBox" in bbox and "__resetDocument" in shim and "__renderLikeMmdc" in driver
    assert "__esbuild_esm_mermaid_nm" in alias and len(mermaid) > 100_000


_STUBS = """
globalThis.calls = [];
globalThis.__resetDocument = () => calls.push(["reset"]);
globalThis.mermaid = { initialize: (c) => calls.push(["init", c]) };
globalThis.document = { head: { appendChild: (el) => calls.push(["css", el.textContent]) },
  getElementById: () => null,
  createElement: () => ({ setAttribute() {}, textContent: "" }) };
globalThis.__renderLikeMmdc = (id, code, bg) => { calls.push(["render", id, code, bg]); return Promise.resolve("<svg/>"); };
"""


def _run(script: str):
    ctx = quickjs.Context()
    ctx.eval(_STUBS)
    ctx.eval(script)
    while ctx.execute_pending_job():
        pass
    return json.loads(ctx.eval("JSON.stringify(calls)")), ctx.eval("globalThis.__renderResult"), ctx.eval("globalThis.__renderError")


def test_render_script_resets_configures_then_renders_with_mmdc_arguments():
    calls, result, error = _run(_common.render_script("graph TD\nA-->B", "default", {"x": 1}, None))
    assert [c[0] for c in calls] == ["reset", "init", "render"]
    assert calls[1][1]["x"] == 1
    assert calls[2][1:] == ["my-svg", "graph TD\nA-->B", "transparent"]
    assert result == "<svg/>" and error is None


def test_render_script_injects_css_only_when_given():
    assert "css" not in [c[0] for c in _run(_common.render_script("g", None, None, None))[0]]
    calls = _run(_common.render_script("g", None, None, ".a { fill: red }"))[0]
    assert ["css", ".a { fill: red }"] in calls
    assert [c[0] for c in calls] == ["reset", "init", "css", "render"]


@pytest.mark.parametrize("code", ['A["it\'s \\"quoted\\""]', "line1\nline2\ttab", "日本語 \u2028 \u2029 \u00e9", "</script> ${x} `tpl`"])
def test_render_script_passes_any_text_through_unchanged(code):
    assert _run(_common.render_script(code, None, None, None))[0][2][2] == code


def test_a_failed_render_is_reported_through_the_error_slot():
    ctx = quickjs.Context()
    ctx.eval(_STUBS.replace('Promise.resolve("<svg/>")', 'Promise.reject({name: "Error", message: "boom"})'))
    ctx.eval(_common.render_script("g", None, None, None))
    while ctx.execute_pending_job():
        pass
    assert ctx.eval("globalThis.__renderError") == "Error: boom"


def test_collect_svg():
    assert _common.collect_svg({"globalThis.__renderError": None, "globalThis.__renderResult": "<svg/>"}.get) == "<svg/>"
    with pytest.raises(_common.MermaidRenderError, match="boom"):
        _common.collect_svg({"globalThis.__renderError": "boom"}.get)
    with pytest.raises(_common.MermaidRenderError, match="no output"):
        _common.collect_svg({"globalThis.__renderError": None, "globalThis.__renderResult": None}.get)


# ---------------------------------------------------------------------------
# The page's event loop, shared by both engines: all the promise jobs, then the next timer, then the jobs again...
# ---------------------------------------------------------------------------

class _FakePage:
    """What run_event_loop sees of a page: some promise jobs now, a list of timers, each of which may queue more
    jobs, and a render that is done after a given number of steps of its own."""

    def __init__(self, jobs=0, timers=0, jobs_per_timer=0, done_after_timers=None):
        self.jobs, self.timers, self.jobs_per_timer = jobs, timers, jobs_per_timer
        self.done_after_timers = done_after_timers
        self.log = []
        self.timer_calls = 0

    def done(self):
        return self.done_after_timers is not None and self.timers_run >= self.done_after_timers

    timers_run = 0

    def evaluate(self, js):
        if "__renderResult" in js:
            return self.done()
        assert js == "__runNextTimer()", js
        self.timer_calls += 1
        if self.timers == 0:
            return False
        self.timers -= 1
        self.timers_run += 1
        self.jobs += self.jobs_per_timer
        self.log.append("timer")
        return True

    def run_job(self):
        if self.jobs == 0:
            return False
        self.jobs -= 1
        self.log.append("job")
        return True


def test_event_loop_drains_the_jobs_before_each_timer():
    from mermaidx.engines._common import run_event_loop

    page = _FakePage(jobs=2, timers=2, jobs_per_timer=1)
    run_event_loop(page.evaluate, page.run_job)
    assert page.log == ["job", "job", "timer", "job", "timer", "job"]


def test_event_loop_stops_as_soon_as_the_render_is_done():
    from mermaidx.engines._common import run_event_loop

    page = _FakePage(jobs=0, timers=10, jobs_per_timer=1, done_after_timers=2)
    run_event_loop(page.evaluate, page.run_job)
    assert page.timers_run == 2 and page.jobs == 1          # the job the second timer queued was not run
    assert page.log == ["timer", "job", "timer"]


def test_event_loop_checks_for_the_result_before_running_anything():
    from mermaidx.engines._common import run_event_loop

    page = _FakePage(jobs=3, timers=3, done_after_timers=0)
    run_event_loop(page.evaluate, page.run_job)
    assert page.log == []


def test_event_loop_stops_when_nothing_is_left():
    from mermaidx.engines._common import run_event_loop

    page = _FakePage(jobs=1, timers=1)
    run_event_loop(page.evaluate, page.run_job)
    assert page.log == ["job", "timer"] and page.jobs == 0 and page.timers == 0
    assert page.timer_calls == 2            # the one that ran, and the one that found the queue empty: then it stopped


def test_event_loop_without_a_job_runner_only_runs_timers():
    from mermaidx.engines._common import run_event_loop

    page = _FakePage(jobs=5, timers=2)
    run_event_loop(page.evaluate)
    assert page.log == ["timer", "timer"]


def test_event_loop_is_bounded_when_a_page_never_stops(monkeypatch):
    from mermaidx.engines import _common

    monkeypatch.setattr(_common, "MAX_EVENT_LOOP_STEPS", 50)
    page = _FakePage(timers=10**9)
    _common.run_event_loop(page.evaluate, page.run_job)
    assert page.timers_run == 50
