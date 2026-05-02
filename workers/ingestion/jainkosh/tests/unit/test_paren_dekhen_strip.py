from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.see_also import strip_paren_dekhen


def _cfg():
    return load_config()


def test_strip_paren_around_dekhen_with_redlink():
    s = "X यह लक्षण नहीं बनता (इसी प्रकार ... कह सकते–देखें द्रव्य - 1.4)। बाकी।"
    assert strip_paren_dekhen(s, _cfg()) == "X यह लक्षण नहीं बनता । बाकी।"


def test_keep_unparenthesised_dekhen():
    s = "जीव शुद्ध है। देखें जीव - 3.8"
    assert strip_paren_dekhen(s, _cfg()) == s


def test_strip_paren_with_translation_newline():
    s = "...कहते हैं।\n(देखें सत्\n)।"
    assert strip_paren_dekhen(s, _cfg()) == "...कहते हैं।।"


def test_paren_dekhen_inside_brackets_when_enabled():
    s = "X [देखें Y] Z"
    out = strip_paren_dekhen(s, _cfg())
    assert "[" not in out and "]" not in out
    assert "देखें" not in out
