from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import unicodedata
from typing import Any

from app.publish.java_compat import java_is_blank, java_trim, java_utf16_length
from app.publish.package import PackageEntry, normalize_entry_path

FIELD_NAME = "x-astron-compliance"
SNAPSHOT_FIELD_NAME = "complianceSnapshot"
SCHEMA_VERSION = "1.0"

MAX_MAPPINGS = 50
MAX_EVIDENCE_ITEMS = 10
MAX_STANDARD_LENGTH = 64
MAX_VERSION_LENGTH = 64
MAX_CONTROL_ID_LENGTH = 128
MAX_TITLE_LENGTH = 200
MAX_EVIDENCE_TYPE_LENGTH = 32
MAX_PACKAGED_PATH_LENGTH = 512
MAX_EXTERNAL_URL_LENGTH = 2048

STANDARD_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")
CONTROL_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
MAPPING_FIELDS = frozenset({"standard", "version", "controlId", "title", "evidence"})
EVIDENCE_FIELDS = frozenset({"type", "path", "url"})
ASCII_ALPHA = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
ASCII_DIGITS = frozenset("0123456789")
ASCII_ALNUM = ASCII_ALPHA | ASCII_DIGITS
URI_UNRESERVED = ASCII_ALPHA | ASCII_DIGITS | frozenset("-_.!~*'()")
URI_SUBDELIMS = frozenset("!$&'()*+,;=")
URI_USER_INFO = URI_UNRESERVED | URI_SUBDELIMS | frozenset(":")
URI_PATH = URI_UNRESERVED | URI_SUBDELIMS | frozenset(":@/")
URI_QUERY_FRAGMENT = URI_PATH | frozenset("?[]")
IPV6_SCOPE_CHARACTERS = ASCII_ALNUM | frozenset("_.")
HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
SCHEME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\Z")
JAVA_INTEGER_MAX_VALUE = 2_147_483_647


class ComplianceMetadataError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__(", ".join(errors))


def validate_compliance_metadata(
    frontmatter: dict[str, Any],
    entries: list[PackageEntry],
) -> list[str]:
    _, errors = _parse_compliance_metadata(frontmatter, entries)
    return errors


def build_compliance_snapshot(
    frontmatter: dict[str, Any],
    entries: list[PackageEntry],
) -> dict[str, object]:
    mappings, errors = _parse_compliance_metadata(frontmatter, entries)
    if errors:
        raise ComplianceMetadataError(errors)

    digest_payload = {
        "schemaVersion": SCHEMA_VERSION,
        "items": mappings,
    }
    serialized = json.dumps(
        digest_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        **digest_payload,
        "digest": f"sha256:{hashlib.sha256(serialized).hexdigest()}",
    }


