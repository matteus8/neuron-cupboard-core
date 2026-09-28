package proto

import (
	"testing"

	neuronv1 "github.com/matteus8/neuron-cupboard-core/proto/gen/go"
)

func TestPackUnpackStateParity(t *testing.T) {
	packed := PackState(
		neuronv1.OperationalMode_MODE_FORMATION_LOCK,
		neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED,
		true,
		false,
		true,
		false,
	)

	// Mode 2 (0b10) | Lock 3 (0b1100 = 0x0C) | ACK (0x10) | SWaP (0x40) = 0x5E
	if packed != 0x5E {
		t.Fatalf("expected packed state 0x5E, got 0x%02X", packed)
	}

	state := UnpackState(packed)
	if state.Mode != neuronv1.OperationalMode_MODE_FORMATION_LOCK {
		t.Errorf("mode mismatch: got %v", state.Mode)
	}
	if state.LockStatus != neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED {
		t.Errorf("lock status mismatch: got %v", state.LockStatus)
	}
	if !state.ConsensusAck {
		t.Errorf("expected ConsensusAck true")
	}
	if state.ProximityAlert {
		t.Errorf("expected ProximityAlert false")
	}
	if !state.SwapCritical {
		t.Errorf("expected SwapCritical true")
	}
	if state.SyncMarker {
		t.Errorf("expected SyncMarker false")
	}
}

func TestWireFrameEncodingDecoding(t *testing.T) {
	var frameBuf [WireFrameLen]byte
	stateByte := PackState(
		neuronv1.OperationalMode_MODE_FORMATION_LOCK,
		neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED,
		true,
		false,
		true,
		false,
	)

	PackFrame(&frameBuf, 42, 100, stateByte)

	if frameBuf[0] != Preamble || frameBuf[1] != SyncWord {
		t.Fatalf("invalid preamble/sync in packed frame: %v", frameBuf)
	}
	if frameBuf[5] != 0xF8 {
		t.Fatalf("expected CRC 0xF8, got 0x%02X", frameBuf[5])
	}

	neuron, err := UnpackFrame(frameBuf[:], 123456789)
	if err != nil {
		t.Fatalf("failed to unpack valid frame: %v", err)
	}
	if neuron.NodeId != 42 {
		t.Errorf("expected node ID 42, got %d", neuron.NodeId)
	}
	if neuron.SequenceNum != 100 {
		t.Errorf("expected sequence num 100, got %d", neuron.SequenceNum)
	}
	if neuron.State.RawByte != uint32(stateByte) {
		t.Errorf("expected raw byte %d, got %d", stateByte, neuron.State.RawByte)
	}
	if neuron.TimestampUs != 123456789 {
		t.Errorf("expected timestamp 123456789, got %d", neuron.TimestampUs)
	}

	// Corrupt frame
	frameBuf[4] ^= 0x01
	_, err = UnpackFrame(frameBuf[:], 123456789)
	if err != ErrCrcMismatch {
		t.Fatalf("expected ErrCrcMismatch on corrupted frame, got %v", err)
	}
}
