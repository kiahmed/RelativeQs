"""backend/.env.example must document every variable the backend reads, and must
contain only placeholders (never a real-looking secret)."""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
EXAMPLE = BACKEND / ".env.example"

_READ = re.compile(
    r"""(?:getenv|environ\.get|_env_int|_env_float)\(\s*["']([A-Z][A-Z0-9_]+)["']"""
    r"""|environ\[\s*["']([A-Z][A-Z0-9_]+)["']\s*\]"""
)


def _vars_read_by_code() -> set:
    out = set()
    files = list((BACKEND / "app").rglob("*.py")) + [BACKEND / "backend" / "main.py"]
    for f in files:
        for a, b in _READ.findall(f.read_text(encoding="utf-8", errors="ignore")):
            out.add(a or b)
    return out


def _vars_in_example() -> set:
    text = EXAMPLE.read_text(encoding="utf-8")
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]{2,})=", text, re.M))


def test_every_variable_the_code_reads_is_documented():
    missing = sorted(_vars_read_by_code() - _vars_in_example())
    assert not missing, (
        f"add these to backend/.env.example (with a dummy value and a comment): {missing}"
    )


def test_example_has_only_placeholders():
    text = EXAMPLE.read_text(encoding="utf-8")
    assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", text), "looks like a real JWT"
    assert not re.search(r"sk_live_|pk_live_|rk_live_", text), "live Stripe key"
    assert not re.search(r"rediss?://[^\s@/]+:[^\s@/]+@", text), "Redis URL with credentials"
    assert not re.search(r"https://(?!YOUR-PROJECT-REF)[a-z0-9]{20}\.supabase\.co", text), \
        "real Supabase project ref"
