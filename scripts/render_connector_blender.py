"""
Blender scene for images/board_with_connector.png: the routed board (GLB) with
its XLR-pad edge slotted between three modelled gold pins on a black insulator
insert -- pins 1 & 2 against the front (component) face, pin 3 against the back
-- the sandwich mount.  Pin X positions come from netlist.py's XLR pads.  Run
via scripts/render_connector.py (renders on transparent film + GPU; the caller
composites over grey).  Camera via AZ / EL env vars.

    blender -b -P scripts/render_connector_blender.py -- <board.glb> <out.png>
"""
import bpy, math, sys, os
from mathutils import Vector, Matrix
GLB, OUT = sys.argv[-2], sys.argv[-1]
def envf(k,d): return float(os.environ.get(k,d))
AZ=envf("AZ","52"); EL=envf("EL","30"); SPP=int(envf("SPP","160"))
bpy.ops.wm.read_factory_settings(use_empty=True)
sc=bpy.context.scene; sc.render.engine="CYCLES"; sc.cycles.samples=SPP; sc.cycles.use_denoising=True
try:
    pr=bpy.context.preferences.addons["cycles"].preferences
    for be in ("OPTIX","CUDA"):
        ds=pr.get_devices_for_type(be)
        if ds:
            pr.compute_device_type=be
            for dv in ds: dv.use = dv.type!="CPU"
            sc.cycles.device="GPU"; break
except Exception as e: print("gpu",e)
sc.render.resolution_x,sc.render.resolution_y=1600,1050; sc.view_settings.view_transform="Standard"
sc.render.film_transparent=True
w=bpy.data.worlds.new("W"); w.use_nodes=True
w.node_tree.nodes["Background"].inputs[0].default_value=(0.92,0.92,0.93,1)
w.node_tree.nodes["Background"].inputs[1].default_value=0.55; sc.world=w
def wb(os_):
    cs=[o.matrix_world@Vector(c) for o in os_ for c in o.bound_box]
    return (Vector((min(c.x for c in cs),min(c.y for c in cs),min(c.z for c in cs))),
            Vector((max(c.x for c in cs),max(c.y for c in cs),max(c.z for c in cs))))
def mat(name,col,met,ro):
    m=bpy.data.materials.new(name); m.use_nodes=True; b=m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value=(*col,1); b.inputs["Metallic"].default_value=met; b.inputs["Roughness"].default_value=ro
    return m
BLACK=mat("blk",(0.02,0.02,0.022),0.0,0.42); GOLD=mat("gold",(0.83,0.66,0.26),1.0,0.24)
def cyl(p0,p1,r,m,v=48):
    p0,p1=Vector(p0),Vector(p1); vv=p1-p0
    bpy.ops.mesh.primitive_cylinder_add(radius=r,depth=vv.length,vertices=v,location=(p0+p1)/2)
    o=bpy.context.active_object; o.rotation_euler=vv.to_track_quat('Z','Y').to_euler()
    o.data.materials.append(m); bpy.ops.object.shade_smooth(); return o
def ball(p,r,m):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r,location=p,segments=32,ring_count=16)
    o=bpy.context.active_object; o.data.materials.append(m); bpy.ops.object.shade_smooth(); return o
# ---- board ----
before=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=GLB)
board=[o for o in bpy.data.objects if o not in before and o.type=='MESH']
for o in board: o.matrix_world=Matrix.Scale(1000.0,4)@o.matrix_world
bpy.context.view_layer.update()
lo,hi=wb(board); d=Vector((-(lo.x+hi.x)/2,-(lo.y+hi.y)/2,-lo.z))
for o in board: o.matrix_world=Matrix.Translation(d)@o.matrix_world
bpy.context.view_layer.update()
# board: X[-5.55,5.55], XLR edge Y=-16.2, top face z~0.8, bottom z~0, mid 0.4
EDGE=-16.205
# ---- pin insert: black insulator disc behind the board edge ----
disc_c=(0,EDGE-2.5,0.4)  # centre; thickness 4 -> front face at EDGE-0.5 (touching board)
cyl((0,EDGE-4.5,0.4),(0,EDGE-0.5,0.4),7.0,BLACK,64)          # insulator disc
cyl((0,EDGE-4.7,0.4),(0,EDGE-4.4,0.4),8.2,BLACK,64)          # rear rim
# ---- 3 gold pins straddling the board: 1&2 front(top), 3 back(bottom) ----
PINS=[(-3.65,0.95),(3.97,0.95),(0.16,-0.15)]   # (x, z)  board pad positions
for (x,z) in PINS:
    cyl((x,EDGE-8.5,z),(x,-9.0,z),1.2,GOLD,32)   # pin runs from free tip(-Y) onto the pad(+Y)
    ball((x,EDGE-8.5,z),1.2,GOLD)                # rounded mating tip
# ---- shadow catcher ----
allm=[o for o in bpy.data.objects if o.type=='MESH']
lo2,hi2=wb(allm)
bpy.ops.mesh.primitive_plane_add(size=8000,location=(0,0,lo2.z-0.02))
fl=bpy.context.active_object; fl.is_shadow_catcher=True
def sun(dir,e,a):
    L=bpy.data.lights.new("s","SUN"); L.energy=e; L.angle=math.radians(a)
    o=bpy.data.objects.new("s",L); bpy.context.collection.objects.link(o)
    o.rotation_euler=Vector(dir).to_track_quat("Z","Y").to_euler()
sun((0.5,-1,0.9),3,7); sun((-1,-0.3,0.5),1.1,22); sun((0.2,0.7,0.4),0.7,22)
lo3,hi3=wb([o for o in allm]); center=(lo3+hi3)/2; radius=(hi3-lo3).length/2
cd=bpy.data.cameras.new("c"); cd.clip_start=0.1; cd.clip_end=1e6
cam=bpy.data.objects.new("c",cd); bpy.context.collection.objects.link(cam); sc.camera=cam
a,e,mg=math.radians(AZ),math.radians(EL),1.14
asp=sc.render.resolution_y/sc.render.resolution_x
fh=cd.angle; fv=2*math.atan(math.tan(fh/2)*asp)
dist=mg*radius/math.tan(min(fh,fv)/2)
cam.location=center+Vector((math.cos(e)*math.sin(a),-math.cos(e)*math.cos(a),math.sin(e)))*dist
cam.rotation_euler=(cam.location-center).to_track_quat("Z","Y").to_euler()
sc.render.filepath=OUT; bpy.ops.render.render(write_still=True); print("wrote",OUT)
