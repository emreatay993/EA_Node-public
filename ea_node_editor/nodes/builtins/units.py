# Purpose: Declare strict COREX quantity and unit-system value contracts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_unit_types.py

from __future__ import annotations

import math
from types import MappingProxyType
from typing import Mapping

from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.runtime_contracts import DataTypeFamilySpec, DataTypeSpec

COREX_UNITS_OWNER_ID = "corex.units"
COREX_UNITS_OWNER_VERSION = "1"
IQUANTITY_DATA_TYPE_ID = "COREX.DataTypes.Units.IQuantity"
LENGTH_DATA_TYPE_ID = "COREX.DataTypes.Units.Length"
PLANE_ANGLE_DATA_TYPE_ID = "COREX.DataTypes.Units.PlaneAngle"
QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID = (
    "COREX.DataTypes.Units.Quantifiable`2[[COREX.DataTypes.Interval1D],"
    "[COREX.DataTypes.Units.LengthUnit]]"
)
TIME_DATA_TYPE_ID = "COREX.DataTypes.Units.Time"
UNIT_SYSTEM_DATA_TYPE_ID = "COREX.DataTypes.Units.UnitSystem"

LENGTH_UNIT_NAMES = frozenset(
    {
        "Meter",
        "Nanometer",
        "Micrometer",
        "Millimeter",
        "Centimeter",
        "Decimeter",
        "Decameter",
        "Hectometer",
        "Kilometer",
        "Megameter",
        "Gigameter",
        "Microinch",
        "Thou",
        "Mil",
        "Inch",
        "Foot",
        "Yard",
        "Mile",
        "Angstrom",
    }
)
PLANE_ANGLE_UNIT_NAMES = frozenset(
    {
        "Radian",
        "Degree",
        "Arcminute",
        "Arcsecond",
        "Gradian",
        "PiRadian",
        "Turn",
    }
)
TIME_UNIT_NAMES = frozenset(
    {
        "Second",
        "Nanosecond",
        "Microsecond",
        "Millisecond",
        "Minute",
        "Hour",
        "Day",
    }
)
UNIT_SYSTEM_IDENTIFIERS = frozenset(
    {
        "MmTS",
        "MKgS",
        "MmGS",
        "MmKgS",
        "MmKgMs",
        "CmGS",
        "InLbfsspinS",
        "FtSlugS",
    }
)

