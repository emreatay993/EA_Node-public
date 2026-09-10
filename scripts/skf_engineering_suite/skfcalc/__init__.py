"""SKF Engineering Bearing Suite calculation package."""

from .models import *  # noqa: F401,F403
from .solver import solve_case

__all__ = ["solve_case"]
__version__ = "1.0.0"
