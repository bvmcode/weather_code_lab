import argparse
import io
import os
import json
import math
from datetime import datetime
import time
import cartopy.crs as ccrs
import pandas as pd
import requests
from metpy.io import parse_metar_file
from metpy.plots import MapPanel, PanelContainer, PlotObs
from metpy.units import units
from openai import OpenAI
from concurrent.futures import ProcessPoolExecutor
from pyproj import Geod
from shapely.geometry import Polygon


def _get_data(hour):
    url = f"https://tgftp.nws.noaa.gov/data/observations/metar/cycles/{hour:02d}Z.TXT"
    data = requests.get(url, verify=False).text
    return data.strip().split("\n\n")

def _proces_data(text):
    """Module-level function for multiprocessing"""
    try:
        text_lines = text.split("\n")
        metar = text_lines[1]
        metar_df = parse_metar_file(io.StringIO(metar))
        return metar_df
    except KeyError:
        return pd.DataFrame()

class MetarReport:

    def __init__(self, location, max_workers=12, write_csv_file=False, write_bounding_box=False):
        self.location = location
        self.max_workers = max_workers
        self.write_bounding_box = write_bounding_box
        self.write_csv_file = write_csv_file
        now = datetime.utcnow()
        self.date = now.strftime("%Y-%m-%d")
        self.hour = now.hour

    def __repr__(self):
        return f"MetarReport(location={self.location}, hour={self.hour}, date={self.date})"

    def _write_bounding_box(self):
        if os.path.exists("bounding_box.json"):
            with open("bounding_box.json", "r") as f:
                bbox_json = json.load(f)
            bbox_json[self.location.lower()] = self.bounding_box
            with open("bounding_box.json", "w") as f:
                json.dump(bbox_json, f, indent=4)
        else:
            with open("bounding_box.json", "w") as f:
                json.dump({self.location.lower(): self.bounding_box}, f, indent=4)
        return True

    def _load_bounding_box(self):
        if os.path.exists("bounding_box.json"):
            with open("bounding_box.json", "r") as f:
                bbox_json = json.load(f)
            if self.location.lower() in bbox_json:
                return bbox_json[self.location.lower()]

    def _get_bounding_box(self):
        self.bounding_box = self._load_bounding_box()
        if self.bounding_box is None:
            model = "gpt-4o"
            prompt = f"""
                Provide the bounding box coordinates (west, east, south, north) for {self.location.upper()}.
                The response should be in a comma separated format: `west,east,south,north` 
                Include no additional text.
                """
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that provides bounding box coordinates.",
                },
                {"role": "user", "content": prompt},
            ]
            client = OpenAI()
            response = client.chat.completions.create(
                model=model, messages=messages, max_tokens=100, temperature=0
            )
            bbox = response.choices[0].message.content.split(",")
            self.bounding_box = [float(coord) for coord in bbox]
        if self.write_bounding_box:
            self._write_bounding_box()

    def _process_metar_data(self):
        self._get_bounding_box()
        self._df = self._df[self._df["latitude"].between(self.bounding_box[2], self.bounding_box[3])]
        self._df = self._df[self._df["longitude"].between(self.bounding_box[0], self.bounding_box[1])]
        self.df = self._df.reset_index(drop=True)

    def get_latest_metar_report(self):
        start = time.time()
        self.raw_data = _get_data(self.hour)
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            dataframes = list(executor.map(_proces_data, self.raw_data))
        self._df = pd.concat(dataframes, ignore_index=True).drop_duplicates()
        end = time.time()
        print(f"Data processing completed in {end - start:.2f} seconds.")
        self._process_metar_data()
        if self.write_csv_file:
            self.df.to_csv(f"metar_data_{self.location.lower().replace(' ', '_').replace(',', '')}.csv", index=False)

