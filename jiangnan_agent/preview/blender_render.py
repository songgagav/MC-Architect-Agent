"""Standalone Blender Python script used by the preview command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--obj", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--camera-scales", required=True)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def _world_bounds(objects):
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not points:
        raise RuntimeError("OBJ import produced no mesh bounds")
    minimum = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return minimum, maximum


def _engine_id() -> str:
    available = {
        item.identifier
        for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    }
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        if candidate in available:
            return candidate
    raise RuntimeError(f"no supported Blender render engine is available: {sorted(available)}")


def main() -> None:
    args = _arguments()
    camera_scales = json.loads(args.camera_scales)
    if not isinstance(camera_scales, dict):
        raise RuntimeError("camera scales must be a JSON object")

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.wm.obj_import(filepath=args.obj, forward_axis="NEGATIVE_Z", up_axis="Y")
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    minimum, maximum = _world_bounds(objects)
    center = (minimum + maximum) * 0.5
    extent = maximum - minimum
    largest = max(extent)

    scene = bpy.context.scene
    scene.render.engine = _engine_id()
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = ""
    scene.camera = None

    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("JiangnanPreviewWorld")
    scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.57, 0.62, 0.68, 1.0)
        background.inputs["Strength"].default_value = 0.75

    light_data = bpy.data.lights.new("JiangnanPreviewLight", type="AREA")
    light_data.energy = 50.0 * largest * largest
    light_data.shape = "DISK"
    light_data.size = largest * 0.9
    light = bpy.data.objects.new("JiangnanPreviewLight", light_data)
    scene.collection.objects.link(light)
    light.location = center + Vector((largest, -largest, largest * 1.8))
    light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()

    camera_data = bpy.data.cameras.new("JiangnanPreviewCamera")
    camera = bpy.data.objects.new("JiangnanPreviewCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.clip_end = largest * 20.0 + 100.0
    camera.data.lens = 52.0

    views = {
        "top": Vector((0.0, 0.0, 1.0)),
        "front": Vector((0.0, -1.0, 0.0)),
        "side": Vector((1.0, 0.0, 0.0)),
        "perspective": Vector((1.0, -1.0, 0.75)).normalized(),
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    for name, direction in views.items():
        camera.location = center + direction * float(camera_scales["perspective_distance"])
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        if name == "perspective":
            camera.data.type = "PERSP"
        else:
            camera.data.type = "ORTHO"
            camera.data.ortho_scale = float(camera_scales[name])
        output_path = output_dir / f"{args.prefix}{name}.png"
        scene.render.filepath = str(output_path)
        bpy.ops.render.render(write_still=True)
        rendered.append(output_path.name)

    marker = {"rendered": rendered, "blender_version": bpy.app.version_string}
    print("JiangnanPreview: " + json.dumps(marker, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
