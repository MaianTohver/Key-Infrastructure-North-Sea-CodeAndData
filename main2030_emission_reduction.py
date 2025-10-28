from pathlib import Path
from mes_north_sea.optimization.utilities import *
import random

test = 1
settings = Settings(test=test)
settings.demand_factor = 1
settings.year = 2030
settings.variable_h2_demand = 0
cys = [2008,2009]
c_permutation = 0.01

data_path  = "mes_north_sea/data_" + str(settings.year)
save_path = "path_to_save_results"

write_to_network_data(settings)
write_to_technology_data(settings)

h2_emissions = 29478397.12

emission_targets = [0.99, 0.98, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0]
emission_targets.reverse()

scenarios = {
    'Baseline': 'Baseline',
              'Battery_on': 'Battery (onshore only)',
              'Battery_off': 'Battery (offshore only)',
              'Battery_all': 'Battery (all)',
              'Battery_all_HP': 'Battery (all, high power-energy-ratio)',
              'ElectricityGrid_all': 'Grid Expansion (all)',
              'ElectricityGrid_on': 'Grid Expansion (onshore only)',
              'ElectricityGrid_off': 'Grid Expansion (offshore only)',
              'ElectricityGrid_noBorder': 'Grid Expansion (no Border)',
              'Hydrogen_Baseline': 'Hydrogen (all)',
              'Hydrogen_H1': 'Hydrogen (no storage)',
              'Hydrogen_H2': 'Hydrogen (no hydrogen offshore)',
              'Hydrogen_H3': 'Hydrogen (no hydrogen onshore)',
              'Hydrogen_H4': 'Hydrogen (local use only)',
              'All': 'All Pathways'
             }

for stage in scenarios.keys():
    if stage != 'Baseline':
        if stage in ['Baseline', 'Battery_on',
                  'Battery_off',
                  'Battery_all',
                  'Battery_all_HP',
                  'ElectricityGrid_all',
                  'ElectricityGrid_on',
                  'ElectricityGrid_off',
                  'ElectricityGrid_noBorder']:
            settings.model_h2 = 0
        else:
            settings.model_h2 = 1

        for cy in cys:
            settings.climate_year = cy
            input_data_path = Path(data_path + "_" + str(cy))

            baseline_emissions = pd.read_excel("//Soliscom.uu.nl/geo/USERS/StaffUsers/6574114/EhubResults/MES NorthSea/20250515/2030/cost/00_cy" + str(settings.climate_year) + "/Summary.xlsx")
            baseline_emissions = baseline_emissions[baseline_emissions["case"] == "Baseline_costs_cy" + str(cy)]["emissions_net"][0] + h2_emissions

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
            define_network_topology(input_data_path, settings, nodes)
            adopt.copy_network_data(input_data_path, Path(settings.data_path / "network_data"))

            define_demand(input_data_path, settings, nodes)

            define_generic_production(input_data_path, settings, nodes)
            define_hydro_inflow(input_data_path, settings)

            define_imports_exports(input_data_path, settings, nodes)

            m = adopt.ModelHub()
            m.read_data(input_data_path)

            for node in m.data.technology_data["period1"]:
                for tec in m.data.technology_data["period1"][node]:
                    print(m.data.technology_data["period1"][node][tec].economics['unit_capex'])
                    m.data.technology_data["period1"][node][tec].economics['unit_capex'] = \
                        m.data.technology_data["period1"][node][tec].economics['unit_capex'] * random.uniform(
                            1 - c_permutation, 1 + c_permutation)
                    print(m.data.technology_data["period1"][node][tec].economics['unit_capex'])

            m = define_charging_efficiencies(settings, nodes, m)
            m.data.model_config["solveroptions"]["threads"]["value"] = 8
            if settings.test:
                m.data.model_config["reporting"]["save_summary_path"][
                    "value"] = save_path + "/2030_test/"
                m.data.model_config["reporting"]["save_path"][
                    "value"] = save_path + "/2030_test/"
            else:
                m.data.model_config["reporting"]["save_summary_path"][
                    "value"] = save_path + "/2030/emission_reduction/00_cy" + str(settings.climate_year)
                m.data.model_config["reporting"]["save_path"][
                    "value"] = save_path + "/2030/emission_reduction/"

            m.construct_model()
            m.construct_balances()
            m._define_solver_settings()

            # min emissions
            m.data.model_config["reporting"]["case_name"]["value"] = stage + '_minE' + "_cy" + str(settings.climate_year)
            m._optimize_emissions_net()
            max_em_reduction = (m.model[m.info_solving_algorithms["aggregation_model"]].var_emissions_net.value + h2_emissions) / baseline_emissions

            print(max_em_reduction)

            # min cost at emission limit
            for reduction in emission_targets:
                if max_em_reduction <= reduction:
                    m.data.model_config["optimization"]["emission_limit"]["value"] = baseline_emissions * reduction - h2_emissions
                    if settings.test == 1:
                        m.data.model_config["reporting"]["case_name"]["value"] = 'TEST' + stage + '_minCost_at_' + str(reduction)
                    else:
                        m.data.model_config["reporting"]["case_name"]["value"] = stage + '_minCost_at_' + str(reduction)

                    m._optimize_costs_emissionslimit()



