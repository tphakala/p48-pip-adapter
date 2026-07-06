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
CONN_ROTX = envf("CROTX", "-90")    # lay connector axis from Z to Y (solder-cup end toward board)
CONN_ROTY = envf("CROTY", "0")      # roll about the connector axis
CONN_ROTZ = envf("CROTZ", "0")
CONN_Y    = envf("CY", "-24.5")     # connector position along the board axis
CONN_Z    = envf("CZ", "0.4")       # board mid-plane
CAM_AZ    = envf("AZ", "50")
CAM_EL    = envf("EL", "27")
SAMPLES   = int(envf("SPP", "220"))
BODY_THR  = envf("BODYTHR", "0.62") # radial threshold for the black body band

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
# Use the GPU (OptiX/CUDA) if available -- big speedup on an NVIDIA card.
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
        devs = prefs.get_devices_for_type(backend)
        if devs:
            prefs.compute_device_type = backend
            for dev in devs:
                dev.use = dev.type != "CPU"
            sc.cycles.device = "GPU"
            print("Cycles GPU:", backend)
            break
except Exception as e:
    print("GPU setup skipped:", e)
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
def pbr(name, color, metallic, rough):
    mm = bpy.data.materials.new(name); mm.use_nodes = True
    bb = mm.node_tree.nodes["Principled BSDF"]
    bb.inputs["Base Color"].default_value = (*color, 1)
    bb.inputs["Metallic"].default_value = metallic
    bb.inputs["Roughness"].default_value = rough
    return mm

# Two-tone by geometry (the 3MF carries no per-part materials): the bulky
# central collar is the black body; the contacts protruding at each axial end
# are gold.  Classify each face by the mesh's local long axis (Z) -- faces in
# the contiguous central high-radius band are body, the rest are contacts.
BLACK = pbr("body_black", (0.022, 0.022, 0.024), 0.0, 0.42)
GOLD = pbr("pins_gold", (0.83, 0.66, 0.26), 1.0, 0.28)
me = conn.data
vs = me.vertices
x0 = sum(v.co.x for v in vs) / len(vs)
y0 = sum(v.co.y for v in vs) / len(vs)
zmin = min(v.co.z for v in vs); zmax = max(v.co.z for v in vs)
N = 80
import math as _m
rad = [0.0] * N
def _bin(z): return min(N - 1, max(0, int((z - zmin) / (zmax - zmin) * N)))
for v in vs:
    i = _bin(v.co.z); r = _m.hypot(v.co.x - x0, v.co.y - y0)
    if r > rad[i]:
        rad[i] = r
thr = BODY_THR * max(rad)
# contiguous band of high-radius bins around the centre = the collar/body
c = N // 2
while c > 0 and rad[c] < thr:
    c += 1 if rad[min(c + 1, N - 1)] >= thr else -1
    if c in (0, N - 1):
        break
lo = c
while lo > 0 and rad[lo - 1] >= thr:
    lo -= 1
hi = c
while hi < N - 1 and rad[hi + 1] >= thr:
    hi += 1
zlo = zmin + lo / N * (zmax - zmin)
zhi = zmin + (hi + 1) / N * (zmax - zmin)
me.materials.clear(); me.materials.append(BLACK); me.materials.append(GOLD)
for p in me.polygons:
    zc = sum(vs[i].co.z for i in p.vertices) / len(p.vertices)
    p.material_index = 0 if zlo <= zc <= zhi else 1
me.update()
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