UNIT_SYSTEM_DERIVED_UNIT_ENUMS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "Area": frozenset(
            {
                "SquareMeter",
                "SquareNanometer",
                "SquareMicrometer",
                "SquareMillimeter",
                "SquareCentimeter",
                "SquareDecimeter",
                "SquareDecameter",
                "SquareHectometer",
                "SquareKilometer",
                "SquareMegameter",
                "SquareGigameter",
                "Hectare",
                "SquareInch",
                "SquareFoot",
                "SquareYard",
                "Acre",
                "SquareMile",
            }
        ),
        "Density": frozenset(
            {
                "KilogramPerCubicMeters",
                "TonnePerCubicMillimeters",
                "GramPerCubicMillimeters",
                "KilogramPerCubicMillimeters",
                "GramPerCubicCentimeters",
                "PoundForceSquareSecondPerInchPerCubicInches",
                "SlugPerCubicFoot",
            }
        ),
        "Energy": frozenset(
            {
                "Joule",
                "Nanojoule",
                "Microjoule",
                "Millijoule",
                "Centijoule",
                "Decijoule",
                "Decajoule",
                "Hectojoule",
                "Kilojoule",
                "Megajoule",
                "Gigajoule",
                "Erg",
                "DyneCentimeter",
                "StheneMeter",
                "KilogramForceMeter",
                "KilopondMeter",
                "FootPoundForce",
                "FootPoundal",
                "Calorie",
                "Kilocalorie",
                "Megacalorie",
                "Btu",
                "Kilobtu",
                "Megabtu",
                "InchPoundForce",
            }
        ),
        "Force": frozenset(
            {
                "Newton",
                "Nanonewton",
                "Micronewton",
                "Millinewton",
                "Centinewton",
                "Decinewton",
                "Decanewton",
                "Hectonewton",
                "Kilonewton",
                "Meganewton",
                "Giganewton",
                "Dyne",
                "Sthene",
                "KilogramForce",
                "Kilopond",
                "PoundForce",
                "KilopoundForce",
                "Poundal",
                "Kilopound",
            }
        ),
        "Frequency": frozenset(
            {
                "Hertz",
                "Megahertz",
                "Kilohertz",
                "Gigahertz",
                "Microhertz",
                "Millihertz",
            }
        ),
        "HeatCapacity": frozenset(
            {
                "JoulePerKelvin",
                "NanojoulePerKelvin",
                "MicrojoulePerKelvin",
                "MillijoulePerKelvin",
                "CentijoulePerKelvin",
                "DecijoulePerKelvin",
                "DecajoulePerKelvin",
                "HectojoulePerKelvin",
                "KilojoulePerKelvin",
                "MegajoulePerKelvin",
                "GigajoulePerKelvin",
                "ErgPerKelvin",
                "FootPoundForcePerKelvin",
                "InchPoundForcePerKelvin",
            }
        ),
        "HeatFlux": frozenset(
            {
                "WattPerSquareMeter",
                "NanowattPerSquareMeter",
                "MicrowattPerSquareMeter",
                "MilliwattPerSquareMeter",
                "CentiwattPerSquareMeter",
                "DeciwattPerSquareMeter",
                "DecawattPerSquareMeter",
                "HectowattPerSquareMeter",
                "KilowattPerSquareMeter",
                "MegawattPerSquareMeter",
                "GigawattPerSquareMeter",
                "PoundForcePerSecondPerFoot",
                "PoundalPerSecondPerFoot",
                "PoundMassPerCubicSecond",
                "PoundPerCubicSecond",
                "SlugPerCubicSecond",
                "BtuPerSecondPerSquareFoot",
                "BtuPerHourPerSquareFoot",
                "PoundForcePerSecondPerInch",
            }
        ),
        "HeatTransferCoefficient": frozenset(
            {
                "WattPerSquareMeterPerKelvin",
                "NanowattPerSquareMeterPerKelvin",
                "MicrowattPerSquareMeterPerKelvin",
                "MilliwattPerSquareMeterPerKelvin",
                "CentiwattPerSquareMeterPerKelvin",
                "DeciwattPerSquareMeterPerKelvin",
                "DecawattPerSquareMeterPerKelvin",
                "HectowattPerSquareMeterPerKelvin",
                "KilowattPerSquareMeterPerKelvin",
                "MegawattPerSquareMeterPerKelvin",
                "GigawattPerSquareMeterPerKelvin",
                "WattPerSquareMeterPerDegreeCelsius",
                "CaloriePerHourPerSquareMeterPerDegreeCelsius",
                "KilocaloriePerHourPerSquareMeterPerDegreeCelsius",
                "BtuPerHourPerSquareFootPerDegreeFahrenheit",
                "PoundForcePerSecondPerFootPerKelvin",
                "PoundForcePerSecondPerInchPerKelvin",
            }
        ),
        "Moment": frozenset(
            {
                "NewtonMeter",
                "NanonewtonMeter",
                "MicronewtonMeter",
                "MillinewtonMeter",
                "CentinewtonMeter",
                "DecinewtonMeter",
                "DecanewtonMeter",
                "HectonewtonMeter",
                "KilonewtonMeter",
                "MeganewtonMeter",
                "GiganewtonMeter",
                "DyneCentimeter",
                "StheneMeter",
                "KilogramForceMeter",
                "KilopondMeter",
                "PoundForceFoot",
                "KilopoundForceFoot",
                "PoundalFoot",
                "KilopoundFoot",
                "PoundForceInch",
            }
        ),
        "Power": frozenset(
            {
                "Watt",
                "Nanowatt",
                "Microwatt",
                "Milliwatt",
                "Centiwatt",
                "Deciwatt",
                "Decawatt",
                "Hectowatt",
                "Kilowatt",
                "Megawatt",
                "Gigawatt",
                "ErgPerSecond",
                "StheneMeterPerSecond",
                "KilopondMeterPerSecond",
                "MetricHorsepower",
                "FootPoundForcePerSecond",
                "FootPoundalPerSecond",
                "MechanicalHorsepower",
                "BtuPerHour",
                "KilobtuPerHour",
                "MegabtuPerHour",
                "InchPoundForcePerSecond",
            }
        ),
        "Pressure": frozenset(
            {
                "Pascal",
                "Nanopascal",
                "Micropascal",
                "Millipascal",
                "Centipascal",
                "Decipascal",
                "Decapascal",
                "Hectopascal",
                "Kilopascal",
                "Megapascal",
                "Gigapascal",
                "Microbar",
                "Millibar",
                "Centibar",
                "Decibar",
                "Bar",
                "Decabar",
                "Hectobar",
                "Kilobar",
                "Megabar",
                "Barye",
                "Pieze",
                "KilogramForcePerSquareCentimeter",
                "KilopondPerSquareCentimeter",
                "TechnicalAtmosphere",
                "PoundForcePerSquareInch",
                "PoundForcePerSquareFoot",
                "KilopoundForcePerSquareInch",
                "KilopoundForcePerSquareFoot",
                "PoundalPerSquareFoot",
                "Atmosphere",
            }
        ),
        "SpecificHeatCapacity": frozenset(
            {
                "JoulePerKilogramPerKelvin",
                "NanojoulePerKilogramPerKelvin",
                "MicrojoulePerKilogramPerKelvin",
                "MillijoulePerKilogramPerKelvin",
                "CentijoulePerKilogramPerKelvin",
                "DecijoulePerKilogramPerKelvin",
                "DecajoulePerKilogramPerKelvin",
                "HectojoulePerKilogramPerKelvin",
                "KilojoulePerKilogramPerKelvin",
                "MegajoulePerKilogramPerKelvin",
                "GigajoulePerKilogramPerKelvin",
                "ErgPerGramPerKelvin",
                "FootPoundForcePerSlugPerKelvin",
                "SquareInchPerSquareSecondPerKelvin",
            }
        ),
        "Stiffness": frozenset(
            {
                "NewtonPerMeter",
                "NanonewtonPerMeter",
                "MicronewtonPerMeter",
                "MillinewtonPerMeter",
                "CentinewtonPerMeter",
                "DecinewtonPerMeter",
                "DecanewtonPerMeter",
                "HectonewtonPerMeter",
                "KilonewtonPerMeter",
                "MeganewtonPerMeter",
                "GiganewtonPerMeter",
                "DynePerCentimeter",
                "SthenePerMeter",
                "KilogramForcePerMeter",
                "KilopondPerMeter",
                "PoundForcePerFoot",
                "KilopoundForcePerFoot",
                "PoundalPerFoot",
                "KilopoundPerFoot",
                "PoundForcePerInch",
            }
        ),
        "Stress": frozenset(
            {
                "Pascal",
                "Nanopascal",
                "Micropascal",
                "Millipascal",
                "Centipascal",
                "Decipascal",
                "Decapascal",
                "Hectopascal",
                "Kilopascal",
                "Megapascal",
                "Gigapascal",
                "KilogramForcePerSquareCentimeter",
                "KilopondPerSquareCentimeter",
                "PoundForcePerSquareInch",
                "PoundForcePerSquareFoot",
                "KilopoundForcePerSquareInch",
                "KilopoundForcePerSquareFoot",
                "PoundalPerSquareFoot",
                "DynePerSquareCentimeters",
            }
        ),
        "Torque": frozenset(
            {
                "NewtonMeter",
                "NanonewtonMeter",
                "MicronewtonMeter",
                "MillinewtonMeter",
                "CentinewtonMeter",
                "DecinewtonMeter",
                "DecanewtonMeter",
                "HectonewtonMeter",
                "KilonewtonMeter",
                "MeganewtonMeter",
                "GiganewtonMeter",
                "DyneCentimeter",
                "StheneMeter",
                "KilogramForceMeter",
                "KilopondMeter",
                "PoundForceFoot",
                "KilopoundForceFoot",
                "PoundalFoot",
                "KilopoundFoot",
                "PoundForceInch",
            }
        ),
        "Volume": frozenset(
            {
                "CubicMeter",
                "CubicNanometer",
                "CubicMicrometer",
                "CubicMillimeter",
                "CubicCentimeter",
                "CubicDecimeter",
                "CubicDecameter",
                "CubicHectometer",
                "CubicKilometer",
                "CubicMegameter",
                "CubicGigameter",
                "Liter",
                "CubicInch",
                "CubicFoot",
                "CubicYard",
                "CubicMile",
            }
        ),
    }
)

