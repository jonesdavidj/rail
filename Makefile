.PHONY: check test build ci

check:
	./scripts/check.sh

test:
	./scripts/test.sh

build:
	./scripts/build.sh

ci: check test build
