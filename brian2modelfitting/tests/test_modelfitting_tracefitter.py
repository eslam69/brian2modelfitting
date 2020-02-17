'''
Test the modelfitting module
'''
import pytest
import numpy as np
import pandas as pd
try:
    import lmfit
except ImportError:
    lmfit = None
from numpy.testing.utils import assert_equal
from brian2 import (zeros, Equations, NeuronGroup, StateMonitor, TimedArray,
                    nS, mV, volt, ms, Quantity, set_device, get_device, Network)
from brian2 import have_same_dimensions
from brian2modelfitting import (NevergradOptimizer, TraceFitter, MSEMetric,
                                OnlineTraceFitter, Simulator, Metric,
                                Optimizer, GammaFactor)
from brian2.devices.device import reinit_devices, reset_device
from brian2modelfitting.fitter import get_param_dic


E = 40*mV
input_traces = zeros((10, 5))*volt
for i in range(5):
    input_traces[5:, i] = i*10*mV

output_traces = 10*nS*input_traces

model = Equations('''
    I = g*(v-E) : amp
    g : siemens (constant)
    ''')

strmodel = '''
    I = g*(v-E) : amp
    g : siemens (constant)
    '''

constant_model = Equations('''
    v = c + x: volt
    c : volt (constant)''')

n_opt = NevergradOptimizer()
metric = MSEMetric()


@pytest.fixture
def setup(request):
    dt = 0.01 * ms
    tf = TraceFitter(dt=dt,
                     model=model,
                     input_var='v',
                     output_var='I',
                     input=input_traces,
                     output=output_traces,
                     n_samples=2,)

    def fin():
        reinit_devices()
    request.addfinalizer(fin)

    return dt, tf


@pytest.fixture
def setup_constant(request):
    dt = 0.1 * ms
    # Membrane potential is constant at 10mV for first 50 steps, then at 20mV
    out_trace = np.hstack([np.ones(50) * 10 * mV, np.ones(50) * 20 * mV])
    tf = TraceFitter(dt=dt,
                     model=constant_model,
                     input_var='x',
                     output_var='v',
                     input=(np.zeros(100)*mV)[None, :],
                     output=out_trace[None, :],
                     n_samples=100,)

    def fin():
        reinit_devices()
    request.addfinalizer(fin)

    return dt, tf


@pytest.fixture
def setup_online(request):
    dt = 0.01 * ms

    otf = OnlineTraceFitter(dt=dt,
                            model=strmodel,
                            input_var='v',
                            output_var='I',
                            input=input_traces,
                            output=output_traces,
                            n_samples=10,)

    def fin():
        reinit_devices()
    request.addfinalizer(fin)

    return dt, otf


@pytest.fixture
def setup_standalone(request):
    set_device('cpp_standalone', directory=None)
    dt = 0.01 * ms
    tf = TraceFitter(dt=dt,
                     model=model,
                     input_var='v',
                     output_var='I',
                     input=input_traces,
                     output=output_traces,
                     n_samples=2)

    def fin():
        reinit_devices()
        set_device('runtime')
    request.addfinalizer(fin)

    return dt, tf

def test_get_param_dic():
    d = get_param_dic([1, 2], ['a', 'b'], 2, 2)
    assert isinstance(d, dict)
    assert_equal(d, {'a': [1, 1, 1, 1], 'b': [2, 2, 2, 2]})

    d = get_param_dic([[1, 3], [2, 4]], ['a', 'b'], 1, 1)
    assert_equal(d, {'a': [1, 2], 'b': [3, 4]})

    d = get_param_dic([[1, 3], [2, 4]], ['a', 'b'], 1, 2)
    assert_equal(d, {'a': [1, 2], 'b': [3, 4]})

    d = get_param_dic([[1, 3], [2, 4]], ['a', 'b'], 2, 1)
    assert_equal(d, {'a': [1, 1, 2, 2], 'b': [3, 3, 4, 4]})