_QUANTITY_PAYLOAD_KEYS = frozenset({"value", "unit"})
_QUANTIFIABLE_PAYLOAD_KEYS = frozenset({"data", "unit"})
_INTERVAL_PAYLOAD_KEYS = frozenset({"start", "end"})
_UNIT_SYSTEM_PAYLOAD_KEYS = frozenset({"identifier", "derived_units"})
_UNIT_SYSTEM_DERIVED_UNIT_KEYS = frozenset(UNIT_SYSTEM_DERIVED_UNIT_ENUMS)


def _is_finite_float(value: object) -> bool:
    return type(value) is float and math.isfinite(value)


def _has_exact_keys(value: object, expected: frozenset[str]) -> bool:
    return (
        type(value) is dict
        and len(value) == len(expected)
        and all(type(key) is str and key in expected for key in value)
    )


def _is_quantity_payload(
    value: object,
    unit_names: frozenset[str],
) -> bool:
    return (
        _has_exact_keys(value, _QUANTITY_PAYLOAD_KEYS)
        and _is_finite_float(value["value"])
        and type(value["unit"]) is str
        and value["unit"] in unit_names
    )


def is_length_payload(value: object) -> bool:
    return _is_quantity_payload(value, LENGTH_UNIT_NAMES)


def is_plane_angle_payload(value: object) -> bool:
    return _is_quantity_payload(value, PLANE_ANGLE_UNIT_NAMES)


