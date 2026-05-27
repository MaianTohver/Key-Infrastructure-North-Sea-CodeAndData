import pandas as pd
import requests
import time
from pathlib import Path


def generate_historical_weather(nodes_file, save_dir, years=[1995, 2008, 2009]):
    print(f"loading nodes from: {nodes_file}")
    nodes_df = pd.read_excel(nodes_file)

    # check that these match your excel column headers
    node_col = 'Node'
    lat_col = 'y'
    lon_col = 'x'

    Path(save_dir).mkdir(parents=True, exist_ok=True)

    for year in years:
        print(f"\nfetching data for {year}...")
        yearly_data = pd.DataFrame()

        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        for idx, row in nodes_df.iterrows():
            node = row[node_col]
            lat = row[lat_col]
            lon = row[lon_col]

            print(f"pulling {node} ({lat}, {lon})...")

            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date,
                "end_date": end_date,
                "hourly": "temperature_2m,relative_humidity_2m",
                "timezone": "GMT"
            }

            response = requests.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                hourly = data['hourly']

                if yearly_data.empty:
                    yearly_data['time'] = hourly['time']
                    yearly_data.set_index('time', inplace=True)

                yearly_data[f"{node}_temp"] = hourly['temperature_2m']
                yearly_data[f"{node}_rh"] = hourly['relative_humidity_2m']

            else:
                print(f"error fetching {node}: {response.text}")

            time.sleep(1)

        save_path = Path(save_dir) / f"weather_{year}.csv"
        yearly_data.to_csv(save_path)
        print(f"saved: {save_path}")


if __name__ == "__main__":
    nodes_file = "/Users/maiant/PycharmProjects/Key-Infrastructure-North-Sea-CodeAndData/mes_north_sea/clean_data/nodes/nodes_2040.xlsx"
    save_dir = "/mes_north_sea/clean_data/database/weather_data"

    generate_historical_weather(nodes_file, save_dir)