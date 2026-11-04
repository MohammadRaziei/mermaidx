Diagrams that only the benchmark (`benchmarks/run.py`) renders, next to the ones in `tests/samples`.

They have no mermaid-cli reference `.svg`, which is why they are not in `tests/samples`: `tests/test_sample_layout.py`
and `tests/test_mmdc_structural.py` need a reference for every sample there. Without a reference the benchmark simply
skips the "words drawn" measurement for them.

* `00_info`: the bare `info` diagram (just the word `info`), the smallest possible input
* `44`-`46`: the ELK layout (`flowchart-elk` and `layout: elk`), issue #33
* `47`-`49`: ZenUML, issue #20

A renderer that cannot draw one of them is recorded as an error and shown as "Not supported" on the page.
Name new files `NN_short_name.mmd`, with a number that no sample in either directory uses.
