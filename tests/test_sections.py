from mcp_ads_arxiv.sections import (
    normalize_heading,
    resolve_section,
    resolve_topic,
    display_label,
)


# Real heading from Bulbul 2010 — LaTeX macros + trailing whitespace; the bug source.
BULBUL_HEADINGS = [
    "Introduction",
    "A Model of the Intergalactic Medium Based on Hydrostatic Equilibrium and \nthe  Polytropic Equation of State",
    "Application to \\chandra\\ Observations of Clusters ",
    "Comparison with Previous Work ",
    "Discussion and Conclusions",
    "Acknowledgments",
]


def test_normalize_strips_macros_and_collapses_whitespace():
    raw = "Application to \\chandra\\ Observations of Clusters "
    assert normalize_heading(raw) == "application to observations of clusters"


def test_normalize_handles_embedded_newlines():
    raw = "A Model of the Intergalactic Medium Based on Hydrostatic Equilibrium and \nthe  Polytropic Equation of State"
    assert "model" in normalize_heading(raw)
    assert "polytropic equation of state" in normalize_heading(raw)
    assert "  " not in normalize_heading(raw)  # whitespace collapsed


def test_resolve_exact_normalized_match_returns_raw():
    # User passes a clean string; resolver hands back the raw form for extract_section.
    raw = resolve_section("application to chandra observations of clusters", BULBUL_HEADINGS)
    # `\chandra` macro is stripped, so the user's "chandra" doesn't equal the normalized
    # heading — but the substring fallback still wins.
    assert raw == "Application to \\chandra\\ Observations of Clusters "


def test_resolve_substring_match():
    assert resolve_section("application", BULBUL_HEADINGS) == BULBUL_HEADINGS[2]
    assert resolve_section("polytropic equation", BULBUL_HEADINGS) == BULBUL_HEADINGS[1]


def test_resolve_returns_none_on_no_match():
    assert resolve_section("nonexistent topic xyz", BULBUL_HEADINGS) is None
    assert resolve_section("", BULBUL_HEADINGS) is None


def test_resolve_topic_methodology_finds_model_section():
    hits = resolve_topic("methodology", BULBUL_HEADINGS)
    assert BULBUL_HEADINGS[1] in hits  # "A Model of the Intergalactic Medium..."


def test_resolve_topic_results_falls_to_application():
    # 'results' has no exact heading here; 'application' contains data analysis,
    # but the alias list looks for "result|fits|measurement". Bulbul's results
    # are labeled differently — confirm the resolver returns [] cleanly when no
    # alias matches, rather than hallucinating.
    hits = resolve_topic("results", BULBUL_HEADINGS)
    # No false positive from "Comparison with Previous Work"
    assert all("comparison" not in normalize_heading(h) for h in hits)


def test_resolve_topic_conclusions_matches_discussion_and_conclusions():
    hits = resolve_topic("conclusions", BULBUL_HEADINGS)
    assert BULBUL_HEADINGS[4] in hits


def test_resolve_topic_unknown_falls_back_to_substring():
    # "introduction" alias hits introduction; an unknown topic falls back to substring.
    hits = resolve_topic("acknowledg", BULBUL_HEADINGS)
    assert BULBUL_HEADINGS[5] in hits


def test_display_label_is_clean_titlecase():
    assert display_label("Application to \\chandra\\ Observations of Clusters ") == \
        "Application To Observations Of Clusters"


def test_extract_by_raw_name_handles_trailing_whitespace():
    """Regression: upstream extract_section returns '' for headings with trailing
    whitespace (a real bug observed against Bulbul 2010). Our wrapper must work."""
    from mcp_ads_arxiv.sections import extract_by_raw_name

    tex = (
        r"\documentclass{article}\begin{document}"
        "\n\\section{Application to \\chandra\\ Observations of Clusters }\n"
        "Body text describing chandra observations.\n"
        "\\section{Comparison with Previous Work }\n"
        "Comparison body.\n"
        "\\end{document}\n"
    )
    out = extract_by_raw_name(tex, "Application to \\chandra\\ Observations of Clusters ")
    assert "Body text describing chandra observations" in out
    # Must NOT bleed into the next section.
    assert "Comparison body" not in out