def test_tracefitter_init(setup):
    dt, tf = setup
    attr_fitter = ['dt', 'simulator', 'parameter_names', 'n_traces',
                   'duration', 'n_neurons', 'n_samples', 'method', 'threshold',
                   'reset', 'refractory', 'input', 'output', 'output_var',
                   'best_params', 'input_traces', 'model', 'optimizer',
                   'metric']
    for attr in attr_fitter:
        assert hasattr(tf, attr)

    assert tf.metric is None
    assert tf.optimizer is None
    assert tf.best_params is None

    attr_tracefitter = ['input_traces', 'model', 'simulator']
    for attr in attr_tracefitter:
        assert hasattr(tf, attr)

    assert isinstance(tf.simulator, Simulator)
    assert isinstance(tf.input_traces, TimedArray)
    assert isinstance(tf.model, Equations)


def test_tracefitter_init_errors(setup):
    dt, _ = setup
    with pytest.raises(Exception):
        TraceFitter(dt=dt, model=model, input=input_traces,
                    n_samples=10,
                    output=output_traces,
                    output_var='I',
                    input_var='Exception',)

    with pytest.raises(Exception):
        TraceFitter(dt=0.1*ms, model=model, input=input_traces,
                    n_samples=10,
                    output=output_traces,
                    input_var='v',
                    output_var='Exception',)

    with pytest.raises(Exception):
        TraceFitter(dt=0.1*ms, model=model, input=input_traces,
                    n_samples=10,
                    output=[1],
                    input_var='v',
                    output_var='I',)


def test_fitter_fit(setup):
    dt, tf = setup
    results, errors = tf.fit(n_rounds=2,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS],
                             callback=None)

    attr_fit = ['optimizer', 'metric', 'best_params']
    for attr in attr_fit:
        assert hasattr(tf, attr)

    assert isinstance(tf.metric, Metric)
    assert isinstance(tf.optimizer, Optimizer)
    assert isinstance(tf.simulator, Simulator)

    assert isinstance(results, dict)
    assert isinstance(errors, float)
    assert 'g' in results.keys()

    assert_equal(results, tf.best_params)


def test_fitter_fit_errors(setup):
    dt, tf = setup
    with pytest.raises(TypeError):
        tf.fit(n_rounds=2,
               optimizer=None,
               metric=metric,
               g=[1*nS, 30*nS])

    with pytest.raises(TypeError):
        tf.fit(n_rounds=2,
               optimizer=n_opt,
               metric=1,
               g=[1*nS, 30*nS])


def test_fitter_fit_tstart(setup_constant):
    dt, tf = setup_constant

    # Ignore the first 50 steps at 10mV
    params, result = tf.fit(n_rounds=10, optimizer=n_opt,
                            metric=MSEMetric(t_start=50*dt),
                            c=[0 * mV, 30 * mV])
    # Fit should be close to 20mV
    assert np.abs(params['c']*volt - 20*mV) < 1*mV

@pytest.mark.skipif(lmfit is None, reason="needs lmfit package")
def test_fitter_refine(setup):
    dt, tf = setup
    results, errors = tf.fit(n_rounds=2,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS],
                             callback=None)
    # Run refine after running fit
    params, result = tf.refine()
    assert result.method == 'leastsq'
    assert isinstance(params, dict)
    assert isinstance(result, lmfit.minimizer.MinimizerResult)

    # Pass options to lmfit.minimize
    params, result = tf.refine(method='least_squares')
    assert result.method == 'least_squares'


@pytest.mark.skipif(lmfit is None, reason="needs lmfit package")
def test_fitter_refine_standalone(setup_standalone):
    dt, tf = setup_standalone
    results, errors = tf.fit(n_rounds=2,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS],
                             callback=None)
    # Run refine after running fit
    params, result = tf.refine()
    assert result.method == 'leastsq'
    assert isinstance(params, dict)
    assert isinstance(result, lmfit.minimizer.MinimizerResult)

    # Pass options to lmfit.minimize
    params, result = tf.refine(method='least_squares')
    assert result.method == 'least_squares'


