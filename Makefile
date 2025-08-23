# Makefile for fedrate project

PYTHON = /opt/homebrew/bin/python3.11

venv:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate; pip install --upgrade pip
	. .venv/bin/activate; pip install -r requirements.txt

clean:
	rm -rf .venv
