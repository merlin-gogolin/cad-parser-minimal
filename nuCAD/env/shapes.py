from dataclasses import dataclass, field
from typing import Tuple, List, Union, Dict, Optional
from OCC.Core.TopoDS import (
    TopoDS_Shape,
    TopoDS_Vertex,
    TopoDS_Edge,
    TopoDS_Wire,
    TopoDS_Face,
    TopoDS_Shell,
    TopoDS_Solid,
    TopoDS_Compound,
)





@dataclass(frozen=True)
class Vertex:
    id: str
    point: Tuple[float, float, float]
    shape: TopoDS_Vertex

    def __str__(self):
        return f"{self.id}: Vertex at {self.point}"


@dataclass(frozen=True)
class Edge:
    id: str
    vertices: Tuple[Tuple[float, float, float], Tuple[float, float, float]]
    shape: TopoDS_Edge

    def __str__(self):
        return f"{self.id}: Edge from {self.vertices[0]} to {self.vertices[1]}"


@dataclass(frozen=True)
class Wire:
    id: str
    edges: List[Edge]
    shape: TopoDS_Wire

    def __str__(self):
        return f"{self.id}: Wire with {len(self.edges)} edges"


@dataclass(frozen=True)
class Face:
    id: str
    edges: List[Edge]
    centroid: Tuple[float, float, float]
    shape: TopoDS_Face

    def __str__(self):
        return f"{self.id}: Face with centroid at {self.centroid} and {len(self.edges)} edges"


@dataclass(frozen=True)
class Shell:
    id: str
    faces: List[Face]
    shape: TopoDS_Shell

    def __str__(self):
        return f"{self.id}: Shell with {len(self.faces)} faces"


@dataclass(frozen=True)
class Solid:
    id: str
    faces: List[Face]
    bbox_min: Tuple[float, float, float]
    bbox_max: Tuple[float, float, float]
    shape: TopoDS_Shape
    faces_full: List[TopoDS_Face] = field(default_factory=list)  


    def __str__(self):
        return f"{self.id}: Solid with {len(self.faces)} faces"

    def __repr__(self):
        return self.__str__()


@dataclass(frozen=True)
class Compound:
    id: str
    children: List[Union[Vertex, Edge, Wire, Face, Solid]]
    shape: TopoDS_Compound

    def __str__(self):
        return f"{self.id}: Compound with {len(self.children)} children"


@dataclass
class CADState:
    edges: Dict[str, dict] = field(default_factory=dict)
    wires: Dict[str, dict] = field(default_factory=dict)
    faces: Dict[str, dict] = field(default_factory=dict)
    solids: List[Solid] = field(default_factory=list)
    sketches: Dict[str, dict] = field(default_factory=dict)

    def __str__(self):
        return (
            f"CADState with {len(self.sketches)} sketches, "
            f"{len(self.edges)} edges, "
            f"{len(self.wires)} wires, "
            f"{len(self.faces)} faces, "
            f"{len(self.solids)} solids, "
        )
