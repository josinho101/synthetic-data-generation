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
    for s in specs:
        room = Rect(0, 0, *s["footprint_m"])
        for name, r in s["layout"]["obstacles"].items():
            assert Rect.from_list(r).inside(room), f"{s['id']}: {name} outside the room"


def test_beam_corridor_door_swings_and_marker_stay_clear(specs):
    for s in specs:
        lay = s["layout"]
        keep = {n: Rect.from_list(r) for n, r in lay["keepouts"].items()}
        for item in lay["props"] + ([lay["patient_support"]] if lay.get("patient_support") else []):
            r = Rect.from_list(item["rect"])
            for name in ("beam_corridor", "entrance_swing", "entrance_clear", "changing_door_clear", "floor_marker"):
                assert not r.overlaps(keep[name]), f"{s['id']}: {item.get('name', item['kind'])} in {name}"


def test_detector_and_tube_face_each_other(specs):
    for s in specs:
        eq = s["layout"]["equipment"]
        det, focal = eq["detector"]["center"], eq["focal_spot"]
        assert det[0] == pytest.approx(focal[0])
        assert abs(det[1] - focal[1]) == pytest.approx(eq["sid_m"], abs=1e-6)
        assert eq["detector_wall"] != eq["tube_wall"]
        assert eq["detector_wall"] == ("north" if s["detector_side"] == "left" else "south")


def test_changing_room_inside_the_footprint_with_its_own_door(specs):
    for s in specs:
        cr = s["layout"]["changing_room"]
        interior, room = Rect.from_list(cr["interior"]), Rect(0, 0, *s["footprint_m"])
        assert interior.inside(room)
        assert cr["door"]["width"] >= 0.7
        assert s["layout"]["walk_ok"]


def test_other_footprints_solve(cfg):
    for ft in ([20, 10], [15, 7.5]):
        c = apply_overrides(cfg, {"room.footprint_ft": ft})
        s = build_room_spec(c, 0)
        assert s["footprint_m"][0] == pytest.approx(ft[0] * 0.3048, abs=1e-3)


def test_entrance_marker_inside_the_room_facing_in_and_clear_of_props(specs):
    for s in specs:
        lay = s["layout"]
        em, door = lay["entrance_marker"], lay["entrance"]
        room = Rect(0, 0, *s["footprint_m"])
        assert Rect.from_list(em["outline"]).inside(room), s["id"]
        # local -Y (toes) points into the room, away from the door
        a = math.radians(em["yaw_deg"])
        toes = (math.sin(a), -math.cos(a))
        inward = {"west": (1, 0), "south": (0, 1), "north": (0, -1)}[door["wall"]]
        assert toes[0] == pytest.approx(inward[0], abs=1e-9) and toes[1] == pytest.approx(inward[1], abs=1e-9)
        clear = Rect.from_list(lay["keepouts"]["entrance_clear"])
        sx, sy = em["stand_point"]
        assert clear.x0 <= sx <= clear.x1 and clear.y0 <= sy <= clear.y1, s["id"]


def test_tape_contrasts_with_the_floor(specs, cfg):
    from sdg_room.sampling.distributions import delta_e
    need = cfg["equipment"]["floor_marker"]["min_floor_delta_e"]
    for s in specs:
        assert delta_e(s["layout"]["marker"]["tape_color"], s["floor"]["color"]) >= need - 0.5, s["id"]
