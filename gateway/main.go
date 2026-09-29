package main

import (
	"context"
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/protobuf/proto"

	neuronproto "github.com/matteus8/neuron-cupboard-core/proto"
	neuronv1 "github.com/matteus8/neuron-cupboard-core/proto/gen/go"
)

type RelayConfig struct {
	ZenohRouterEndpoint string
	ListenAddr          string
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
	config    RelayConfig
	publisher ZenohPublisher
}

func NewGatewayRelay(cfg RelayConfig, pub ZenohPublisher) *GatewayRelay {
	return &GatewayRelay{
		config:    cfg,
		publisher: pub,
	}
}

// IngestAndRelayWireFrame takes a 6-byte raw optical wire frame, unpacks it to Protobuf, and publishes it across Zenoh.
func (g *GatewayRelay) IngestAndRelayWireFrame(ctx context.Context, frameBytes []byte) error {
	nowUs := uint64(time.Now().UnixMicro())
	neuronMsg, err := neuronproto.UnpackFrame(frameBytes, nowUs)
	if err != nil {
		fmt.Fprintf(os.Stderr, "level=WARN ts=%d event=frame_decode_failed err=%q\n", nowUs, err)
		return err
	}

	// Serialize Protobuf payload
	protoBytes, err := proto.Marshal(neuronMsg)
	if err != nil {
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

	stateByte := neuronproto.PackState(mode, lock, false, false, false, false)
	var wireFrame [neuronproto.WireFrameLen]byte
	neuronproto.PackFrame(&wireFrame, byte(cmd.TargetNodeId), byte(cmd.CommandSeq), stateByte)

	fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=tactical_command_relayed target=%d cmd=%v wire_crc=0x%02X\n",
		nowUs, cmd.TargetNodeId, cmd.CommandType, wireFrame[5])

	return &wireFrame, nil
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

func main() {
	routerEndpoint := flag.String("zenoh-router", "tcp/127.0.0.1:7447", "Zenoh router peer endpoint")
	listenAddr := flag.String("listen-addr", "127.0.0.1:9090", "Local optical mesh bridge ingest address")
	runOnce := flag.Bool("once", false, "Run single self-test frame and exit")
	flag.Parse()

	cfg := RelayConfig{
		ZenohRouterEndpoint: *routerEndpoint,
		ListenAddr:          *listenAddr,
		PublishTimeout:      50 * time.Millisecond,
	}

	fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=gateway_starting zenoh_router=%s listen_addr=%s\n",
		time.Now().UnixMicro(), cfg.ZenohRouterEndpoint, cfg.ListenAddr)

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

	fmt.Fprintf(os.Stdout, "level=INFO ts=%d event=gateway_ready mode=relay_active\n", time.Now().UnixMicro())
	_ = relay.ListenUDP(ctx)
}