class MetarPlot:
    field_map = {
        'air_temperature': {"format": None, "placement": "NW", "color": "tab:red"},
        'dew_point_temperature': {"format": None, "placement": "SW", "color": "tab:green"},
        'pressure_mb': {"format": lambda v: format(v*10, ".0f")[-3:], "placement": "NE", "color": "black"},
        'cloud_coverage': {"format": "sky_cover", "placement": "C", "color": "black"},
        'station_id': {"format": "text", "placement": "SE", "color": "black"},
    }

    def __init__(self, metar_data):
        self.metar_data = metar_data

    def __repr__(self):
        return f"MetarPlot(location={self.metar_data.location}, hour={self.metar_data.hour}, date={self.metar_data.date})"

    def _get_plot_df(self):
        plot_df = self.metar_data.df.copy().reset_index(drop=True)
        plot_df["air_temperature"] = (
            plot_df["air_temperature"].values * units.degC
        ).to("degF")
        plot_df["dew_point_temperature"] = (
            plot_df["dew_point_temperature"].values * units.degC
        ).to("degF")
        plot_df["pressure_mb"] = (
            plot_df["altimeter"].values * units.inHg
        ).to("hPa")        
        return plot_df
    
    def _calculate_sizes(self):
        """Calculate reduce_points based on number of observations."""
        coords = [(self.metar_data.bounding_box[0], self.metar_data.bounding_box[2]),
                  (self.metar_data.bounding_box[0], self.metar_data.bounding_box[3]),
                  (self.metar_data.bounding_box[1], self.metar_data.bounding_box[3]),
                  (self.metar_data.bounding_box[1], self.metar_data.bounding_box[2]),
                  (self.metar_data.bounding_box[0], self.metar_data.bounding_box[2])]
        poly = Polygon(coords)
        geod = Geod(ellps="WGS84")
        area_sq_meters = abs(geod.geometry_area_perimeter(poly)[0])
        area_sq_miles = area_sq_meters * 3.86102e-7
        self.remove_station_ids = False
        self.fontsize = 16
        if area_sq_miles <= 20000:
            self.reduce_points = 0
        elif area_sq_miles <= 50000:
            self.reduce_points = 0.20
            self.fontsize = 14
        elif area_sq_miles <= 200000:
            self.reduce_points = 0.50
            self.fontsize = 12
        elif area_sq_miles <= 500000:
            self.reduce_points = 0.60
            self.remove_station_ids = True
            self.fontsize = 12
        elif area_sq_miles <= 900000:
            self.reduce_points = 0.70
            self.remove_station_ids = True
            self.fontsize = 11
        elif area_sq_miles <= 1500000:
            self.reduce_points = 0.80
            self.remove_station_ids = True
            self.fontsize = 10
        else:
            self.reduce_points = 1.0
            self.remove_station_ids = True
            self.fontsize = 10
        print(f"Calculated reduce_points: {self.reduce_points} for area: {area_sq_miles:.2f} sq miles")

    def plot_observations(self):
        if not hasattr(self.metar_data, "df"):
            self.metar_data.get_metar_data()
        plot_df = self._get_plot_df()
        obs = PlotObs()
        obs.data = plot_df
        obs.time = None
        obs.level = None
        self._calculate_sizes()
        mapping = self.field_map.copy()
        if self.remove_station_ids:
            mapping.pop('station_id', None)
        obs.fields = list(mapping.keys())
        obs.formats = [v["format"] for v in mapping.values()]
        obs.locations = [v["placement"] for v in mapping.values()]
        obs.colors = [v["color"] for v in mapping.values()]
        obs.reduce_points = self.reduce_points
        obs.fontsize = self.fontsize
        obs.vector_field = ["eastward_wind", "northward_wind"]
        panel = MapPanel()
        panel.area = self.metar_data.bounding_box
        panel.projection = ccrs.PlateCarree()
        panel.layers = ["coastline", "borders", "states"]
        panel.plots = [obs]
        pc = PanelContainer()
        pc.size = (20, 20)
        pc.panels = [panel]
        rpt_hr = str(self.metar_data.hour).zfill(2)
        rprt_dt = self.metar_data.date
        loc = self.metar_data.location.lower().replace(" ", "_").replace(",", "")
        pc.save(f"metar_obs_{rprt_dt}_{rpt_hr}00_{loc}.png")

if __name__ == '__main__':
    locations = ["all of the United States, northern Mexico and southern Canada",
                    "California, USA",
                    "Texas, USA",
                    "Florida, USA",
                    "New York, USA",
                    "New Jersey, USA",
                    "Northeast USA",]
    for loc in locations:
        mr = MetarReport(location=loc, write_csv_file=False, write_bounding_box=True)
        mr.get_latest_metar_report()
        mp = MetarPlot(metar_data=mr)
        mp.plot_observations()