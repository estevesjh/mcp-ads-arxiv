from mcp_ads_arxiv import survey


def _papers():
    return [
        {"title": "Galaxy cluster mass calibration", "keywords": ["galaxy clusters", "weak lensing"]},
        {"title": "Weak lensing of clusters", "keywords": ["galaxy clusters", "weak lensing"]},
        {"title": "Cluster scaling relations", "keywords": ["galaxy clusters", "scaling relations"]},
        {"title": "X-ray cluster surveys", "keywords": ["galaxy clusters", "X-ray"]},
    ]


def test_focus_ranks_uat_keywords_highest():
    result = survey.generate(_papers())
    # "galaxy clusters" appears in all keyword lists (weight 3 each) -> should rank first.
    assert result["focus"][0] == "galaxy clusters"
    assert result["n_papers"] == 4


def test_focus_and_exclude_are_disjoint_and_sized():
    result = survey.generate(_papers(), n=2)
    assert len(result["focus"]) <= 2
    assert len(result["exclude"]) <= 2
    assert set(result["focus"]).isdisjoint(result["exclude"])


def test_handles_empty_input():
    result = survey.generate([])
    assert result["n_papers"] == 0
    assert result["focus"] == []
    assert "Pre-Flight Survey" in result["prompt"]


def test_stopwords_filtered():
    papers = [{"title": "A study of the new data analysis", "keywords": []}]
    result = survey.generate(papers)
    assert "the" not in result["focus"]
    assert "study" not in result["focus"]
