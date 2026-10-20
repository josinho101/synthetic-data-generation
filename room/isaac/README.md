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

## Capturing images from the room cameras

```bash
./python.sh <repo>/room/isaac/capture_cameras.py --usd <run>/rooms/R0001/scene_R0001_H0001.usda --out /tmp/caps
```

Alternatively, set `USD_PATH` in the file and run it in the Script Editor. Every `…/Cameras/*`
camera (except `Viewer_Entrance`) gets a render product at its `sdg:resolution`, and `BasicWriter`
writes RGB, colourised semantic segmentation and depth. This script is not tested outside Isaac Sim.

The chest height comes from `H0001.json → landmarks.T7.rest_position_m`, or the midpoint of
jugular notch and xiphoid. The scene's `customLayerData.sdg_scene` records the room, the human,
the stand position, the yaw and the detector height.
