# Renders images/fit_test.png from the 3D-printable fit-test STL.
# Invoked by scripts/render_previews.py; run standalone with:
#   blender -b -P scripts/render_fittest.py -- <input.stl> <output.png>
import math
import sys

import bpy
from mathutils import Vector

STL, OUTPNG = sys.argv[-2], sys.argv[-1]

RES = (1600, 1000)
SAMPLES = 96


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.view_settings.view_transform = "Standard"
    sc.render.film_transparent = False

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.92, 0.92, 0.93, 1.0)
    bg.inputs[1].default_value = 0.5
    sc.world = world
    return sc


def resin_material():
    mat = bpy.data.materials.new("resin")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.32, 0.45, 0.55, 1.0)
    b.inputs["Roughness"].default_value = 0.5
    return mat


def floor_material():
    mat = bpy.data.materials.new("floor")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.90, 0.90, 0.91, 1.0)
    b.inputs["Roughness"].default_value = 0.9
    return mat


def import_stl(path):
    bpy.ops.wm.stl_import(filepath=path)
    obj = bpy.context.selected_objects[0]
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    min_z = min(c.z for c in corners)
    cx = (min(c.x for c in corners) + max(c.x for c in corners)) / 2
    cy = (min(c.y for c in corners) + max(c.y for c in corners)) / 2
    obj.location = (obj.location.x - cx, obj.location.y - cy,
                    obj.location.z - min_z)
    obj.data.materials.clear()
    obj.data.materials.append(resin_material())
    return obj


def add_sun(direction, energy, angle_deg):
    light = bpy.data.lights.new("sun", type="SUN")
    light.energy = energy
    light.angle = math.radians(angle_deg)
    lamp = bpy.data.objects.new("sun", light)
    bpy.context.collection.objects.link(lamp)
    lamp.rotation_euler = Vector(direction).to_track_quat("Z", "Y").to_euler()


def add_floor():
    bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, 0, 0))
    bpy.context.active_object.data.materials.append(floor_material())


def frame_camera(obj, azim_deg=32.0, elev_deg=30.0, margin=1.05):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    center = (lo + hi) / 2
    radius = (hi - lo).length / 2

    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam_data.clip_end = 100000

    sc = bpy.context.scene
    aspect = sc.render.resolution_y / sc.render.resolution_x
    fov_h = cam_data.angle
    fov_v = 2 * math.atan(math.tan(fov_h / 2) * aspect)
    dist = margin * radius / math.tan(min(fov_h, fov_v) / 2)

    azim, elev = math.radians(azim_deg), math.radians(elev_deg)
    offset = Vector((math.cos(elev) * math.sin(azim),
                     -math.cos(elev) * math.cos(azim),
                     math.sin(elev))) * dist
    cam.location = center + offset
    cam.rotation_euler = (cam.location - center).to_track_quat("Z", "Y").to_euler()


def main():
    reset_scene()
    obj = import_stl(STL)
    add_floor()
    add_sun((0.5, -1.0, 0.9), energy=2.5, angle_deg=15)
    add_sun((-1.0, -0.3, 0.5), energy=0.8, angle_deg=30)
    frame_camera(obj)
    bpy.context.scene.render.filepath = OUTPNG
    bpy.ops.render.render(write_still=True)
    print("wrote", OUTPNG)


main()
