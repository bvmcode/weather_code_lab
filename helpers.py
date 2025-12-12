import requests
import pandas as pd

STATES = {
    "AK": "Alaska",
    "AL": "Alabama",
    "AR": "Arkansas",
    "AZ": "Arizona",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "IA": "Iowa",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "MA": "Massachusetts",
    "MD": "Maryland",
    "ME": "Maine",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MO": "Missouri",
    "MS": "Mississippi",
    "MT": "Montana",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "NE": "Nebraska",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NV": "Nevada",
    "NY": "New York",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VA": "Virginia",
    "VT": "Vermont",
    "WA": "Washington",
    "WI": "Wisconsin",
    "WV": "West Virginia",
    "WY": "Wyoming",
    "DC": "District of Columbia",
    "AS": "American Samoa",
    "GU": "Guam GU",
    "MP": "Northern Mariana Islands",
    "PR": "Puerto Rico PR",
    "VI": "U.S. Virgin Islands",
}


def convert_to_decimal(coord):
    # Example input: "44 54N" or "119 38W"
    parts = coord.strip()
    
    # Extract degrees, minutes, and direction
    import re
    match = re.match(r"(\d+)\s+(\d+)([NSEW])", parts)
    if not match:
        raise ValueError("Invalid coordinate format")
    
    degrees = int(match.group(1))
    minutes = int(match.group(2))
    direction = match.group(3)
    
    decimal = degrees + minutes / 60.0
    
    # Apply sign for South or West
    if direction in ['S', 'W']:
        decimal = -decimal
    
    return decimal


def station_data_us(metar=None, nexrad=None, rawinsonde=None, office_type=None, states=None):
    url = "https://weather.rap.ucar.edu/surface/stations.txt"
    response = requests.get(url, verify=False)
    data = response.text
    lines = data.strip().split("\n")
    column_map = {
        "state": (0, 2),
        "station_name": (3, 19),
        "icao": (20, 24),
        "iata": (25, 30),
        "synoptic": (31, 37),
        "lat": (37, 45),
        "lng": (45, 54),
        "elevation": (54, 60),
        "metar": (61, 64),
        "nexrad": (64, 67),
        "aviation": (67, 70),
        "upper_air": (70, 73),
        "auto": (73, 76),
        "office_type": (76, 79),
        "plotting_priority": (79, 81),
    }
    column_data = {key: [] for key in column_map.keys()}
    column_data["state_full"] = []
    for line in lines:  # Print first 5 lines as a sample
        split_line = line.split()
        if line.startswith("!") or line.startswith("#") or line.strip() == "" or len(split_line)<=2 or split_line[0]=="CD":
            continue
        if split_line[0] in STATES and split_line[-1]=="US":
            for c, r in column_map.items():
                column_data[c].append(line[r[0]:r[1]].strip())
            column_data["state_full"].append(STATES.get(split_line[0], ""))
    df = pd.DataFrame(column_data)
    df["metar"] = df["metar"].apply(lambda x: 1 if x.strip()=="X" else 0).astype(bool)
    df["nexrad"] = df["nexrad"].apply(lambda x: 1 if x.strip()=="X" else 0).astype(bool)
    df["upper_air_rawinsonde"] = df["upper_air"].apply(lambda x: 1 if x.strip()=="X" else 0).astype(bool)
    df["upper_air_wind_profiler"] = df["upper_air"].apply(lambda x: 1 if x.strip()=="W" else 0).astype(bool)
    del df["upper_air"]
    df["aviation_sigmet"] = df["aviation"].apply(lambda x: 1 if x.strip() in ["V", "U"] else 0).astype(bool)
    df["aviation_artcc"] = df["aviation"].apply(lambda x: 1 if x.strip()=="A" else 0).astype(bool)
    df["aviation_taf"] = df["aviation"].apply(lambda x: 1 if x.strip() in ["T", "U"] else 0).astype(bool)
    del df["aviation"]
    df["auto_asos"] = df["auto"].apply(lambda x: 1 if x.strip() == "A" else 0).astype(bool)
    df["auto_awos"] = df["auto"].apply(lambda x: 1 if x.strip() == "W" else 0).astype(bool)
    df["auto_meso"] = df["auto"].apply(lambda x: 1 if x.strip() == "M" else 0).astype(bool)
    df["auto_human"] = df["auto"].apply(lambda x: 1 if x.strip() == "H" else 0).astype(bool)
    df["auto_augmented"] = df["auto"].apply(lambda x: 1 if x.strip() == "G" else 0).astype(bool)
    del df["auto"]
    df["office_type_wfo"] = df["office_type"].apply(lambda x: 1 if x.strip()=="F" else 0).astype(bool)
    df["office_type_rfc"] = df["office_type"].apply(lambda x: 1 if x.strip()=="R" else 0).astype(bool)
    df["office_type_ncep"] = df["office_type"].apply(lambda x: 1 if x.strip()=="C" else 0).astype(bool)
    del df["office_type"]
    df["lat"] = df["lat"].apply(convert_to_decimal)
    df["lng"] = df["lng"].apply(convert_to_decimal)
    if metar is not None:
        if isinstance(metar, bool):
            df = df[df["metar"]==metar]
        else:
            raise ValueError("metar parameter must be a boolean value (True/False)")
    if nexrad is not None:
        if isinstance(nexrad, bool):
            df = df[df["nexrad"]==nexrad]
        else:
            raise ValueError("nexrad parameter must be a boolean value (True/False)")
    if rawinsonde is not None:
        if isinstance(rawinsonde, bool):
            df = df[df["upper_air_rawinsonde"]==rawinsonde]
        else:
            raise ValueError("rawinsonde parameter must be a boolean value (True/False)")
    if states is not None:
        if isinstance(states, list):
            df = df[df["state"].isin(states)]
        else:
            raise ValueError("states parameter must be a list of state abbreviations (e.g., ['PA', 'NY'])")
    if office_type is not None:
        if office_type.lower() == "wfo":
            df = df[df["office_type_wfo"]==True]
        elif office_type.lower() == "rfc":
            df = df[df["office_type_rfc"]==True]
        elif office_type.lower() == "ncep":
            df = df[df["office_type_ncep"]==True]
        else:
            raise ValueError("office_type parameter must be one of: 'wfo', 'rfc', 'ncep'")
    return df

    
station_data_us(office_type="wfo", nexrad=True).to_csv("stations_metar_wfo_nexrad.csv", index=False)