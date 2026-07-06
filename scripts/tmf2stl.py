#!/usr/bin/env python3
"""
Minimal 3MF -> binary STL converter (no dependencies).

3MF is a zip of an XML mesh; this unions every <mesh> in the model (all
component transforms in the models used here are identity) and writes a binary
STL.  Used to turn a downloaded connector 3MF into a mesh Blender can import.

    python scripts/tmf2stl.py input.3mf output.stl
"""
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile


def convert(tmf, out):
    with zipfile.ZipFile(tmf) as z:
        name = next(n for n in z.namelist() if n.endswith("3dmodel.model"))
        root = ET.fromstring(z.read(name))
    ns = root.tag.split('}')[0].strip('{')
    def q(t): return f"{{{ns}}}{t}"

    tris = []
    for obj in root.find(q("resources")).findall(q("object")):
        mesh = obj.find(q("mesh"))
        if mesh is None:
            continue
        verts = [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
                 for v in mesh.find(q("vertices")).findall(q("vertex"))]
        for t in mesh.find(q("triangles")).findall(q("triangle")):
            tris.append((verts[int(t.get("v1"))], verts[int(t.get("v2"))],
                         verts[int(t.get("v3"))]))

    with open(out, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
            vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
            nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
            l = (nx*nx + ny*ny + nz*nz) ** 0.5 or 1.0
            f.write(struct.pack("<3f", nx/l, ny/l, nz/l))
            for p in (a, b, c):
                f.write(struct.pack("<3f", *p))
            f.write(struct.pack("<H", 0))
    return len(tris)


if __name__ == "__main__":
    n = convert(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]} ({n} triangles)")
