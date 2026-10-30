# Convenience targets (macOS/Linux, or Windows with make). Windows without make: see README Quickstart.
PY ?= .venv/bin/python

.PHONY: venv run test lint
venv:
	python3.13 -m venv .venv && $(PY) -m pip install -r requirements.txt
run:
	$(PY) -m pipeline.run
test:
	$(PY) -m pipeline.run --test
lint:
	$(PY) -m ruff check .
