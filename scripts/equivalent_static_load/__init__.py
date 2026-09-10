"""Equivalent Static Load (ESL) derivation tool.

Derives static rig actuator loads that reproduce the critical dynamic stress
state of an MSUP transient (blade-out secondary vibrations) in the virtual rig
FE model. Methodology: MyLife knowledge base,
``work/methodology-equivalent-static-loads.md``.

Companion tools in this scripts folder:
- ``mcf_dpf_section_resultants`` — Route A (dynamic interface resultants);
  its ``parse_mcf`` is reused here for modal-coordinate input.
"""

from __future__ import annotations

__version__ = "0.1.0"
