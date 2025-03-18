import scipy.stats  # ignore:import-untyped
from pcm import copulas
import pytest
import numpy as np
import scipy
import scipy.special


def copula_margins(copula_samples):
    # check values are between 0 and 1
    y = [(0 < x < 1).values.all() for x in copula_samples]
    assert np.array(y).all()

    # check the values are uniform by checking the moments
    for u in copula_samples:
        assert np.isclose(u.mean(), 0.5, atol=1e-2)
        assert np.isclose(u.std(), 1 / np.sqrt(12), atol=1e-2)
        assert np.isclose(u.skew(), 0, atol=1e-1)
        assert np.isclose(u.kurt(), 3 - 6 / 5, atol=1e-1)


@pytest.mark.parametrize("correlation", [-0.999, 0.5, 0, -0.5, 0.25, 0.75, 0.999])
def test_gaussian_copula(correlation):
    samples = copulas.GaussianCopula([[1, correlation], [correlation, 1]]).generate(
        100000
    )
    # test the correlations
    emp_corr = np.corrcoef((samples[0].values, samples[1].values))[0, 1]
    # convert from rank to linear
    rank_corr = 2 * np.sin(emp_corr * np.pi / 6)
    assert np.isclose(rank_corr, correlation, atol=1e-2)
    k = scipy.stats.kendalltau(samples[0].values, samples[1].values).statistic
    assert np.isclose(k, 2 / np.pi * np.asin(correlation), atol=1e-2)
    # test the margins
    copula_margins(samples)


@pytest.mark.parametrize("correlation", [-0.999, 0.5, -0.5, 0, 0.25, 0.75, 0.999])
def test_studentst_copula(correlation):
    samples = copulas.StudentsTCopula([[1, correlation], [correlation, 1]], 5).generate(
        100000
    )
    k = scipy.stats.kendalltau(samples[0].values, samples[1].values).statistic
    assert np.isclose(k, 2 / np.pi * np.asin(correlation), atol=1e-2)
    # test the margins
    copula_margins(samples)


@pytest.mark.parametrize("alpha", [0.0, 0.5, 1.25, 2.75])
def test_clayton_copula(alpha):
    samples = copulas.ClaytonCopula(alpha, 2).generate(100000)
    k = scipy.stats.kendalltau(samples[0].values, samples[1].values).statistic
    assert np.isclose(k, alpha / (2 + alpha), atol=1e-2)
    # test the margins
    copula_margins(samples)


@pytest.mark.parametrize("theta", [1.001, 1.25, 2.2, 5])
def test_gumbel_copula(theta):
    samples = copulas.GumbelCopula(theta, 2).generate(100000)
    # calculate the Kendall's tau value
    k = scipy.stats.kendalltau(samples[0].values, samples[1].values).statistic
    assert np.isclose(k, 1 - 1 / theta, atol=1e-2)
    # test the margins
    copula_margins(samples)


@pytest.mark.parametrize("theta", [1.001, 1.25, 2.2, 3])
def test_joe_copula(theta):
    samples = copulas.JoeCopula(theta, 2).generate(100000)
    # calculate the Kendall's tau value
    k = scipy.stats.kendalltau(samples[0].values, samples[1].values).statistic
    assert np.isclose(
        k,
        1
        + 2
        / (2 - theta)
        * (scipy.special.digamma(2) - scipy.special.digamma(2 / theta + 1)),
        atol=1e-2,
    )
    # test the margins
    copula_margins(samples)


def debye1(x):
    """The first Debye function"""
    return (
        np.log(1 - np.exp(-x)) * x
        + scipy.special.zeta(2)
        - scipy.special.spence(1 - np.exp(-x))
    ) / x


@pytest.mark.parametrize("theta", [0.001, 0.5, 2, 4])
def test_frank_copula(theta):
    samples = copulas.FrankCopula(theta, 2).generate(100000)
    # calculate the Kendall's tau value
    k = scipy.stats.kendalltau(samples[0].values, samples[1].values).statistic
    assert np.isclose(
        k,
        1 + 4 / theta * (debye1(theta) - 1),
        atol=1e-2,
    )
    # test the margins
    copula_margins(samples)
