# Single entry point for the documentation site and its benchmark.
# CI (.github/workflows/docs.yml) runs these same targets, so what works here works there.
#
#   make install-python install-docs     one-time setup
#   make install-mmdc                    optional: adds mermaid-cli to the benchmark
#   make serve                           live-reload docs at http://localhost:3000/mermaidx/
#   make all                             benchmark + showcase + production build

PYTHON ?= python3
NPM    ?= npm

DOCS      := docs
BENCH_OUT := $(DOCS)/static/benchmarks

# Extra arguments for benchmarks/run.py, e.g.
#   make benchmark BENCH_ARGS="--skip-mmdc --only 01_simple_flowchart --repeats 1"
BENCH_ARGS ?=
RUN_ARGS   := $(BENCH_ARGS)

# NO_SANDBOX=1 lets mmdc's headless Chrome start on CI runners (no user namespaces).
PUPPETEER_CONFIG := .puppeteer.json
ifdef NO_SANDBOX
RUN_ARGS   += --puppeteer-config $(PUPPETEER_CONFIG)
BENCH_DEPS := $(PUPPETEER_CONFIG)
endif

.DEFAULT_GOAL := help
.PHONY: help install-python install-mmdc install-docs benchmark showcase docs serve all clean

help: ## Show this list
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

install-python: ## Install mermaidx with every backend (editable)
	$(PYTHON) -m pip install -e ".[all]"

install-mmdc: ## Install mermaid-cli globally, so the benchmark can include it
	$(NPM) install -g @mermaid-js/mermaid-cli

install-docs: ## Install the docs site dependencies (npm ci)
	cd $(DOCS) && $(NPM) ci

$(PUPPETEER_CONFIG):
	printf '{"args": ["--no-sandbox"]}\n' > $@

benchmark: $(BENCH_DEPS) ## Render tests/samples with mmdc and every backend, write results + PNGs
	$(PYTHON) benchmarks/run.py --out $(BENCH_OUT) $(RUN_ARGS)

showcase: ## Render the landing-page examples with mermaidx
	$(PYTHON) $(DOCS)/scripts/make_showcase.py

docs: showcase ## Build the static site into docs/build (uses benchmark results if present)
	cd $(DOCS) && $(NPM) run build

serve: showcase ## Start the docs dev server with live reload
	cd $(DOCS) && $(NPM) run start

all: benchmark docs ## Benchmark, then build the site

clean: ## Remove everything the targets above generate
	rm -rf $(DOCS)/build $(DOCS)/.docusaurus $(DOCS)/static/img/showcase $(DOCS)/src/data/showcase.json $(PUPPETEER_CONFIG)
	rm -rf $(DOCS)/docs/architecture.md $(DOCS)/docs/changelog.md
	find $(BENCH_OUT) -mindepth 1 ! -name .gitkeep -delete
