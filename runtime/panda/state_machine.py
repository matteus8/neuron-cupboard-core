"""Panda Runtime: Autonomous Swarm State Machine.

Evaluates local optical lock quality, neighbor consensus votes from The Cupboard,
and triggers deterministic state transitions across Operational Modes
(SEARCH -> FORMATION_LOCK -> DISPERSAL) without external GPS or RF coordination.
"""

from typing import Optional, NamedTuple
import proto.neuron_wire as nw
from .cupboard import TheCupboard


class NodeDecision(NamedTuple):
    mode: int
    lock_status: int
    consensus_ack: bool
    proximity_alert: bool
    swap_critical: bool
    state_byte: int


class SwarmStateMachine:
    """Deterministic local state machine for a single Bamboo Node."""

    def __init__(
        self,
        node_id: int,
        cupboard: TheCupboard,
        min_lock_frames: int = 3,
        proximity_range_threshold_mm: int = 1500,
    ):
        self.node_id = node_id
        self.cupboard = cupboard
        self.min_lock_frames = min_lock_frames
        self.proximity_range_threshold_mm = proximity_range_threshold_mm

        # Local state vector
        self.mode = nw.MODE_SEARCH
        self.lock_status = nw.LOCK_NONE
        self.consensus_ack = False
        self.proximity_alert = False
        self.swap_critical = False

        self.consecutive_locked_frames = 0

    def evaluate_tick(self) -> NodeDecision:
        """Evaluate current swarm consensus in The Cupboard and update local state."""
        active_count = self.cupboard.active_node_count

        # 1. Proximity / Anti-collision check
        proximity_warning = False
        for nid, neighbor in self.cupboard.nodes.items():
            if nid == self.node_id:
                continue
            if neighbor.state.proximity_alert:
                proximity_warning = True
                break

        if proximity_warning:
            self.proximity_alert = True
            self.mode = nw.MODE_DISPERSAL
            self.consensus_ack = False
            return self._build_decision()

        self.proximity_alert = False

        # 2. Optical Line-of-Sight Bearing Lock Evaluation
        if active_count == 0:
            self.lock_status = nw.LOCK_NONE
            self.consecutive_locked_frames = 0
            self.mode = nw.MODE_SEARCH
            self.consensus_ack = False
        else:
            self.consecutive_locked_frames += 1
            if self.consecutive_locked_frames < self.min_lock_frames:
                self.lock_status = nw.LOCK_ACQUIRING
                self.mode = nw.MODE_SEARCH
                self.consensus_ack = False
            else:
                self.lock_status = nw.LOCK_TRACKING

        # 3. Consensus Quorum Check
        # If we have tracked neighbors and optical tracking is stable
        if self.lock_status == nw.LOCK_TRACKING:
            # Check if all active neighbors are also tracking
            all_tracking = all(
                n.state.lock_status in (nw.LOCK_TRACKING, nw.LOCK_HARD_LOCKED)
                for n in self.cupboard.nodes.values()
                if n.node_id != self.node_id
            )

            if all_tracking and active_count >= 1:
                self.consensus_ack = True
                # Check if all active neighbors also acknowledged consensus
                all_acked = all(
                    n.state.consensus_ack
                    for n in self.cupboard.nodes.values()
                    if n.node_id != self.node_id
                )
                if all_acked:
                    self.lock_status = nw.LOCK_HARD_LOCKED
                    self.mode = nw.MODE_FORMATION_LOCK
                else:
                    self.mode = nw.MODE_SEARCH
            else:
                self.consensus_ack = False
                self.mode = nw.MODE_SEARCH

        return self._build_decision()

    def set_swap_critical(self, critical: bool):
        """Set SWaP low-battery / critical power alert flag."""
        self.swap_critical = critical

    def _build_decision(self) -> NodeDecision:
        packed_byte = nw.pack_state(
            mode=self.mode,
            lock_status=self.lock_status,
            consensus_ack=self.consensus_ack,
            proximity_alert=self.proximity_alert,
            swap_critical=self.swap_critical,
        )
        return NodeDecision(
            mode=self.mode,
            lock_status=self.lock_status,
            consensus_ack=self.consensus_ack,
            proximity_alert=self.proximity_alert,
            swap_critical=self.swap_critical,
            state_byte=packed_byte,
        )
