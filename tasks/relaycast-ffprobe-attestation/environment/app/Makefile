.PHONY: build reproduce
build:
	go build -o bin/relaycast ./cmd/relaycast
reproduce: build
	./bin/relaycast reproduce --graph "$${GRAPHML_PATH:-/app/incident/topology.graphml}" --out "$${REPORT_PATH:-/app/out/provenance.json}"
