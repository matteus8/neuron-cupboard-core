export PATH := $(shell go env GOPATH)/bin:$(PATH)

CC ?= cc
CFLAGS ?= -Wall -Wextra -Werror -std=c99 -O2
SEC_CFLAGS ?= -Wall -Wextra -Werror -Wformat -Wformat-security -Wconversion -std=c99 -O2

.PHONY: all proto test build build-firmware clean test-proto test-firmware test-runtime test-gateway test-sim bench sast sast-go sast-python sast-c release-build

all: proto test build

proto:
	@echo "==> Compiling Protocol Buffers..."
	@./proto/generate.sh

test-proto: proto
	@echo "==> Testing proto (C wire codec)..."
	@$(CC) $(CFLAGS) -Iproto/c proto/c/neuron_wire_test.c -o /tmp/neuron_wire_test && /tmp/neuron_wire_test
	@echo "==> Testing proto (C exhaustive CRC-8 robustness proof)..."
	@$(CC) $(CFLAGS) -Iproto/c proto/c/neuron_crc8_robust_test.c -o /tmp/neuron_crc8_robust_test && /tmp/neuron_crc8_robust_test
	@echo "==> Testing proto (Go wire codec)..."
	@cd proto && go test -v ./...
	@echo "==> Testing proto (Python wire codec)..."
	@PYTHONPATH=. python3 -c "import proto.neuron_wire as nw; assert nw.pack_state(2, 3, True, False, True, False) == 0x5E; print('Python wire parity: OK')"

test-firmware:
	@echo "==> Testing firmware Manchester pulse modulation (C)..."
	@$(CC) $(CFLAGS) -Ifirmware/include -Iproto/c firmware/src/manchester.c firmware/test/test_manchester.c -o /tmp/test_manchester && /tmp/test_manchester
	@echo "==> Testing RP2040 PIO FIFO frame packing (C)..."
	@$(CC) $(CFLAGS) -Ifirmware/include -Iproto/c firmware/src/manchester.c firmware/test/test_bamboo_pio.c -o /tmp/test_bamboo_pio && /tmp/test_bamboo_pio
	@echo "==> Testing firmware MicroPython transmitter..."
	@PYTHONPATH=. python3 firmware/python/bamboo_transmitter.py

test-runtime:
	@echo "==> Testing Panda Runtime (vision, decoder, cupboard consensus, state machine, fuzzing, scale)..."
	@PYTHONPATH=. python3 -m unittest discover -s runtime/tests -v

test-gateway:
	@echo "==> Testing gateway (Zenoh Protobuf relay with Go race detector)..."
	@cd gateway && go test -v -race ./...

test-gcs:
	@echo "==> Testing GCS (Ground Control Station HUD with Go race detector)..."
	@cd gcs && go test -v -race ./...

test-sim:
	@echo "==> Running End-to-End Multi-Node Optical Swarm Simulation..."
	@PYTHONPATH=. python3 scripts/simulate_swarm.py

bench:
	@echo "==> Running Gateway Throughput and Allocation Benchmarks..."
	@cd gateway && go test -bench=. -benchmem -run=^$$ ./...

test: test-proto test-firmware test-runtime test-gateway test-gcs test-sim
	@echo "==> All subsystem and end-to-end simulation tests passed successfully."

sast: sast-go sast-python sast-c
	@echo "==> All SAST security audits passed cleanly."

sast-go:
	@echo "==> Running Go SAST (go vet, govulncheck, gosec)..."
	@cd gateway && go vet ./...
	@cd gcs && go vet ./...
	@if command -v govulncheck >/dev/null 2>&1; then cd gateway && govulncheck ./... && cd ../gcs && govulncheck ./...; else echo "WARN: govulncheck not installed"; fi
	@if command -v gosec >/dev/null 2>&1; then cd gateway && gosec -quiet ./... && cd ../gcs && gosec -quiet ./...; else echo "WARN: gosec not installed"; fi

sast-python:
	@echo "==> Running Python SAST (bandit)..."
	@python3 -m bandit -q -r runtime/panda proto/
	@echo "  [OK] Python static security audit clean."

