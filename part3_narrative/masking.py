"""Part 3 - Masking policy for externally shared narratives.

Any narrative that could reach an external-facing summary must never expose a
raw reseller name. Resellers are referenced only by region and a coded alias.

    alias_for("RS019")  -> "ALIAS-19"
    alias_for("RS006")  -> "ALIAS-06"

Deterministic and dependency-free (standard library only).
"""


def alias_for(reseller_id: str) -> str:
    """Return the coded alias for a reseller ID.

    Slices off the "RS" prefix plus the first digit, i.e. reseller_id[3:], and keeps
    the remaining digits (including padding) unchanged. The same ID always maps to the
    same alias, e.g. "RS019" -> "ALIAS-19", "RS006" -> "ALIAS-06".
    """
    return f"ALIAS-{reseller_id[3:]}"


def assert_no_raw_names_leak(text: str, reseller_names: list[str]) -> bool:
    """Return True if no raw reseller name appears verbatim in text, else False.

    Does a genuine case-sensitive substring search for every name and returns
    False as soon as any one is found. Empty names are ignored.
    """
    for name in reseller_names:
        if name and name in text:
            return False
    return True


def require_no_raw_names_leak(text: str, reseller_names: list[str]) -> None:
    """Strict variant of assert_no_raw_names_leak: raise AssertionError on a leak.

    Use this where a leak must stop execution (e.g. before a draft is held for
    approval). It reports how many names leaked, not the names themselves, so the
    error message does not repeat the leak.
    """
    leaked = [name for name in reseller_names if name and name in text]
    if leaked:
        raise AssertionError(f"{len(leaked)} raw reseller name(s) found in text")
