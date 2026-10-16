"""V8 cannot call back into Python while it runs, and novasvg lays out the HTML labels of a <foreignObject>
(wrapping, bold and italic runs, a declared width...) -- far too much to copy into JS. So the page is rendered
more than once: a label whose size is not known yet is recorded and given a rough size, the child process asks
novasvg for exactly the recorded ones, and the page is rendered again, until nothing new is asked. The last
pass has seen only exact sizes, so what it renders is what QuickJS renders."""
import json

import pytest

mini_racer = pytest.importorskip("py_mini_racer")

from mermaidx.engines import v8_engine  # noqa: E402
from mermaidx.engines._common import MermaidRenderError  # noqa: E402

_HTML = '<div xmlns="http://www.w3.org/1999/xhtml">Hello</div>'


def _new_ctx():
    c = mini_racer.MiniRacer()
    c.eval("globalThis.__log = (s) => {};")
    c.eval(v8_engine._measure_text_js())
    return c


def _ask(ctx, html=_HTML, size=16):
    return json.loads(ctx.eval(f"JSON.stringify(__measureForeignObject({json.dumps(html)}, {size}, 'sans-serif', '400', 'normal'))"))


def _missing(ctx):
    return json.loads(ctx.eval("JSON.stringify(globalThis.__foMissing)"))


# -- the JS side ---------------------------------------------------------------------------------------

def test_an_unknown_label_is_recorded_and_gets_a_finite_positive_size():
    ctx = _new_ctx()
    got = _ask(ctx)
    assert got["width"] > 0 and got["height"] > 0 and got["line_count"] == 1
    asked = list(_missing(ctx).values())
    assert asked == [[_HTML, 16, "sans-serif", "400", "normal"]]


def test_a_known_label_gets_exactly_the_recorded_size_and_is_not_asked_again():
    ctx = _new_ctx()
    _ask(ctx)
    (key,) = _missing(ctx)
    exact = {"width": 12.5, "height": 24.0, "line_count": 3, "line_height": 8.0}
    ctx.eval(f"globalThis.__foKnown = {json.dumps({key: exact})}; globalThis.__foMissing = {{}};")
    assert _ask(ctx) == exact
    assert _missing(ctx) == {}


def test_each_distinct_request_is_its_own_key():
    ctx = _new_ctx()
    _ask(ctx)
    _ask(ctx, size=17)
    _ask(ctx, html="<div>other</div>")
    _ask(ctx)                       # the same again: not a new key
    assert len(_missing(ctx)) == 3


def test_a_rough_size_is_wider_for_longer_text():
    ctx = _new_ctx()
    assert _ask(ctx, html="<div>a</div>")["width"] < _ask(ctx, html="<div>a much longer label</div>")["width"]


# -- the passes ----------------------------------------------------------------------------------------

_EXACT = {"width": 11.0, "height": 22.0, "line_count": 1, "line_height": 22.0}


class _Script:
    """Stands in for render_script: asks for the sizes of some labels and 'renders' the answers."""

    def __init__(self, labels, fail_unless_exact=False):
        self.labels, self.fail_unless_exact, self.passes = labels, fail_unless_exact, 0

    def __call__(self, code, theme, config, css):
        self.passes += 1
        asks = ", ".join(f"__measureForeignObject({json.dumps(h.format(n=self.passes))}, 16, 's', '400', 'normal')" for h in self.labels)
        check = (
            "if (answers.some((a) => a.width !== 11)) { globalThis.__renderError = 'rough size used'; } else "
            if self.fail_unless_exact else ""
        )
        return (
            "globalThis.__renderResult = null; globalThis.__renderError = null;\n"
            f"const answers = [{asks}];\n"
            f"{check}globalThis.__renderResult = JSON.stringify(answers);\n"
        )


@pytest.fixture
def passes(monkeypatch):
    monkeypatch.setattr(v8_engine, "run_event_loop", lambda evaluate: None)

    def run(script, known=None):
        monkeypatch.setattr(v8_engine, "render_script", script)
        asked = []

        def measure(*args):
            asked.append(args)
            return dict(_EXACT)

        known = {} if known is None else known
        svg = v8_engine._render(_new_ctx(), "code", "default", None, None, known, measure, _new_ctx)
        return svg, asked, known

    return run


def test_a_diagram_without_labels_is_rendered_once(passes):
    script = _Script([])
    svg, asked, _ = passes(script)
    assert script.passes == 1 and asked == [] and json.loads(svg) == []


def test_unknown_labels_are_measured_by_novasvg_and_the_page_rendered_again(passes):
    script = _Script(["<div>a</div>", "<div>b</div>"])
    svg, asked, _ = passes(script)
    assert script.passes == 2
    assert [a[0] for a in asked] == ["<div>a</div>", "<div>b</div>"]
    assert json.loads(svg) == [_EXACT, _EXACT]            # the last pass saw only exact sizes


def test_a_label_asked_twice_in_a_pass_is_measured_once(passes):
    script = _Script(["<div>a</div>", "<div>a</div>"])
    _, asked, _ = passes(script)
    assert len(asked) == 1


def test_sizes_learned_in_one_render_are_known_in_the_next(passes):
    known = {}
    script = _Script(["<div>a</div>"])
    passes(script, known)
    again = _Script(["<div>a</div>"])
    _, asked, _ = passes(again, known)
    assert again.passes == 1 and asked == []


def test_an_error_while_sizes_were_still_rough_is_not_the_answer(passes):
    script = _Script(["<div>a</div>"], fail_unless_exact=True)
    svg, _, _ = passes(script)
    assert script.passes == 2 and json.loads(svg) == [_EXACT]


def test_an_error_with_exact_sizes_is_reported(passes):
    class Broken(_Script):
        def __call__(self, *args):
            return "globalThis.__renderResult = null; globalThis.__renderError = 'Parse error on line 1';"

    with pytest.raises(MermaidRenderError, match="Parse error on line 1"):
        passes(Broken([]))


def test_labels_that_never_settle_are_an_error_not_a_loop(passes):
    script = _Script(["<div>pass {n}</div>"])               # a different label in every pass
    with pytest.raises(MermaidRenderError, match="did not settle"):
        passes(script)
    assert script.passes == v8_engine._MAX_PASSES


def test_each_pass_gets_a_context_of_its_own(monkeypatch):
    monkeypatch.setattr(v8_engine, "run_event_loop", lambda evaluate: None)
    monkeypatch.setattr(v8_engine, "render_script", _Script(["<div>a</div>"]))
    built = []

    def build():
        built.append(1)
        return _new_ctx()

    v8_engine._render(_new_ctx(), "code", "default", None, None, {}, lambda *a: dict(_EXACT), build)
    assert len(built) == 1                                  # pass 1 used the context it was given; pass 2 a fresh one


def test_the_known_sizes_do_not_grow_for_ever(passes):
    known = {f"k{i}": _EXACT for i in range(v8_engine._KNOWN_LIMIT + 5)}
    _, _, known = passes(_Script(["<div>a</div>"]), known)
    assert len(known) <= v8_engine._KNOWN_LIMIT
