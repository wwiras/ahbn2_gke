"""K6 stage wiring for the shared experiment controller."""
from __future__ import annotations
import sys
import k6_exp10_tools

# The shared controller retains its legacy import for historical images. K6
# supplies the canonical stage module under that internal import name.
sys.modules["k5_exp10_tools"] = k6_exp10_tools
import controller_shared as controller

if __name__ == "__main__":
    controller.main()