@pytest.mark.skipif(lmfit is None, reason="needs lmfit package")
def test_fitter_refine_direct(setup):
    dt, tf = setup
    # Run refine without running fit before
    params, result = tf.refine({'g': 5*nS}, g=[1*nS, 30*nS])
    assert isinstance(params, dict)
    assert isinstance(result, lmfit.minimizer.MinimizerResult)


@pytest.mark.skipif(lmfit is None, reason="needs lmfit package")
def test_fitter_refine_tstart(setup_constant):
    dt, tf = setup_constant

    # Ignore the first 50 steps at 10mV
    params, result = tf.refine({'c': 5*mV}, c=[0 * mV, 30 * mV],
                               t_start=50*dt)

    # Fit should be close to 20mV
    print(params['c'])
    assert np.abs(params['c']*volt - 20*mV) < 1*mV


@pytest.mark.skipif(lmfit is None, reason="needs lmfit package")
def test_fitter_refine_reuse_tstart(setup_constant):
    dt, tf = setup_constant

    # Ignore the first 50 steps at 10mV but do not actually fit (0 rounds)
    params, result = tf.fit(n_rounds=0, optimizer=n_opt,
                            metric=MSEMetric(t_start=50*dt),
                            c=[0 * mV, 30 * mV])
    # t_start should be reused
    params, result = tf.refine({'c': 5 * mV}, c=[0 * mV, 30 * mV])

    # Fit should be close to 20mV
    assert np.abs(params['c'] * volt - 20 * mV) < 1 * mV


@pytest.mark.skipif(lmfit is None, reason="needs lmfit package")
def test_fitter_refine_errors(setup):
    dt, tf = setup
    with pytest.raises(TypeError):
        # Missing start parameter
        tf.refine(g=[1*nS, 30*nS])

    with pytest.raises(TypeError):
        # Missing bounds
        tf.refine({'g': 5*nS})


def test_fit_restart(setup):
    dt, tf = setup
    results, errors = tf.fit(n_rounds=2,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS])

    results, errors = tf.fit(n_rounds=2,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS])

    results, errors = tf.fit(n_rounds=2,
                             restart=True,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS])


def test_fit_continue_with_generate(setup):
    dt, tf = setup
    results, error = tf.fit(n_rounds=2,
                            optimizer=n_opt,
                            metric=metric,
                            g=[1*nS, 30*nS])

    fits = tf.generate_traces()

    results, error = tf.fit(n_rounds=2,
                            optimizer=n_opt,
                            metric=metric,
                            g=[1*nS, 30*nS])

    fits = tf.generate_traces()


def test_fit_restart_errors(setup):
    dt, tf = setup
    results, errors = tf.fit(n_rounds=2,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS],
                             restart=False,)

    n_opt2 = NevergradOptimizer('PSO')
    with pytest.raises(Exception):
        tf.fit(n_rounds=2,
               optimizer=n_opt2,
               metric=metric,
               g=[1*nS, 30*nS],
               restart=False,)

    metric2 = GammaFactor(40*ms, 40*ms)
    with pytest.raises(Exception):
        tf.fit(n_rounds=2,
               optimizer=n_opt,
               metric=metric2,
               g=[1*nS, 30*nS],
               restart=False,)


def test_fit_restart_change(setup):
    dt, tf = setup
    results, errors = tf.fit(n_rounds=2,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS],
                             restart=False,)

    n_opt2 = NevergradOptimizer('PSO')
    results2, errors2 = tf.fit(n_rounds=2,
                               optimizer=n_opt2,
                               metric=metric,
                               g=[1*nS, 30*nS],
                               restart=True,)


def test_fitter_generate_traces(setup):
    dt, tf = setup
    results, errors = tf.fit(n_rounds=2,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS],
                             restart=False,)
    traces = tf.generate_traces()
    assert isinstance(traces, np.ndarray)
    assert_equal(np.shape(traces), np.shape(output_traces))


