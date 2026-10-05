from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED = "Immediate_" + "Gold9789"

SCAN = [
    ROOT / "syndicate" / "syndicate" / "config.py",
    ROOT / "syndicate" / "syndicate" / "platforms" / "reddit.py",
    ROOT / "syndicate" / "README_SYNDICATION.md",
]


def test_retired_reddit_identity_is_absent_from_syndication_surfaces():
    offenders = []
    for path in SCAN:
        text = path.read_text(encoding="utf-8")
        if RETIRED.casefold() in text.casefold():
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, "Retired Reddit identity found in: " + ", ".join(offenders)


def test_reddit_syndication_has_no_implicit_destination():
    text = (ROOT / "syndicate" / "syndicate" / "config.py").read_text(encoding="utf-8")
    assert 'REDDIT_SUBREDDIT: str = os.getenv("REDDIT_SUBREDDIT", "")' in text
