from futbol.models.poisson_markets import best_confident_pick, line_probabilities


def test_line_probabilities_over_under_sum_to_one():
    probs = line_probabilities(mu=5.0, lines=[2.5, 4.5, 8.5])
    for line, sides in probs.items():
        assert abs(sides["over"] + sides["under"] - 1.0) < 1e-9


def test_line_probabilities_low_mu_favours_under():
    probs = line_probabilities(mu=0.3, lines=[2.5])
    assert probs[2.5]["under"] > probs[2.5]["over"]


def test_best_confident_pick_respects_threshold():
    # mu muy bajo: "menos de 0.5" debería tener probabilidad muy alta
    pick = best_confident_pick(mu=0.05, lines=[0.5, 1.5, 2.5], min_conf=0.9)
    assert pick is not None
    assert pick["side"] == "under"
    assert pick["prob"] >= 0.9


def test_best_confident_pick_returns_none_when_uncertain():
    pick = best_confident_pick(mu=3.0, lines=[3.5], min_conf=0.75)
    assert pick is None
