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

SKILLS := $(patsubst %/SKILL.md,%,$(wildcard plugins/*/skills/*/SKILL.md))

.PHONY: help setup runtime-check outputs package clean

help:
	@echo "make setup          Create .venv, install Chromium and Node modules (nvm)"
	@echo "make runtime-check  Run the runtime check against the local environment"
	@echo "make outputs        Render every skill fixture in dev/fixtures/ into $(OUT)/"
	@echo "make package        Zip every skill (and runtime-check) into $(DIST)/"
	@echo "make clean          Remove $(OUT)/ and $(DIST)/"

setup:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r dev/requirements.txt
	$(PY) -m playwright install chromium
	. "$${NVM_DIR:-$$HOME/.nvm}/nvm.sh" && nvm install && cd dev && npm install --silent

runtime-check:
	@$(NVM) $(DEV_ENV) $(PY) dev/runtime-check/scripts/check.py

# Each skill exposes scripts/render.py DATA.json --format all --out DIR.
# Fixtures live in dev/fixtures/<skill>/*.json and are never shipped.
outputs:
	@for f in $(wildcard dev/fixtures/*/*.json); do \
		skill=$$(basename $$(dirname $$f)); name=$$(basename $$f .json); \
		dir=$$(dirname $$(ls plugins/*/skills/$$skill/SKILL.md)); \
		echo "$$skill: $$name"; \
		$(NVM) $(DEV_ENV) OUTPUT_DIR="$(OUT)/$$skill/$$name" \
			$(PY) $$dir/scripts/render.py $$f --format all --out "$(OUT)/$$skill/$$name" || exit 1; \
	done

package:
	@mkdir -p $(DIST)
	@for s in $(SKILLS); do \
		plugin=$$(echo $$s | cut -d/ -f2); name=$$(basename $$s); \
		rm -f $(DIST)/$$plugin-$$name.zip; \
		(cd $$(dirname $$s) && zip -qr $(CURDIR)/$(DIST)/$$plugin-$$name.zip $$name -x '*.DS_Store' '*__pycache__*'); \
		echo "$(DIST)/$$plugin-$$name.zip"; \
	done
	@rm -f $(DIST)/runtime-check.zip
	@cd dev && zip -qr $(CURDIR)/$(DIST)/runtime-check.zip runtime-check -x '*.DS_Store' '*__pycache__*'
	@echo "$(DIST)/runtime-check.zip"

clean:
	rm -rf $(OUT) $(DIST)
