from typing import List, Optional

import pyradiance as pr
from frads.geom import Polygon
from frads import utils
import numpy as np


class Surface:
    """Surface object."""

    def __init__(self, base: Polygon) -> None:
        """."""
        self.base = base
        self._vertices = base.vertices
        self._vect1 = (base.vertices[1] - base.vertices[0]) / np.linalg.norm(
            base.vertices[1] - base.vertices[0]
        )
        self._vect2 = (base.vertices[2] - base.vertices[1]) / np.linalg.norm(
            base.vertices[2] - base.vertices[1]
        )
        self.polygons: List[Polygon] = [self.base]
        self.windows: List[Surface] = []
        self._modifier: str = "void"
        self._identifier: str = "void"
        self._primitives: Optional[List[pr.Primitive]] = None

    @property
    def modifier(self):
        """."""
        return self._modifier

    @property
    def identifier(self):
        """."""
        return self._identifier

    @modifier.setter
    def modifier(self, mod):
        """."""
        self._modifier = mod

    @identifier.setter
    def identifier(self, identifier):
        """."""
        self._identifier = identifier

    @property
    def primitives(self) -> Optional[List[pr.Primitive]]:
        """."""
        self._primitives = []
        for idx, polygon in enumerate(self.polygons):
            self._primitives.append(
                pr.Primitive(
                    self.modifier,
                    "polygon",
                    f"{self.identifier}_{idx:02d}",
                    [],
                    polygon.coordinates,
                )
            )
        return self._primitives

    def make_window_wwr(self, wwr: float) -> None:
        """Make a window based on window-to-wall ratio."""
        window_polygon = self.base.scale(np.array((wwr, wwr, wwr)), self.base.centroid)
        self.base = self.base - window_polygon
        self.windows.append(Surface(window_polygon))

    def make_window(
        self, dist_left: float, dist_bot: float, width: float, height: float
    ) -> None:
        """Make a window and punch a hole."""
        win_pt1 = self._vertices[0] + self._vect1 * dist_bot + self._vect2 * dist_left
        win_pt2 = win_pt1 + self._vect1 * height
        win_pt3 = win_pt1 + self._vect2 * width
        window_polygon = Polygon.rectangle3pts(win_pt3, win_pt1, win_pt2)
        self.base = self.base - window_polygon
        self.windows.append(Surface(window_polygon))

    def thicken(self, thickness: float) -> None:
        """Thicken the surface."""
        direction = self.base.normal * thickness
        polygons = self.base.extrude(direction)
        counts = [polygons.count(plg) for plg in polygons]
        self.polygons = [plg for plg, cnt in zip(polygons, counts) if cnt == 1]

    def move_window(self, distance: float) -> None:
        """Move windows in its normal direction."""
        direction = self.base.normal * distance
        self.windows = [Surface(window.base.move(direction)) for window in self.windows]

    def rotate(self, deg):
        """Rotate the surface counter clock-wise."""
        polygons = []
        center = np.zeros(3)
        zaxis = np.array((0, 0, 1))
        for plg in self.polygons:
            polygons.append(plg.rotate(center, zaxis, deg))
        self.polygons = polygons
        for window in self.windows:
            wpolygons = []
            for plg in window.polygons:
                wpolygons.append(plg.rotate(center, zaxis, deg))


class Room:
    """Make a shoebox."""

    def __init__(
        self,
        floor: Surface,
        ceiling: Surface,
        swall: Surface,
        ewall: Surface,
        nwall: Surface,
        wwall: Surface,
    ) -> None:
        """."""
        self.floor = floor
        self.ceiling = ceiling
        self.swall = swall
        self.ewall = ewall
        self.nwall = nwall
        self.wwall = wwall
        self.materials = utils.material_lib()

    @classmethod
    def from_wdh(
        cls,
        width: float,
        depth: float,
        floor_floor: float,
        floor_ceiling: float,
        origin: Optional[np.ndarray] = None,
    ) -> "Room":
        """Generate a room from width, depth, and height."""
        pt1 = np.array((0, 0, 0)) if origin is None else origin
        pt2 = pt1 + np.array((width, 0, 0))
        pt3 = pt2 + np.array((0, depth, 0))
        floor = Polygon.rectangle3pts(pt1, pt2, pt3)
        _, ceiling, swall, ewall, nwall, wwall = floor.extrude(
            np.array((0, 0, floor_floor))
        )
        ceiling = ceiling.move(np.array((0, 0, floor_ceiling - floor_floor)))
        return cls(
            Surface(floor),
            Surface(ceiling),
            Surface(swall),
            Surface(ewall),
            Surface(nwall),
            Surface(wwall),
        )

    @property
    def primitives(self):
        """."""
        return [
            *self.materials.values(),
            *self.floor.primitives,
            *self.ceiling.primitives,
            *self.swall.primitives,
            *self.ewall.primitives,
            *self.nwall.primitives,
            *self.wwall.primitives,
        ]

    @property
    def window_primitives(self):
        """."""
        return [
            *[prim for srf in self.ceiling.windows for prim in srf.primitives],
            *[prim for srf in self.swall.windows for prim in srf.primitives],
            *[prim for srf in self.ewall.windows for prim in srf.primitives],
            *[prim for srf in self.nwall.windows for prim in srf.primitives],
            *[prim for srf in self.wwall.windows for prim in srf.primitives],
        ]

    def get_material_names(self) -> List[str]:
        """Get material identifiers."""
        return [prim.identifier for prim in self.materials.values()]

    def add_material(self, primitive) -> None:
        """Add a material to the material library."""
        self.materials[primitive.identifier] = primitive

    def validate(self) -> None:
        """Validate the room model."""
        for prim in [
            *self.floor.primitives,
            *self.ceiling.primitives,
            *self.swall.primitives,
            *self.ewall.primitives,
            *self.nwall.primitives,
            *self.wwall.primitives,
        ]:
            if prim.modifier not in self.materials:
                raise ValueError(
                    f"Unknown modifier {prim.modifier} in {prim.identifier}"
                )

    def rotate(self, deg):
        """Rotate the room counter clock-wise."""
        self.floor.rotate(deg)
        self.ceiling.rotate(deg)
        self.swall.rotate(deg)
        self.ewall.rotate(deg)
        self.wwall.rotate(deg)
        self.nwall.rotate(deg)


def make_room(
    width: float,
    depth: float,
    floor_floor: float,
    floor_ceiling: float,
    windows,
    swall_thickness=None,
):
    """Make a side-lit shoebox room as a Room object."""
    aroom = Room.from_wdh(width, depth, floor_floor, floor_ceiling)
    if windows is not None:
        for window in windows:
            aroom.swall.make_window(*window)
        for window in aroom.swall.windows:
            window.modifier = "glass_60"
    if swall_thickness is not None:
        aroom.swall.thicken(swall_thickness)
    aroom.swall.modifier = "neutral_lambertian_0.5"
    aroom.ewall.modifier = "neutral_lambertian_0.5"
    aroom.nwall.modifier = "neutral_lambertian_0.5"
    aroom.wwall.modifier = "neutral_lambertian_0.5"
    aroom.ceiling.modifier = "neutral_lambertian_0.7"
    aroom.floor.modifier = "neutral_lambertian_0.2"
    return aroom
