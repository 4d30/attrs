#!/usr/bin/env python

import hashlib
import os


ATTRS_ROOT = os.getenv("ATTRS_ROOT")

CID_BYTES = 32

_HANDLES = {}


def _get_handle(value: str, attrs_root: str):
    key = (attrs_root, value)
    handle = _HANDLES.get(key)

    if handle is None:
        os.makedirs(attrs_root, exist_ok=True)
        value_id = _value_id(value)
        path = os.path.join(
            attrs_root,
            f"{value_id}_today.bin",
        )
        handle = open(path, "ab")
        _HANDLES[key] = handle

    return handle


def _cid_bytes(cid: str) -> bytes:
    value = bytes.fromhex(cid)

    if len(value) != CID_BYTES:
        raise ValueError("invalid content ID")

    return value


def _value_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def put(
    value: str,
    cid: str,
    attrs_root: str = ATTRS_ROOT,
) -> None:
    """Append a CID to today's posting list for value."""
    if attrs_root is None:
        raise ValueError("attrs_root is not configured")

    handle = _get_handle(value, attrs_root)
    handle.write(_cid_bytes(cid))


def get(
    value: str,
    attrs_root: str = ATTRS_ROOT,
):
    """Yield every CID associated with value."""
    if attrs_root is None:
        raise ValueError("attrs_root is not configured")

    value_id = _value_id(value)
    path = os.path.join(attrs_root, f"{value_id}.bin")

    if not os.path.exists(path):
        return

    with open(path, "rb") as handle:
        while cid := handle.read(CID_BYTES):
            if len(cid) != CID_BYTES:
                raise ValueError("corrupt attribute file")

            yield cid.hex()


def _sort_value(
    value_id: str,
    attrs_root: str,
) -> None:
    """Sort and deduplicate today's posting list for a value."""
    today_path = os.path.join(
        attrs_root,
        f"{value_id}_today.bin",
    )

    sorted_path = os.path.join(
        attrs_root,
        f"{value_id}_sorted.bin",
    )

    if not os.path.exists(today_path):
        return

    with open(today_path, "rb") as handle:
        data = handle.read()

    if len(data) % CID_BYTES:
        raise ValueError("corrupt attribute file")

    records = [
        data[i:i + CID_BYTES]
        for i in range(0, len(data), CID_BYTES)
    ]

    records = sorted(set(records))

    with open(sorted_path, "wb") as handle:
        handle.writelines(records)


def _merge_files(
    existing_path: str,
    today_path: str,
    merged_path: str,
) -> None:
    """Merge two sorted posting lists, removing duplicates."""

    with open(existing_path, "rb") as existing, \
         open(today_path, "rb") as today, \
         open(merged_path, "wb") as merged:

        a = existing.read(CID_BYTES)
        b = today.read(CID_BYTES)

        while a and b:
            if a < b:
                merged.write(a)
                a = existing.read(CID_BYTES)

            elif b < a:
                merged.write(b)
                b = today.read(CID_BYTES)

            else:
                merged.write(a)
                a = existing.read(CID_BYTES)
                b = today.read(CID_BYTES)

        while a:
            merged.write(a)
            a = existing.read(CID_BYTES)

        while b:
            merged.write(b)
            b = today.read(CID_BYTES)


def _merge_value(
    value_id: str,
    attrs_root: str,
) -> None:
    """Merge today's sorted posting list into the persistent list."""

    today_path = os.path.join(
        attrs_root,
        f"{value_id}_sorted.bin",
    )

    existing_path = os.path.join(
        attrs_root,
        f"{value_id}.bin",
    )

    merged_path = os.path.join(
        attrs_root,
        f"{value_id}.new.bin",
    )

    if not os.path.exists(today_path):
        return

    if os.path.exists(existing_path):
        _merge_files(
            existing_path,
            today_path,
            merged_path,
        )
        os.replace(merged_path, existing_path)
    else:
        os.replace(today_path, existing_path)


def build(attrs_root: str = ATTRS_ROOT) -> None:
    """Build queryable posting lists from today's records."""
    if attrs_root is None:
        raise ValueError("attrs_root is not configured")

    close(attrs_root)

    if not os.path.isdir(attrs_root):
        return

    value_ids = set()

    for filename in os.listdir(attrs_root):
        if filename.endswith("_today.bin"):
            value_ids.add(filename[:-10])

    for value_id in value_ids:
        _sort_value(value_id, attrs_root)

    for value_id in value_ids:
        _merge_value(value_id, attrs_root)

        today_path = os.path.join(
            attrs_root,
            f"{value_id}_today.bin",
        )

        sorted_path = os.path.join(
            attrs_root,
            f"{value_id}_sorted.bin",
        )

        if os.path.exists(today_path):
            os.unlink(today_path)

        if os.path.exists(sorted_path):
            os.unlink(sorted_path)


def walk(attrs_root: str = ATTRS_ROOT):
    """Yield every value ID in sorted order."""
    if attrs_root is None:
        raise ValueError("attrs_root is not configured")

    if not os.path.isdir(attrs_root):
        return

    for filename in sorted(os.listdir(attrs_root)):
        if filename.endswith(".bin") and not filename.endswith(
            "_today.bin"
        ):
            yield filename[:-4]


def close(attrs_root: str | None = None) -> None:
    """Flush and close open attribute posting files."""
    if attrs_root is not None:
        keys = [
            key
            for key in _HANDLES
            if key[0] == attrs_root
        ]

        for key in keys:
            handle = _HANDLES.pop(key)
            handle.close()

        return

    for handle in _HANDLES.values():
        handle.close()

    _HANDLES.clear()
