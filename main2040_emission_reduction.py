import random
from mes_north_sea.optimization.utilities import *
from pathlib import Path
import pyomo.environ as pyo
from pyomo.util.infeasible import log_infeasible_constraints
import logging
import pandas as pd
from multiprocessing import Pool

test = 1
settings = Settings(test=test)
settings.demand_factor = 1
settings.year = 2040
settings.variable_h2_demand = 0
cys = [1995] # 2008, 2009
co2_tax = [100]
c_permutation = 0.01

data_path = "mes_north_sea/data_" + str(settings.year)
save_path = "results"
Path(save_path + "/2040_test/").mkdir(parents=True, exist_ok=True)
Path(save_path + "/2040/").mkdir(parents=True, exist_ok=True)

write_to_network_data(settings)
write_to_technology_data(settings)

neg_emission_cap = 5000
emission_targets = [0.5] # 0.99, 0.98, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0
emission_targets.reverse()

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
    # 'Battery_on': 'Battery (onshore only)',
    # 'Battery_off': 'Battery (offshore only)',
             }

for stage in scenarios.keys():

    if stage in [
    'ElectricityGrid_all',
    'ElectricityGrid_on',
    'ElectricityGrid_off',
    'ElectricityGrid_noBorder',
    'RE_only',
    'Battery_on',
    'Battery_off',
    'Battery_all']:
        settings.model_h2 = 0
    else:
        settings.model_h2 = 1


    def run_climate_year(cy):
        input_data_path = Path(data_path + "_" + str(cy))
        input_data_path.mkdir(parents=True, exist_ok=True)
        Path(f"results/2040/emission_reduction/cy{cy}/summaries/").mkdir(parents=True, exist_ok=True)
        Path("results/2040_test/").mkdir(parents=True, exist_ok=True)

        for tax in co2_tax:
            settings.co2_tax = tax

            settings.climate_year = cy

            # baseline emissions value cy1995
            # baseline_value = 69408942.54299

            settings.new_technologies_stage = stage

            adopt.create_optimization_templates(input_data_path)

            nodes = read_nodes(settings)

            define_topology(settings, input_data_path, nodes)
            define_configuration(input_data_path, settings)

            adopt.create_input_data_folder_template(input_data_path)

            define_node_locations(input_data_path, nodes)
            define_installed_capacities(input_data_path, settings, nodes)
            define_new_technologies(input_data_path, settings, nodes)
            adopt.copy_technology_data(input_data_path, Path(settings.data_path / "technology_data"))
            define_networks(input_data_path, settings)
            define_storage(input_data_path, settings, nodes)
            define_network_topology(input_data_path, settings, nodes)
            adopt.copy_network_data(input_data_path, Path(settings.data_path / "network_data"))

            define_demand(input_data_path, settings, nodes)

            define_generic_production(input_data_path, settings, nodes)
            define_hydro_inflow(input_data_path, settings)
            define_capacity_factors(input_data_path, settings)
            define_max_renewable_capacities(input_data_path, settings)

            define_imports_exports(input_data_path, settings, nodes)

            m = adopt.ModelHub()
            m.read_data(input_data_path)

            if settings.test:
                m.data.model_config["reporting"]["save_summary_path"]["value"] = save_path + "/2040_test/"
                m.data.model_config["reporting"]["save_path"]["value"] = save_path + "/2040_test/"
            else:
                m.data.model_config["reporting"]["save_summary_path"]["value"] = save_path + "/2040/emission_reduction/cy" + str(settings.climate_year) + "/summaries/"
                m.data.model_config["reporting"]["save_path"]["value"] = save_path + "/2040/emission_reduction/cy" + str(settings.climate_year) + "/"

            m.construct_model()
            m.construct_balances()
            m._define_solver_settings()

            # Baseline
            m.data.model_config["reporting"]["case_name"]["value"] = stage + '_baseline_cy' + str(cy)
            m._optimize_cost()
            baseline_value = m.model[
                m.info_solving_algorithms["aggregation_model"]
            ].var_emissions_net.value
            print(f"2040 baseline emissions: {baseline_value:.0f} tCO2")

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

            # min neg emissions at emission limit
            m.data.model_config["optimization"].setdefault("neg_emission_limit", {})["value"] = neg_emission_cap
            for reduction in emission_targets:
                m.data.model_config["optimization"]["emission_limit"]["value"] = baseline_value * reduction

                if settings.test == 1:
                    m.data.model_config["reporting"]["case_name"]["value"] = 'TEST' + stage + '_minNegE_at_' + str(
                        reduction)
                else:
                    m.data.model_config["reporting"]["case_name"]["value"] = stage + '_minNegE_at_' + str(reduction)

                m._optimize_neg_emissions_emissionslimit()

if __name__ == '__main__':
    with Pool(processes=len(cys)) as pool:
        pool.map(run_climate_year, cys)
