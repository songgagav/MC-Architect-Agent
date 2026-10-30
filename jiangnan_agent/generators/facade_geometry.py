"""Face-local geometry, opening reservations, and explicit block ownership."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..core.geometry import BoundingBox, Position
from ..core.scene import VoxelModel
from .facade_profiles import FacadeOpening, WallPanelProfile

_FACES = frozenset({"front", "rear", "left", "right"})
_OPENING_KINDS = frozenset({"door", "window"})


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}")
    return value


def _signed_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _position(value: object, name: str = "position") -> Position:
    if (
        not isinstance(value, tuple)
        or len(value) != 3
        or any(isinstance(part, bool) or not isinstance(part, int) for part in value)
    ):
        raise ValueError(f"{name} must contain three integer coordinates")
    return value


@dataclass(frozen=True)
class FaceBasis:
    """Local horizontal axis, vertical axis, and outward world normal."""

    face: str
    tangent_axis: int
    outward_normal: Position
    vertical_axis: Position = (0, 1, 0)


_FACE_BASES: Mapping[str, FaceBasis] = MappingProxyType(
    {
        "front": FaceBasis("front", 0, (0, 0, 1)),
        "rear": FaceBasis("rear", 0, (0, 0, -1)),
        "left": FaceBasis("left", 2, (-1, 0, 0)),
        "right": FaceBasis("right", 2, (1, 0, 0)),
    }
)


def face_basis(face: str) -> FaceBasis:
    try:
        return _FACE_BASES[face]
    except (KeyError, TypeError) as exc:
        raise ValueError("face must be front, rear, left, or right") from exc


def point_on_face(
    face: str,
    *,
    along: int,
    y: int,
    plane: int,
    outward_offset: int = 0,
) -> Position:
    """Map face-local coordinates to X/Y/Z; positive normal offset is outward."""

    basis = face_basis(face)
    along = _signed_integer(along, "along")
    y = _signed_integer(y, "y")
    plane = _signed_integer(plane, "plane")
    outward_offset = _integer(outward_offset, "outward_offset")
    values = [0, y, 0]
    values[basis.tangent_axis] = along
    normal_axis = next(index for index, component in enumerate(basis.outward_normal) if component)
    values[normal_axis] = plane + outward_offset * basis.outward_normal[normal_axis]
    return tuple(values)  # type: ignore[return-value]


@dataclass(frozen=True)
class FaceSegmentBounds:
    """One wall panel between a particular adjacent pair of supporting posts."""

    face: str
    segment_index: int
    bounds: BoundingBox

    def __post_init__(self) -> None:
        basis = face_basis(self.face)
        _integer(self.segment_index, "segment_index")
        if not isinstance(self.bounds, BoundingBox) or any(size <= 0 for size in self.bounds.size):
            raise ValueError("segment bounds must have positive width, height, and depth")
        normal_axis = 2 if basis.tangent_axis == 0 else 0
        if self.bounds.size[normal_axis] != 1:
            raise ValueError("face segment bounds must be exactly one block thick")


def build_facade_segments(
    face: str,
    bounds: BoundingBox,
    post_positions: Iterable[int],
) -> tuple[FaceSegmentBounds, ...]:
    """Build panels from real post coordinates, excluding both post columns."""

    basis = face_basis(face)
    if not isinstance(bounds, BoundingBox) or any(size <= 0 for size in bounds.size):
        raise ValueError("façade bounds must have positive width, height, and depth")
    normal_axis = 2 if basis.tangent_axis == 0 else 0
    if bounds.size[normal_axis] != 1:
        raise ValueError("façade bounds must be one block thick along their normal")
    posts = tuple(post_positions)
    if len(posts) < 2 or any(isinstance(value, bool) or not isinstance(value, int) for value in posts):
        raise ValueError("post_positions must contain at least two integer coordinates")
    if tuple(sorted(set(posts))) != posts:
        raise ValueError("post_positions must be unique and sorted")
    low = (bounds.min_x, bounds.min_y, bounds.min_z)[basis.tangent_axis]
    high = (bounds.max_x, bounds.max_y, bounds.max_z)[basis.tangent_axis]
    if posts[0] < low or posts[-1] >= high:
        raise ValueError("post positions must lie within the façade bounds")

    segments: list[FaceSegmentBounds] = []
    for index, (start, end) in enumerate(zip(posts, posts[1:])):
        if end - start <= 1:
            continue
        values = [
            bounds.min_x,
            bounds.min_y,
            bounds.min_z,
            bounds.max_x,
            bounds.max_y,
            bounds.max_z,
        ]
        min_index, max_index = basis.tangent_axis, basis.tangent_axis + 3
        values[min_index] = start + 1
        values[max_index] = end
        segments.append(FaceSegmentBounds(face, index, BoundingBox(*values)))
    return tuple(segments)


def resolve_facade_opening(
    opening: FacadeOpening,
    segment_bounds: FaceSegmentBounds,
    *,
    width: int,
    height: int,
) -> BoundingBox:
    """Resolve an opening's segment-relative offset into a half-open block box."""

    if not isinstance(opening, FacadeOpening):
        raise ValueError("opening must be a FacadeOpening")
    if not isinstance(segment_bounds, FaceSegmentBounds):
        raise ValueError("segment_bounds must be a FaceSegmentBounds")
    if opening.face != segment_bounds.face or opening.segment_index != segment_bounds.segment_index:
        raise ValueError("opening face or segment_index does not match segment bounds")
    width = _integer(width, "opening width", minimum=1)
    height = _integer(height, "opening height", minimum=1)
    basis = face_basis(opening.face)
    values = [
        segment_bounds.bounds.min_x,
        segment_bounds.bounds.min_y,
        segment_bounds.bounds.min_z,
        segment_bounds.bounds.max_x,
        segment_bounds.bounds.max_y,
        segment_bounds.bounds.max_z,
    ]
    min_index, max_index = basis.tangent_axis, basis.tangent_axis + 3
    along_start = values[min_index] + opening.offset
    along_end = along_start + width
    y_start = segment_bounds.bounds.min_y + opening.sill_offset
    y_end = y_start + height
    if along_end > values[max_index]:
        raise ValueError("opening width extends beyond its post segment")
    if y_end > segment_bounds.bounds.max_y:
        raise ValueError("opening height extends beyond its wall panel")
    values[min_index], values[max_index] = along_start, along_end
    values[1], values[4] = y_start, y_end
    return BoundingBox(*values)


