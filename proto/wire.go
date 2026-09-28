package proto

import (
	"errors"

	neuronv1 "github.com/matteus8/neuron-cupboard-core/proto/gen/go"
)

const (
	Preamble       byte = 0xAA
	SyncWord       byte = 0xD5
	WireFrameLen   int  = 6
	WirePayloadLen int  = 3

	StateModeMask      byte = 0x03
	StateModeShift     uint = 0
	StateLockMask      byte = 0x0C
	StateLockShift     uint = 2
	StateConsensusAck  byte = 0x10
	StateProximityWarn byte = 0x20
	StateSwapCritical  byte = 0x40
	StateSyncMarker    byte = 0x80
)

var (
	ErrInvalidFrameLength = errors.New("invalid wire frame length")
	ErrInvalidPreamble    = errors.New("invalid frame preamble")
	ErrInvalidSyncWord    = errors.New("invalid sync word")
	ErrCrcMismatch        = errors.New("crc8 checksum mismatch")
)

// Crc8Update calculates single-byte CRC-8-CCITT (polynomial 0x07, init 0x00).
func Crc8Update(crc byte, data byte) byte {
	crc ^= data
	for i := 0; i < 8; i++ {
		if (crc & 0x80) != 0 {
			crc = (crc << 1) ^ 0x07
		} else {
			crc = crc << 1
		}
	}
	return crc
}

// Crc8 calculates CRC-8-CCITT over a byte slice.
func Crc8(data []byte) byte {
	var crc byte = 0x00
	for _, b := range data {
		crc = Crc8Update(crc, b)
	}
	return crc
}

// PackState packs discrete state components into an 8-bit discrete state vector.
func PackState(
	mode neuronv1.OperationalMode,
	lock neuronv1.OpticalLockStatus,
	consensusAck bool,
	proximityAlert bool,
	swapCritical bool,
	syncMarker bool,
) byte {
	var state byte
	state |= (byte(mode) & 0x03) << StateModeShift
	state |= (byte(lock) & 0x03) << StateLockShift
	if consensusAck {
		state |= StateConsensusAck
	}
	if proximityAlert {
		state |= StateProximityWarn
	}
	if swapCritical {
		state |= StateSwapCritical
	}
	if syncMarker {
		state |= StateSyncMarker
	}
	return state
}

// UnpackState unpacks an 8-bit discrete state byte into a DiscreteStateVector protobuf message.
func UnpackState(stateByte byte) *neuronv1.DiscreteStateVector {
	modeVal := neuronv1.OperationalMode((stateByte & StateModeMask) >> StateModeShift)
	lockVal := neuronv1.OpticalLockStatus((stateByte & StateLockMask) >> StateLockShift)

	return &neuronv1.DiscreteStateVector{
		RawByte:        uint32(stateByte),
		Mode:           modeVal,
		LockStatus:     lockVal,
		ConsensusAck:   (stateByte & StateConsensusAck) != 0,
		ProximityAlert: (stateByte & StateProximityWarn) != 0,
		SwapCritical:   (stateByte & StateSwapCritical) != 0,
		SyncMarker:     (stateByte & StateSyncMarker) != 0,
	}
}

// PackFrame packs node ID, sequence number, and state byte into a 6-byte wire frame buffer.
func PackFrame(dst *[WireFrameLen]byte, nodeID, seqNum, stateByte byte) {
	dst[0] = Preamble
	dst[1] = SyncWord
	dst[2] = nodeID
	dst[3] = seqNum
	dst[4] = stateByte
	dst[5] = Crc8(dst[2:5])
}

// UnpackFrame validates a 6-byte wire buffer and decodes it into a Protobuf Neuron message.
func UnpackFrame(frame []byte, timestampUs uint64) (*neuronv1.Neuron, error) {
	if len(frame) != WireFrameLen {
		return nil, ErrInvalidFrameLength
	}
	if frame[0] != Preamble {
		return nil, ErrInvalidPreamble
	}
	if frame[1] != SyncWord {
		return nil, ErrInvalidSyncWord
	}

	expectedCrc := Crc8(frame[2:5])
	if frame[5] != expectedCrc {
		return nil, ErrCrcMismatch
	}

	state := UnpackState(frame[4])
	return &neuronv1.Neuron{
		NodeId:      uint32(frame[2]),
		SequenceNum: uint32(frame[3]),
		State:       state,
		Crc8:        uint32(frame[5]),
		TimestampUs: timestampUs,
	}, nil
}
