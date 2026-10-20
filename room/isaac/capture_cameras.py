"""Capture images from the room cameras with Isaac Sim Replicator (RGB + semantic segmentation + depth).

NOT tested outside Isaac Sim (needs omni.replicator.core). Run either way:

  * Isaac Sim -> Window -> Script Editor: set USD_PATH / OUT_DIR below, paste, Run.
  * Headless:  ./python.sh <repo>/room/isaac/capture_cameras.py --usd <room or scene .usd(a)> --out /tmp/captures

Every UsdGeom.Camera whose path contains "/Cameras/" gets a render product at its `sdg:resolution`
(default 1280 x 720) and a BasicWriter writes <out>/<camera>/rgb_*.png, semantic_segmentation_*.png,
distance_to_image_plane_*.npy. Set SKIP to leave cameras out (e.g. the Viewer_Entrance camera).
"""

import argparse
import sys

USD_PATH = ""          # Script Editor use: path to R0001.usd or scene_R0001_H0001.usda
OUT_DIR = "/tmp/room_captures"
FRAMES = 1
SKIP = ("Viewer_Entrance",)


def main(usd_path, out_dir, frames=FRAMES, headless=False):
    if headless:
        from isaacsim import SimulationApp
        app = SimulationApp({"headless": True})
    import omni.replicator.core as rep
    import omni.usd
    from pxr import UsdGeom

    ctx = omni.usd.get_context()
    ctx.open_stage(usd_path)
    stage = ctx.get_stage()
    cameras = [p for p in stage.Traverse() if p.IsA(UsdGeom.Camera) and "/Cameras/" in str(p.GetPath())
               and p.GetName() not in SKIP]
    if not cameras:
        print("no room cameras found")
        return 1
    for prim in cameras:
        res = prim.GetAttribute("sdg:resolution").Get()
        res = (int(res[0]), int(res[1])) if res is not None else (1280, 720)
        product = rep.create.render_product(str(prim.GetPath()), res)
        writer = rep.WriterRegistry.get("BasicWriter")
        writer.initialize(output_dir=f"{out_dir}/{prim.GetName()}", rgb=True, semantic_segmentation=True,
                          colorize_semantic_segmentation=True, distance_to_image_plane=True)
        writer.attach([product])
        print(f"camera {prim.GetPath()} -> {out_dir}/{prim.GetName()} at {res[0]}x{res[1]}")
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
        args = parser.parse_args()
        sys.exit(main(args.usd, args.out, args.frames, headless=True))
