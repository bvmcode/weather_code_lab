import io
import requests
from concurrent.futures import ProcessPoolExecutor
import pandas as pd
from metpy.io import parse_metar_file
import time


def _get_data(hour):
    url = f"https://tgftp.nws.noaa.gov/data/observations/metar/cycles/{hour:02d}Z.TXT"
    data = requests.get(url, verify=False).text
    return data.strip().split("\n\n")

def _proces_data(text):
    """Module-level function for multiprocessing"""
    metar = text.split("\n")[1]
    metar_df = parse_metar_file(io.StringIO(metar))
    return metar_df


class MetarData:
    def __init__(self, hour, max_workers=8):
        self.hour = hour
        self.max_workers = max_workers
    
    def get_data(self):
        start = time.time()
        self.raw_data = _get_data(self.hour)
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            dataframes = list(executor.map(_proces_data, self.raw_data))
        self.df = pd.concat(dataframes, ignore_index=True).drop_duplicates()
        end = time.time()
        print(f"Data processing completed in {end - start:.2f} seconds.")


if __name__ == '__main__':
    md = MetarData(2)
    md.get_data()
    print(md.df.head())












import argparse
import io
import os
import json
import math
from datetime import datetime

import cartopy.crs as ccrs
import pandas as pd
import requests
from metpy.io import parse_metar_file
from metpy.plots import MapPanel, PanelContainer, PlotObs
from metpy.units import units
from openai import OpenAI


def _get_data(hour):
    url = f"https://tgftp.nws.noaa.gov/data/observations/metar/cycles/{hour:02d}Z.TXT"
    data = requests.get(url, verify=False).text
    return data.strip().split("\n\n")

def _proces_data(text):
    """Module-level function for multiprocessing"""
    metar = text.split("\n")[1]
    metar_df = parse_metar_file(io.StringIO(metar))
    return metar_df

class MetarReport:

    def __init__(self, hour, max_workers=8):
        self.hour = hour
        self.max_workers = max_workers


    def __repr__(self):
        return f"MetarReport(location={self.location})"

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
                Provide the bounding box coordinates (west, east, south, north) for {self.location.upper()} region/state of the United States.
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
        df = df[df["latitude"].between(self.bounding_box[2], self.bounding_box[3])]
        df = df[df["longitude"].between(self.bounding_box[0], self.bounding_box[1])]
        self.df = df.reset_index(drop=True)

    def get_metar_report(self):
        start = time.time()
        self.raw_data = _get_data(self.hour)
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            dataframes = list(executor.map(_proces_data, self.raw_data))
        self.df = pd.concat(dataframes, ignore_index=True).drop_duplicates()
        end = time.time()
        print(f"Data processing completed in {end - start:.2f} seconds.")
        if self.write_csv_file:
            self.df.to_csv(f"metar_data_{self.location.lower()}.csv", index=False)

class MetarPlot:
    def __init__(self, metar_data):
        self.metar_data = metar_data

    def _get_plot_df(self):
        plot_df = self.metar_data.df.copy().reset_index(drop=True)
        plot_df["air_temperature"] = (
            plot_df["air_temperature"].values * units.degC
        ).to("degF")
        plot_df["dew_point_temperature"] = (
            plot_df["dew_point_temperature"].values * units.degC
        ).to("degF")
        return plot_df

    def plot_observations(self):
        if not hasattr(self.metar_data, "df"):
            self.metar_data.get_metar_data()
        plot_df = self._get_plot_df()
        obs = PlotObs()
        obs.data = plot_df
        obs.time = None
        obs.level = None
        obs.fields = [
            "air_temperature",
            "dew_point_temperature",
            "altimeter",
            "cloud_coverage",
        ]
        obs.locations = ["NW", "SW", "NE", "C"]
        obs.colors = ["tab:red", "tab:green", "black", "black"]
        obs.formats = [None, None, lambda v: format(10 * v, ".0f")[-3:], "sky_cover"]
        obs.reduce_points = 0
        obs.vector_field = ["eastward_wind", "northward_wind"]

        panel = MapPanel()
        panel.area = self.metar_data.bounding_box
        panel.projection = ccrs.PlateCarree()
        panel.layers = ["coastline", "borders", "states"]
        panel.plots = [obs]

        pc = PanelContainer()
        pc.size = (15, 15)
        pc.panels = [panel]
        rpt_hr = self.metar_data.df["report_time"].dt.hour.min()
        rprt_dt = self.metar_data.df["report_time"].dt.strftime("%Y-%m-%d").min()
        pc.save(f"metar_obs_{rprt_dt}_{rpt_hr:02d}00_{self.metar_data.location.lower()}.png")

mr = MetarReport(location="NJ", write_csv_file=True, write_bounding_box=True)
mr.get_metar_report()
print(mr.df.head())
mp = MetarPlot(metar_data=mr)
mp.plot_observations()