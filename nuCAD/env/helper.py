from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_VERTEX, TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import topods
from OCC.Core.BRep import BRep_Tool
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib


from .shapes import Edge as EdgeClass
from .shapes import Face as FaceClass




def compute_bbox(shape):
    bbox = Bnd_Box()
    brepbndlib.Add(shape, bbox)
    return bbox.Get()


def get_edge_vertices(edge):
    """Extract vertices from an edge as a tuple of 3D coordinates."""
    vertices = []
    exp = TopExp_Explorer(edge, TopAbs_VERTEX)
    while exp.More():
        vertex = topods.Vertex(exp.Current())
        point = BRep_Tool.Pnt(vertex)
        vertices.append((point.X(), point.Y(), point.Z()))
        exp.Next()
    return tuple(vertices)


def get_edge_vertices_sorted(edge):
    """Extract vertices from an edge as sorted tuple for comparison."""
    ve = TopExp_Explorer(edge, TopAbs_VERTEX)
    verts = []
    while ve.More():
        v = topods.Vertex(ve.Current())
        p = BRep_Tool.Pnt(v)
        verts.append(tuple(round(x, 6) for x in (p.X(), p.Y(), p.Z())))
        ve.Next()
    return tuple(sorted(verts))


def get_sorted_edge_list(shape): 

    edge_explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    seen_edges = set()
    edge_list = []

    while edge_explorer.More():
        edge_shape = topods.Edge(edge_explorer.Current())

        vertex_explorer = TopExp_Explorer(edge_shape, TopAbs_VERTEX)
        verts = []
        while vertex_explorer.More():
            vertex = topods.Vertex(vertex_explorer.Current())
            point = BRep_Tool.Pnt(vertex)
            verts.append(tuple(round(x, 6) for x in (point.X(), point.Y(), point.Z())))
            vertex_explorer.Next()

        if len(verts) == 2:
            sorted_verts = tuple(sorted(verts))
            if sorted_verts not in seen_edges:
                seen_edges.add(sorted_verts)
                mid = tuple(round((a + b) / 2, 6) for a, b in zip(*sorted_verts))
                edge_list.append((mid, sorted_verts, edge_shape))

        edge_explorer.Next()

    edge_list.sort(key=lambda x: x[0])

    return edge_list


def get_sorted_face_list(shape, edge_dict): 

    face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_list = []

    while face_explorer.More():
        face = topods.Face(face_explorer.Current())
        surf = BRep_Tool.Surface(face)
        umin, umax, vmin, vmax = surf.Bounds()
        centroid = tuple(round((a + b) / 2, 6) for a, b in [(umin, umax), (vmin, vmax)])

        face_edges = []
        edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while edge_explorer.More():
            edge = topods.Edge(edge_explorer.Current())
            edge_verts = get_edge_vertices_sorted(edge)

            for eid, e in edge_dict.items():
                if get_edge_vertices_sorted(e.shape) == edge_verts:
                    face_edges.append(eid)
                    break
            edge_explorer.Next()

        face_list.append((centroid, face, face_edges))
        face_explorer.Next()

    face_list.sort(key=lambda x: x[0])

    return face_list



def get_edge_dict_for_solid(solid_id, shape):
    sorted_edges = get_sorted_edge_list(shape)
    return {
        f"{solid_id}e{i}": EdgeClass(
            id=f"{solid_id}e{i}",
            vertices=verts,
            shape=edge_shape
        )
        for i, (midpoint, verts, edge_shape) in enumerate(sorted_edges)
    }


def get_face_dict_for_solid(solid_id, shape, edge_dict):
    sorted_faces = get_sorted_face_list(shape, edge_dict)
    return {
        f"{solid_id}f{i}": FaceClass(
            id=f"{solid_id}f{i}",
            centroid=centroid,
            edges=[edge_dict[eid] for eid in edge_ids],
            shape=face
        )
        for i, (centroid, face, edge_ids) in enumerate(sorted_faces)
    }

