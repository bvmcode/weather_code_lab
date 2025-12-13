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


class MetarReport:

    def __init__(self, location, write_raw_file=False, write_bounding_box=False):
        self.location = location
        self.write_bounding_box = write_bounding_box
        self.write_raw_file = write_raw_file
        self.url = None
        self.raw_data = None
        self.bounding_box = None
        self.df = None

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
        bbox_api = [self.bounding_box[2], self.bounding_box[0], self.bounding_box[3], self.bounding_box[1]]
        self._bounding_box_api = "%2C".join([str(int(math.ceil(c))) for c in bbox_api])
        if self.write_bounding_box:
            self._write_bounding_box()

    def _create_dataframe(self):
        self.df = pd.DataFrame()
        for rpt in self.raw_data:
            raw_ob = rpt["rawOb"]
            raw_ob_file = io.StringIO(raw_ob)
            metar_df = parse_metar_file(raw_ob_file)
            metar_df["report_time"] = datetime.strptime(
                rpt["reportTime"], "%Y-%m-%dT%H:%M:%S.%fZ"
            )
            metar_df["obs_time"] = datetime.utcfromtimestamp(rpt["obsTime"])
            if self.df.empty:
                self.df = metar_df
            else:
                self.df = pd.concat([self.df, metar_df], ignore_index=True)

    def get_metar_report(self):
        self._get_bounding_box()
        self.url = f"https://aviationweather.gov/api/data/metar?bbox={self._bounding_box_api}&format=json&taf=false"
        print(self.url)
        response = requests.get(self.url)
        self.raw_data = response.json()
        if "status" in self.raw_data:
            if self.raw_data["status"] == "error":
                raise ValueError(self.raw_data["error"])
        if self.write_raw_file:
            with open(f"metar_raw_{self.location.lower()}.json", "w") as f:
                json.dump(self.raw_data, f, indent=4)
        self._create_dataframe()

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
            "air_pressure_at_sea_level",
            "cloud_coverage",
        ]
        obs.locations = ["NW", "SW", "NE", "C"]
        obs.colors = ["tab:red", "tab:green", "black", "black"]
        obs.formats = [None, None, lambda v: format(10 * v, ".0f")[-3:], "sky_cover"]
        obs.reduce_points = 0
        obs.vector_field = ["eastward_wind", "northward_wind"]

        panel = MapPanel()
        panel.area = self.metar_data.bounding_box
        print(panel.area)
        panel.projection = ccrs.PlateCarree()
        panel.layers = ["coastline", "borders", "states"]
        panel.plots = [obs]

        pc = PanelContainer()
        pc.size = (15, 15)
        pc.panels = [panel]
        rpt_hr = self.metar_data.df["report_time"].dt.hour.min()
        rprt_dt = self.metar_data.df["report_time"].dt.strftime("%Y-%m-%d").min()
        pc.save(f"metar_obs_{rprt_dt}_{rpt_hr:02d}00_{self.metar_data.location.lower()}.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Fetch and plot METAR weather observations "
            "for a specified location"
        )
    )
    parser.add_argument(
        "location",
        type=str,
        help=(
            "Location/state name "
            "(e.g., 'NJ', 'Northeast, 'Southern California')"
        )
    )
    parser.add_argument(
        "--write-raw-file",
        action="store_true",
        help="Write raw METAR data to JSON file",
        default=False
    )
    parser.add_argument(
        "--write-bounding-box",
        action="store_true",
        help="Write bounding box coordinates to bounding_box.json",
        default=False
    )

    args = parser.parse_args()

    mr = MetarReport(
        location=args.location,
        write_raw_file=args.write_raw_file,
        write_bounding_box=args.write_bounding_box
    )
    mr.get_metar_report()
    mp = MetarPlot(metar_data=mr)
    mp.plot_observations()
