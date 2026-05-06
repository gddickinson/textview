"""A small example used to verify Python syntax highlighting."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


def centroid(points: Iterable[Point]) -> Point:
    pts = list(points)
    if not pts:
        raise ValueError("need at least one point")
    return Point(
        x=sum(p.x for p in pts) / len(pts),
        y=sum(p.y for p in pts) / len(pts),
    )


if __name__ == "__main__":
    triangle = [Point(0, 0), Point(4, 0), Point(2, 3)]
    print(f"centroid = {centroid(triangle)}")