def test_fitter_generate_traces_standalone(setup_standalone):
    dt, tf = setup_standalone
    results, errors = tf.fit(n_rounds=2,
                             optimizer=n_opt,
                             metric=metric,
                             g=[1*nS, 30*nS],
                             restart=False,)

    traces = tf.generate_traces()
    assert isinstance(traces, np.ndarray)
    assert_equal(np.shape(traces), np.shape(output_traces))


def test_fitter_results(setup):
    dt, tf = setup
    best_params, errors = tf.fit(n_rounds=2,
                              optimizer=n_opt,
                              metric=metric,
                              g=[1*nS, 30*nS],
                              restart=False,)

    params_list = tf.results(format='list')
    assert isinstance(params_list, list)
    assert isinstance(params_list[0], dict)
    assert isinstance(params_list[0]['g'], Quantity)
    assert 'g' in params_list[0].keys()
    assert 'errors' in params_list[0].keys()
    assert_equal(np.shape(params_list), (4,))
    assert_equal(len(params_list[0]), 2)
    assert have_same_dimensions(params_list[0]['g'].dim, nS)

    params_dic = tf.results(format='dict')
    assert isinstance(params_dic, dict)
    assert 'g' in params_dic.keys()
    assert 'errors' in params_dic.keys()
    assert isinstance(params_dic['g'], Quantity)
    assert_equal(len(params_dic), 2)
    assert_equal(np.shape(params_dic['g']), (4,))
    assert_equal(np.shape(params_dic['errors']), (4,))

    params_df = tf.results(format='dataframe')
    assert isinstance(params_df, pd.DataFrame)
    assert_equal(params_df.shape, (4, 2))
    assert 'g' in params_df.keys()
    assert 'errors' in params_df.keys()


# OnlineTraceFitter
def test_onlinetracefitter_init(setup_online):
    dt, otf = setup_online
    attr_fitter = ['dt', 'simulator', 'parameter_names', 'n_traces',
                   'duration', 'n_neurons', 'n_samples', 'method', 'threshold',
                   'reset', 'refractory', 'input', 'output', 'output_var',
                   'best_params', 'input_traces', 'model', 'optimizer',
                   'metric', 't_start']
    for attr in attr_fitter:
        assert hasattr(otf, attr)

    assert otf.metric is None
    assert otf.optimizer is None
    assert otf.best_params is None
    assert_equal(otf.t_start, 0*ms)

    attr_tracefitter = ['input_traces', 'model', 'simulator']
    for attr in attr_tracefitter:
        assert hasattr(otf, attr)

    assert isinstance(otf.simulator, Simulator)
    assert isinstance(otf.input_traces, TimedArray)
    assert isinstance(otf.model, Equations)


def test_onlinetracefitter_init_errors(setup_online):
    dt, _ = setup_online
    with pytest.raises(Exception):
        OnlineTraceFitter(dt=dt, model=model, input=input_traces,
                          n_samples=10,
                          output=output_traces,
                          output_var='I',
                          input_var='Exception',)

    with pytest.raises(Exception):
        OnlineTraceFitter(dt=0.1*ms, model=model, input=input_traces,
                          n_samples=10,
                          output=output_traces,
                          input_var='v',
                          output_var='Exception',)

    with pytest.raises(Exception):
        OnlineTraceFitter(dt=0.1*ms, model=model, input=input_traces,
                          n_samples=10,
                          output=[1],
                          input_var='v',
                          output_var='I',)


def test_onlinetracefitter_fit(setup_online):
    dt, otf = setup_online
    results, errors = otf.fit(n_rounds=2,
                              optimizer=n_opt,
                              g=[1*nS, 30*nS],
                              restart=False,)

    attr_fit = ['optimizer', 'metric', 'best_params']
    for attr in attr_fit:
        assert hasattr(otf, attr)

    assert otf.metric is None
    assert isinstance(otf.optimizer, Optimizer)
    assert isinstance(otf.simulator, Simulator)

    assert isinstance(results, dict)
    assert isinstance(errors, float)
    assert 'g' in results.keys()

    assert_equal(results, otf.best_params)
