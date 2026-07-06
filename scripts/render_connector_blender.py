"""
Blender scene: the routed board (GLB) plugged into a 3-pin XLR connector (STL).
Invoked by scripts/render_connector.py; not run directly.

    blender -b -P scripts/render_connector_blender.py -- <board.glb> <connector.stl> <out.png>

Renders with a transparent film + shadow-catcher floor; the caller composites
the result over a light-grey backdrop.  Orientation/framing are tuned for this
board and the XB-XLR-CT3-3TX insert; override via the CROTX/CROTY/CY/AZ/EL/SPP
environment variables if you swap the connector model.
"""
import math
import os
import sys

import bpy
from mathutils import Vector, Matrix

GLB, CONN_STL, OUT = sys.argv[-3], sys.argv[-2], sys.argv[-1]

def envf(k, d): return float(os.environ.get(k, d))
CONN_ROTX = envf("CROTX", "90")     # lay connector axis from Z to Y
CONN_ROTY = envf("CROTY", "180")    # roll: 2 contacts to the top face
CONN_ROTZ = envf("CROTZ", "0")
CONN_Y    = envf("CY", "-24.5")     # connector position along the board axis
CONN_Z    = envf("CZ", "0.4")       # board mid-plane
CAM_AZ    = envf("AZ", "50")
CAM_EL    = envf("EL", "27")
SAMPLES   = int(envf("SPP", "220"))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 1600, 1050
sc.view_settings.view_transform = "Standard"; sc.render.film_transparent = True
world = bpy.data.worlds.new("W"); world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.93, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.55
sc.world = world


def world_bbox(objs):
    cs = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    return (Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs))),
            Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs))))


# board (GLB is in metres; scale to mm and rest on Z=0, XLR end at -Y)
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=GLB)
board = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
for o in board:
    o.matrix_world = Matrix.Scale(1000.0, 4) @ o.matrix_world
bpy.context.view_layer.update()
lo, hi = world_bbox(board)
d = Vector((-(lo.x+hi.x)/2, -(lo.y+hi.y)/2, -lo.z))
for o in board:
    o.matrix_world = Matrix.Translation(d) @ o.matrix_world
bpy.context.view_layer.update()

# connector
bpy.ops.wm.stl_import(filepath=CONN_STL)
conn = bpy.context.selected_objects[0]
bpy.ops.object.shade_smooth()
lo, hi = world_bbox([conn])
conn.matrix_world = Matrix.Translation(-(lo+hi)/2) @ conn.matrix_world
R = (Matrix.Rotation(math.radians(CONN_ROTZ), 4, 'Z') @
     Matrix.Rotation(math.radians(CONN_ROTY), 4, 'Y') @
     Matrix.Rotation(math.radians(CONN_ROTX), 4, 'X'))
conn.matrix_world = R @ conn.matrix_world
conn.matrix_world = Matrix.Translation(Vector((0, CONN_Y, CONN_Z))) @ conn.matrix_world
m = bpy.data.materials.new("chrome"); m.use_nodes = True
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.60, 0.60, 0.63, 1)
b.inputs["Metallic"].default_value = 0.9; b.inputs["Roughness"].default_value = 0.25
conn.data.materials.clear(); conn.data.materials.append(m)
bpy.context.view_layer.update()

# shadow-catcher floor at the lowest point
allm = [o for o in bpy.data.objects if o.type == 'MESH']
lo2, hi2 = world_bbox(allm)
bpy.ops.mesh.primitive_plane_add(size=8000, location=(0, 0, lo2.z - 0.02))
floor = bpy.context.active_object; floor.is_shadow_catcher = True

def sun(direction, energy, angle):
    L = bpy.data.lights.new("s", "SUN"); L.energy = energy; L.angle = math.radians(angle)
    o = bpy.data.objects.new("s", L); bpy.context.collection.objects.link(o)
    o.rotation_euler = Vector(direction).to_track_quat("Z", "Y").to_euler()
sun((0.5, -1.0, 0.9), 3.0, 7); sun((-1.0, -0.3, 0.5), 1.1, 22); sun((0.2, 0.7, 0.4), 0.7, 22)

lo3, hi3 = world_bbox([o for o in allm])
center = (lo3 + hi3) / 2; radius = (hi3 - lo3).length / 2
cd = bpy.data.cameras.new("c"); cd.clip_start = 0.1; cd.clip_end = 1e6
cam = bpy.data.objects.new("c", cd); bpy.context.collection.objects.link(cam); sc.camera = cam
az, el, margin = math.radians(CAM_AZ), math.radians(CAM_EL), 1.16
aspect = sc.render.resolution_y / sc.render.resolution_x
fov_h = cd.angle; fov_v = 2*math.atan(math.tan(fov_h/2)*aspect)
dist = margin * radius / math.tan(min(fov_h, fov_v)/2)
off = Vector((math.cos(el)*math.sin(az), -math.cos(el)*math.cos(az), math.sin(el))) * dist
cam.location = center + off
cam.rotation_euler = (cam.location - center).to_track_quat("Z", "Y").to_euler()

sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("wrote", OUT)
