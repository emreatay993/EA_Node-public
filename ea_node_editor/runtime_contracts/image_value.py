# Purpose: Define strict immutable PNG runtime values.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_image_value.py

from __future__ import annotations

import base64
import hashlib
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ea_node_editor.common.payload_tools import validate_payload_fields
from ea_node_editor.runtime_contracts.data_types import DataTypeCatalogError

if TYPE_CHECKING:
    from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog

IMAGE_VALUE_DATA_TYPE_ID = "COREX.DataTypes.Image"
IMAGE_VALUE_SCHEMA_VERSION = 1
IMAGE_VALUE_MAX_ENCODED_BYTES = 64 * 1024 * 1024
_RUNTIME_VALUE_MARKER_KEY = "__ea_runtime_value__"
_RUNTIME_IMAGE_MARKER_VALUE = "image_value"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IMAGE_VALUE_MAX_PIXELS = 64_000_000
_PNG_DECODE_CHUNK_BYTES = 64 * 1024
_PNG_CHANNELS_BY_COLOR_TYPE = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _png_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 8 or payload[:8] != _PNG_SIGNATURE:
        raise ValueError("encoded_bytes must contain a valid PNG header")
    offset = 8
    dimensions: tuple[int, int] | None = None
    color_type = -1
    seen_plte = False
    seen_idat = False
    idat_closed = False
    row_stride = 0
    expected_decoded_bytes = 0
    decoded_bytes = 0
    decompressor: zlib.Decompress | None = None

    def consume_raster(decoded: bytes) -> None:
        nonlocal decoded_bytes
        if len(decoded) > expected_decoded_bytes - decoded_bytes:
            raise ValueError("PNG decoded raster exceeds the IHDR byte count")
        first_filter = (-decoded_bytes) % row_stride
        for index in range(first_filter, len(decoded), row_stride):
            if decoded[index] > 4:
                raise ValueError("PNG scanline filter byte is invalid")
        decoded_bytes += len(decoded)

    def consume_idat(compressed: bytes | memoryview) -> None:
        if decompressor is None:
            raise ValueError("PNG IDAT decoder is unavailable")
        pending: bytes | memoryview = compressed
        while pending:
            if decompressor.eof:
                raise ValueError("PNG IDAT contains trailing compressed stream data")
            output_limit = max(
                1,
                min(
                    _PNG_DECODE_CHUNK_BYTES,
                    expected_decoded_bytes - decoded_bytes + 1,
                ),
            )
            previous_length = len(pending)
            try:
                decoded = decompressor.decompress(pending, output_limit)
            except zlib.error as exc:
                raise ValueError("PNG IDAT contains invalid zlib data") from exc
            pending = decompressor.unconsumed_tail
            consume_raster(decoded)
            if decompressor.eof:
                if decompressor.unused_data or pending:
                    raise ValueError(
                        "PNG IDAT contains trailing compressed stream data"
                    )
                return
            if not pending:
                return
            if len(pending) == previous_length and not decoded:
                raise ValueError("PNG IDAT decoder made no progress")

    def finish_raster() -> None:
        if decompressor is None:
            raise ValueError("PNG IDAT chunk is missing")
        while not decompressor.eof:
            output_limit = max(
                1,
                min(
                    _PNG_DECODE_CHUNK_BYTES,
                    expected_decoded_bytes - decoded_bytes + 1,
                ),
            )
            try:
                decoded = decompressor.decompress(b"", output_limit)
            except zlib.error as exc:
                raise ValueError("PNG IDAT contains invalid zlib data") from exc
            if not decoded:
                break
            consume_raster(decoded)
        if not decompressor.eof:
            raise ValueError("PNG IDAT zlib stream did not reach EOF")
        if decompressor.unused_data or decompressor.unconsumed_tail:
            raise ValueError("PNG IDAT contains trailing compressed stream data")
        if decoded_bytes != expected_decoded_bytes:
            raise ValueError("PNG decoded raster byte count does not match IHDR")

    while offset < len(payload):
        if len(payload) - offset < 12:
            raise ValueError("PNG chunk is truncated")
        length = int.from_bytes(payload[offset : offset + 4], "big")
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(payload):
            raise ValueError("PNG chunk length exceeds encoded_bytes")
        if (
            len(chunk_type) != 4
            or not all(
                ord("A") <= byte <= ord("Z") or ord("a") <= byte <= ord("z")
                for byte in chunk_type
            )
            or chunk_type[2] & 0x20
        ):
            raise ValueError("PNG chunk type is invalid")
        data = memoryview(payload)[offset + 8 : offset + 8 + length]
        expected_crc = int.from_bytes(payload[offset + 8 + length : chunk_end], "big")
        chunk_crc = zlib.crc32(data, zlib.crc32(chunk_type)) & 0xFFFFFFFF
        if chunk_crc != expected_crc:
            raise ValueError("PNG chunk CRC is invalid")
        if dimensions is None:
            if chunk_type != b"IHDR" or length != 13:
                raise ValueError("PNG IHDR must be the first chunk")
            width = int.from_bytes(data[0:4], "big")
            height = int.from_bytes(data[4:8], "big")
            bit_depth, color_type, compression, filter_method, interlace = data[8:13]
            valid_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if interlace != 0:
                raise ValueError("interlaced PNG images are not supported")
            if (
                width < 1
                or height < 1
                or width * height > _IMAGE_VALUE_MAX_PIXELS
                or bit_depth not in valid_depths.get(color_type, set())
                or compression != 0
                or filter_method != 0
            ):
                raise ValueError("PNG IHDR is invalid or exceeds 64 megapixels")
            dimensions = width, height
            row_bytes = (
                width * _PNG_CHANNELS_BY_COLOR_TYPE[color_type] * bit_depth + 7
            ) // 8
            row_stride = row_bytes + 1
            expected_decoded_bytes = height * row_stride
        elif chunk_type == b"IHDR":
            raise ValueError("PNG contains multiple IHDR chunks")
        elif chunk_type == b"PLTE":
            if (
                seen_plte
                or seen_idat
                or color_type in {0, 4}
                or length < 3
                or length > 768
                or length % 3
            ):
                raise ValueError("PNG PLTE chunk order or length is invalid")
            seen_plte = True
        elif chunk_type == b"IDAT":
            if idat_closed or (color_type == 3 and not seen_plte):
                raise ValueError("PNG IDAT chunk order is invalid")
            seen_idat = True
            if decompressor is None:
                decompressor = zlib.decompressobj()
            consume_idat(data)
        elif chunk_type == b"IEND":
            if length != 0 or not seen_idat or chunk_end != len(payload):
                raise ValueError("PNG IEND chunk is invalid or not final")
            finish_raster()
            return dimensions
        elif not chunk_type[0] & 0x20:
            raise ValueError("PNG contains an unsupported critical chunk")
        if seen_idat and chunk_type != b"IDAT":
            idat_closed = True
        offset = chunk_end
    raise ValueError("PNG IEND chunk is missing")


