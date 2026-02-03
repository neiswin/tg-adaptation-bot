import bleach

ALLOWED_TAGS = {"b", "i", "u", "a", "code", "pre"}
ALLOWED_ATTRS = {"a": ["href"]}

def sanitize_html(text: str) -> str:
    text = (text or "").strip()
    # если пусто — вернем пусто, а в логике запретим
    return bleach.clean(text, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
