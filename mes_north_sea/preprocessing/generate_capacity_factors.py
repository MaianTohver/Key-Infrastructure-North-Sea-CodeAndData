import pandas as pd
from pathlib import Path

script_dir = Path(__file__).parent.parent
clean_data_path = script_dir / "clean_data"

def calculate_cap_factors(re_profiles, save_path, tec, caps_type=None):
    cap_factors = pd.DataFrame()

    available_nodes = [col[0] for col in re_profiles.columns if col[1] == tec]
    capacity_lookup = dict(zip(caps_type['Node'], caps_type['Capacity our work'])) if caps_type is not None else {}

    for node in available_nodes:
        re_profile = re_profiles[(node, tec)]

        if re_profile.max() == 0:  
            print(f"  Skipping {node} - zero profile (inland node)")
            continue

        if tec == 'Wind offshore':
            cap = re_profile.max()
        elif node in capacity_lookup:
            cap = capacity_lookup[node]
        else:
            cap = re_profile.max()
            print(f"  Note: {node} has no installed capacity for {tec}, normalizing by profile max ({cap:.2f})")

        cap_factors[node] = re_profile / cap

    print(f"\n{tec} - nodes written: {sorted(cap_factors.columns.tolist())}")
    print(f"Max CF:\n{cap_factors.max()}")
    print(f"Mean CF:\n{cap_factors.mean()}")
    cap_factors.to_csv(save_path)


for climate_year in [1995, 2008, 2009]:
    print(f"\nProcessing year {climate_year}")

    re_profiles_path = clean_data_path / "production_profiles_re" / f"production_profiles_re{climate_year}.csv"
    caps_path = clean_data_path / "installed_capacities" / "capacities_node.csv"

    re_profiles = pd.read_csv(re_profiles_path, header=[0, 1])
    caps = pd.read_csv(caps_path, index_col=[0])

    pv_path = clean_data_path / "capacity_factors" / f"pv{climate_year}.csv"
    wind_onshore_path = clean_data_path / "capacity_factors" / f"wind_onshore{climate_year}.csv"
    wind_offshore_path = clean_data_path / "capacity_factors" / f"wind_offshore{climate_year}.csv"

    calculate_cap_factors(re_profiles, pv_path, 'PV', caps[caps['Technology'] == 'Solar'])
    calculate_cap_factors(re_profiles, wind_onshore_path, 'Wind onshore', caps[caps['Technology'] == 'Wind Onshore'])
    calculate_cap_factors(re_profiles, wind_offshore_path, 'Wind offshore')