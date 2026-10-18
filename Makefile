# Documentation site and benchmark: one entry point, `make <target>`.
# Dependencies are real prerequisites, so every target installs what it needs, once,
# and skips the install while its inputs (pyproject.toml, package-lock.json) are unchanged.
# CI (.github/workflows/docs.yml) runs `make all`; it is the same thing you run locally.
#
#   make serve      docs with live reload   -> http://localhost:3000/mermaidx/
#   make build      static site             -> docs/build
#   make all        benchmark, then build   (what CI does)
#   make help       every target
#
# See docs/README.md for the guide.

BASE_PYTHON ?= python3
NPM         ?= npm
NODE        ?= node

DOCS      := docs
CACHE     := .cache

# Everything Python runs inside a virtualenv, so it never touches the system Python
# (which refuses `pip install` on current Debian and Ubuntu, see PEP 668).
VENV   := $(CACHE)/venv
PYTHON := $(VENV)/bin/python
BENCH_OUT := $(DOCS)/static/benchmarks
SHOWCASE  := $(DOCS)/src/data/showcase.json
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
WITH_MMDC  ?= 1
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
$(PY_STAMP): pyproject.toml
	$(call need,$(BASE_PYTHON),Install Python 3.9 or newer.)
	$(BASE_PYTHON) -m venv $(VENV)
	$(PYTHON) -m pip install --quiet --upgrade pip
	$(PYTHON) -m pip install --quiet -e ".[all]"
	@mkdir -p $(CACHE) && touch $@

$(NPM_STAMP): $(DOCS)/package.json $(DOCS)/package-lock.json
	$(call need,$(NODE),Install Node.js 20 or newer.)
	cd $(DOCS) && $(NPM) ci --no-audit --no-fund
	@mkdir -p $(CACHE) && touch $@

$(MMDC_BIN):
	$(call need,$(NODE),Install Node.js 20 or newer, or run with WITH_MMDC=0.)
	@mkdir -p $(MMDC_DIR)
	$(NPM) install --prefix $(MMDC_DIR) --no-audit --no-fund @mermaid-js/mermaid-cli

$(PUPPETEER_CONFIG):
	@mkdir -p $(CACHE)
	printf '{"args": ["--no-sandbox"]}\n' > $@

# Copies architecture.md and CHANGELOG.md into the docs, so they stay the single source.
$(SYNC_STAMP): architecture.md CHANGELOG.md $(DOCS)/scripts/sync.js
	$(NODE) $(DOCS)/scripts/sync.js
	@mkdir -p $(CACHE) && touch $@

# ---- generated content -------------------------------------------------------------
$(SHOWCASE): $(PY_STAMP) $(DOCS)/scripts/make_showcase.py $(wildcard tests/samples/*.mmd)
	$(PYTHON) $(DOCS)/scripts/make_showcase.py

showcase: $(SHOWCASE) ## Render the landing-page examples with mermaidx

benchmark: $(BENCH_DEPS) ## Render tests/samples with mmdc and every backend (always runs)
	PATH="$(BENCH_PATH)$$PATH" $(PYTHON) benchmarks/run.py --out $(BENCH_OUT) $(RUN_ARGS)

# ---- the site ----------------------------------------------------------------------
build: $(NPM_STAMP) $(SYNC_STAMP) $(SHOWCASE) ## Build the static site into docs/build
	cd $(DOCS) && $(DOCUSAURUS) build

serve: $(NPM_STAMP) $(SYNC_STAMP) $(SHOWCASE) ## Dev server with live reload
	cd $(DOCS) && $(DOCUSAURUS) start

preview: build ## Build, then serve the result exactly as GitHub Pages will
	cd $(DOCS) && $(DOCUSAURUS) serve

all: benchmark build ## Benchmark, then build the site (what CI runs)

# ---- cleaning ----------------------------------------------------------------------
clean: ## Remove generated files (keeps installed dependencies)
	rm -rf $(DOCS)/build $(DOCS)/.docusaurus $(DOCS)/static/img/showcase $(SHOWCASE)
	rm -f $(DOCS)/docs/architecture.md $(DOCS)/docs/changelog.md $(SYNC_STAMP)
	find $(BENCH_OUT) -mindepth 1 ! -name .gitkeep -delete

distclean: clean ## Also remove node_modules and the install stamps
	rm -rf $(DOCS)/node_modules $(CACHE)
