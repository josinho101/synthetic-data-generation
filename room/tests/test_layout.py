import math

import pytest

from sdg_room.config import apply_overrides
from sdg_room.layout.geometry import Rect
from sdg_room.sampling.manifest import build_room_spec


def _specs(cfg, n=30):
    return [build_room_spec(cfg, i) for i in range(n)]


@pytest.fixture(scope="module")
def specs(cfg):
    return _specs(cfg)


def test_objects_do_not_overlap(specs):
    for s in specs:
        rects = [(n, Rect.from_list(r)) for n, r in s["layout"]["obstacles"].items()]
        for i, (na, a) in enumerate(rects):
            for nb, b in rects[i + 1:]:
                if {na, nb} <= {"wall_stand", "wall_conduit"}:
                    continue
                assert not a.overlaps(b), f"{s['id']}: {na} overlaps {nb}"


def test_everything_inside_the_footprint(specs):
    """X-ray room objects inside the footprint; check-in furniture inside the check-in room (outside the footprint)."""
    for s in specs:
        room = Rect(0, 0, *s["footprint_m"])
        checkin = Rect.from_list(s["layout"]["changing_room"]["interior"])
        for name, r in s["layout"]["obstacles"].items():
            area = checkin if name in ("bench", "changing_chair") else room
            assert Rect.from_list(r).inside(area), f"{s['id']}: {name} outside its room"


def test_beam_corridor_door_swings_and_marker_stay_clear(specs):
    for s in specs:
        lay = s["layout"]
        keep = {n: Rect.from_list(r) for n, r in lay["keepouts"].items()}
        for item in lay["props"] + ([lay["patient_support"]] if lay.get("patient_support") else []):
            r = Rect.from_list(item["rect"])
            for name in ("beam_corridor", "changing_door_swing", "changing_door_clear", "floor_marker"):
                assert not r.overlaps(keep[name]), f"{s['id']}: {item.get('name', item['kind'])} in {name}"


def test_detector_and_tube_face_each_other(specs):
    for s in specs:
        eq = s["layout"]["equipment"]
        det, focal = eq["detector"]["center"], eq["focal_spot"]
        assert det[0] == pytest.approx(focal[0])
        assert abs(det[1] - focal[1]) == pytest.approx(eq["sid_m"], abs=1e-6)
        assert eq["detector_wall"] != eq["tube_wall"]
        assert eq["detector_wall"] == ("north" if s["detector_side"] == "left" else "south")


def test_checkin_room_outside_the_xray_room_is_the_only_way_in(cfg, specs):
    """Check-in room against the west wall, outside the footprint; entrance in its wall; connecting door in the
    shared west wall; patient route entrance -> check-in room -> connecting door -> X-ray room."""
    t = cfg["room"]["wall_thickness_m"]
    for s in specs:
        lay = s["layout"]
        cr, ent = lay["changing_room"], lay["entrance"]
        it, W = Rect.from_list(cr["interior"]), s["footprint_m"][1]
        assert it.x1 == pytest.approx(-t) and 0.0 - 1e-9 <= it.y0 and it.y1 <= W + 1e-9, s["id"]
        assert (it.y1 == pytest.approx(W)) if cr["corner"] == "north" else (it.y0 == pytest.approx(0.0))
        door = cr["door"]                                   # connecting door in the X-ray room's west wall
        assert door["wall"] == "west" and door["plane"] == [-t, 0.0] and door["width"] >= 0.7
        assert it.y0 <= door["center"][1] - door["width"] / 2 and door["center"][1] + door["width"] / 2 <= it.y1
        # entrance: a wall of the check-in room facing outside, opening within the check-in room's wall
        assert ent["placed_on"] in ("west", "side") and ent["swings"] == "out"
        if ent["placed_on"] == "west":
            assert ent["center"][0] == pytest.approx(it.x0) and it.y0 < ent["center"][1] < it.y1
        else:
            assert ent["wall"] == cr["corner"] and it.x0 < ent["center"][0] < it.x1
        assert ent["width"] >= cfg["room"]["entrance"]["min_width_m"] - 1e-9
        assert Rect.from_list(cr["bench"]["rect"]).inside(it)
        assert lay["walk_ok"] and lay["walk_start"] == cr["point_outside"]