def _parse_compliance_metadata(
    frontmatter: dict[str, Any],
    entries: list[PackageEntry],
) -> tuple[list[dict[str, object]], list[str]]:
    raw_mappings = frontmatter.get(FIELD_NAME)
    if raw_mappings is None:
        return [], []
    if not isinstance(raw_mappings, list):
        return [], [f"{FIELD_NAME} must be an array"]

    errors: list[str] = []
    if len(raw_mappings) > MAX_MAPPINGS:
        errors.append(f"{FIELD_NAME} must contain at most {MAX_MAPPINGS} items")

    package_entries = _package_entry_map(entries)
    seen_mappings: set[tuple[str, str, str]] = set()
    mappings: list[dict[str, object]] = []

    for mapping_index, raw_mapping in enumerate(raw_mappings):
        if not isinstance(raw_mapping, dict):
            errors.append(f"{FIELD_NAME}[{mapping_index}] must be an object")
            continue
        mapping = _string_keyed_map(raw_mapping)
        _validate_allowed_fields(
            mapping,
            MAPPING_FIELDS,
            f"{FIELD_NAME}[{mapping_index}]",
            errors,
        )

        standard = _required_string(
            mapping,
            "standard",
            MAX_STANDARD_LENGTH,
            f"{FIELD_NAME}[{mapping_index}]",
            errors,
        )
        normalized_standard = standard.lower() if standard is not None else None
        if normalized_standard is not None and STANDARD_PATTERN.fullmatch(normalized_standard) is None:
            errors.append(f"{FIELD_NAME}[{mapping_index}].standard has an invalid format")

        version = _required_string(
            mapping,
            "version",
            MAX_VERSION_LENGTH,
            f"{FIELD_NAME}[{mapping_index}]",
            errors,
        )
        control_id = _required_string(
            mapping,
            "controlId",
            MAX_CONTROL_ID_LENGTH,
            f"{FIELD_NAME}[{mapping_index}]",
            errors,
        )
        if control_id is not None and CONTROL_ID_PATTERN.fullmatch(control_id) is None:
            errors.append(f"{FIELD_NAME}[{mapping_index}].controlId has an invalid format")
        title = _optional_string(
            mapping,
            "title",
            MAX_TITLE_LENGTH,
            f"{FIELD_NAME}[{mapping_index}]",
            errors,
        )
        evidence = _parse_evidence(
            mapping.get("evidence"),
            mapping_index,
            package_entries,
            errors,
        )

        if normalized_standard is None or version is None or control_id is None:
            continue
        duplicate_key = (normalized_standard, version, control_id)
        if duplicate_key in seen_mappings:
            errors.append(
                f"{FIELD_NAME} contains duplicate mapping "
                f"{normalized_standard}/{version}/{control_id}"
            )
            continue
        seen_mappings.add(duplicate_key)

        normalized_mapping: dict[str, object] = {
            "standard": normalized_standard,
            "version": version,
            "controlId": control_id,
        }
        if title is not None:
            normalized_mapping["title"] = title
        normalized_mapping["evidence"] = evidence
        mappings.append(normalized_mapping)

    return mappings, errors


def _parse_evidence(
    raw_evidence: object,
    mapping_index: int,
    package_entries: dict[str, PackageEntry],
    errors: list[str],
) -> list[dict[str, str]]:
    if raw_evidence is None:
        return []
    path_prefix = f"{FIELD_NAME}[{mapping_index}].evidence"
    if not isinstance(raw_evidence, list):
        errors.append(f"{path_prefix} must be an array")
        return []
    if len(raw_evidence) > MAX_EVIDENCE_ITEMS:
        errors.append(f"{path_prefix} must contain at most {MAX_EVIDENCE_ITEMS} items")

    evidence: list[dict[str, str]] = []
    for evidence_index, raw_item in enumerate(raw_evidence):
        evidence_path = f"{path_prefix}[{evidence_index}]"
        if not isinstance(raw_item, dict):
            errors.append(f"{evidence_path} must be an object")
            continue
        item = _string_keyed_map(raw_item)
        _validate_allowed_fields(item, EVIDENCE_FIELDS, evidence_path, errors)
        evidence_type = _required_string(
            item,
            "type",
            MAX_EVIDENCE_TYPE_LENGTH,
            evidence_path,
            errors,
        )
        if evidence_type is None:
            continue
        normalized_type = evidence_type.lower()
        if normalized_type == "packaged-file":
            packaged_evidence = _parse_packaged_file_evidence(
                item,
                evidence_path,
                package_entries,
                errors,
            )
            if packaged_evidence is not None:
                evidence.append(packaged_evidence)
        elif normalized_type == "external-url":
            external_evidence = _parse_external_url_evidence(item, evidence_path, errors)
            if external_evidence is not None:
                evidence.append(external_evidence)
        else:
            errors.append(
                f"{evidence_path}.type must be one of packaged-file, external-url"
            )
    return evidence


def _parse_packaged_file_evidence(
    item: dict[str, Any],
    evidence_path: str,
    package_entries: dict[str, PackageEntry],
    errors: list[str],
) -> dict[str, str] | None:
    raw_path = _required_string(
        item,
        "path",
        MAX_PACKAGED_PATH_LENGTH,
        evidence_path,
        errors,
    )
    if raw_path is None:
        return None
    try:
        normalized_path = normalize_entry_path(raw_path)
    except ValueError as exc:
        errors.append(f"{evidence_path}.path {exc}")
        return None
    entry = package_entries.get(normalized_path)
    if entry is None:
        errors.append(
            f"{evidence_path}.path does not exist in package: {normalized_path}"
        )
        return None
    return {
        "type": "packaged-file",
        "path": normalized_path,
        "sha256": hashlib.sha256(entry.content).hexdigest(),
    }


