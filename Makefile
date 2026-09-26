# Local development. Skills run in the claude.ai / Cowork sandbox; this mirrors it
# so every output can be generated and debugged locally.

PYTHON   ?= python3.12
VENV     := .venv
PY       := $(VENV)/bin/python
NVM      := . "$${NVM_DIR:-$$HOME/.nvm}/nvm.sh" && nvm use --silent >/dev/null &&
LO_BIN   ?= /Applications/LibreOffice.app/Contents/MacOS
DEV_ENV := NODE_PATH="$(CURDIR)/dev/node_modules" PATH="$(CURDIR)/$(VENV)/bin:$(LO_BIN):$$PATH"
OUT      := out
DIST     := dist
# The version lives only in plugin.json (a comment on the line below would add trailing spaces to the value)
VERSION   = $(shell $(PY) -c 'import json; print(json.load(open(".claude-plugin/plugin.json"))["version"])')

.PHONY: help setup hooks test style-check lint-skills py311 sync check-sync runtime-check preview-design outputs samples package package-skills release clean

help:
	@echo "make setup          Create .venv, install Chromium and Node modules (nvm)"
	@echo "make hooks          Install the git pre-commit hook (shared/ copies must be in sync)"
	@echo "make test           Run unit tests in dev/tests/"
	@echo "make style-check    Render every fixture and flag em dashes and labels not in Title Case"
	@echo "make lint-skills    Check every SKILL.md: frontmatter, description length, Guardrails first, paths"
	@echo "make py311          Check shipped Python for 3.11 (the Cowork runtime)"
	@echo "make sync           Copy shared/ into every skill's scripts/_shared/"
	@echo "make check-sync     Fail if any scripts/_shared/ copy differs from shared/"
	@echo "make runtime-check  Run the runtime check against the local environment"
	@echo "make preview-design Render brand palettes for sample scenarios into $(OUT)/design/"
	@echo "make outputs        Render every skill fixture in dev/fixtures/ into $(OUT)/"
	@echo "make samples        Regenerate the committed preview files and samples/README.md from the mock data in dev/samples/"
	@echo "make package        Run every check, then build $(DIST)/real-estate-<version>.plugin and the release zip (plugin + README + PDF manual)"
	@echo "make release        From an up-to-date main: run make package, then publish GitHub release v<version> with the release zip only"
	@echo "make package-skills Run every check, then zip every skill into $(DIST)/skills/ (runtime-check into $(DIST)/dev/)"
	@echo "make clean          Remove $(OUT)/ and $(DIST)/"

# SHARP_IGNORE_GLOBAL_LIBVIPS: use sharp's bundled binaries even when Homebrew vips is installed.
setup:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r dev/requirements.txt
	$(PY) -m playwright install chromium
	. "$${NVM_DIR:-$$HOME/.nvm}/nvm.sh" && nvm install && cd dev && SHARP_IGNORE_GLOBAL_LIBVIPS=1 npm install --silent
	git config core.hooksPath dev/hooks

hooks:
	git config core.hooksPath dev/hooks

style-check:
	@$(NVM) $(DEV_ENV) $(PY) dev/style_check.py

test:
	@PATH="$$PATH:$(LO_BIN)" $(PY) -m unittest discover -s dev/tests  # LibreOffice, when installed, for the deck-PDF check

lint-skills:
	@$(PY) dev/lint_skills.py

py311:
	@$(PY) dev/py311_check.py

preview-design:
	@$(PY) dev/preview_design.py

sync:
	@python3 dev/sync_shared.py

check-sync:
	@python3 dev/sync_shared.py --check

runtime-check:
	@$(NVM) $(DEV_ENV) $(PY) dev/runtime-check/scripts/check.py

# Each skill exposes scripts/render.py DATA.json --format all --out DIR.
# Fixtures live in dev/fixtures/<skill>/*.json and are never shipped.
outputs:
	@for f in $(filter-out dev/fixtures/_profiles/%,$(wildcard dev/fixtures/*/*.json)); do \
		skill=$$(basename $$(dirname $$f)); name=$$(basename $$f .json); \
		dir=skills/$$skill; \
		echo "$$skill: $$name"; \
		$(NVM) $(DEV_ENV) OUTPUT_DIR="$(OUT)/$$skill/$$name" \
			$(PY) $$dir/scripts/render.py $$f --format all --out "$(OUT)/$$skill/$$name" \
			$(if $(wildcard dev/fixtures/_profiles/profile.md),--profile dev/fixtures/_profiles/profile.md) || exit 1; \
	done

# One happy-path sample per skill for previews, committed. Inputs in dev/samples/ are fully mocked.
samples:
	@for skill in buyer-cma seller-cma buyer-offer-strategy contract-timeline seller-offer-review; do \
		echo "$$skill"; rm -rf samples/$$skill; \
		$(NVM) $(DEV_ENV) OUTPUT_DIR="samples/$$skill" \
			$(PY) skills/$$skill/scripts/render.py dev/samples/$$skill.json --format all --out samples/$$skill \
			--profile dev/samples/profile.md || exit 1; \
	done
	@echo "seller-offer-review (single offer)"; \
		$(NVM) $(DEV_ENV) OUTPUT_DIR="samples/seller-offer-review" \
		$(PY) skills/seller-offer-review/scripts/render.py dev/samples/seller-offer-review-single.json --format all \
		--out samples/seller-offer-review --profile dev/samples/profile.md
	@$(PY) dev/samples_readme.py

package: check-sync test lint-skills py311 style-check
	@$(PY) dev/package.py plugin

# The version comes from plugin.json, never an argument, so the tag and the zip can't disagree. The guards run before
# the build: on main, nothing uncommitted, level with origin/main, and a tag that doesn't exist yet (bump plugin.json).
release:
	@test "$$(git branch --show-current)" = main || { echo "Release from main (git checkout main && git pull)."; exit 1; }
	@git diff --quiet && git diff --cached --quiet || { echo "Commit or stash your changes first."; exit 1; }
	@git fetch -q origin && test "$$(git rev-parse HEAD)" = "$$(git rev-parse origin/main)" || { echo "main isn't level with origin/main: pull or push first."; exit 1; }
	@! gh release view v$(VERSION) >/dev/null 2>&1 || { echo "Release v$(VERSION) already exists: bump the version in .claude-plugin/plugin.json."; exit 1; }
	@$(MAKE) --no-print-directory package
	@echo "Publishing v$(VERSION) with $(DIST)/real-estate-skills-$(VERSION).zip"
	gh release create v$(VERSION) $(DIST)/real-estate-skills-$(VERSION).zip --target main --title $(VERSION) --generate-notes

package-skills: check-sync test lint-skills py311 style-check
	@$(PY) dev/package.py skills

clean:
	rm -rf $(OUT) $(DIST)
