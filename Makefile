.PHONY: dev install test

install:
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port $${PORT:-7001}

test:
	pytest tests/