def _parse_external_url_evidence(
    item: dict[str, Any],
    evidence_path: str,
    errors: list[str],
) -> dict[str, str] | None:
    url = _required_string(
        item,
        "url",
        MAX_EXTERNAL_URL_LENGTH,
        evidence_path,
        errors,
    )
    if url is None:
        return None
    if not _is_java_http_uri_with_host(url):
        errors.append(f"{evidence_path}.url must be an http or https URL")
        return None
    return {"type": "external-url", "url": url}


def _required_string(
    item: dict[str, Any],
    field_name: str,
    max_length: int,
    path_prefix: str,
    errors: list[str],
) -> str | None:
    raw_value = item.get(field_name)
    if not isinstance(raw_value, str) or java_is_blank(raw_value):
        errors.append(f"{path_prefix}.{field_name} is required")
        return None
    value = java_trim(raw_value)
    if _contains_lone_surrogate(value):
        errors.append(f"{path_prefix}.{field_name} must contain valid Unicode")
        return None
    if java_utf16_length(value) > max_length:
        errors.append(
            f"{path_prefix}.{field_name} must be at most {max_length} characters"
        )
        return None
    return value


def _optional_string(
    item: dict[str, Any],
    field_name: str,
    max_length: int,
    path_prefix: str,
    errors: list[str],
) -> str | None:
    raw_value = item.get(field_name)
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or java_is_blank(raw_value):
        errors.append(f"{path_prefix}.{field_name} must be a non-empty string")
        return None
    value = java_trim(raw_value)
    if _contains_lone_surrogate(value):
        errors.append(f"{path_prefix}.{field_name} must contain valid Unicode")
        return None
    if java_utf16_length(value) > max_length:
        errors.append(
            f"{path_prefix}.{field_name} must be at most {max_length} characters"
        )
        return None
    return value


def _validate_allowed_fields(
    item: dict[str, Any],
    allowed_fields: frozenset[str],
    path_prefix: str,
    errors: list[str],
) -> None:
    for field_name in item:
        if field_name not in allowed_fields:
            errors.append(f"{path_prefix}.{field_name} is not allowed")


def _contains_lone_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(char) <= 0xDFFF for char in value)


def _package_entry_map(entries: list[PackageEntry]) -> dict[str, PackageEntry]:
    package_entries: dict[str, PackageEntry] = {}
    for entry in entries:
        try:
            normalized_path = normalize_entry_path(entry.path)
        except ValueError:
            continue
        package_entries.setdefault(normalized_path, entry)
    return package_entries


def _is_java_http_uri_with_host(value: str) -> bool:
    """Match the URI.create/getHost subset used by upstream compliance parsing."""
    scheme_separator = value.find(":")
    if scheme_separator < 1:
        return False
    scheme = value[:scheme_separator]
    if SCHEME_PATTERN.fullmatch(scheme) is None or scheme.lower() not in {"http", "https"}:
        return False
    remainder = value[scheme_separator + 1 :]
    if not remainder.startswith("//"):
        return False
    hierarchical = remainder[2:]
    authority_end = len(hierarchical)
    for delimiter in "/?#":
        delimiter_index = hierarchical.find(delimiter)
        if delimiter_index >= 0:
            authority_end = min(authority_end, delimiter_index)
    authority = hierarchical[:authority_end]
    path_query_fragment = hierarchical[authority_end:]
    if not _has_java_server_authority(authority):
        return False

    fragment_separator = path_query_fragment.find("#")
    if fragment_separator >= 0:
        before_fragment = path_query_fragment[:fragment_separator]
        fragment = path_query_fragment[fragment_separator + 1 :]
    else:
        before_fragment = path_query_fragment
        fragment = None
    query_separator = before_fragment.find("?")
    if query_separator >= 0:
        path = before_fragment[:query_separator]
        query = before_fragment[query_separator + 1 :]
    else:
        path = before_fragment
        query = None
    return (
        _has_java_uri_component_syntax(path, URI_PATH)
        and (query is None or _has_java_uri_component_syntax(query, URI_QUERY_FRAGMENT))
        and (
            fragment is None
            or _has_java_uri_component_syntax(fragment, URI_QUERY_FRAGMENT)
        )
    )


