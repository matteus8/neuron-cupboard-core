package main

import (
	"context"
	"fmt"
	"net"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	neuronproto "github.com/matteus8/neuron-cupboard-core/proto"
	neuronv1 "github.com/matteus8/neuron-cupboard-core/proto/gen/go"
)

type ConcurrentZenohCounter struct {
	Count int64
}

func (c *ConcurrentZenohCounter) Publish(ctx context.Context, key string, payload []byte) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
		atomic.AddInt64(&c.Count, 1)
		return nil
	}
}

func (c *ConcurrentZenohCounter) Close() error {
	return nil
}

// BenchmarkIngestAndRelayWireFrame measures throughput and allocations per frame ingestion.
func BenchmarkIngestAndRelayWireFrame(b *testing.B) {
	counter := &ConcurrentZenohCounter{}
	cfg := RelayConfig{
		PublishTimeout: 50 * time.Millisecond,
	}
	relay := NewGatewayRelay(cfg, counter)
	ctx := context.Background()

	var frame [6]byte
	stateByte := neuronproto.PackState(
		neuronv1.OperationalMode_MODE_FORMATION_LOCK,
		neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED,
		true,
		false,
		false,
		false,
	)
	neuronproto.PackFrame(&frame, 42, 1, stateByte)

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		_ = relay.IngestAndRelayWireFrame(ctx, frame[:])
	}
}

// TestConcurrentIngestionStress launches multiple goroutines blasting wire frames to verify race safety.
func TestConcurrentIngestionStress(t *testing.T) {
	counter := &ConcurrentZenohCounter{}
	cfg := RelayConfig{
		PublishTimeout: 100 * time.Millisecond,
	}
	relay := NewGatewayRelay(cfg, counter)
	ctx := context.Background()

	var frame [6]byte
	stateByte := neuronproto.PackState(
		neuronv1.OperationalMode_MODE_FORMATION_LOCK,
		neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED,
		true,
		false,
		false,
		false,
	)
	neuronproto.PackFrame(&frame, 15, 10, stateByte)

	const goroutines = 10
	const iterationsPerGoroutine = 500
	var wg sync.WaitGroup
	wg.Add(goroutines)

	for g := 0; g < goroutines; g++ {
		go func(gID int) {
			defer wg.Done()
			for i := 0; i < iterationsPerGoroutine; i++ {
				err := relay.IngestAndRelayWireFrame(ctx, frame[:])
				if err != nil {
					t.Errorf("goroutine %d failed frame ingestion: %v", gID, err)
				}
			}
		}(g)
	}

	wg.Wait()

	expected := int64(goroutines * iterationsPerGoroutine)
	if atomic.LoadInt64(&counter.Count) != expected {
		t.Errorf("expected %d published frames, got %d", expected, counter.Count)
	}
}

// TestUDPFloodSoak floods 1,000 UDP frames into the gateway listener.
func TestUDPFloodSoak(t *testing.T) {
	counter := &ConcurrentZenohCounter{}
	cfg := RelayConfig{
		ListenAddr:     "127.0.0.1:19095",
		PublishTimeout: 50 * time.Millisecond,
	}
	relay := NewGatewayRelay(cfg, counter)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		_ = relay.ListenUDP(ctx)
	}()

	time.Sleep(20 * time.Millisecond)

	conn, err := net.Dial("udp", "127.0.0.1:19095")
	if err != nil {
		t.Fatalf("failed to dial UDP listener: %v", err)
	}
	defer conn.Close()

	var frame [6]byte
	stateByte := neuronproto.PackState(
		neuronv1.OperationalMode_MODE_SEARCH,
		neuronv1.OpticalLockStatus_LOCK_BEARING_TRACKING,
		true,
		false,
		false,
		false,
	)
	neuronproto.PackFrame(&frame, 33, 1, stateByte)

	const floodCount = 1000
	for i := 0; i < floodCount; i++ {
		_, _ = conn.Write(frame[:])
	}

	time.Sleep(100 * time.Millisecond)
	cancel()

	totalPublished := atomic.LoadInt64(&counter.Count)
	if totalPublished == 0 {
		t.Errorf("expected frames published from UDP flood, got 0")
	}
	fmt.Printf("INFO: UDP flood soak successfully processed %d / %d frames\n", totalPublished, floodCount)
}
