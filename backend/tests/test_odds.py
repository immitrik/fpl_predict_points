import numpy as np

from fplpredict.odds import _implied, _model_probs, fit_lambdas


def test_fit_recovers_poisson_rates():
    lh, la = 1.8, 0.9
    home, draw, over = _model_probs(lh, la)
    got = fit_lambdas(np.array([home, draw, 1 - home - draw]), over)
    assert np.allclose(got, (lh, la), atol=1e-3)


def test_implied_probabilities_sum_to_one():
    p = _implied(np.array([[1.5, 4.0, 7.0]]))
    assert np.isclose(p.sum(), 1.0)
    assert p[0, 0] > p[0, 1] > p[0, 2]
