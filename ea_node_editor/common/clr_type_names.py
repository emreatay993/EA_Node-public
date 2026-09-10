# Purpose: Parse and normalize CLR type identities without loading CLR assemblies.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_registry_validation.py

from __future__ import annotations

import re
from dataclasses import dataclass

_GENERIC_ARITY = re.compile(r"`([1-9][0-9]*)$")
_ARRAY_RANK = re.compile(r",*")
_DRIVE_PATH_PREFIX = re.compile(r"^[A-Za-z]:")


class ClrTypeNameError(ValueError):
    """Raised when a CLR type identity is malformed."""


@dataclass(frozen=True, slots=True)
class ClrAssemblyIdentity:
    name: str
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ClrTypeName:
    name: str
    generic_arguments: tuple[ClrTypeName, ...] = ()
    array_ranks: tuple[int, ...] = ()
    assembly: ClrAssemblyIdentity | None = None

    @property
    def canonical_id(self) -> str:
        value = self.name
        if self.generic_arguments:
            arguments = ",".join(
                f"[{argument.canonical_id}]" for argument in self.generic_arguments
            )
            value += f"[{arguments}]"
        for rank in self.array_ranks:
            value += f"[{',' * (rank - 1)}]"
        return value

    def assembly_provenance(
        self, path: str = "self"
    ) -> tuple[tuple[str, ClrAssemblyIdentity], ...]:
        entries: list[tuple[str, ClrAssemblyIdentity]] = []
        if self.assembly is not None:
            entries.append((path, self.assembly))
        for index, argument in enumerate(self.generic_arguments):
            entries.extend(argument.assembly_provenance(f"{path}.generic[{index}]"))
        return tuple(entries)


def parse_clr_type_name(value: str) -> ClrTypeName:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ClrTypeNameError("CLR type identity must be a non-empty, trimmed string")
    parser = _Parser(value)
    parsed = parser.parse_type(allow_assembly=True, terminators=frozenset())
    if not parser.at_end:
        parser.fail("unexpected trailing content")
    return parsed


def normalize_clr_type_name(value: str) -> str:
    return parse_clr_type_name(value).canonical_id


def validate_canonical_clr_type_id(value: str) -> str:
    parsed = parse_clr_type_name(value)
    if parsed.assembly_provenance():
        raise ClrTypeNameError(
            "canonical CLR type IDs must not contain assembly metadata"
        )
    _reject_path_shaped_type_names(parsed)
    if parsed.canonical_id != value:
        raise ClrTypeNameError(f"non-canonical CLR type ID: {value!r}")
    return value


def _reject_path_shaped_type_names(parsed: ClrTypeName) -> None:
    if (
        "/" in parsed.name
        or "\\" in parsed.name
        or _DRIVE_PATH_PREFIX.match(parsed.name)
    ):
        raise ClrTypeNameError(
            "canonical CLR type IDs must not contain filesystem path syntax"
        )
    for argument in parsed.generic_arguments:
        _reject_path_shaped_type_names(argument)


