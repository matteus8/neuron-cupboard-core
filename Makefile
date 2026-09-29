.PHONY: all proto test build clean test-proto test-firmware test-runtime test-gateway

CC ?= cc
CFLAGS ?= -Wall -Wextra -Werror -std=c99 -O2

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

test-sim:
	@echo "==> Running End-to-End Multi-Node Optical Swarm Simulation..."
	@PYTHONPATH=. python3 scripts/simulate_swarm.py

bench:
	@echo "==> Running Gateway Throughput and Allocation Benchmarks..."
	@cd gateway && go test -bench=. -benchmem -run=^$$ ./...

test: test-proto test-firmware test-runtime test-gateway test-sim
	@echo "==> All subsystem and end-to-end simulation tests passed successfully."

build:
	@echo "==> Building Gateway..."
	@mkdir -p bin
	@cd gateway && go build -o ../bin/gateway .
	@echo "  [OK] bin/gateway created"

clean:
	@rm -rf bin/ /tmp/neuron_wire_test /tmp/neuron_crc8_robust_test /tmp/test_manchester /tmp/test_bamboo_pio /tmp/neuron_gateway
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "  [OK] Clean complete."
