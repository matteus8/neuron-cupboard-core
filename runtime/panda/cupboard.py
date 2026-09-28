"""Panda Runtime: Swarm Consensus Engine ("The Cupboard").

Maintains decentralized state consensus for active Bamboo Nodes in optical line-of-sight.
Calculates bearing consensus, proximity warnings, and bounded-latency node timeouts.
"""

from typing import Dict, List, Optional, NamedTuple
import time
import proto.neuron_wire as nw


class SwarmNodeState(NamedTuple):
    node_id: int
    last_seq: int
    state_byte: int
    state: nw.DiscreteState
    azimuth_mrad: int
    elevation_mrad: int
    last_seen_us: int


class TheCupboard:
    """Decentralized swarm state manager for active optical nodes."""

    def __init__(self, node_timeout_us: int = 1_000_000): # 1.0s timeout
        self.node_timeout_us = node_timeout_us
        self.epoch = 0
        self.nodes: Dict[int, SwarmNodeState] = {}

    def update_node(
        self,
        node_id: int,
        seq_num: int,
        state_byte: int,
        azimuth_mrad: int = 0,
        elevation_mrad: int = 0,
        timestamp_us: Optional[int] = None,
    ) -> bool:
        """Update node state from a newly decoded optical Neuron packet."""
        if timestamp_us is None:
            timestamp_us = int(time.time() * 1_000_000)

        discrete_state = nw.unpack_state(state_byte)
        is_new = node_id not in self.nodes

        self.nodes[node_id] = SwarmNodeState(
            node_id=node_id,
            last_seq=seq_num,
            state_byte=state_byte,
            state=discrete_state,
            azimuth_mrad=azimuth_mrad,
            elevation_mrad=elevation_mrad,
            last_seen_us=timestamp_us,
        )

        self.epoch += 1

        # Structured key-value log
        mode_str = ["UNSPECIFIED", "SEARCH", "FORMATION_LOCK", "DISPERSAL"][discrete_state.mode]
        lock_str = ["NONE", "ACQUIRING", "TRACKING", "HARD_LOCKED"][discrete_state.lock_status]
        print(
            f"level=INFO ts={timestamp_us} node={node_id} seq={seq_num} "
            f"mode={mode_str} lock={lock_str} ack={int(discrete_state.consensus_ack)} "
            f"prox={int(discrete_state.proximity_alert)} az_mrad={azimuth_mrad} "
            f"event={'node_joined' if is_new else 'state_update'}"
        )
        return True

    def evict_stale_nodes(self, current_time_us: Optional[int] = None) -> List[int]:
        """Evict nodes that have exceeded the optical line-of-sight timeout."""
        if current_time_us is None:
            current_time_us = int(time.time() * 1_000_000)

        stale_nodes = []
        for node_id, state in list(self.nodes.items()):
            if (current_time_us - state.last_seen_us) > self.node_timeout_us:
                stale_nodes.append(node_id)
                del self.nodes[node_id]
                print(f"level=WARN ts={current_time_us} node={node_id} event=optical_los_lost")

        if stale_nodes:
            self.epoch += 1
        return stale_nodes

    @property
    def active_node_count(self) -> int:
        return len(self.nodes)

    def is_consensus_reached(self) -> bool:
        """Evaluate if all active nodes in The Cupboard have confirmed consensus ACK."""
        if not self.nodes:
            return False
        return all(n.state.consensus_ack for n in self.nodes.values())

    def get_proximity_alerts(self) -> List[int]:
        """Return list of node IDs indicating proximity / anti-collision alert."""
        return [node_id for node_id, n in self.nodes.items() if n.state.proximity_alert]
