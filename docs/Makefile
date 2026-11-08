# Documentation site and benchmark: one entry point, `make <target>`, run from this directory (docs/).
# Dependencies are real prerequisites, so every target installs what it needs, once,
# and skips the install while its inputs (pyproject.toml, package-lock.json) are unchanged.
# CI (.github/workflows/docs.yml) runs `make all` here; it is the same thing you run locally.
#
#   make serve      docs with live reload   -> http://localhost:3000/mermaidx/
#   make build      static site             -> build/
#   make all        benchmark, then build   (what CI does)
#   make help       every target
#
# See README.md in this directory for the guide.

BASE_PYTHON ?= python3
NPM         ?= npm
NODE        ?= node

# The repository root: the package itself, the samples, the benchmark script and the files synced into the docs.
ROOT  := ..
CACHE := .cache

# Everything Python runs inside a virtualenv, so it never touches the system Python
# (which refuses `pip install` on current Debian and Ubuntu, see PEP 668).
VENV   := $(CACHE)/venv
PYTHON := $(VENV)/bin/python
BENCH_OUT := static/benchmarks
SHOWCASE  := src/data/showcase.json
DOCUSAURUS := ./node_modules/.bin/docusaurus

# Install stamps: a target is re-run only when the files it depends on change.
PY_STAMP   := $(CACHE)/python.stamp
NPM_STAMP  := $(CACHE)/docs-npm.stamp
SYNC_STAMP := $(CACHE)/sync.stamp

# Fail early with a readable message when a tool is missing.
define need
@command -v $(1) >/dev/null 2>&1 || { echo "error: '$(1)' is required but was not found. $(2)"; exit 1; }
endef

# ---- benchmark options -------------------------------------------------------------
# WITH_MMDC=0       skip mermaid-cli (it installs ~170 MB of Chromium on first use)
# NO_SANDBOX=1      let mmdc's headless Chrome start on CI runners
# BENCH_ARGS="..."  extra arguments for benchmarks/run.py, e.g.
#                   make benchmark BENCH_ARGS="--only 31_venn --repeats 10"
# WITH_BYTECODE=0   keep the quickjs-ng from PyPI (no Context.compile / eval_bytecode), so js:mermaid loads
#                   mermaid.js from source on every render instead of from cached bytecode
WITH_MMDC  ?= 1
WITH_BYTECODE ?= 1
BENCH_ARGS ?=
RUN_ARGS   := $(BENCH_ARGS)
BENCH_DEPS := $(PY_STAMP)

MMDC_DIR := $(CACHE)/mmdc
MMDC_BIN := $(MMDC_DIR)/node_modules/.bin/mmdc
PUPPETEER_CONFIG := $(CACHE)/puppeteer.json

ifeq ($(WITH_MMDC),1)
BENCH_DEPS += $(MMDC_BIN)
BENCH_PATH := $(abspath $(MMDC_DIR))/node_modules/.bin:
else
RUN_ARGS   += --skip-mmdc
endif

ifdef NO_SANDBOX
BENCH_DEPS += $(PUPPETEER_CONFIG)
RUN_ARGS   += --puppeteer-config $(PUPPETEER_CONFIG)
endif

.DEFAULT_GOAL := help
.PHONY: help install showcase benchmark build serve preview all clean distclean

help: ## Show this list
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

install: $(PY_STAMP) $(NPM_STAMP) ## Install every dependency (the other targets do this on their own)

# ---- dependencies ------------------------------------------------------------------
$(PY_STAMP): $(ROOT)/pyproject.toml
	$(call need,$(BASE_PYTHON),Install Python 3.9 or newer.)
	$(BASE_PYTHON) -m venv $(VENV)
	$(PYTHON) -m pip install --quiet --upgrade pip
	$(PYTHON) -m pip install --quiet -e "$(ROOT)[all]"
	# pyoxipng recompresses the benchmark PNGs without loss (benchmarks/run.py: optimize_png); optional there, so a failure here is not fatal.
	-$(PYTHON) -m pip install --quiet pyoxipng
ifeq ($(WITH_BYTECODE),1)
	# The quickjs-ng on PyPI has no Context.compile / eval_bytecode; build the patched wheel (tools/quickjs_ng_bytecode)
	# and put it over the stock one, so the published benchmark numbers include the bytecode cache.
	bash $(ROOT)/tools/quickjs_ng_bytecode/build.sh $(abspath $(CACHE))/quickjs-bytecode
	$(PYTHON) -m pip install --quiet --force-reinstall --no-deps $(abspath $(CACHE))/quickjs-bytecode/quickjs_ng-*.whl
	$(PYTHON) -c "import quickjs; assert hasattr(quickjs.Context, 'compile') and hasattr(quickjs.Context, 'eval_bytecode')"
endif
	@mkdir -p $(CACHE) && touch $@

$(NPM_STAMP): package.json package-lock.json
	$(call need,$(NODE),Install Node.js 20 or newer.)
	$(NPM) ci --no-audit --no-fund
	@mkdir -p $(CACHE) && touch $@

$(MMDC_BIN):
	$(call need,$(NODE),Install Node.js 20 or newer, or run with WITH_MMDC=0.)
	@mkdir -p $(MMDC_DIR)
	$(NPM) install --prefix $(MMDC_DIR) --no-audit --no-fund @mermaid-js/mermaid-cli

$(PUPPETEER_CONFIG):
	@mkdir -p $(CACHE)
	printf '{"args": ["--no-sandbox"]}\n' > $@

# Copies architecture.md and CHANGELOG.md into the docs, so they stay the single source.
$(SYNC_STAMP): $(ROOT)/architecture.md $(ROOT)/CHANGELOG.md scripts/sync.js
	$(NODE) scripts/sync.js
	@mkdir -p $(CACHE) && touch $@

# ---- generated content -------------------------------------------------------------
$(SHOWCASE): $(PY_STAMP) scripts/make_showcase.py $(wildcard $(ROOT)/tests/samples/*.mmd)
	$(PYTHON) scripts/make_showcase.py

showcase: $(SHOWCASE) ## Render the landing-page examples with mermaidx

benchmark: $(BENCH_DEPS) ## Render tests/samples and benchmarks/samples with mmdc and every backend (always runs)
	PATH="$(BENCH_PATH)$$PATH" $(PYTHON) $(ROOT)/benchmarks/run.py --out $(BENCH_OUT) $(RUN_ARGS)

# ---- the site ----------------------------------------------------------------------
build: $(NPM_STAMP) $(SYNC_STAMP) $(SHOWCASE) ## Build the static site into build/
	$(DOCUSAURUS) build

serve: $(NPM_STAMP) $(SYNC_STAMP) $(SHOWCASE) ## Dev server with live reload
	$(DOCUSAURUS) start

preview: build ## Build, then serve the result exactly as GitHub Pages will
	$(DOCUSAURUS) serve

all: benchmark build ## Benchmark, then build the site (what CI runs)

# ---- cleaning ----------------------------------------------------------------------
clean: ## Remove generated files (keeps installed dependencies)
	rm -rf build .docusaurus static/img/showcase $(SHOWCASE)
	rm -f docs/architecture.md docs/changelog.md $(SYNC_STAMP)
	find $(BENCH_OUT) -mindepth 1 ! -name .gitkeep -delete

distclean: clean ## Also remove node_modules and the install stamps
	rm -rf node_modules $(CACHE)
