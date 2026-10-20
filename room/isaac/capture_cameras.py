"""Capture images from the room cameras with Isaac Sim Replicator (RGB + semantic segmentation + depth).

NOT tested outside Isaac Sim (needs omni.replicator.core). Run either way:

  * Isaac Sim -> Window -> Script Editor: set USD_PATH / OUT_DIR below, paste, Run.
  * Headless:  ./python.sh <repo>/room/isaac/capture_cameras.py --usd <room or scene .usd(a)> --out /tmp/captures

Every UsdGeom.Camera whose path contains "/Cameras/" gets a render product at its `sdg:resolution`
(default 1280 x 720) and a BasicWriter writes <out>/<camera>/rgb_*.png, semantic_segmentation_*.png,
distance_to_image_plane_*.npy. Set SKIP to leave cameras out (e.g. the Viewer_Entrance camera).

RGB-D exam cameras (Intel RealSense D455, /Room/Cameras/RealSense_D455_*) have one camera prim per stream:
  .../RealSense_D455_Left/RealSense_D455_Left_RGB    -> <out>/RealSense_D455_Left_RGB/    rgb + semantic segmentation
  .../RealSense_D455_Left/RealSense_D455_Left_Depth  -> <out>/RealSense_D455_Left_Depth/  distance_to_image_plane
                                                        (+ pointcloud with --pointcloud)
Front / Left / Right are portrait (720 x 1280 depth, 800 x 1280 RGB, upright), Top is landscape looking down.
--only exam captures just these (the later patient-pose pipeline); --only room just the ceiling cameras.
"""

import argparse
import sys

USD_PATH = ""          # Script Editor use: path to R0001.usd or scene_R0001_H0001.usda
OUT_DIR = "/tmp/room_captures"
FRAMES = 1
SKIP = ("Viewer_Entrance",)
ONLY = "all"           # all | exam | room
POINTCLOUD = False


def _camera_name(prim) -> str:
    """Output folder = the camera prim name (stream prims of RGB-D rigs are unique: <rig>_RGB / <rig>_Depth)."""
    return prim.GetName()


def main(usd_path, out_dir, frames=FRAMES, headless=False, only=ONLY, pointcloud=POINTCLOUD):
    if headless:
        from isaacsim import SimulationApp
        app = SimulationApp({"headless": True})
    import omni.replicator.core as rep
    import omni.usd
    from pxr import UsdGeom

    ctx = omni.usd.get_context()
    ctx.open_stage(usd_path)
    stage = ctx.get_stage()
    cameras = []
    for p in stage.Traverse():
        if not (p.IsA(UsdGeom.Camera) and "/Cameras/" in str(p.GetPath())) or _camera_name(p) in SKIP \
                or p.GetName() in SKIP or p.GetParent().GetName() in SKIP:
            continue
        stream = p.GetAttribute("sdg:stream")
        stream = stream.Get() if stream else None
        if (only == "exam" and not stream) or (only == "room" and stream):
            continue
        cameras.append((p, stream))
    if not cameras:
        print(f"no cameras found (--only {only})")
        return 1
    for prim, stream in cameras:
        res = prim.GetAttribute("sdg:resolution").Get()
        res = (int(res[0]), int(res[1])) if res is not None else (1280, 720)
        product = rep.create.render_product(str(prim.GetPath()), res)
        writer = rep.WriterRegistry.get("BasicWriter")
        name = _camera_name(prim)
        if stream == "depth":
            outputs = dict(distance_to_image_plane=True, pointcloud=pointcloud)
        elif stream == "color":
            outputs = dict(rgb=True, semantic_segmentation=True, colorize_semantic_segmentation=True)
        else:
            outputs = dict(rgb=True, semantic_segmentation=True, colorize_semantic_segmentation=True,
                           distance_to_image_plane=True)
        writer.initialize(output_dir=f"{out_dir}/{name}", **outputs)
        writer.attach([product])
        print(f"camera {prim.GetPath()} -> {out_dir}/{name} at {res[0]}x{res[1]} ({', '.join(outputs)})")
    for _ in range(frames):
        rep.orchestrator.step()
    rep.orchestrator.wait_until_complete()
    if headless:
        app.close()
    return 0


if __name__ == "__main__":
    if USD_PATH and len(sys.argv) <= 1:          # Script Editor
        main(USD_PATH, OUT_DIR)
    else:
        parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("--usd", required=True)
        parser.add_argument("--out", default=OUT_DIR)
        parser.add_argument("--frames", type=int, default=FRAMES)
        parser.add_argument("--only", choices=("all", "exam", "room"), default=ONLY,
                            help="exam = RGB-D exam cameras (D455) only, room = the other cameras only")
        parser.add_argument("--pointcloud", action="store_true", help="also write point clouds of depth streams")
        args = parser.parse_args()
        sys.exit(main(args.usd, args.out, args.frames, headless=True, only=args.only, pointcloud=args.pointcloud))
