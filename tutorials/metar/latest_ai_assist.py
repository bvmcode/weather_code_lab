import io
import json
from datetime import datetime

import cartopy.crs as ccrs
import pandas as pd
import requests
from metpy.io import parse_metar_file
from metpy.plots import MapPanel, PanelContainer, PlotObs
from metpy.units import units
from openai import OpenAI


class MetarReport:

    def __init__(self, location, write_raw_file=False):
        self.location = location
        self._get_bounding_box()
        self.write_raw_file = write_raw_file

    def __repr__(self):
        return (
            f"MetarReport(location={self.location}, bounding_box={self.bounding_box})"
        )

    def _get_bounding_box(self):
        model = "gpt-4o"
        prompt = f"""
            Provide the bounding box coordinates (south, west, north, east) for {self.location} United States.
            The response should be in a comma separated format: `south,west,north,east` 
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
        self.bounding_box = response.choices[0].message.content.split(",")

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
        bbox = "%2C".join(self.bounding_box)
        self._url_template = f"https://aviationweather.gov/api/data/metar?bbox={bbox}&format=json&taf=false"
        self.url = self._url_template.format(bbox=bbox)
        self.raw_data = requests.get(self.url).json()
        self._create_dataframe()
        if self.write_raw_file:
            with open("metar_raw.json", "w") as f:
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
        panel.area = (-75.6, -73.9, 38.9, 41.4)  # [west, east, south, north] for NJ
        panel.projection = ccrs.PlateCarree()
        panel.layers = ["coastline", "borders", "states"]
        panel.plots = [obs]

        pc = PanelContainer()
        pc.size = (15, 15)
        pc.panels = [panel]
        rpt_hr = self.metar_data.df["report_time"].dt.hour.min()
        rprt_dt = self.metar_data.df["report_time"].dt.strftime("%Y-%m-%d").min()
        pc.save(f"metar_obs_{rprt_dt}_{rpt_hr:02d}00.png")


if __name__ == "__main__":
    mr = MetarReport(location="NJ", write_raw_file=True)
    mr.get_metar_report()
    mp = MetarPlot(metar_data=mr)
    mp.plot_observations()