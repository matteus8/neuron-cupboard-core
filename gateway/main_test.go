package main

import (
	"context"
	"net"
	"testing"
	"time"

	"google.golang.org/protobuf/proto"

	neuronproto "github.com/matteus8/neuron-cupboard-core/proto"
	neuronv1 "github.com/matteus8/neuron-cupboard-core/proto/gen/go"
)

type TestZenohCapture struct {
	CapturedKey     string
	CapturedPayload []byte
}

func (c *TestZenohCapture) Publish(ctx context.Context, key string, payload []byte) error {
	c.CapturedKey = key
	c.CapturedPayload = payload
	return nil
}

func (c *TestZenohCapture) Close() error {
	return nil
}

func TestGatewayRelayWireIngestion(t *testing.T) {
	capture := &TestZenohCapture{}
	cfg := RelayConfig{
		PublishTimeout: 100 * time.Millisecond,
	}
	relay := NewGatewayRelay(cfg, capture)

	var frame [6]byte
	stateByte := neuronproto.PackState(
		neuronv1.OperationalMode_MODE_FORMATION_LOCK,
		neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED,
		true,
		false,
		true,
		false,
	)
	neuronproto.PackFrame(&frame, 42, 100, stateByte)

	err := relay.IngestAndRelayWireFrame(context.Background(), frame[:])
	if err != nil {
		t.Fatalf("expected successful relay, got error: %v", err)
	}

	if capture.CapturedKey != "neuron/mesh/42/state" {
		t.Errorf("expected Zenoh key 'neuron/mesh/42/state', got %s", capture.CapturedKey)
	}

	var decoded neuronv1.Neuron
	if err := proto.Unmarshal(capture.CapturedPayload, &decoded); err != nil {
		t.Fatalf("failed to unmarshal published Protobuf payload: %v", err)
	}

	if decoded.NodeId != 42 {
		t.Errorf("expected NodeId 42, got %d", decoded.NodeId)
	}
	if decoded.SequenceNum != 100 {
		t.Errorf("expected SequenceNum 100, got %d", decoded.SequenceNum)
	}
	if decoded.State.Mode != neuronv1.OperationalMode_MODE_FORMATION_LOCK {
		t.Errorf("expected formation lock mode, got %v", decoded.State.Mode)
	}
	if !decoded.State.ConsensusAck {
		t.Errorf("expected ConsensusAck true")
	}
	if !decoded.State.SwapCritical {
		t.Errorf("expected SwapCritical true")
	}
}

func TestGatewayRelayUDPListener(t *testing.T) {
	capture := &TestZenohCapture{}
	cfg := RelayConfig{
		ListenAddr:     "127.0.0.1:19091", // dedicated test port
		PublishTimeout: 100 * time.Millisecond,
	}
	relay := NewGatewayRelay(cfg, capture)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	serverErrCh := make(chan error, 1)
	go func() {
		serverErrCh <- relay.ListenUDP(ctx)
	}()

	// Wait for listener to bind
	time.Sleep(20 * time.Millisecond)

	var frame [6]byte
	stateByte := neuronproto.PackState(
		neuronv1.OperationalMode_MODE_SEARCH,
		neuronv1.OpticalLockStatus_LOCK_ACQUIRING,
		false,
		true,
		false,
		false,
	)
	neuronproto.PackFrame(&frame, 88, 200, stateByte)

	conn, err := net.Dial("udp", "127.0.0.1:19091")
	if err != nil {
		t.Fatalf("failed to dial UDP listener: %v", err)
	}
	defer conn.Close()

	if _, err := conn.Write(frame[:]); err != nil {
		t.Fatalf("failed to send frame over UDP: %v", err)
	}

	// Wait for processing
	time.Sleep(30 * time.Millisecond)
	cancel()

	if capture.CapturedKey != "neuron/mesh/88/state" {
		t.Errorf("expected Zenoh key 'neuron/mesh/88/state', got %s", capture.CapturedKey)
	}
}

func TestIngestAndRelayTacticalCommand(t *testing.T) {
	capture := &TestZenohCapture{}
	cfg := RelayConfig{}
	relay := NewGatewayRelay(cfg, capture)

	cmd := &neuronv1.SwarmCommand{
		TargetNodeId: 77,
		CommandSeq:   5,
		CommandType:  neuronv1.CommandType_CMD_SET_MODE_DISPERSAL,
		IssuerId:     999,
		IssuedAtUs:   uint64(time.Now().UnixMicro()),
	}

	cmdBytes, err := proto.Marshal(cmd)
	if err != nil {
		t.Fatalf("failed to marshal SwarmCommand: %v", err)
	}

	frame, err := relay.IngestAndRelayTacticalCommand(context.Background(), cmdBytes)
	if err != nil {
		t.Fatalf("failed to relay tactical command: %v", err)
	}

	if frame[0] != neuronproto.Preamble || frame[1] != neuronproto.SyncWord {
		t.Errorf("invalid frame header: %v", frame)
	}
	if frame[2] != 77 {
		t.Errorf("expected target node 77, got %d", frame[2])
	}
	if frame[3] != 5 {
		t.Errorf("expected sequence 5, got %d", frame[3])
	}

	unpacked := neuronproto.UnpackState(frame[4])
	if unpacked.Mode != neuronv1.OperationalMode_MODE_DISPERSAL {
		t.Errorf("expected DISPERSAL mode, got %v", unpacked.Mode)
	}

	expectedCrc := neuronproto.Crc8(frame[2:5])
	if frame[5] != expectedCrc {
		t.Errorf("expected CRC 0x%02X, got 0x%02X", expectedCrc, frame[5])
	}
}