def wall_layer_bounds(
    base_bounds: BoundingBox,
    face: str,
    *,
    thickness: int,
    expand_direction: str,
) -> tuple[BoundingBox, ...]:
    """Return one-block wall layers starting at the reference plane and expanding."""

    basis = face_basis(face)
    thickness = _integer(thickness, "thickness", minimum=1)
    if expand_direction not in {"inward", "outward"}:
        raise ValueError("expand_direction must be inward or outward")
    if not isinstance(base_bounds, BoundingBox) or any(size <= 0 for size in base_bounds.size):
        raise ValueError("base wall bounds must have positive width, height, and depth")
    normal_axis = 2 if basis.tangent_axis == 0 else 0
    if base_bounds.size[normal_axis] != 1:
        raise ValueError("base wall bounds must be one block thick along the face normal")
    normal_sign = basis.outward_normal[normal_axis]
    direction_sign = normal_sign if expand_direction == "outward" else -normal_sign
    layers: list[BoundingBox] = []
    for layer_index in range(thickness):
        delta = direction_sign * layer_index
        shift = [0, 0, 0]
        shift[normal_axis] = delta
        layers.append(base_bounds.translated(*shift))
    return tuple(layers)


@dataclass(frozen=True)
class OpeningReservation:
    opening_id: str
    kind: str


class OpeningMask:
    """Explicit per-block opening reservations with a matching component identity."""

    def __init__(self) -> None:
        self._cells: dict[Position, OpeningReservation] = {}
        self._kinds: dict[str, str] = {}

    def reserve(self, opening_id: str, kind: str, bounds: BoundingBox) -> None:
        if not isinstance(opening_id, str) or not opening_id.strip():
            raise ValueError("opening_id must be a non-empty string")
        if kind not in _OPENING_KINDS:
            raise ValueError("opening kind must be door or window")
        if not isinstance(bounds, BoundingBox) or any(size <= 0 for size in bounds.size):
            raise ValueError("opening reservation bounds must have positive dimensions")
        reservation = OpeningReservation(opening_id.strip(), kind)
        existing_kind = self._kinds.get(reservation.opening_id)
        if existing_kind is not None and existing_kind != reservation.kind:
            raise ValueError(f"opening {reservation.opening_id!r} cannot reserve multiple component kinds")
        positions = tuple(
            (x, y, z)
            for y in range(bounds.min_y, bounds.max_y)
            for z in range(bounds.min_z, bounds.max_z)
            for x in range(bounds.min_x, bounds.max_x)
        )
        conflicts = [
            position
            for position in positions
            if position in self._cells and self._cells[position] != reservation
        ]
        if conflicts:
            raise ValueError(f"opening mask overlaps another reservation at {min(conflicts)}")
        for position in positions:
            self._cells[position] = reservation
        self._kinds[reservation.opening_id] = reservation.kind

    def contains(self, position: Position) -> bool:
        return _position(position) in self._cells

    def reservation_at(self, position: Position) -> OpeningReservation | None:
        return self._cells.get(_position(position))

    @property
    def positions(self) -> frozenset[Position]:
        return frozenset(self._cells)


