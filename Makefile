.PHONY: setup up test stop

setup:
	python3 setup.py

up: setup
	docker compose up -d --wait kestra-db
	docker compose up -d kestra

test: up
	python3 -m unittest discover -s tests -p 'test_*.py' -v

stop:
	docker compose --profile replica stop