class _Parser:
    def __init__(self, value: str) -> None:
        self.value = value
        self.index = 0

    @property
    def at_end(self) -> bool:
        return self.index == len(self.value)

    def fail(self, message: str) -> None:
        raise ClrTypeNameError(f"{message} at offset {self.index}: {self.value!r}")

    def parse_type(
        self, *, allow_assembly: bool, terminators: frozenset[str]
    ) -> ClrTypeName:
        name = self._parse_name(terminators)
        arity = sum(
            int(match.group(1))
            for part in re.split(r"[.+]", name)
            if (match := _GENERIC_ARITY.search(part))
        )
        arguments: tuple[ClrTypeName, ...] = ()
        arrays: list[int] = []

        if self._peek() == "[" and not self._looks_like_array():
            if arity == 0:
                self.fail("generic arguments require a CLR generic arity")
            arguments = self._parse_generic_arguments()
            if len(arguments) != arity:
                self.fail(
                    f"generic arity {arity} does not match {len(arguments)} arguments"
                )

        while self._peek() == "[":
            arrays.append(self._parse_array_rank())

        assembly = None
        if allow_assembly and self._peek() == ",":
            assembly = self._parse_assembly(terminators)

        next_character = self._peek()
        if next_character is not None and next_character not in terminators:
            self.fail(f"unexpected character {next_character!r}")
        return ClrTypeName(
            name=name,
            generic_arguments=arguments,
            array_ranks=tuple(arrays),
            assembly=assembly,
        )

    def _parse_name(self, terminators: frozenset[str]) -> str:
        start = self.index
        while (character := self._peek()) is not None:
            if character == "]" and character not in terminators:
                self.fail("unexpected closing bracket")
            if character in "[," or character in terminators:
                break
            self.index += 1
        name = self.value[start : self.index]
        if (
            not name
            or name.strip() != name
            or any(character.isspace() for character in name)
        ):
            self.fail("invalid CLR type name")
        parts = re.split(r"[.+]", name)
        if any(not part for part in parts):
            self.fail(
                "CLR type name contains an empty namespace or nested-type segment"
            )
        for part in parts:
            if "`" in part and _GENERIC_ARITY.search(part) is None:
                self.fail("invalid CLR generic arity marker")
        return name

    def _parse_generic_arguments(self) -> tuple[ClrTypeName, ...]:
        self._consume("[")
        arguments: list[ClrTypeName] = []
        while True:
            wrapped = self._peek() == "["
            if wrapped:
                self._consume("[")
            argument = self.parse_type(
                allow_assembly=wrapped,
                terminators=frozenset({"]"}) if wrapped else frozenset({",", "]"}),
            )
            if wrapped:
                self._consume("]")
            arguments.append(argument)
            character = self._peek()
            if character == ",":
                self._consume(",")
                if self._peek() in {None, ",", "]"}:
                    self.fail("missing generic argument")
                continue
            if character == "]":
                self._consume("]")
                return tuple(arguments)
            self.fail("unterminated generic argument list")

    def _looks_like_array(self) -> bool:
        close = self.value.find("]", self.index + 1)
        if close < 0:
            return False
        return _ARRAY_RANK.fullmatch(self.value[self.index + 1 : close]) is not None

    def _parse_array_rank(self) -> int:
        self._consume("[")
        start = self.index
        while self._peek() == ",":
            self.index += 1
        commas = self.index - start
        self._consume("]")
        return commas + 1

    def _parse_assembly(self, terminators: frozenset[str]) -> ClrAssemblyIdentity:
        parts: list[str] = []
        while self._peek() == ",":
            self._consume(",")
            self._skip_spaces()
            start = self.index
            while (character := self._peek()) is not None:
                if character == "]" and character not in terminators:
                    self.fail("unexpected closing bracket")
                if character in terminators or character == ",":
                    break
                self.index += 1
            token = self.value[start : self.index].strip()
            if not token:
                self.fail("empty assembly identity component")
            parts.append(token)
        if not parts or "=" in parts[0]:
            self.fail("assembly identity must start with an assembly name")
        metadata: list[tuple[str, str]] = []
        for token in parts[1:]:
            key, separator, metadata_value = token.partition("=")
            if not separator or not key.strip() or not metadata_value.strip():
                self.fail("invalid assembly metadata")
            metadata.append((key.strip(), metadata_value.strip()))
        return ClrAssemblyIdentity(name=parts[0], metadata=tuple(metadata))

    def _skip_spaces(self) -> None:
        while self._peek() == " ":
            self.index += 1

    def _peek(self) -> str | None:
        if self.index >= len(self.value):
            return None
        return self.value[self.index]

    def _consume(self, expected: str) -> None:
        if not self.value.startswith(expected, self.index):
            self.fail(f"expected {expected!r}")
        self.index += len(expected)
