from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List

from osrs_console.utils.api import _XP_TABLE


def load_actions(skill: str) -> list["TrainingAction"]:
    data_path = Path(__file__).parent / "data" / "actions.json"
    with open(data_path, "r") as f:
        raw = json.load(f)
    return [TrainingAction(**entry) for entry in raw.get(skill, [])]


@dataclass
class InputMaterial:
    name: str
    qty: float
    stackable: bool = False


@dataclass
class OutputMaterial:
    name: str
    qty: float
    rarity: float = 1.0
    stackable: bool = False


@dataclass
class SkillTool:
    name: str
    qty: float
    level_req: int = 1


@dataclass
class PreRollOutput:
    name: str
    qty: float
    rarity: float
    stackable: bool = False


@dataclass
class TrainingAction:
    name: str
    level_req: int
    xp: float
    members: bool
    inputs: list[dict]
    tools: list[dict]
    outputs: list[dict]
    pre_roll_outputs: list[dict]

    def input_materials(self) -> list[InputMaterial]:
        return [InputMaterial(i["name"], i["qty"], i["stackable"]) for i in self.inputs if i.get("qty", 0) > 0]
    
    def skill_tools(self) -> list[SkillTool]:
        return [SkillTool(t["name"], t["qty"], t["level_req"]) for t in self.tools if t.get("qty", 0) > 0]

    def output_materials(self) -> list[OutputMaterial]:
        return [OutputMaterial(o["name"], o["qty"], o["rarity"], o["stackable"]) for o in self.outputs if o.get("qty", 0) > 0]
    
    def pre_rolls(self) -> list[PreRollOutput]:
        return [PreRollOutput(o["name"], o["qty"], o["rarity"], o["stackable"]) for o in self.pre_roll_outputs if o.get("qty", 0) > 0]
    

@dataclass
class CalcSession:
    skill: str
    start_xp: int
    target_xp: int
    selected_actions: list[str] = field(default_factory=list)

    results: list["ActionResult"] = field(default_factory=list)
    total_xp_per: int = 0
    total_actions: int = 0

    @property
    def xp_needed(self) -> int:
        return max(0, self.target_xp - self.start_xp)
    
    @property
    def start_level(self) -> int:
        return self._xp_to_level(self.start_xp)
    
    @property
    def target_level(self) -> int:
        return self._xp_to_level(self.target_xp)
    
    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "start_xp": self.start_xp,
            "target_xp": self.target_xp,
            "selected_actions": self.selected_actions,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "CalcSession":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
    
    @staticmethod
    def _xp_to_level(xp: int) -> int:
        level = 1
        for i, threshold in enumerate(_XP_TABLE, start=1):
            if xp >= threshold:
                level = i
            else:
                break
        return min(level, 99)
    
    @staticmethod
    def _level_to_xp(lvl: int) -> int:
        if lvl <= 1:
            return 0
        if lvl > 99:
            return _XP_TABLE[-1]
        return _XP_TABLE[lvl - 1]
    

@dataclass
class ActionResult:
    action: TrainingAction
    actions_needed: int

    @property
    def total_xp(self) -> float:
        return self.actions_needed * self.action.xp
    
    def material_totals(self) -> list[InputMaterial]:
        return [
            InputMaterial(
                m.name,
                math.ceil(m.qty * self.actions_needed)
            )
            for m in self.action.input_materials()
        ]
    

def calculate(
    session: CalcSession,
    all_actions: list[TrainingAction]
) -> Tuple[List[ActionResult], Tuple[int, int]]:
    action_map = {a.name: a for a in all_actions}
    results = []
    actions_xp = []
    for name in session.selected_actions:
        if name not in action_map:
            continue
        action = action_map[name]
        actions_xp.append(action.xp)
        needed = math.ceil(session.xp_needed / action.xp) if action.xp > 0 else 0
        results.append(ActionResult(action=action, actions_needed=needed))
    
    total_xp = sum(actions_xp)
    agg_needed = math.ceil(session.xp_needed / total_xp) if total_xp > 0 else 0
    return results, (total_xp, agg_needed)