sast-c:
	@echo "==> Running C Static Analysis and Hardened Compilation..."
	@$(CC) $(SEC_CFLAGS) -Iproto/c proto/c/neuron_wire_test.c -o /tmp/c_sast_wire && /tmp/c_sast_wire && rm -f /tmp/c_sast_wire
	@$(CC) $(SEC_CFLAGS) -Ifirmware/include -Iproto/c firmware/src/manchester.c firmware/test/test_manchester.c -o /tmp/c_sast_manchester && /tmp/c_sast_manchester && rm -f /tmp/c_sast_manchester
	@echo "  [OK] C static security audit clean."

build: build-firmware
	@echo "==> Building Gateway & GCS..."
	@mkdir -p bin
	@cd gateway && go build -o ../bin/gateway .
	@cd gcs && go build -o ../bin/gcs .
	@echo "  [OK] bin/gateway and bin/gcs created"

build-firmware:
	@mkdir -p bin
	@if [ -n "$$PICO_SDK_PATH" ] && command -v cmake >/dev/null 2>&1; then \
		echo "==> Building RP2040 firmware (Pico SDK)..."; \
		mkdir -p firmware/build && cd firmware/build && cmake .. && cmake --build . && cp -f bamboo_node.uf2 ../../bin/ && echo "  [OK] bin/bamboo_node.uf2 created"; \
	else \
		echo "==> Building firmware host simulation binary..."; \
		$(CC) $(CFLAGS) -Ifirmware/include -Iproto/c firmware/src/manchester.c firmware/src/main.c -o bin/bamboo_node_sim; \
		echo "  [OK] bin/bamboo_node_sim created"; \
	fi

package-runtime:
	@echo "==> Packaging Panda Runtime for Raspberry Pi 5..."
	@mkdir -p bin /tmp/panda-pkg
	@rm -rf /tmp/panda-pkg/*
	@cp -r runtime /tmp/panda-pkg/
	@cp -r proto /tmp/panda-pkg/
	@cp -r scripts /tmp/panda-pkg/
	@cp runtime/requirements.txt /tmp/panda-pkg/
	@cp deploy/systemd/panda-runtime.service /tmp/panda-pkg/
	@cp deploy/systemd/neuron-gateway.service /tmp/panda-pkg/
	@cp deploy/install_runtime.sh /tmp/panda-pkg/install.sh
	@cp deploy/install_gateway.sh /tmp/panda-pkg/install_gateway.sh
	@chmod +x /tmp/panda-pkg/install.sh /tmp/panda-pkg/install_gateway.sh /tmp/panda-pkg/scripts/*.py
	@tar -czf bin/panda-runtime.tar.gz -C /tmp/panda-pkg .
	@rm -rf /tmp/panda-pkg
	@echo "  [OK] bin/panda-runtime.tar.gz created"

release-build: build-firmware package-runtime
	@echo "==> Cross-compiling lightweight standalone native binaries..."
	@mkdir -p bin
	@cd gateway && CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -ldflags="-s -w" -o ../bin/gateway-linux-arm64 .
	@cd gateway && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o ../bin/gateway-linux-amd64 .
	@cd gateway && CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -ldflags="-s -w" -o ../bin/gateway-darwin-arm64 .
	@cd gcs && CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -ldflags="-s -w" -o ../bin/gcs-linux-arm64 .
	@cd gcs && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o ../bin/gcs-linux-amd64 .
	@cd gcs && CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -ldflags="-s -w" -o ../bin/gcs-darwin-arm64 .
	@cd bin && if command -v sha256sum >/dev/null 2>&1; then \
		sha256sum gateway-* gcs-* $$(ls bamboo_node.uf2 panda-runtime.tar.gz 2>/dev/null || true) > checksums.sha256; \
	else \
		shasum -a 256 gateway-* gcs-* $$(ls bamboo_node.uf2 panda-runtime.tar.gz 2>/dev/null || true) > checksums.sha256; \
	fi
	@echo "  [OK] Release artifacts generated in bin/:"
	@ls -lh bin/

clean:
	@rm -rf bin/ firmware/build /tmp/neuron_wire_test /tmp/neuron_crc8_robust_test /tmp/test_manchester /tmp/test_bamboo_pio /tmp/neuron_gateway /tmp/bamboo_node_sim
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "  [OK] Clean complete."
