package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"google.golang.org/protobuf/proto"

	neuronproto "github.com/matteus8/neuron-cupboard-core/proto"
	neuronv1 "github.com/matteus8/neuron-cupboard-core/proto/gen/go"
)

type RelayConfig struct {
	ZenohRouterEndpoint string
	ListenAddr          string
	MetricsAddr         string
	PublishTimeout      time.Duration
}

// ZenohPublisher abstracts tactical network publication.
type ZenohPublisher interface {
	Publish(ctx context.Context, key string, payload []byte) error
	Close() error
}

// StdoutZenohMock implements ZenohPublisher for headless tactical demonstration without external daemon.
type StdoutZenohMock struct{}

func (m *StdoutZenohMock) Publish(ctx context.Context, key string, payload []byte) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
		// Headless structured key-value log output
		fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=zenoh_publish key=%s bytes=%d\n",
			time.Now().UnixMicro(), key, len(payload))
		return nil
	}
}

func (m *StdoutZenohMock) Close() error {
	return nil
}

// GatewayRelay translates raw optical mesh frames into serialized Protobuf packets and dispatches to Zenoh.
type GatewayRelay struct {
	config          RelayConfig
	publisher       ZenohPublisher
	framesIngested  int64
	framesInvalid   int64
	commandsRelayed int64
	startTime       time.Time
}

func NewGatewayRelay(cfg RelayConfig, pub ZenohPublisher) *GatewayRelay {
	return &GatewayRelay{
		config:    cfg,
		publisher: pub,
		startTime: time.Now(),
	}
}

// IngestAndRelayWireFrame takes a 6-byte raw optical wire frame, unpacks it to Protobuf, and publishes it across Zenoh.
func (g *GatewayRelay) IngestAndRelayWireFrame(ctx context.Context, frameBytes []byte) error {
	nowUs := uint64(time.Now().UnixMicro())
	neuronMsg, err := neuronproto.UnpackFrame(frameBytes, nowUs)
	if err != nil {
		atomic.AddInt64(&g.framesInvalid, 1)
		fmt.Fprintf(os.Stderr, "level=WARN ts=%d event=frame_decode_failed err=%q\n", nowUs, err)
		return err
	}

	// Serialize Protobuf payload
	protoBytes, err := proto.Marshal(neuronMsg)
	if err != nil {
		atomic.AddInt64(&g.framesInvalid, 1)
		fmt.Fprintf(os.Stderr, "level=ERROR ts=%d event=proto_marshal_failed err=%q\n", nowUs, err)
		return err
	}

	// Form tactical network Zenoh key expression
	zenohKey := fmt.Sprintf("neuron/mesh/%d/state", neuronMsg.NodeId)

	pubCtx, cancel := context.WithTimeout(ctx, g.config.PublishTimeout)
	defer cancel()

	if err := g.publisher.Publish(pubCtx, zenohKey, protoBytes); err != nil {
		fmt.Fprintf(os.Stderr, "level=ERROR ts=%d event=zenoh_publish_failed key=%s err=%q\n", nowUs, zenohKey, err)
		return err
	}

	atomic.AddInt64(&g.framesIngested, 1)
	return nil
}

// IngestAndRelayTacticalCommand unmarshals an external SwarmCommand Protobuf and formats a 6-byte optical frame.
func (g *GatewayRelay) IngestAndRelayTacticalCommand(ctx context.Context, cmdBytes []byte) (*[neuronproto.WireFrameLen]byte, error) {
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	var cmd neuronv1.SwarmCommand
	if err := proto.Unmarshal(cmdBytes, &cmd); err != nil {
		return nil, fmt.Errorf("failed to unmarshal SwarmCommand: %w", err)
	}

	nowUs := uint64(time.Now().UnixMicro())
	var mode neuronv1.OperationalMode
	var lock neuronv1.OpticalLockStatus = neuronv1.OpticalLockStatus_LOCK_NONE

	switch cmd.CommandType {
	case neuronv1.CommandType_CMD_SET_MODE_SEARCH:
		mode = neuronv1.OperationalMode_MODE_SEARCH
	case neuronv1.CommandType_CMD_SET_MODE_FORMATION:
		mode = neuronv1.OperationalMode_MODE_FORMATION_LOCK
		lock = neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED
	case neuronv1.CommandType_CMD_SET_MODE_DISPERSAL:
		mode = neuronv1.OperationalMode_MODE_DISPERSAL
	case neuronv1.CommandType_CMD_EMISSION_SILENCE:
		mode = neuronv1.OperationalMode_MODE_UNSPECIFIED
	default:
		mode = neuronv1.OperationalMode_MODE_SEARCH
	}

	if cmd.TargetNodeId > 255 || cmd.CommandSeq > 255 {
		return nil, fmt.Errorf("node ID or command sequence exceeds 8-bit wire bounds: target=%d seq=%d", cmd.TargetNodeId, cmd.CommandSeq)
	}

	stateByte := neuronproto.PackState(mode, lock, false, false, false, false)
	var wireFrame [neuronproto.WireFrameLen]byte
	neuronproto.PackFrame(&wireFrame, uint8(cmd.TargetNodeId), uint8(cmd.CommandSeq), stateByte)

	atomic.AddInt64(&g.commandsRelayed, 1)
	fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=tactical_command_relayed target=%d cmd=%v wire_crc=0x%02X\n",
		nowUs, cmd.TargetNodeId, cmd.CommandType, wireFrame[5])

	return &wireFrame, nil
}

