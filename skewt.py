import numpy as np
import matplotlib.pyplot as plt
import metpy.calc as mpcalc
from metpy.plots import SkewT
from metpy.units import units
import pandas as pd
from siphon.simplewebservice.wyoming import WyomingUpperAir
from datetime import datetime

def get_sounding_data():
    # Set up the time and station
    time = datetime(1997, 8, 20, 12)  # 12Z = 12 UTC
    station = 'CHH'  # Chatham, MA
    
    try:
        # Download the sounding data
        df = WyomingUpperAir.request_data(time, station)
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def create_skewt():
    # Get the sounding data
    df = get_sounding_data()
    if df is None:
        print("Could not fetch sounding data")
        return None, None

    # Pull out the variables and attach units
    p = df['pressure'].values * units.hPa
    T = df['temperature'].values * units.degC
    Td = df['dewpoint'].values * units.degC
    u = df['u_wind'].values * units.knots
    v = df['v_wind'].values * units.knots

    # Calculate LCL
    lcl_pressure, lcl_temperature = mpcalc.lcl(p[0], T[0], Td[0])
    print(f"LCL Pressure: {lcl_pressure:.1f}")
    print(f"LCL Temperature: {lcl_temperature:.1f}°C")

    # Calculate CAPE and CIN
    cape, cin = mpcalc.cape_cin(p, T, Td, T[0])
    print(f"CAPE: {cape:.1f} J/kg")
    print(f"CIN: {cin:.1f} J/kg")

    # Create figure and axis
    fig = plt.figure(figsize=(9, 9))
    skew = SkewT(fig)

    # Plot temperature and dewpoint
    skew.plot(p, T, 'red', label='Temperature')
    skew.plot(p, Td, 'green', label='Dew Point')

    # Plot LCL
    skew.plot(lcl_pressure, lcl_temperature, 'ko', label='LCL')

    # Plot wind barbs
    skew.plot_barbs(p, u, v)

    # Set reasonable limits
    skew.ax.set_xlim(-40, 40)
    skew.ax.set_ylim(1000, 100)

    # Add dry adiabats
    skew.plot_dry_adiabats()

    # Add moist adiabats
    skew.plot_moist_adiabats()

    # Add mixing ratio lines
    skew.plot_mixing_lines()

    # Add labels and title
    skew.ax.set_xlabel('Temperature (°C)')
    skew.ax.set_ylabel('Pressure (hPa)')
    title = f'Skew-T Log-P Diagram\nChatham, MA (CHH)\n1997-08-20 12Z\n'
    title += f'CAPE: {cape:.1f} J/kg, CIN: {cin:.1f} J/kg\n'
    title += f'LCL: {lcl_pressure:.1f} hPa, {lcl_temperature:.1f}°C'
    skew.ax.set_title(title)

    # Add grid
    skew.ax.grid(True, alpha=0.3)

    # Add legend
    skew.ax.legend()

    return fig, skew

if __name__ == "__main__":
    fig, skew = create_skewt()
    if fig is not None:
        plt.show()