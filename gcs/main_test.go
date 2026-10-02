package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	neuronproto "github.com/matteus8/neuron-cupboard-core/proto"
	neuronv1 "github.com/matteus8/neuron-cupboard-core/proto/gen/go"
)

func TestSwarmMonitorIngestAndSnapshot(t *testing.T) {
	monitor := NewSwarmMonitor()

	neuron := &neuronv1.Neuron{
		NodeId:      42,
		SequenceNum: 10,
		State: &neuronv1.DiscreteStateVector{
			Mode:           neuronv1.OperationalMode_MODE_FORMATION_LOCK,
			LockStatus:     neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED,
			ConsensusAck:   true,
			ProximityAlert: false,
			SwapCritical:   false,
		},
		Bearing: &neuronv1.OpticalBearing{
			AzimuthMrad:   -120,
			ElevationMrad: 45,
		},
		Crc8:        0xF8,
		TimestampUs: uint64(time.Now().UnixMicro()),
	}

	monitor.IngestNeuron(neuron)
	snap := monitor.Snapshot()

	if len(snap.ActiveNodes) != 1 {
		t.Fatalf("expected 1 active node, got %d", len(snap.ActiveNodes))
	}

	node := snap.ActiveNodes[0]
	if node.NodeId != 42 {
		t.Errorf("expected node ID 42, got %d", node.NodeId)
	}
	if node.Mode != "MODE_FORMATION_LOCK" {
		t.Errorf("expected MODE_FORMATION_LOCK, got %s", node.Mode)
	}
	if node.AzimuthMrad != -120 {
		t.Errorf("expected azimuth -120, got %d", node.AzimuthMrad)
	}
	if snap.Stats.TotalFrames != 1 {
		t.Errorf("expected total frames 1, got %d", snap.Stats.TotalFrames)
	}
	if len(snap.RecentPackets) != 1 {
		t.Errorf("expected 1 recent packet, got %d", len(snap.RecentPackets))
	}
}

func TestGCSHttpEndpoints(t *testing.T) {
	server := NewGCSServer(":0", ":0", ":0", false)

	// Ingest a test packet
	server.monitor.IngestNeuron(&neuronv1.Neuron{
		NodeId:      7,
		SequenceNum: 1,
		State: &neuronv1.DiscreteStateVector{
			Mode:       neuronv1.OperationalMode_MODE_SEARCH,
			LockStatus: neuronv1.OpticalLockStatus_LOCK_NONE,
		},
		Crc8: 0x12,
	})

	// 1. Test GET / (HTML Dashboard)
	reqIndex := httptest.NewRequest(http.MethodGet, "/", nil)
	recIndex := httptest.NewRecorder()
	server.HandleIndex(recIndex, reqIndex)

	if recIndex.Code != http.StatusOK {
		t.Fatalf("expected status 200 for index, got %d", recIndex.Code)
	}
	if !bytes.Contains(recIndex.Body.Bytes(), []byte("Bamboo Node")) {
		t.Errorf("index HTML does not contain expected title")
	}

	// 2. Test GET /api/state
	reqState := httptest.NewRequest(http.MethodGet, "/api/state", nil)
	recState := httptest.NewRecorder()
	server.HandleState(recState, reqState)

	if recState.Code != http.StatusOK {
		t.Fatalf("expected status 200 for state, got %d", recState.Code)
	}
	var stateResp SwarmState
	if err := json.Unmarshal(recState.Body.Bytes(), &stateResp); err != nil {
		t.Fatalf("failed to parse state json: %v", err)
	}
	if len(stateResp.ActiveNodes) != 1 || stateResp.ActiveNodes[0].NodeId != 7 {
		t.Errorf("unexpected active nodes in state: %+v", stateResp.ActiveNodes)
	}

	// 3. Test GET /healthz
	reqHealth := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	recHealth := httptest.NewRecorder()
	server.HandleHealthz(recHealth, reqHealth)

	if recHealth.Code != http.StatusOK {
		t.Fatalf("expected status 200 for healthz, got %d", recHealth.Code)
	}

	// 4. Test POST /api/command
	cmdPayload := []byte(`{"target_node_id": 2, "command_type": 2}`)
	reqCmd := httptest.NewRequest(http.MethodPost, "/api/command", bytes.NewReader(cmdPayload))
	recCmd := httptest.NewRecorder()
	server.HandleCommand(recCmd, reqCmd)

	if recCmd.Code != http.StatusOK {
		t.Fatalf("expected status 200 for command, got %d: %s", recCmd.Code, recCmd.Body.String())
	}
}

func TestGCSListenUDPIngest(t *testing.T) {
	server := NewGCSServer("127.0.0.1:0", "127.0.0.1:19098", "127.0.0.1:0", false)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		_ = server.ListenUDP(ctx)
	}()

	time.Sleep(50 * time.Millisecond) // Allow UDP listener to bind

	// Format a valid 6-byte optical frame
	var frame [6]byte
	stateByte := neuronproto.PackState(
		neuronv1.OperationalMode_MODE_FORMATION_LOCK,
		neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED,
		true,
		false,
		false,
		false,
	)
	neuronproto.PackFrame(&frame, 99, 15, stateByte)

	conn, err := net.Dial("udp", "127.0.0.1:19098")
	if err != nil {
		t.Fatalf("failed to dial UDP listener: %v", err)
	}
	defer conn.Close()

	if _, err := conn.Write(frame[:]); err != nil {
		t.Fatalf("failed to send test optical frame: %v", err)
	}

	// Wait briefly for ingest
	time.Sleep(80 * time.Millisecond)

	snap := server.monitor.Snapshot()
	if len(snap.ActiveNodes) != 1 {
		t.Fatalf("expected 1 active node from UDP ingest, got %d", len(snap.ActiveNodes))
	}
	if snap.ActiveNodes[0].NodeId != 99 {
		t.Errorf("expected node ID 99, got %d", snap.ActiveNodes[0].NodeId)
	}
}
