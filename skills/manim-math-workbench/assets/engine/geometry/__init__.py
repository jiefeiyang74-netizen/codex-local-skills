"""Declarative geometry-1.0 engine; math utilities do not require Manim."""
from .math2d import resolve_points, evaluate_checks

__all__ = ["resolve_points", "evaluate_checks", "GeometryScene"]

def __getattr__(name):
    if name == "GeometryScene":
        from .runtime import GeometryScene
        return GeometryScene
    raise AttributeError(name)