@dataclass(slots=True, frozen=True)
class ImageValue:
    encoded_bytes: bytes
    format: str
    width: int
    height: int
    sha256: str
    schema_version: int = IMAGE_VALUE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.encoded_bytes) is not bytes:
            raise TypeError("encoded_bytes must be immutable bytes")
        encoded_size = ((len(self.encoded_bytes) + 2) // 3) * 4
        if encoded_size > IMAGE_VALUE_MAX_ENCODED_BYTES:
            raise ValueError("encoded PNG exceeds the 64 MiB runtime payload limit")
        if type(self.format) is not str:
            raise TypeError("format must be an exact string")
        if type(self.width) is not int or type(self.height) is not int:
            raise TypeError("width and height must be exact integers")
        if type(self.sha256) is not str:
            raise TypeError("sha256 must be an exact string")
        if type(self.schema_version) is not int:
            raise TypeError("schema_version must be an exact integer")
        if self.format != "png":
            raise ValueError("ImageValue format must be 'png'")
        if self.schema_version != IMAGE_VALUE_SCHEMA_VERSION:
            raise ValueError("ImageValue schema_version must be 1")
        png_width, png_height = _png_dimensions(self.encoded_bytes)
        if self.width != png_width or self.height != png_height:
            raise ValueError("ImageValue dimensions do not match the PNG header")
        digest = hashlib.sha256(self.encoded_bytes).hexdigest()
        if self.sha256 != digest:
            raise ValueError("ImageValue sha256 does not match encoded_bytes")

    @property
    def data_type_id(self) -> str:
        return IMAGE_VALUE_DATA_TYPE_ID

    @classmethod
    def from_png(cls, encoded_bytes: bytes) -> ImageValue:
        if type(encoded_bytes) is not bytes:
            raise TypeError("encoded_bytes must be immutable bytes")
        payload = encoded_bytes
        width, height = _png_dimensions(payload)
        return cls(
            encoded_bytes=payload,
            format="png",
            width=width,
            height=height,
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> ImageValue | None:
        if payload.get(_RUNTIME_VALUE_MARKER_KEY) != _RUNTIME_IMAGE_MARKER_VALUE:
            return None
        if catalog is None:
            raise DataTypeCatalogError(
                "an active data-type catalog is required for image values"
            )
        validate_payload_fields(
            payload,
            label="ImageValue payload",
            required=frozenset(
                {
                    _RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "format",
                    "width",
                    "height",
                    "sha256",
                    "encoded_base64",
                }
            ),
        )
        if payload["data_type_id"] != IMAGE_VALUE_DATA_TYPE_ID:
            raise ValueError("ImageValue data_type_id is invalid")
        encoded = payload["encoded_base64"]
        if not isinstance(encoded, str) or len(encoded) > IMAGE_VALUE_MAX_ENCODED_BYTES:
            raise ValueError("ImageValue encoded_base64 exceeds the 64 MiB limit")
        try:
            png = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("ImageValue encoded_base64 is invalid") from exc
        value = cls(
            encoded_bytes=png,
            format=payload["format"],
            width=payload["width"],
            height=payload["height"],
            sha256=payload["sha256"],
            schema_version=payload["schema_version"],
        )
        catalog.validate_carrier(IMAGE_VALUE_DATA_TYPE_ID, value)
        return value

    def to_payload(self, *, catalog: DataTypeCatalog | None = None) -> dict[str, Any]:
        if catalog is None:
            raise DataTypeCatalogError(
                "an active data-type catalog is required for image values"
            )
        catalog.validate_carrier(IMAGE_VALUE_DATA_TYPE_ID, self)
        encoded = base64.b64encode(self.encoded_bytes).decode("ascii")
        if len(encoded) > IMAGE_VALUE_MAX_ENCODED_BYTES:
            raise ValueError("ImageValue encoded_base64 exceeds the 64 MiB limit")
        return {
            _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_IMAGE_MARKER_VALUE,
            "data_type_id": IMAGE_VALUE_DATA_TYPE_ID,
            "schema_version": self.schema_version,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "sha256": self.sha256,
            "encoded_base64": encoded,
        }


__all__ = [
    "IMAGE_VALUE_DATA_TYPE_ID",
    "IMAGE_VALUE_MAX_ENCODED_BYTES",
    "IMAGE_VALUE_SCHEMA_VERSION",
    "ImageValue",
]
