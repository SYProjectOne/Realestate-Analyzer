# scripts/tasks.py 의 얇은 래퍼. make 가 없으면(Windows) 직접:
#   python scripts/tasks.py <작업> [인자…]
# 예: make test M=judge   ==  python scripts/tasks.py test judge

PY ?= python
TASKS = $(PY) scripts/tasks.py
M ?=

.PHONY: help test lint typecheck fmt gen migrate api worker web dev regress check compose-config

help:
	$(TASKS) --list

test:
	$(TASKS) test $(M)

lint:
	$(TASKS) lint

typecheck:
	$(TASKS) typecheck

fmt:
	$(TASKS) fmt

gen:
	$(TASKS) gen

migrate:
	$(TASKS) migrate

api:
	$(TASKS) api

worker:
	$(TASKS) worker

web:
	$(TASKS) web

dev:
	$(TASKS) dev

regress:
	$(TASKS) regress

check:
	$(TASKS) check

compose-config:
	$(TASKS) compose-config
