package main

import (
	"context"
	_ "embed"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"net"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"google.golang.org/protobuf/proto"

	neuronproto "github.com/matteus8/neuron-cupboard-core/proto"
	neuronv1 "github.com/matteus8/neuron-cupboard-core/proto/gen/go"
)

//go:embed web/index.html
var indexHTML []byte

type NodeSnapshot struct {
	NodeId         uint32 `json:"node_id"`
	SequenceNum    uint32 `json:"sequence_num"`
	Mode           string `json:"mode"`
	LockStatus     string `json:"lock_status"`
	ConsensusAck   bool   `json:"consensus_ack"`
	ProximityAlert bool   `json:"proximity_alert"`
	SwapCritical   bool   `json:"swap_critical"`
	AzimuthMrad    int32  `json:"azimuth_mrad"`
	ElevationMrad  int32  `json:"elevation_mrad"`
	Crc8           uint32 `json:"crc8"`
	LastSeenMs     int64  `json:"last_seen_ms"`
}

type SwarmEvent struct {
	Time    string `json:"time"`
	NodeId  uint32 `json:"node_id"`
	Level   string `json:"level"` // "INFO", "LOCK", "WARN"
	Message string `json:"message"`
}

type LatestPulse struct {
	Time        string `json:"time"`
	NodeId      uint32 `json:"node_id"`
	SequenceNum uint32 `json:"sequence_num"`
	Mode        string `json:"mode"`
	LockStatus  string `json:"lock_status"`
	AzimuthMrad int32  `json:"azimuth_mrad"`
	Crc8        uint32 `json:"crc8"`
}

type SwarmStats struct {
	TotalFrames  int64   `json:"total_frames"`
	PacketRateHz float64 `json:"packet_rate_hz"`
}

type SwarmState struct {
	ActiveNodes []NodeSnapshot `json:"active_nodes"`
	Stats       SwarmStats     `json:"stats"`
	Events      []SwarmEvent   `json:"events"`
	LatestPulse *LatestPulse   `json:"latest_pulse,omitempty"`
}

type SwarmMonitor struct {
	mu           sync.Mutex
	nodes        map[uint32]*NodeSnapshot
	events       []SwarmEvent
	latestPulse  *LatestPulse
	totalFrames  int64
	lastFrameSec int64
	framesInSec  int64
	currentRate  float64
	maxEvents    int
}

func NewSwarmMonitor() *SwarmMonitor {
	return &SwarmMonitor{
		nodes:     make(map[uint32]*NodeSnapshot),
		events:    make([]SwarmEvent, 0, 20),
		maxEvents: 8,
	}
}

func cleanLabel(s string) string {
	if len(s) > 5 && s[:5] == "MODE_" {
		return s[5:]
	}
	if len(s) > 5 && s[:5] == "LOCK_" {
		return s[5:]
	}
	return s
}

func (m *SwarmMonitor) addEventLocked(evt SwarmEvent) {
	m.events = append([]SwarmEvent{evt}, m.events...)
	if len(m.events) > m.maxEvents {
		m.events = m.events[:m.maxEvents]
	}
}

func (m *SwarmMonitor) IngestNeuron(n *neuronv1.Neuron) {
	m.mu.Lock()
	defer m.mu.Unlock()

	now := time.Now()
	nowMs := now.UnixMilli()
	nowSec := now.Unix()

	m.totalFrames++
	if nowSec == m.lastFrameSec {
		m.framesInSec++
	} else {
		if m.lastFrameSec > 0 {
			m.currentRate = float64(m.framesInSec)
		}
		m.lastFrameSec = nowSec
		m.framesInSec = 1
	}

	modeStr := "MODE_SEARCH"
	lockStr := "LOCK_NONE"
	var ack, prox, swap bool

	if n.State != nil {
		modeStr = n.State.Mode.String()
		lockStr = n.State.LockStatus.String()
		ack = n.State.ConsensusAck
		prox = n.State.ProximityAlert
		swap = n.State.SwapCritical
	}

	var az, el int32
	if n.Bearing != nil {
		az = n.Bearing.AzimuthMrad
		el = n.Bearing.ElevationMrad
	}

	timeStr := now.Format("15:04:05")

	prev, exists := m.nodes[n.NodeId]
	if !exists {
		m.addEventLocked(SwarmEvent{
			Time:    timeStr,
			NodeId:  n.NodeId,
			Level:   "INFO",
			Message: "Optical line-of-sight acquired",
		})
	} else {
		if prev.Mode != modeStr {
			m.addEventLocked(SwarmEvent{
				Time:    timeStr,
				NodeId:  n.NodeId,
				Level:   "INFO",
				Message: fmt.Sprintf("Operational mode -> %s", cleanLabel(modeStr)),
			})
		}
		if prev.LockStatus != lockStr {
			lvl := "INFO"
			if lockStr == "LOCK_HARD_LOCKED" {
				lvl = "LOCK"
			}
			m.addEventLocked(SwarmEvent{
				Time:    timeStr,
				NodeId:  n.NodeId,
				Level:   lvl,
				Message: fmt.Sprintf("Optical lock -> %s", cleanLabel(lockStr)),
			})
		}
		if !prev.ProximityAlert && prox {
			m.addEventLocked(SwarmEvent{
				Time:    timeStr,
				NodeId:  n.NodeId,
				Level:   "WARN",
				Message: "Proximity alert flag active",
			})
		}
	}

	m.nodes[n.NodeId] = &NodeSnapshot{
		NodeId:         n.NodeId,
		SequenceNum:    n.SequenceNum,
		Mode:           modeStr,
		LockStatus:     lockStr,
		ConsensusAck:   ack,
		ProximityAlert: prox,
		SwapCritical:   swap,
		AzimuthMrad:    az,
		ElevationMrad:  el,
		Crc8:           n.Crc8,
		LastSeenMs:     nowMs,
	}

	m.latestPulse = &LatestPulse{
		Time:        now.Format("15:04:05.000"),
		NodeId:      n.NodeId,
		SequenceNum: n.SequenceNum,
		Mode:        modeStr,
		LockStatus:  lockStr,
		AzimuthMrad: az,
		Crc8:        n.Crc8,
	}
}

