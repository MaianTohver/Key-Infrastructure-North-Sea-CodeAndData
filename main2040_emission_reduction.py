import random
from mes_north_sea.optimization.utilities import *
from pathlib import Path
import pyomo.environ as pyo
from pyomo.util.infeasible import log_infeasible_constraints
import logging
import pandas as pd
import signal
from multiprocessing import Pool, TimeoutError
import os
import copy

# prevent infinite loops 8 hours
job_timeout = 8 * 60 * 60

test = 0
settings = Settings(test=test)
settings.demand_factor = 1
settings.year = 2040
settings.variable_h2_demand = 0
cys = [1995, 2008, 2009] # 1995, 2008, 2009
co2_tax = [100]
c_permutation = 0.01

data_path = "mes_north_sea/data_" + str(settings.year)
save_path = "/data/8051917/results"

neg_emission_cap = 5000000 #500,000 tco2/yr
# emission_targets = [0.6, 0.4, 0.2] # 0.99, 0.98, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0
# emission_targets.reverse()
max_neg_by_cy = {1995: 50340843.62, 2008: 50340843.62, 2009: 50340843.62} # 1995: 50340843.62, 2008: 50340843.62, 2009: 50340843.62,
neg_target_fracs = [0.2, 0.4, 0.6, 0.8, 1.0] # 0.2, 0.4, 0.6, 0.8, 1.0

scenarios = {
    # 'Hydrogen_H2': 'Hydrogen (no hydrogen offshore)',
    # 'Hydrogen_H1': 'Hydrogen (no storage)',
    # 'Hydrogen_H4': 'Hydrogen (local use only)',
    # 'Hydrogen_Baseline': 'Hydrogen (all)'
    # 'All': 'All Pathways',
    # 'Hydrogen_H3': 'Hydrogen (no hydrogen onshore)',
    # 'ElectricityGrid_all': 'Grid Expansion (all)',
    # 'ElectricityGrid_on': 'Grid Expansion (onshore only)',
    # 'ElectricityGrid_off': 'Grid Expansion (offshore only)',
    # 'ElectricityGrid_noBorder': 'Grid Expansion (no Border)',
    'RE_only': 'RE only',
    'Offshore_DAC_only': 'Offshore DAC only',
    'Onshore_DAC_only': 'Onshore DAC only',
    'Onshore_DAC_retrofits' : 'Onshore DAC retrofits',
    # 'Battery_on': 'Battery (onshore only)',
    # 'Battery_off': 'Battery (offshore only)',
             }


