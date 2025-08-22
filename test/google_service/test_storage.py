import json
import os
from datetime import datetime

import pytest





@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("k:dict_simple", {"a": 1, "b": "x"}, {"a": 1, "b": "x"}),
        ("k:list", {"lst": [1, 2, 3]}, {"lst": [1, 2, 3]}),
        ("k:bool_num", {"ok": True, "n": 7}, {"ok": True, "n": 7}),
        # default=str convert datetime to string
        ("k:dt", {"ts": datetime(2023, 1, 2, 3, 4, 5)}, {"ts": "2023-01-02 03:04:05"}),
        ("k:scalar_int", 42, 42),
        ("k:scalar_str", "hello", "hello"),
        ("k:list_plain", [1, "x", False], [1, "x", False]),
    ],
)
def test_set_get_roundtrip_parametrized(store, key, value, expected):
    store.set(key, value)
    out = store.get(key)
    assert out == expected


def test_overwrite_replaces_value(store):
    store.set("user:1", {"name": "Alice", "age": 30})
    assert store.get("user:1") == {"name": "Alice", "age": 30}

    # overwrite (REPLACE)
    store.set("user:1", {"name": "Alice", "age": 31})
    assert store.get("user:1") == {"name": "Alice", "age": 31}


@pytest.mark.parametrize(
    "inserted_keys,prefix,expected_subset",
    [
        (["user:1", "user:2", "config:app"], "user:", {"user:1", "user:2"}),
        (["a:1", "β:2", "a:extra"], "a:", {"a:1", "a:extra"}),  # unicode
        (["plain", "prefix:x", "prefix:y"], "", {"plain", "prefix:x", "prefix:y"}),
        (["a", "b", "c"], "zzz", set()),
    ],
)
def test_list_keys_with_prefix_variants(store, inserted_keys, prefix, expected_subset):
    for k in inserted_keys:
        store.set(k, {"v": k})

    keys = set(store.list_keys(prefix))
    assert keys == expected_subset


def test_list_keys_no_prefix_returns_all(store):
    keys_in = {"k1", "k2", "k3"}
    for k in keys_in:
        store.set(k, {"v": 1})

    keys_out = set(store.list_keys())
    # Do not assume order
    assert keys_out == keys_in


def test_get_nonexistent_returns_none(store):
    assert store.get("no:such:key") is None


def test_delete_removes_key_and_is_idempotent(store):
    store.set("tmp", {"x": 1})
    assert store.get("tmp") == {"x": 1}

    store.delete("tmp")
    assert store.get("tmp") is None

    # deleting again should not fail nor change anything
    store.delete("tmp")
    assert store.get("tmp") is None


def test_invalid_json_in_db_raises_jsondecodeerror(store):
    # insert manually invalid JSON
    store.conn.execute(
        "REPLACE INTO kv (key, value) VALUES (?, ?)", ("bad", "not json")
    )
    store.conn.commit()

    with pytest.raises(json.JSONDecodeError):
        store.get("bad")