def is_time_payload(value: object) -> bool:
    return _is_quantity_payload(value, TIME_UNIT_NAMES)


def is_quantifiable_interval_length_payload(value: object) -> bool:
    if (
        not _has_exact_keys(value, _QUANTIFIABLE_PAYLOAD_KEYS)
        or type(value["unit"]) is not str
        or value["unit"] not in LENGTH_UNIT_NAMES
    ):
        return False
    data = value["data"]
    return (
        _has_exact_keys(data, _INTERVAL_PAYLOAD_KEYS)
        and _is_finite_float(data["start"])
        and _is_finite_float(data["end"])
    )


def is_unit_system_payload(value: object) -> bool:
    if (
        not _has_exact_keys(value, _UNIT_SYSTEM_PAYLOAD_KEYS)
        or type(value["identifier"]) is not str
        or value["identifier"] not in UNIT_SYSTEM_IDENTIFIERS
    ):
        return False
    derived_units = value["derived_units"]
    if not _has_exact_keys(derived_units, _UNIT_SYSTEM_DERIVED_UNIT_KEYS):
        return False
    return all(
        type(derived_units[property_name]) is str
        and derived_units[property_name] in enum_names
        for property_name, enum_names in UNIT_SYSTEM_DERIVED_UNIT_ENUMS.items()
    )


COREX_UNITS_DATA_TYPE_FAMILIES = (
    DataTypeFamilySpec("units", "COREX Units", "data.engineering", "data"),
)

COREX_UNITS_DATA_TYPES = (
    DataTypeSpec(
        IQUANTITY_DATA_TYPE_ID,
        "Physical Quantity",
        "units",
        lambda _value: False,
        parents=(GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"inline"}),
        persistence="never",
    ),
    DataTypeSpec(
        LENGTH_DATA_TYPE_ID,
        "Length",
        "units",
        is_length_payload,
        parents=(IQUANTITY_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
    ),
    DataTypeSpec(
        PLANE_ANGLE_DATA_TYPE_ID,
        "Plane Angle",
        "units",
        is_plane_angle_payload,
        parents=(IQUANTITY_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
    ),
    DataTypeSpec(
        QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID,
        "Length Interval",
        "units",
        is_quantifiable_interval_length_payload,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
    ),
    DataTypeSpec(
        TIME_DATA_TYPE_ID,
        "Time",
        "units",
        is_time_payload,
        parents=(IQUANTITY_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
    ),
    DataTypeSpec(
        UNIT_SYSTEM_DATA_TYPE_ID,
        "Unit System",
        "units",
        is_unit_system_payload,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
    ),
)

COREX_UNITS_CONTRACT_MANIFEST = PluginContractManifest(
    data_type_families=COREX_UNITS_DATA_TYPE_FAMILIES,
    data_types=COREX_UNITS_DATA_TYPES,
)

__all__ = [
    "IQUANTITY_DATA_TYPE_ID",
    "LENGTH_DATA_TYPE_ID",
    "LENGTH_UNIT_NAMES",
    "PLANE_ANGLE_DATA_TYPE_ID",
    "PLANE_ANGLE_UNIT_NAMES",
    "QUANTIFIABLE_INTERVAL_LENGTH_DATA_TYPE_ID",
    "COREX_UNITS_CONTRACT_MANIFEST",
    "COREX_UNITS_DATA_TYPE_FAMILIES",
    "COREX_UNITS_DATA_TYPES",
    "COREX_UNITS_OWNER_ID",
    "COREX_UNITS_OWNER_VERSION",
    "TIME_DATA_TYPE_ID",
    "TIME_UNIT_NAMES",
    "UNIT_SYSTEM_DATA_TYPE_ID",
    "UNIT_SYSTEM_DERIVED_UNIT_ENUMS",
    "UNIT_SYSTEM_IDENTIFIERS",
    "is_length_payload",
    "is_plane_angle_payload",
    "is_quantifiable_interval_length_payload",
    "is_time_payload",
    "is_unit_system_payload",
]
