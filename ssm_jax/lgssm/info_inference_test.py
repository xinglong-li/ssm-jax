from jax import vmap
from jax import numpy as jnp
from jax import random as jr

from ssm_jax.lgssm.models import LinearGaussianSSM
from ssm_jax.lgssm.inference import LGSSMParams, lgssm_filter
from ssm_jax.lgssm.info_inference import LGSSMInfoParams, lgssm_info_filter, lgssm_info_smoother


def info_to_moment_form(etas,Lambdas):
    """Convert information form parameters to moment form.

    Args:
        etas (N,D): precision weighted means.
        Lambdas (N,D,D): precision matrices.

    Returns:
        means (N,D)
        covs (N,D,D)
    """
    means = vmap(jnp.linalg.solve)(Lambdas,etas)
    covs = jnp.linalg.inv(Lambdas)
    return means, covs

def test_info_kalman_filtering_and_smoothing():
    """ Test information form Kalman filter against the moment form version."""

    delta = 1.0
    F = jnp.array([
        [1., 0, delta, 0],
        [0, 1., 0, delta],
        [0, 0, 1., 0],
        [0, 0, 0, 1.]
    ])

    H = jnp.array([
        [1., 0, 0, 0],
        [0, 1., 0, 0]
    ])

    state_size, _ = F.shape
    observation_size, _ = H.shape

    Q = jnp.eye(state_size) * 0.001
    Q_prec = jnp.linalg.inv(Q)
    R = jnp.eye(observation_size) * 1.0
    R_prec = jnp.linalg.inv(R)

    input_size = 1
    B = jnp.array([1.,0.5,-0.05,-0.01]).reshape((state_size,input_size))
    b = jnp.ones((state_size,)) * 0.01
    D = jnp.ones((observation_size,input_size))
    d = jnp.ones((observation_size,)) * 0.02

    # Prior parameter distribution
    mu0 = jnp.array([8., 10., 1., 0.])
    Sigma0 = jnp.eye(state_size) * 0.1
    Lambda0 = jnp.linalg.inv(Sigma0)

    # Construct LGSSM
    lgssm = LinearGaussianSSM(
        initial_mean=mu0,
        initial_covariance=Sigma0,
        dynamics_matrix=F,
        dynamics_covariance=Q,
        dynamics_input_weights=B,
        dynamics_bias=b,
        emission_matrix=H,
        emission_covariance=R,
        emission_input_weights=D,
        emission_bias=d)

    # Collect information form parameters
    lgssm_info = LGSSMInfoParams(
        initial_mean=mu0,
        initial_precision=Lambda0,
        dynamics_matrix=F,
        dynamics_precision=Q_prec,
        dynamics_input_weights=B,
        dynamics_bias=b,
        emission_matrix=H,
        emission_precision=R_prec,
        emission_input_weights=D,
        emission_bias=d)

    # Sample data from model.
    key = jr.PRNGKey(111)
    num_timesteps = 15
    inputs = jnp.zeros((num_timesteps,input_size))
    x, y = lgssm.sample(key,num_timesteps,inputs)

    lgssm_posterior = lgssm.smoother(y,inputs)
    lgssm_info_posterior = lgssm_info_smoother(lgssm_info, y, inputs) 
    
    info_filtered_means, info_filtered_covs = info_to_moment_form(
            lgssm_info_posterior.filtered_etas,
            lgssm_info_posterior.filtered_precisions
            )
    info_smoothed_means, info_smoothed_covs = info_to_moment_form(
            lgssm_info_posterior.smoothed_etas,
            lgssm_info_posterior.smoothed_precisions
            )

    assert jnp.allclose(info_filtered_means,
                        lgssm_posterior.filtered_means,
                        rtol=1e-2)
    assert jnp.allclose(info_filtered_covs,
                        lgssm_posterior.filtered_covariances,
                        rtol=1e-2)
    assert jnp.allclose(info_smoothed_means,
                        lgssm_posterior.smoothed_means,
                        rtol=1e-2)
    assert jnp.allclose(info_smoothed_covs,
                        lgssm_posterior.smoothed_covariances,
                        rtol=1e-2)
    assert jnp.allclose(lgssm_info_posterior.marginal_loglik,
                        lgssm_posterior.marginal_loglik,
                        rtol=1e-2)


def test_info_kf_linreg():
    """Test non-stationary emission matrix in information filter.
    
    Compare to moment form filter using the example in 
        `lgssm/demos/kf_linreg.py`
    """
    n_obs = 21
    x = jnp.linspace(0, 20, n_obs)
    X = jnp.column_stack((jnp.ones_like(x), x)) # Design matrix.
    F = jnp.eye(2)
    Q = jnp.zeros((2,2)) # No parameter drift.
    Q_prec = jnp.diag(jnp.repeat(1e32, 2)) # Can't use infinite precision.
    obs_var = 1.
    R = jnp.ones((1,1)) * obs_var
    R_prec = jnp.linalg.inv(R)
    mu0 = jnp.zeros(2)
    Sigma0 = jnp.eye(2) * 10.
    Lambda0 = jnp.linalg.inv(Sigma0)

    # Data from original matlab example
    y = jnp.array([2.4865, -0.3033, -4.0531, -4.3359, -6.1742, -5.604, -3.5069,
                   -2.3257, -4.6377, -0.2327, -1.9858, 1.0284, -2.264, -0.4508,
                   1.1672, 6.6524, 4.1452, 5.2677, 6.3403, 9.6264, 14.7842])
    inputs = jnp.zeros((len(y),1))

    lgssm_moment = LGSSMParams(
        initial_mean=mu0,
        initial_covariance=Sigma0,
        dynamics_matrix=F,
        dynamics_input_weights=jnp.zeros((mu0.shape[0],1)), # no inputs
        dynamics_bias=jnp.zeros(1),
        dynamics_covariance=Q,
        emission_matrix=X[:,None,:],
        emission_input_weights=jnp.zeros(1),
        emission_bias=jnp.zeros(1),
        emission_covariance=R
    )

    lgssm_info = LGSSMInfoParams(
        initial_mean=mu0,
        initial_precision=Lambda0,
        dynamics_matrix=F,
        dynamics_input_weights=jnp.zeros((mu0.shape[0],1)), # no inputs
        dynamics_bias=jnp.zeros(1),
        dynamics_precision=Q_prec,
        emission_matrix=X[:,None,:],
        emission_input_weights=jnp.zeros(1),
        emission_bias=jnp.zeros(1),
        emission_precision=R_prec
    )

    lgssm_moment_posterior = lgssm_filter(lgssm_moment, y[:,None], inputs)
    lgssm_info_posterior = lgssm_info_filter(lgssm_info, y[:,None], inputs)

    info_filtered_means, info_filtered_covs = info_to_moment_form(
            lgssm_info_posterior.filtered_etas,
            lgssm_info_posterior.filtered_precisions
            )

    assert jnp.allclose(info_filtered_means,
                        lgssm_moment_posterior.filtered_means,
                        rtol=1e-2)
    assert jnp.allclose(info_filtered_covs,
                        lgssm_moment_posterior.filtered_covariances,
                        rtol=1e-2)

