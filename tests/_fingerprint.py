"""Fingerprints of the optimiser's inputs, to prove a change left them alone.

Variable and constraint names are cleared first: some embed Python object
ids, which differ from run to run."""

import hashlib
import json

from ortools.sat.python import cp_model

from core.metrics import break_slots
from core.solver import PROFILES, _allowed_rooms, _allowed_slots, _build_model
from core.warmstart import build as greedy


def model_hash(u, profile: str, constraints: list[dict]) -> str:
    built = _build_model(u, profile, constraints, _allowed_slots(u, constraints),
                         _allowed_rooms(u, constraints), None, False)
    proto = cp_model.CpModel().Proto()
    proto.copy_from(built.model.Proto())
    for v in proto.variables:
        v.name = ""
    for c in proto.constraints:
        c.name = ""
    return hashlib.sha256(str(proto).encode()).hexdigest()


def warmstart_hash(u, profile: str, constraints: list[dict]) -> str:
    a = greedy(u, _allowed_slots(u, constraints), _allowed_rooms(u, constraints), {},
               PROFILES[profile], breaks=break_slots(constraints))
    return hashlib.sha256(
        json.dumps([sorted(a.slot.items()), sorted(a.room.items())]).encode()
    ).hexdigest()