@dataclass(frozen=True)
class BlockClaim:
    owner: str
    replaceable_by: frozenset[str] = frozenset()
    protected: bool = False


class BlockOwnershipMap:
    """Tracks cell owners and requires explicit replacement or opening permission."""

    def __init__(self, *, opening_mask: OpeningMask | None = None) -> None:
        if opening_mask is not None and not isinstance(opening_mask, OpeningMask):
            raise ValueError("opening_mask must be an OpeningMask")
        self.opening_mask = opening_mask or OpeningMask()
        self._claims: dict[Position, BlockClaim] = {}
        self._protected: dict[Position, str] = {}

    @staticmethod
    def _owner(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty owner role")
        return value.strip()

    def protect(self, position: Position, purpose: str) -> None:
        position = _position(position)
        purpose = self._owner(purpose, "protection purpose")
        if position in self._claims:
            raise ValueError(f"cannot protect already claimed cell {position}")
        self._protected[position] = purpose

    def protect_bounds(self, bounds: BoundingBox, purpose: str) -> None:
        if not isinstance(bounds, BoundingBox) or any(size < 0 for size in bounds.size):
            raise ValueError("protected bounds must be a BoundingBox")
        for y in range(bounds.min_y, bounds.max_y):
            for z in range(bounds.min_z, bounds.max_z):
                for x in range(bounds.min_x, bounds.max_x):
                    self.protect((x, y, z), purpose)

    def allow_replacement(self, position: Position, owner: str) -> None:
        position = _position(position)
        owner = self._owner(owner, "replacement owner")
        claim = self._claims.get(position)
        if claim is None or claim.owner != "wall":
            raise ValueError("replacement permission can only be added to a claimed wall cell")
        if self.opening_mask.contains(position):
            raise ValueError("reserved opening cells cannot be made decoration replacement cells")
        self._claims[position] = BlockClaim(claim.owner, claim.replaceable_by | {owner}, claim.protected)

    def claim(
        self,
        position: Position,
        owner: str,
        *,
        replaceable_by: Iterable[str] = (),
        protected: bool = False,
        opening_id: str | None = None,
        replaces: str | None = None,
    ) -> None:
        position = _position(position)
        owner = self._owner(owner, "block owner")
        roles = frozenset(self._owner(item, "replaceable owner") for item in replaceable_by)
        if not isinstance(protected, bool):
            raise ValueError("protected must be a boolean")
        if position in self._protected:
            raise ValueError(f"cell {position} is protected for {self._protected[position]}")
        reservation = self.opening_mask.reservation_at(position)
        if reservation is not None:
            if owner != reservation.kind or opening_id != reservation.opening_id:
                raise ValueError(f"cell {position} is reserved opening {reservation.opening_id!r}")
        elif owner in _OPENING_KINDS:
            raise ValueError(f"{owner} component requires a matching reserved opening")
        current = self._claims.get(position)
        if current is not None:
            if current.protected:
                raise ValueError(f"cell {position} is protected by {current.owner}")
            if replaces != current.owner or owner not in current.replaceable_by:
                raise ValueError(f"undeclared replacement or overlap at {position}: {current.owner} vs {owner}")
        elif replaces is not None:
            raise ValueError(f"undeclared replacement at unclaimed cell {position}")
        self._claims[position] = BlockClaim(owner, roles, protected)

    def merge(
        self,
        model: VoxelModel,
        owner: str,
        *,
        protected: bool = False,
        opening_id: str | None = None,
        replaces: str | None = None,
    ) -> None:
        if not isinstance(model, VoxelModel):
            raise ValueError("model must be a VoxelModel")
        previous = dict(self._claims)
        try:
            for position in sorted(model.blocks):
                self.claim(
                    position,
                    owner,
                    protected=protected,
                    opening_id=opening_id,
                    replaces=replaces,
                )
        except Exception:
            self._claims = previous
            raise

    def owner_at(self, position: Position) -> str | None:
        claim = self._claims.get(_position(position))
        return None if claim is None else claim.owner

    def claim_at(self, position: Position) -> BlockClaim | None:
        return self._claims.get(_position(position))
