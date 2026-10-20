# Rooms in Isaac Sim

`compose_scene.py` needs only `pxr` (usd-core, or the Python that ships with Isaac Sim). It writes a
small `.usda` that **references** a generated room and, optionally, a synthetic human. The source
files are not changed.

```bash
# room only
python isaac/compose_scene.py <run>/rooms/R0001/R0001.usd

# room + patient on the floor marker; detector + tube at the patient's T7 height
python isaac/compose_scene.py <run>/rooms/R0001/R0001.usd \
    --human ../output/humans/run-<humans run>/humans/H0001/H0001.usd

# animated human, fixed detector height
python isaac/compose_scene.py R0001.usd --human H0001_anim.usda --detector-height 1.35 --out scene.usda
```

Open the `.usda` in Isaac Sim (*File → Open*) and press **Play**.

| Prim | What |
|---|---|
| `/World/Room` | the room (centred at the origin, entrance door facing −Y / the viewer) |
| `/World/Patient` | the human at `Room/Markers/PatientStand`, rotated to face the detector |
| `/World/Room/Equipment/WallStand/Carriage` | translate z set to the patient's T7 height (clamped to `sdg:travel_*`) |
| `/World/Room/Equipment/TubeStand/Carriage/Arm` | tube at the same height (horizontal beam) |
| `/World/Room/Cameras/RealSense_D455_Top`, `RealSense_D455_Front` (+ `_Mount`) | shifted by the same height change as the detector / tube they are mounted on |

## Capturing images from the room cameras

```bash
./python.sh <repo>/room/isaac/capture_cameras.py --usd <run>/rooms/R0001/scene_R0001_H0001.usda --out /tmp/caps
```

Exam cameras only (Intel RealSense D455, for the patient-pose pipeline), with point clouds:

```bash
./python.sh <repo>/room/isaac/capture_cameras.py --usd scene_R0001_H0001.usda --out /tmp/caps --only exam --pointcloud
```

Each D455 stream gets its own folder, named like its camera prim: `RealSense_D455_Left_RGB/` (RGB + semantic
segmentation) and `RealSense_D455_Left_Depth/` (`distance_to_image_plane`, optional point cloud). Front, Left
and Right images are upright portrait (720 × 1280 depth, 800 × 1280 RGB); Top is landscape, looking down.

The big grey camera shapes in the viewport are Isaac's icons for camera prims, not geometry. Hide them with the
viewport eye menu → *Show By Type → Cameras*.

Alternatively, set `USD_PATH` in the file and run it in the Script Editor. Every `…/Cameras/*`
camera (except `Viewer_Entrance`) gets a render product at its `sdg:resolution`, and `BasicWriter`
writes RGB, colourised semantic segmentation and depth. This script is not tested outside Isaac Sim.

The chest height comes from `H0001.json → landmarks.T7.rest_position_m`, or the midpoint of
jugular notch and xiphoid. The scene's `customLayerData.sdg_scene` records the room, the human,
the stand position, the yaw and the detector height.