def test_other_footprints_solve(cfg):
    for ft in ([20, 10], [15, 7.5]):
        c = apply_overrides(cfg, {"room.footprint_ft": ft})
        s = build_room_spec(c, 0)
        assert s["footprint_m"][0] == pytest.approx(ft[0] * 0.3048, abs=1e-3)


def test_entrance_marker_inside_the_room_facing_in_and_clear_of_props(specs):
    for s in specs:
        lay = s["layout"]
        em, door = lay["entrance_marker"], lay["changing_room"]["door"]    # the patient enters through the connecting door
        room = Rect(0, 0, *s["footprint_m"])
        assert Rect.from_list(em["outline"]).inside(room), s["id"]
        # local -Y (toes) points into the room, away from the door
        a = math.radians(em["yaw_deg"])
        toes = (math.sin(a), -math.cos(a))
        inward = {"west": (1, 0), "south": (0, 1), "north": (0, -1)}[door["wall"]]
        assert toes[0] == pytest.approx(inward[0], abs=1e-9) and toes[1] == pytest.approx(inward[1], abs=1e-9)
        clear = Rect.from_list(lay["keepouts"]["changing_door_clear"])
        sx, sy = em["stand_point"]
        assert clear.x0 <= sx <= clear.x1 and clear.y0 <= sy <= clear.y1, s["id"]


def test_tape_contrasts_with_the_floor(specs, cfg):
    from sdg_room.sampling.distributions import delta_e
    need = cfg["equipment"]["floor_marker"]["min_floor_delta_e"]
    for s in specs:
        assert delta_e(s["layout"]["marker"]["tape_color"], s["floor"]["color"]) >= need - 0.5, s["id"]


def _geometry(layout):
    """Layout without the appearance values stored in it (colours)."""
    import json
    skip = ("marker", "patient_support", "changing_room")
    return json.dumps({k: v for k, v in layout.items() if k not in skip}, sort_keys=True)


def test_fixed_layout_same_geometry_varied_appearance(cfg):
    """randomize_layout false (default): one layout for every room; walls, floor, CCT, lux still vary."""
    assert cfg["variations"]["randomize_layout"] is False
    specs = [build_room_spec(cfg, i) for i in range(6)]
    assert len({_geometry(s["layout"]) for s in specs}) == 1
    assert len({(s["ceiling_height_m"], s["detector_side"], s["patient_support"]) for s in specs}) == 1
    assert len({(s["walls"]["color"], s["floor"]["color"], s["cct_k"], s["lux_target"]) for s in specs}) == 6
    other = build_room_spec(apply_overrides(cfg, {"variations.layout_seed": 7}), 0)
    assert _geometry(other["layout"]) != _geometry(specs[0]["layout"])


def test_randomized_layout_option(cfg):
    c = apply_overrides(cfg, {"variations.randomize_layout": True})
    assert len({_geometry(build_room_spec(c, i)["layout"]) for i in range(4)}) == 4


def test_detector_opposite_checkin_at_far_end(cfg):
    """The detector (and its tripods) is on the long wall away from the check-in room, as far from the connecting
    door as possible: the patient's way in stays free."""
    c = apply_overrides(cfg, {"variations.randomize_layout": True})
    for i in range(8):
        s = build_room_spec(c, i)
        lay = s["layout"]
        assert lay["equipment"]["detector_wall"] == ("south" if lay["changing_room"]["corner"] == "north" else "north")
        door = lay["changing_room"]["door"]["center"]
        for stand in lay["exam_cameras"].values():
            x, y = stand["position"][:2]
            assert math.hypot(x - door[0], y - door[1]) > 2.0, s["id"]