def run_climate_year(args):
    cy, stage, save_path = args
    settings_local = copy.deepcopy(settings)

    if stage in [
        'ElectricityGrid_all', 'ElectricityGrid_on', 'ElectricityGrid_off',
        'ElectricityGrid_noBorder', 'RE_only', 'Battery_on', 'Battery_off',
        'Battery_all', 'Offshore_DAC_only', 'Onshore_DAC_only', 'Onshore_DAC_retrofits',
    ]:
        settings_local.model_h2 = 0
    else:
        settings_local.model_h2 = 1

    # Include stage in path so parallel jobs don't overwrite each other
    input_data_path = Path(data_path + "_" + str(cy) + "_" + stage)
    input_data_path.mkdir(parents=True, exist_ok=True)
    Path(f"{save_path}/2040/emission_reduction/cy{cy}/summaries/").mkdir(parents=True, exist_ok=True)
    Path(f"{save_path}/2040_test/").mkdir(parents=True, exist_ok=True)

    for tax in co2_tax:
        settings_local.co2_tax = tax
        settings_local.climate_year = cy

        baseline_values = {1995: 68593610.6, 2008: 67662512.0, 2009: 71982656.0}
        baseline_value = baseline_values[cy]

        settings_local.new_technologies_stage = stage
        adopt.create_optimization_templates(input_data_path)
        nodes = read_nodes(settings_local)
        define_topology(settings_local, input_data_path, nodes)
        define_configuration(input_data_path, settings_local, save_path)
        adopt.create_input_data_folder_template(input_data_path)
        define_node_locations(input_data_path, nodes)
        define_installed_capacities(input_data_path, settings_local, nodes)
        define_new_technologies(input_data_path, settings_local, nodes)
        adopt.copy_technology_data(input_data_path, Path(settings_local.data_path / "technology_data"))
        define_networks(input_data_path, settings_local)
        define_storage(input_data_path, settings_local, nodes)
        define_network_topology(input_data_path, settings_local, nodes)
        adopt.copy_network_data(input_data_path, Path(settings_local.data_path / "network_data"))

        if stage == 'Onshore_DAC_retrofits':
            import json
            co2_pipe_path = input_data_path / "period1" / "network_data" / "CO2_Pipeline.json"
            with open(co2_pipe_path, "r") as f:
                co2_pipe_data = json.load(f)
            co2_pipe_data["Economics"]["gamma4"] = 0
            co2_pipe_data["Economics"]["opex_fixed"] = 0
            with open(co2_pipe_path, "w") as f:
                json.dump(co2_pipe_data, f, indent=2)

        define_demand(input_data_path, settings_local, nodes)
        define_generic_production(input_data_path, settings_local, nodes)
        define_hydro_inflow(input_data_path, settings_local)
        define_capacity_factors(input_data_path, settings_local)
        define_max_renewable_capacities(input_data_path, settings_local)
        define_imports_exports(input_data_path, settings_local, nodes)

        m = adopt.ModelHub()
        m.read_data(input_data_path)

        if settings_local.test:
            test_save_path = save_path + "/2040_test/" + stage + "_cy" + str(cy) + "/"
            Path(test_save_path).mkdir(parents=True, exist_ok=True)
            m.data.model_config["reporting"]["save_path"]["value"] = test_save_path
        else:
            full_save_path = save_path + "/2040/emission_reduction/" + stage + "/cy" + str(cy) + "/"
            Path(full_save_path).mkdir(parents=True, exist_ok=True)
            m.data.model_config["reporting"]["save_path"]["value"] = full_save_path

        os.environ["TMPDIR"] = "/scratch/8051917/tmp"
        os.makedirs("/scratch/8051917/tmp", exist_ok=True)

        m.construct_model()
        m.construct_balances()
        m._define_solver_settings()

            # maximise negative emissions
        for frac in neg_target_fracs:
            neg_target = max_neg_by_cy[cy] * frac
            m.data.model_config["optimization"].setdefault("neg_emission_limit", {})["value"] = neg_target
            m.data.model_config["optimization"].setdefault("pos_emission_limit", {})["value"] = baseline_value
            m.data.model_config["reporting"]["case_name"]["value"] = (
                f"{stage}_minCost_neg{frac:.2f}_cy{cy}")
            m._optimize_costs_emissionslimit()

            # # Baseline
            # m.data.model_config["reporting"]["case_name"]["value"] = stage + '_baseline_cy' + str(cy)
            # m._optimize_cost()
            # baseline_value = m.model[
            #     m.info_solving_algorithms["aggregation_model"]
            # ].var_emissions_net.value
            # print(f"2040 baseline emissions: {baseline_value:.0f} tCO2")

            # # min emissions
            # m.data.model_config["reporting"]["case_name"]["value"] = stage + '_minE' + "_cy" + str(
            #     settings.climate_year)
            # m._optimize_emissions_net()

            # # min cost at emission limit
            # m.data.model_config["optimization"].setdefault("neg_emission_limit", {})["value"] = neg_emission_cap
            # for reduction in emission_targets:
            #     m.data.model_config["optimization"]["emission_limit"]["value"] = baseline_value * reduction
            #
            #     if settings.test == 1:
            #         m.data.model_config["reporting"]["case_name"]["value"] = 'TEST' + stage + '_minCost_at_' + str(
            #             reduction)
            #     else:
            #         m.data.model_config["reporting"]["case_name"]["value"] = stage + '_minCost_at_' + str(reduction)

            # # min neg emissions at emission limit
            # m.data.model_config["optimization"].setdefault("neg_emission_limit", {})["value"] = neg_emission_cap
            # for reduction in emission_targets:
            #     m.data.model_config["optimization"]["emission_limit"]["value"] = baseline_value * reduction
            #
            #     if settings.test == 1:
            #         m.data.model_config["reporting"]["case_name"]["value"] = 'TEST' + stage + '_minNegE_at_' + str(
            #             reduction)
            #     else:
            #         m.data.model_config["reporting"]["case_name"]["value"] = stage + '_minNegE_at_' + str(reduction)
            #
            #     m._optimize_neg_emissions_emissionslimit()

def run_climate_year_with_timeout(args):
        def _timeout_handler(signum, frame):
            raise TimeoutError(f"Job {args} exceeded {job_timeout}s timeout, killing")

        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(job_timeout)

        try:
            result = run_climate_year(args)
            signal.alarm(0)
            return result
        except TimeoutError:
            raise

n_parallel = 4  # number of parallel runs

if __name__ == '__main__':
    write_to_network_data(settings)
    write_to_technology_data(settings)
    Path(save_path + "/2040_test/").mkdir(parents=True, exist_ok=True)
    Path(save_path + "/2040/").mkdir(parents=True, exist_ok=True)
    os.makedirs("/scratch/8051917/tmp", exist_ok=True)
    killed = []
    for stage in scenarios.keys():
        jobs = [(cy, stage, save_path) for cy in cys]
        with Pool(processes=n_parallel) as pool:
            async_results = [pool.apply_async(run_climate_year_with_timeout, (job,)) for job in jobs]
            for job, res in zip(jobs, async_results):
                try:
                    res.get(timeout=job_timeout + 60)
                except TimeoutError:
                    killed.append(job)
                    pool.terminate()
                    pool.join()
                    break
                except Exception as e:
                    killed.append(job)

    if killed:
        print(f"jobs killed or failed: {killed}", flush=True)