func (m *SwarmMonitor) Snapshot() SwarmState {
	m.mu.Lock()
	defer m.mu.Unlock()

	nowMs := time.Now().UnixMilli()
	active := make([]NodeSnapshot, 0, len(m.nodes))

	for id, n := range m.nodes {
		if nowMs-n.LastSeenMs < 5000 {
			active = append(active, *n)
		} else {
			delete(m.nodes, id)
			m.addEventLocked(SwarmEvent{
				Time:    time.Now().Format("15:04:05"),
				NodeId:  id,
				Level:   "WARN",
				Message: "Optical line-of-sight lost (timeout)",
			})
		}
	}

	events := make([]SwarmEvent, len(m.events))
	copy(events, m.events)

	var latest *LatestPulse
	if m.latestPulse != nil {
		lpCopy := *m.latestPulse
		latest = &lpCopy
	}

	return SwarmState{
		ActiveNodes: active,
		Stats: SwarmStats{
			TotalFrames:  m.totalFrames,
			PacketRateHz: m.currentRate,
		},
		Events:      events,
		LatestPulse: latest,
	}
}

type GCSServer struct {
	monitor        *SwarmMonitor
	httpAddr       string
	listenAddr     string
	gatewayCmdAddr string
	demoMode       bool
	framesIngested int64
}

func NewGCSServer(httpAddr, listenAddr, gatewayCmdAddr string, demo bool) *GCSServer {
	return &GCSServer{
		monitor:        NewSwarmMonitor(),
		httpAddr:       httpAddr,
		listenAddr:     listenAddr,
		gatewayCmdAddr: gatewayCmdAddr,
		demoMode:       demo,
	}
}

func (s *GCSServer) HandleIndex(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write(indexHTML)
}

func (s *GCSServer) HandleState(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(s.monitor.Snapshot())
}

func (s *GCSServer) HandleEvents(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming unsupported", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	ticker := time.NewTicker(250 * time.Millisecond) // Calm 4 Hz refresh rate
	defer ticker.Stop()

	for {
		select {
		case <-r.Context().Done():
			return
		case <-ticker.C:
			snapshot := s.monitor.Snapshot()
			data, err := json.Marshal(snapshot)
			if err != nil {
				continue
			}
			_, _ = fmt.Fprintf(w, "data: %s\n\n", data)
			flusher.Flush()
		}
	}
}

