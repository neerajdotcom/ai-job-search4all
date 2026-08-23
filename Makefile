.PHONY: install test app run dry-run verify clean

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

app:
	python -m webapp

run:
	python main.py

dry-run:
	python main.py --dry-run

verify:
	python -m native.cli verify

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find data/traces -type f ! -name ".gitkeep" -delete
	find outputs -type f ! -name ".gitkeep" -delete