// StartMetricsServer serves HTTP healthz and Prometheus telemetry endpoints.
func (g *GatewayRelay) StartMetricsServer(ctx context.Context) {
	if g.config.MetricsAddr == "" {
		return
	}

	mux := http.NewServeMux()

	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		status := map[string]interface{}{
			"status":           "UP",
			"uptime_seconds":   int64(time.Since(g.startTime).Seconds()),
			"frames_ingested":  atomic.LoadInt64(&g.framesIngested),
			"frames_invalid":   atomic.LoadInt64(&g.framesInvalid),
			"commands_relayed": atomic.LoadInt64(&g.commandsRelayed),
		}
		_ = json.NewEncoder(w).Encode(status)
	})

	mux.HandleFunc("/metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		fmt.Fprintf(w, "# HELP neuron_gateway_frames_ingested_total Total optical frames ingested\n")
		fmt.Fprintf(w, "# TYPE neuron_gateway_frames_ingested_total counter\n")
		fmt.Fprintf(w, "neuron_gateway_frames_ingested_total %d\n", atomic.LoadInt64(&g.framesIngested))

		fmt.Fprintf(w, "# HELP neuron_gateway_frames_invalid_total Total invalid optical frames dropped\n")
		fmt.Fprintf(w, "# TYPE neuron_gateway_frames_invalid_total counter\n")
		fmt.Fprintf(w, "neuron_gateway_frames_invalid_total %d\n", atomic.LoadInt64(&g.framesInvalid))

		fmt.Fprintf(w, "# HELP neuron_gateway_commands_relayed_total Total tactical commands relayed\n")
		fmt.Fprintf(w, "# TYPE neuron_gateway_commands_relayed_total counter\n")
		fmt.Fprintf(w, "neuron_gateway_commands_relayed_total %d\n", atomic.LoadInt64(&g.commandsRelayed))

		fmt.Fprintf(w, "# HELP neuron_gateway_uptime_seconds Total process uptime in seconds\n")
		fmt.Fprintf(w, "# TYPE neuron_gateway_uptime_seconds gauge\n")
		fmt.Fprintf(w, "neuron_gateway_uptime_seconds %d\n", int64(time.Since(g.startTime).Seconds()))
	})

	server := &http.Server{
		Addr:              g.config.MetricsAddr,
		Handler:           mux,
		ReadHeaderTimeout: 3 * time.Second,
	}

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), time.Second)
		defer cancel()
		_ = server.Shutdown(shutdownCtx)
	}()

	fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=metrics_server_started addr=%s\n",
		time.Now().UnixMicro(), g.config.MetricsAddr)
	_ = server.ListenAndServe()
}

// ListenUDP runs a bounded-latency UDP server ingesting 6-byte optical frames.
func (g *GatewayRelay) ListenUDP(ctx context.Context) error {
	addr, err := net.ResolveUDPAddr("udp", g.config.ListenAddr)
	if err != nil {
		return err
	}

	conn, err := net.ListenUDP("udp", addr)
	if err != nil {
		return err
	}
	defer conn.Close()

	fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=udp_listener_started addr=%s\n",
		time.Now().UnixMicro(), g.config.ListenAddr)

	buf := make([]byte, 64)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
			// 100ms deadline to remain non-blocking and check context
			_ = conn.SetReadDeadline(time.Now().Add(100 * time.Millisecond))
			n, _, err := conn.ReadFrom(buf)
			if err != nil {
				if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
					continue
				}
				if ctx.Err() != nil {
					return ctx.Err()
				}
				continue
			}

			if n == neuronproto.WireFrameLen {
				_ = g.IngestAndRelayWireFrame(ctx, buf[:n])
			}
		}
	}
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

func main() {
	routerEndpoint := flag.String("zenoh-router", getEnv("NEURON_ZENOH_ROUTER", "tcp/127.0.0.1:7447"), "Zenoh router peer endpoint")
	listenAddr := flag.String("listen-addr", getEnv("NEURON_LISTEN_ADDR", "127.0.0.1:9090"), "Local optical mesh bridge ingest address")
	metricsAddr := flag.String("metrics-addr", getEnv("NEURON_METRICS_ADDR", "127.0.0.1:9093"), "HTTP health and metrics listen address")
	runOnce := flag.Bool("once", false, "Run single self-test frame and exit")
	flag.Parse()

	cfg := RelayConfig{
		ZenohRouterEndpoint: *routerEndpoint,
		ListenAddr:          *listenAddr,
		MetricsAddr:         *metricsAddr,
		PublishTimeout:      50 * time.Millisecond,
	}

	fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=gateway_starting zenoh_router=%s listen_addr=%s metrics_addr=%s\n",
		time.Now().UnixMicro(), cfg.ZenohRouterEndpoint, cfg.ListenAddr, cfg.MetricsAddr)

	publisher := &StdoutZenohMock{}
	relay := NewGatewayRelay(cfg, publisher)

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	if *runOnce {
		var testFrame [6]byte
		stateByte := neuronproto.PackState(
			neuronv1.OperationalMode_MODE_FORMATION_LOCK,
			neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED,
			true,
			false,
			false,
			false,
		)
		neuronproto.PackFrame(&testFrame, 1, 101, stateByte)
		_ = relay.IngestAndRelayWireFrame(ctx, testFrame[:])
		fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=gateway_ready mode=self_test_complete\n", time.Now().UnixMicro())
		return
	}

	go relay.StartMetricsServer(ctx)

	fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=gateway_ready mode=relay_active\n", time.Now().UnixMicro())
	_ = relay.ListenUDP(ctx)
}