func (s *GCSServer) HandleCommand(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		TargetNodeId uint32 `json:"target_node_id"`
		CommandType  int32  `json:"command_type"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	if req.CommandType < 0 || req.CommandType > 4 {
		http.Error(w, "invalid command type", http.StatusBadRequest)
		return
	}

	cmd := &neuronv1.SwarmCommand{
		TargetNodeId: req.TargetNodeId,
		CommandSeq:   1,
		CommandType:  neuronv1.CommandType(req.CommandType),
		IssuerId:     99, // GCS ID
		IssuedAtUs:   uint64(time.Now().UnixMicro()),
	}

	data, err := proto.Marshal(cmd)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Dispatch command over UDP to Gateway if reachable
	if s.gatewayCmdAddr != "" {
		if rAddr, err := net.ResolveUDPAddr("udp", s.gatewayCmdAddr); err == nil {
			if conn, err := net.DialUDP("udp", nil, rAddr); err == nil {
				defer conn.Close()
				_, _ = conn.Write(data)
			}
		}
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "DISPATCHED",
		"command": cmd.CommandType.String(),
		"target":  cmd.TargetNodeId,
	})
}

func (s *GCSServer) HandleHealthz(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"status":          "UP",
		"frames_ingested": atomic.LoadInt64(&s.framesIngested),
	})
}

// ListenUDP ingests 6-byte optical frames directly from local network.
func (s *GCSServer) ListenUDP(ctx context.Context) error {
	addr, err := net.ResolveUDPAddr("udp", s.listenAddr)
	if err != nil {
		return err
	}

	conn, err := net.ListenUDP("udp", addr)
	if err != nil {
		return err
	}
	defer conn.Close()

	fmt.Fprintf(os.Stdout, "level=INFO event=gcs_udp_listener_active addr=%s\n", s.listenAddr)
	buf := make([]byte, 64)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
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
				nowUs := uint64(time.Now().UnixMicro())
				neuronMsg, err := neuronproto.UnpackFrame(buf[:n], nowUs)
				if err == nil {
					atomic.AddInt64(&s.framesIngested, 1)
					s.monitor.IngestNeuron(neuronMsg)
				}
			}
		}
	}
}

// RunDemoEngine generates simulated optical swarm telemetry for testing and demos.
func (s *GCSServer) RunDemoEngine(ctx context.Context) {
	fmt.Fprintf(os.Stdout, "level=INFO event=gcs_demo_engine_active status=simulating_optical_swarm\n")
	ticker := time.NewTicker(100 * time.Millisecond) // Calm 10 Hz frame rate
	defer ticker.Stop()

	var seq uint32 = 0
	var t float64 = 0

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			seq++
			t += 0.1
			nowUs := uint64(time.Now().UnixMicro())

			// Node 1: Primary Emitter at boresight (Formation Lock)
			s.monitor.IngestNeuron(&neuronv1.Neuron{
				NodeId:      1,
				SequenceNum: seq,
				State: &neuronv1.DiscreteStateVector{
					Mode:           neuronv1.OperationalMode_MODE_FORMATION_LOCK,
					LockStatus:     neuronv1.OpticalLockStatus_LOCK_HARD_LOCKED,
					ConsensusAck:   true,
					ProximityAlert: false,
					SwapCritical:   false,
				},
				Bearing: &neuronv1.OpticalBearing{
					AzimuthMrad:   int32(math.Sin(t*0.2) * 25.0),
					ElevationMrad: 10,
				},
				Crc8:        0xF8,
				TimestampUs: nowUs,
			})

			// Node 2: Wingman (Formation Lock)
			s.monitor.IngestNeuron(&neuronv1.Neuron{
				NodeId:      2,
				SequenceNum: seq,
				State: &neuronv1.DiscreteStateVector{
					Mode:           neuronv1.OperationalMode_MODE_FORMATION_LOCK,
					LockStatus:     neuronv1.OpticalLockStatus_LOCK_BEARING_TRACKING,
					ConsensusAck:   true,
					ProximityAlert: false,
					SwapCritical:   false,
				},
				Bearing: &neuronv1.OpticalBearing{
					AzimuthMrad:   180 + int32(math.Cos(t*0.1)*15.0),
					ElevationMrad: -5,
				},
				Crc8:        0x8C,
				TimestampUs: nowUs,
			})
		}
	}
}

func main() {
	httpAddr := flag.String("http-addr", "0.0.0.0:8080", "Tactical GCS web dashboard HTTP address")
	listenAddr := flag.String("listen-addr", "0.0.0.0:9092", "Optical frame UDP ingest address")
	gatewayCmdAddr := flag.String("gateway-cmd", "127.0.0.1:9090", "Tactical Gateway UDP command address")
	demo := flag.Bool("demo", false, "Run in demo mode simulating multi-node optical telemetry")
	flag.Parse()

	server := NewGCSServer(*httpAddr, *listenAddr, *gatewayCmdAddr, *demo)

	mux := http.NewServeMux()
	mux.HandleFunc("/", server.HandleIndex)
	mux.HandleFunc("/events", server.HandleEvents)
	mux.HandleFunc("/api/state", server.HandleState)
	mux.HandleFunc("/api/command", server.HandleCommand)
	mux.HandleFunc("/healthz", server.HandleHealthz)

	httpServer := &http.Server{
		Addr:              *httpAddr,
		Handler:           mux,
		ReadHeaderTimeout: 3 * time.Second,
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	if *demo {
		go server.RunDemoEngine(ctx)
	}

	go func() {
		_ = server.ListenUDP(ctx)
	}()

	go func() {
		<-ctx.Done()
		shutdownCtx, cancelShutdown := context.WithTimeout(context.WithoutCancel(ctx), time.Second)
		defer cancelShutdown()
		_ = httpServer.Shutdown(shutdownCtx)
	}()

	fmt.Fprintf(os.Stdout, "level=INFO event=gcs_started http_addr=%s listen_addr=%s demo=%v\n",
		*httpAddr, *listenAddr, *demo)
	displayAddr := *httpAddr
	if host, port, err := net.SplitHostPort(*httpAddr); err == nil {
		if host == "" || host == "0.0.0.0" {
			displayAddr = "127.0.0.1:" + port
		}
	}
	fmt.Fprintf(os.Stdout, "level=INFO event=gcs_ready dashboard_url=http://%s\n", displayAddr)

	if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		fmt.Fprintf(os.Stderr, "level=ERROR event=gcs_http_failed err=%v\n", err)
	}
}