def _has_java_server_authority(authority: str) -> bool:
    if not authority or authority.count("@") > 1:
        return False
    if "@" in authority:
        user_info, authority = authority.split("@", 1)
        if not _has_java_uri_component_syntax(user_info, URI_USER_INFO):
            return False

    if authority.startswith("["):
        closing_bracket = authority.find("]")
        if closing_bracket < 0:
            return False
        host = authority[1:closing_bracket]
        port_suffix = authority[closing_bracket + 1 :]
        if port_suffix and not port_suffix.startswith(":"):
            return False
        if not _is_java_port(port_suffix[1:] if port_suffix else None):
            return False
        return _is_java_ipv6_literal(host)

    if authority.count(":") > 1:
        return False
    host, separator, port = authority.partition(":")
    if not _is_java_port(port if separator else None):
        return False
    return _is_java_host(host)


def _is_java_port(port: str | None) -> bool:
    if port is None or port == "":
        return True
    return (
        port.isascii()
        and port.isdigit()
        and int(port) <= JAVA_INTEGER_MAX_VALUE
    )


def _is_java_host(host: str) -> bool:
    if not host or not host.isascii():
        return False
    if _is_java_ipv4_address(host):
        return True

    hostname = host.removesuffix(".")
    if not hostname:
        return False
    labels = hostname.split(".")
    if len(labels) > 1 and labels[-1][0] not in ASCII_ALPHA:
        return False
    return all(
        label
        and label[0] in ASCII_ALNUM
        and label[-1] in ASCII_ALNUM
        and all(char in ASCII_ALNUM or char == "-" for char in label)
        for label in labels
    )


def _is_java_ipv4_address(host: str) -> bool:
    components = host.split(".")
    return len(components) == 4 and all(
        component
        and component.isascii()
        and component.isdigit()
        and int(component) <= 255
        for component in components
    )


def _is_java_ipv6_literal(host: str) -> bool:
    address, scope_separator, scope = host.partition("%")
    if scope_separator and (
        not scope
        or "%" in scope
        or any(char not in IPV6_SCOPE_CHARACTERS for char in scope)
    ):
        return False
    normalized_address = _normalize_java_ipv4_tail(address)
    if normalized_address is None:
        return False
    try:
        ipaddress.IPv6Address(normalized_address)
    except ValueError:
        return False
    return True


def _normalize_java_ipv4_tail(address: str) -> str | None:
    if "." not in address:
        return address
    prefix, separator, dotted_tail = address.rpartition(":")
    if not separator or not _is_java_ipv4_address(dotted_tail):
        return None
    normalized_tail = ".".join(str(int(component)) for component in dotted_tail.split("."))
    return f"{prefix}:{normalized_tail}"


def _has_java_uri_component_syntax(value: str, allowed_ascii: frozenset[str]) -> bool:
    index = 0
    while index < len(value):
        char = value[index]
        if char == "%":
            if (
                index + 2 >= len(value)
                or value[index + 1] not in HEX_DIGITS
                or value[index + 2] not in HEX_DIGITS
            ):
                return False
            index += 3
            continue
        if ord(char) < 128:
            if char not in allowed_ascii:
                return False
        elif not _is_java_uri_other(char):
            return False
        index += 1
    return True


def _is_java_uri_other(char: str) -> bool:
    # Java URI admits non-ASCII "other" characters unless they are Unicode
    # space characters or ISO controls; U+200D intentionally falls here.
    code_point = ord(char)
    is_iso_control = code_point <= 0x1F or 0x7F <= code_point <= 0x9F
    return code_point > 0x80 and not is_iso_control and unicodedata.category(char)[0] != "Z"


def _string_keyed_map(raw_map: dict[object, object]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in raw_map.items()
        if key is not None
    }
