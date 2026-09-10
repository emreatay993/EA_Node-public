"""Dependency-free public function plugin used by the novice tutorial."""

import corex


@corex.node(
    id="custom.strain_conditioner.a7c31e9b",
    name="Strain Conditioner",
    category=("Custom", "Mechanical"),
    description="Convert engineering strain into a scaled display value.",
    keywords=("strain", "microstrain", "conditioning"),
)
@corex.number(
    "strain",
    default=0.000037,
    label="Engineering strain",
    description="Dimensionless engineering strain.",
    section="Input",
    port=True,
)
@corex.number(
    "scale",
    default=1000000.0,
    minimum=1.0,
    label="Scale",
    description="Multiplier applied to engineering strain.",
    section="Conditioning",
)
@corex.switch(
    "absolute",
    default=False,
    label="Absolute value",
    section="Conditioning",
    port=True,
)
@corex.output(
    "conditioned_strain",
    value_type=float,
    label="Conditioned strain",
)
def strain_conditioner(ctx, settings):
    strain = float(settings.strain)
    if abs(strain) > 0.1:
        ctx.warn(
            "Engineering strain magnitude is above 0.1.",
            code="large_strain",
        )
    if settings.absolute:
        strain = abs(strain)
    return {"conditioned_strain": strain * settings.scale}
