"""How tests/samples is laid out: every sample is `NN_name.mmd` plus `NN_name.svg`, side by side.

The `.svg` is what mmdc (mermaid-cli, in Chromium) renders from the `.mmd`; see samples/README.md for the
recipe. Nothing else lives there -- no second copy of a reference in a sub-folder.
"""
from pathlib import Path

import pytest

SAMPLES_DIR = Path(__file__).parent / "samples"
NAMES = sorted(p.stem for p in SAMPLES_DIR.glob("*.mmd"))


def test_there_are_samples():
    assert len(NAMES) >= 43


def test_samples_are_numbered_in_order_without_gaps():
    numbers = [int(name[:2]) for name in NAMES]
    assert numbers == list(range(1, len(numbers) + 1))


def test_references_are_not_hidden_in_a_sub_folder():
    assert not [p.name for p in SAMPLES_DIR.iterdir() if p.is_dir()], "tests/samples must be flat"


@pytest.mark.parametrize("name", NAMES)
def test_every_sample_has_its_mmdc_render_next_to_it(name):
    assert (SAMPLES_DIR / f"{name}.svg").is_file()


@pytest.mark.parametrize("svg", sorted(SAMPLES_DIR.glob("*.svg")), ids=lambda p: p.name)
def test_every_svg_belongs_to_a_sample_and_is_a_real_diagram(svg):
    assert svg.with_suffix(".mmd").is_file(), f"{svg.name} has no {svg.stem}.mmd"
    assert 'aria-roledescription="error"' not in svg.read_text(encoding="utf-8")[:2000], "mmdc rendered a syntax-error graphic"


def test_the_recipe_for_making_the_references_is_documented_next_to_them():
    assert "mmdc" in (SAMPLES_DIR / "README.md").read_text(encoding="utf-8")
