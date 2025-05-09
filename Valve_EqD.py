import streamlit as st
import numpy as np
import pandas as pd
from CoolProp.CoolProp import PropsSI
import math
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import datetime
import os
import json
from plotly.subplots import make_subplots

# Add openpyxl dependency check 
try:
    import openpyxl
    EXCEL_EXPORT_AVAILABLE = True
except ImportError:
    EXCEL_EXPORT_AVAILABLE = False

# Version control
APP_VERSION = "1.0.0"

st.set_page_config(page_title="Valve Sizing Calculator ", layout="wide", 
                  initial_sidebar_state="expanded")

# Custom styling for a more professional look
st.markdown("""
<style>
    .main-header {color:#0078D7; font-size:28px;}
    .sub-header {color:#505050; font-size:20px;}
    .info-text {background-color: #E8F4FE; padding: 10px; border-radius: 5px;}
    .container {background-color: #F8F9FA; padding: 20px; border-radius: 10px;}
    .stRadio > div {flex-direction: row;}
    .stTabs [data-baseweb="tab-panel"] {padding-top: 25px;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-header">🧪 Valve Sizing Calculator v'+APP_VERSION+'</p>', unsafe_allow_html=True)
st.markdown('<p class="info-text">Calculate ESEOD (Effective Square-Edged Orifice Diameter) and EqA (Equivalent Flow Area) for valve selection based on flow conditions</p>', unsafe_allow_html=True)

# Define aerospace valve types and their characteristics
# Dictionary structure: valve_type -> {Cd range, typical applications, material compatibility}
AEROSPACE_VALVE_TYPES = {
    "Ball Valve": {
        "typical_cd": (0.50, 0.70),
        "applications": ["Propellant isolation", "Tank fill/drain", "Engine feed system"],
        "materials": {
            "Oxygen": ["Monel", "Stainless Steel (316, 321)", "PTFE seats (limited cycling)"],
            "Hydrogen": ["Stainless Steel", "Aluminum", "PTFE seats"],
            "Methane": ["Stainless Steel", "Inconel", "PCTFE seats"],
            "Nitrogen": ["Stainless Steel", "Aluminum", "PTFE seats"],
            "Helium": ["Stainless Steel", "Aluminum", "PTFE seats"]
        },
        "notes": "Good for cryogenic service. Consider thermal contraction in sizing.",
        "xt_default": 0.72,  # Critical pressure ratio based on NASA-TM-X-52097
        "geo_factor": 1.0    # Flow geometry factor
    },
    "Butterfly Valve": {
        "typical_cd": (0.60, 0.80),
        "applications": ["Vent systems", "Low-pressure isolation", "Ground systems"],
        "materials": {
            "Oxygen": ["Monel", "Bronze", "Stainless Steel (316)"],
            "Hydrogen": ["Aluminum", "Stainless Steel"],
            "Methane": ["Stainless Steel", "Bronze"],
            "Nitrogen": ["Stainless Steel", "Aluminum"],
            "Helium": ["Stainless Steel", "Aluminum"]
        },
        "notes": "Lightweight but less suitable for high pressure differentials.",
        "xt_default": 0.70,  # Critical pressure ratio based on typical butterfly valve values
        "geo_factor": 0.9    # Flow geometry factor
    },
    "Globe Valve": {
        "typical_cd": (0.35, 0.60),
        "applications": ["Flow control", "High pressure systems", "Precise throttling"],
        "materials": {
            "Oxygen": ["Monel", "Stainless Steel (316)", "Bronze"],
            "Hydrogen": ["Stainless Steel", "Copper alloys"],
            "Methane": ["Stainless Steel", "Bronze"],
            "Nitrogen": ["Stainless Steel", "Bronze"],
            "Helium": ["Stainless Steel", "Bronze"]
        },
        "notes": "Good for throttling applications but heavier than other valve types.",
        "xt_default": 0.67,  # Critical pressure ratio based on ISA-75.01.01 for globe valves
        "geo_factor": 0.8    # Flow geometry factor per ISA-75.01.01
    },
    "Poppet Valve": {
        "typical_cd": (0.40, 0.65),
        "applications": ["Relief valves", "Check valves", "Quick-disconnect systems"],
        "materials": {
            "Oxygen": ["Monel", "Stainless Steel", "Sapphire/Ruby seats"],
            "Hydrogen": ["Stainless Steel", "Aluminum", "PCTFE seats"],
            "Methane": ["Stainless Steel", "PCTFE seats"],
            "Nitrogen": ["Stainless Steel", "PCTFE seats"],
            "Helium": ["Stainless Steel", "Polymer seats"]
        },
        "notes": "Fast response times. Often used in safety-critical applications.",
        "xt_default": 0.65,  # Critical pressure ratio based on typical poppet geometry
        "geo_factor": 0.85   # Flow geometry factor 
    },
    "Cryogenic Relief Valve": {
        "typical_cd": (0.42, 0.62),
        "applications": ["Tank pressure relief", "Emergency venting", "System protection"],
        "materials": {
            "Oxygen": ["Stainless Steel (316)", "Monel", "Inconel bellows"],
            "Hydrogen": ["Stainless Steel", "Inconel bellows"],
            "Methane": ["Stainless Steel", "Inconel"],
            "Nitrogen": ["Stainless Steel"],
            "Helium": ["Stainless Steel"]
        },
        "notes": "Typically designed for specific cracking pressures. May have decreased Cd at partial lift.",
        "xt_default": 0.65,  # Critical pressure ratio per ASME Section VIII calculations
        "geo_factor": 0.9    # Flow geometry factor
    },
    "Custom/Proprietary": {
        "typical_cd": (0.35, 0.85),
        "applications": ["Specialized applications", "Unique system requirements"],
        "materials": {
            "Oxygen": ["Mission specific"],
            "Hydrogen": ["Mission specific"],
            "Methane": ["Mission specific"],
            "Nitrogen": ["Mission specific"],
            "Helium": ["Mission specific"]
        },
        "notes": "Discharge coefficient must be determined experimentally.",
        "xt_default": 0.68,  # Default value
        "geo_factor": 1.0    # Default flow geometry factor
    }
}

# Safety factor recommendations based on application
SAFETY_FACTORS = {
    "Human-rated flight": {
        "description": "Human spaceflight systems with direct life safety implications",
        "recommended_factor": 1.5,
        "range": (1.4, 2.0)
    },
    "Critical flight": {
        "description": "Mission-critical unmanned flight systems",
        "recommended_factor": 1.25,
        "range": (1.2, 1.5)
    },
    "Non-critical flight": {
        "description": "Redundant or non-critical flight systems",
        "recommended_factor": 1.15,
        "range": (1.1, 1.25)
    },
    "Ground GSE": {
        "description": "Ground support equipment with maintenance access",
        "recommended_factor": 1.1,
        "range": (1.05, 1.2)
    },
    "Custom": {
        "description": "User-defined safety factor",
        "recommended_factor": 1.0,
        "range": (1.0, 3.0)
    }
}

# Initialize essential variables to prevent "not defined" errors
k = 1.4  # Default value for specific heat ratio (typical for diatomic gases)
fluid = "Nitrogen"  # Default fluid
x_t_ideal = 0.528  # Default theoretical critical pressure ratio

# Sidebar for calculation settings
with st.sidebar:
    st.markdown('<p class="sub-header">Calculation Settings</p>', unsafe_allow_html=True)
    
    # Add valve type selection
    valve_type = st.selectbox("Valve Type", list(AEROSPACE_VALVE_TYPES.keys()))
    
    # Update Cd suggestion based on valve type
    cd_min, cd_max = AEROSPACE_VALVE_TYPES[valve_type]["typical_cd"]
    cd_default = (cd_min + cd_max) / 2
    
    flow_model = st.selectbox("Flow Model", 
                             ["Incompressible", "Compressible - Subsonic", "Compressible - Critical Flow"])
    
    # Show recommended Cd range based on valve type
    st.info(f"Typical Cd for {valve_type}: {cd_min:.2f}-{cd_max:.2f}")
    
    Cd = st.slider("Discharge Coefficient (Cd)", 0.1, 1.0, cd_default, 0.01)
    
    # Add Advanced Settings section with critical pressure ratio control
    with st.expander("Advanced Flow Parameters"):
        # Get default values from valve type
        default_xt = AEROSPACE_VALVE_TYPES[valve_type]["xt_default"]
        default_geo_factor = AEROSPACE_VALVE_TYPES[valve_type]["geo_factor"]
        
        # Allow adjusting critical pressure ratio with detailed explanation
        st.markdown("""
        **Critical Pressure Ratio (xT)** is the ratio of pressure drop to inlet pressure 
        at which flow becomes choked. Values from aerospace standards:
        - Sharp-edged orifice: 0.528 (ideal gas theory)
        - Globe valves: 0.67-0.73 (ISA-75.01.01)
        - Ball valves: 0.70-0.75 (NASA-TM-X-52097)
        - Relief valves: 0.65-0.70 (ASME Section VIII)
        """)
        
        # The theoretical value will be updated after fluid properties are calculated
        custom_xt = st.slider(
            "Critical Pressure Ratio (xT)", 
            0.5, 0.9, 
            default_xt, 
            0.01,
            help="Ratio of ΔP/P1 at which flow becomes choked"
        )
        
        # Allow adjusting geometry factor
        st.markdown("""
        **Geometry Factor (Fg)** accounts for valve internal geometry effects on 
        flow expansion per ISA-75.01.01 (2012).
        """)
        
        custom_geo_factor = st.slider(
            "Geometry Factor (Fg)", 
            0.5, 1.0, 
            default_geo_factor, 
            0.05,
            help="Valve geometry factor from ISA-75.01.01"
        )
    
    # Safety factor selection
    st.markdown("---")
    st.markdown('<p class="sub-header">Safety Considerations</p>', unsafe_allow_html=True)
    safety_application = st.selectbox("Application Type", list(SAFETY_FACTORS.keys()))
    
    if safety_application == "Custom":
        safety_factor = st.slider(
            "Custom Safety Factor", 
            min_value=1.0, 
            max_value=3.0, 
            value=1.5, 
            step=0.05
        )
    else:
        sf_info = SAFETY_FACTORS[safety_application]
        st.info(f"{sf_info['description']}")
        safety_factor = st.slider(
            "Safety Factor", 
            min_value=float(sf_info['range'][0]), 
            max_value=float(sf_info['range'][1]), 
            value=float(sf_info['recommended_factor']), 
            step=0.05
        )
    
    # Monte Carlo settings
    st.markdown("---")
    st.markdown('<p class="sub-header">Monte Carlo Settings</p>', unsafe_allow_html=True)
    n_samples = st.slider("Number of Samples", 100, 10000, 1000, 100)
    random_seed = st.number_input("Random Seed (for reproducibility)", value=42, step=1)

    st.info("For cryogenic applications, compressible flow models are recommended")

# Main tabs for input/output organization
# display_tab1, display_tab2 = st.tabs(["Results", "Technical Details"]) # Removed
main_tabs = st.tabs(["Input Parameters", "Results & Visualization", "Technical Analysis", "Valve Comparison"])

# TAB 1: Input Parameters
with main_tabs[0]:
    st.markdown('<p class="sub-header">Valve Sizing Inputs</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">Fluid Properties</p>', unsafe_allow_html=True)
        
        # Common aerospace fluids for quick selection
        fluid_options = ["Nitrogen", "Oxygen", "Hydrogen", "Methane", "Water", "Helium", "Custom"]
        fluid_selection = st.selectbox("Select Fluid", fluid_options)
        
        if fluid_selection == "Custom":
            fluid = st.text_input("Enter CoolProp fluid name", value="Water")
        else:
            fluid_mapping = {
                "Nitrogen": "Nitrogen",
                "Oxygen": "Oxygen",
                "Hydrogen": "Hydrogen",
                "Methane": "Methane",
                "Water": "Water",
                "Helium": "Helium"
            }
            fluid = fluid_mapping[fluid_selection]
            
        T_unit = st.selectbox("Temperature unit", ["K", "°C", "°F"])
        T_val = st.number_input(f"Temperature ({T_unit})", value=300.0 if T_unit=="K" else 27.0 if T_unit=="°C" else 80.0, 
                               step=1.0, format="%.2f")
        
        # Convert temperature to K for calculations
        if T_unit == "K":
            T = T_val
        elif T_unit == "°C":
            T = T_val + 273.15
        else:  # °F
            T = (T_val - 32) * 5/9 + 273.15
            
        P_unit = st.selectbox("Pressure unit", ["kPa", "psia", "bar", "MPa"])
        P_val = st.number_input(f"Pressure ({P_unit})", 
                                value=101.3 if P_unit=="kPa" else 14.7 if P_unit=="psia" else 1.013 if P_unit=="bar" else 0.1013, 
                                step=1.0 if P_unit in ["kPa", "psia"] else 0.1, 
                                format="%.3f")
        
        # Add pressure type selection (gauge or absolute)
        pressure_type = st.radio("Pressure type", ["Absolute", "Gauge"], horizontal=True)
        
        # Convert pressure value to Pa (moved here from below)
        P_Pa = P_val * (1e3 if P_unit=="kPa" else 6894.76 if P_unit=="psia" else 1e5 if P_unit=="bar" else 1e6)
        
        # Apply gauge pressure correction if needed
        if pressure_type == "Gauge":
            # Add atmospheric pressure to gauge pressure to get absolute
            atm_pressure = 101325.0  # Standard atmospheric pressure in Pa
            P_Pa += atm_pressure
            
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">Flow Parameters</p>', unsafe_allow_html=True)
        
        fr_type = st.selectbox("Flow rate type", ["Mass Flow", "Volumetric Flow"])
        
        if fr_type == "Mass Flow":
            fr_unit = st.selectbox("Flow rate unit", ["kg/s", "lbm/s", "g/s"])
            unit_label = fr_unit
        else:
            fr_unit = st.selectbox("Flow rate unit", ["m³/s", "ft³/s", "L/s", "gpm"])
            unit_label = fr_unit
        
        use_range = st.checkbox("Use flow rate range", value=True)
        
        if use_range:
            max_range = 10.0 if fr_unit in ["kg/s", "lbm/s"] else 100.0 if fr_unit in ["g/s"] else 0.01 if fr_unit in ["m³/s", "ft³/s"] else 10.0
            fr_min, fr_max = st.slider(f"Flow rate ({unit_label})", 
                                       0.0, max_range, 
                                       (max_range*0.1, max_range*0.2),
                                       step=max_range/100)
        else:
            max_val = 10.0 if fr_unit in ["kg/s", "lbm/s"] else 100.0 if fr_unit in ["g/s"] else 0.01 if fr_unit in ["m³/s", "ft³/s"] else 10.0
            fr_min = fr_max = st.number_input(f"Flow rate ({unit_label})", value=max_val*0.1, step=max_val/100)
        
        dp_unit = st.selectbox("ΔP unit", ["kPa", "psi (absolute)", "bar"])
        
        use_dp_range = st.checkbox("Use ΔP range", value=False)
        
        if use_dp_range:
            max_dp = 500.0 if dp_unit == "kPa" else 72.5 if dp_unit == "psi (absolute)" else 5.0
            dp_min, dp_max = st.slider(f"ΔP allowable ({dp_unit})", 
                                      0.0, max_dp, 
                                      (max_dp*0.1, max_dp*0.1),
                                      step=max_dp/100)
        else:
            max_dp = 500.0 if dp_unit == "kPa" else 72.5 if dp_unit == "psi (absolute)" else 5.0
            dp_min = dp_max = st.number_input(f"ΔP allowable ({dp_unit})", value=max_dp*0.1, step=max_dp/100)
        
        st.markdown('</div>', unsafe_allow_html=True)

    # Material compatibility check based on fluid
    if fluid_selection != "Custom":
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">Material Compatibility</p>', unsafe_allow_html=True)
        
        st.write(f"**Recommended materials for {fluid_selection} service with {valve_type}:**")
        
        # Get compatible materials for selected fluid and valve type
        if fluid_selection in AEROSPACE_VALVE_TYPES[valve_type]["materials"]:
            materials = AEROSPACE_VALVE_TYPES[valve_type]["materials"][fluid_selection]
            
            # N-5: Flag hazardous material combinations
            is_high_pressure = P_Pa > 5e6  # 5 MPa / ~725 psi threshold
            
            for material in materials:
                material_line = f"- {material}"
                
                # Check for Bronze in LOX
                if fluid_selection == "Oxygen" and "Bronze" in material:
                    material_line += " ⚠️ **CAUTION**: Bronze in LOX can be hazardous in certain conditions"
                    st.warning(material_line)
                # Check for Aluminum in high-pressure O₂
                elif fluid_selection == "Oxygen" and is_high_pressure and "Aluminum" in material:
                    material_line += " ⚠️ **CAUTION**: Aluminum in high-pressure oxygen requires special engineering controls"
                    st.warning(material_line)
                else:
                    st.write(material_line)
            
            # Add additional warning for high pressure oxygen
            if fluid_selection == "Oxygen" and is_high_pressure:
                st.error("""
                ⚠️ **HIGH-PRESSURE OXYGEN ALERT**:
                High-pressure oxygen service requires special material selection, surface preparation,
                cleanliness standards, and ignition hazard analysis. Consult ASTM G88, NASA-STD-6001,
                and NFPA 53 before finalizing valve selection.
                """)
        else:
            st.warning("No specific material recommendations available for this fluid-valve combination.")
            
        st.info(AEROSPACE_VALVE_TYPES[valve_type]["notes"])
        st.markdown('</div>', unsafe_allow_html=True)

# Before Units conversion to SI (Issue 2)
# Initialize variables that will be calculated later to avoid NameError
eqA = np.array([0.0])
eqD = np.array([0.0])
eqD_safe = np.array([0.0])
fr_samples = np.array([0.0])
dp_samples = np.array([0.0])
area_scale = 1.0
diam_scale = 1.0
Re = np.array([0.0])
Cd_corrected = np.array([0.0])
chart_type = "Histogram" # Initialize chart_type with a default value instead of None

# Initialize stat_df globally to avoid "not defined" errors
stat_df = None
df = pd.DataFrame() # Initialize df globally

# 2) Units conversion to SI
P_Pa = P_val * (1e3 if P_unit=="kPa" else 6894.76 if P_unit=="psia" else 1e5 if P_unit=="bar" else 1e6)

# Convert flow rate to SI
if fr_type == "Mass Flow":
    # Convert to kg/s
    flow_convert = 1.0 if fr_unit == "kg/s" else 0.45359237 if fr_unit == "lbm/s" else 0.001 # g/s
else:
    # Convert to m³/s
    flow_convert = 1.0 if fr_unit == "m³/s" else 0.02831685 if fr_unit == "ft³/s" else 0.001 if fr_unit == "L/s" else 0.0000631 # gpm

# Convert ΔP to Pa
dp_convert = 1e3 if dp_unit == "kPa" else 6894.76 if dp_unit == "psi (absolute)" else 1e5 # bar

# 3) Get fluid properties using CoolProp
try:
    with st.spinner(f"Calculating properties for {fluid} at {T:.2f} K and {P_Pa/1e3:.2f} kPa..."):
        try:
            # M-6: Handle two-phase region risk with specific try/except
            rho = PropsSI("D", "T", T, "P", P_Pa, fluid)  # Density (kg/m³)
            mu = PropsSI("V", "T", T, "P", P_Pa, fluid)   # Dynamic viscosity (Pa·s)
            
            # Calculate specific heat ratio directly - more accurate than previous method
            cp = PropsSI("CPMASS", "T", T, "P", P_Pa, fluid)  # Specific heat capacity (J/kg/K)
            cv = PropsSI("CVMASS", "T", T, "P", P_Pa, fluid)  # Specific heat capacity (J/kg/K)
            k = cp/cv  # Specific heat ratio
            
            # Add compressibility factor for all flow models
            Z = PropsSI("Z", "T", T, "P", P_Pa, fluid)  # Compressibility factor
            
            # Define R_specific for all flow models
            R_universal = 8.314462618  # J/mol/K
            M_molar = PropsSI("MOLAR_MASS", "T", T, "P", P_Pa, fluid)
            R_specific = R_universal / M_molar
            
            # Calculate theoretical critical pressure ratio for the specific gas
            x_t_ideal = (2/(k+1))**(k/(k-1))
            
            # Update the info text in the sidebar with the calculated x_t_ideal
            with st.sidebar:
                with st.expander("Critical Flow Information", expanded=False):
                    st.info(f"Theoretical ideal gas xT for {fluid} (k={k:.3f}): {x_t_ideal:.3f}")
                    st.write(f"Selected xT: {custom_xt:.3f}")
                    if custom_xt < x_t_ideal * 0.95:
                        st.warning(f"Selected xT ({custom_xt:.3f}) is significantly lower than theoretical value ({x_t_ideal:.3f}). Flow may choke before predicted.")
                    elif custom_xt > x_t_ideal * 1.2:
                        st.warning(f"Selected xT ({custom_xt:.3f}) is significantly higher than theoretical value ({x_t_ideal:.3f}). Critical flow might not be predicted correctly.")
            
            # Additional check for phase (liquid, gas, supercritical)
            phase = PropsSI("PHASE", "T", T, "P", P_Pa, fluid)
            if phase == 2:  # Two-phase region
                st.warning(f"⚠️ Warning: The specified conditions for {fluid} lie in the two-phase region where fluid properties can be unpredictable.")
                
        except ValueError as e:
            if "two-phase" in str(e).lower() or "saturated" in str(e).lower():
                st.error("❌ Two-phase fluid state detected. This calculator does not support two-phase flow. Please adjust temperature or pressure to ensure single-phase conditions.")
                st.stop()
            else:
                raise e  # Re-raise if it's a different ValueError
except Exception as e:
    st.error(f"Error calculating fluid properties: {str(e)}")
    st.stop()

# 4) Monte Carlo sampler - Improved
np.random.seed(random_seed)  # Seed only when generating samples

# Add correlation option for Monte Carlo
if fr_min != fr_max or dp_min != dp_max:
    with st.spinner(f"Running Monte Carlo with {n_samples} samples..."):
        # N-2: Add correlation between flow rate and pressure drop
        correlation_option = st.checkbox("Use correlated sampling (flow ↑ → ΔP ↑)", value=False)
        
        if correlation_option and fr_min != fr_max and dp_min != dp_max:
            # Generate correlated samples using bivariate normal distribution
            # First create standard normal samples
            rho_corr = 0.85  # Strong positive correlation coefficient
            
            # Create correlated normal variables
            mean = [0, 0]
            cov = [[1, rho_corr], [rho_corr, 1]]
            z1, z2 = np.random.multivariate_normal(mean, cov, n_samples).T
            
            # Transform to uniform using the normal CDF
            from scipy.stats import norm
            u1 = norm.cdf(z1)
            u2 = norm.cdf(z2)
            
            # Transform uniform to original ranges
            fr_samples = fr_min + (fr_max - fr_min) * u1
            dp_samples = dp_min + (dp_max - dp_min) * u2
            
            # Convert to SI units
            fr_samples = fr_samples * flow_convert
            dp_samples = dp_samples * dp_convert
            
            # Check for excessive pressure drops and clip to prevent negative P2
            dp_samples = np.minimum(dp_samples, 0.98 * P_Pa)  # Clip at 98% of P1 to prevent negative P2
            # Check if any samples were clipped
            if np.any(dp_samples >= 0.98 * P_Pa):
                st.warning("⚠️ Some pressure drop samples exceeded inlet pressure and were clipped to prevent negative downstream pressure.")
        else:
            # Original uncorrelated sampling
            fr_samples = np.random.uniform(fr_min, fr_max, n_samples) * flow_convert
            dp_samples = np.random.uniform(dp_min, dp_max, n_samples) * dp_convert
            
            # Check for excessive pressure drops and clip to prevent negative P2
            dp_samples = np.minimum(dp_samples, 0.98 * P_Pa)
            if np.any(dp_samples >= 0.98 * P_Pa):
                st.warning("⚠️ Some pressure drop samples exceeded inlet pressure and were clipped to prevent negative downstream pressure.")
else:
    fr_samples = np.array([fr_min * flow_convert])
    dp_samples = np.array([dp_min * dp_convert])
    
    # Check single sample too
    if dp_samples[0] >= P_Pa:
        dp_samples[0] = 0.98 * P_Pa
        st.warning("⚠️ Pressure drop exceeds inlet pressure and was clipped to prevent negative downstream pressure.")

# 5) Calculate EqA & EqD based on selected flow model
# if volumetric, convert to mass flow
if fr_type == "Volumetric Flow":
    fr_samples = fr_samples * rho

# Initialize arrays for results
eqA = np.zeros_like(fr_samples)
eqD = np.zeros_like(fr_samples)
Re = np.zeros_like(fr_samples)  # Reynolds number array
Cd_corrected = np.zeros_like(fr_samples)  # Corrected Cd based on Reynolds

# Define choked flow calculation as a function to avoid code duplication
def calculate_choked_flow(mass_flow, pressure, cd_value):
    """Calculate flow area for choked flow conditions"""
    choked_factor = np.sqrt(k) * (2/(k+1))**((k+1)/(2*(k-1)))
    return mass_flow / (cd_value * pressure * choked_factor) * np.sqrt(Z * R_specific * T)

# Pre-calculate critical pressure ratio
x_t = custom_xt  # Use the custom value from advanced settings
geometry_factor = custom_geo_factor

# Track critical flow transitions for reporting
critical_flow_transitions = 0  # Count how many samples switched to critical flow
total_samples = len(fr_samples)

if flow_model == "Incompressible":
    # A = mdot/(Cd*√(2*ρ*ΔP))
    for i in range(len(fr_samples)):
        # Guard against division by zero
        if dp_samples[i] <= 0 or fr_samples[i] <= 0 or rho <= 0:
            eqA[i] = 0
            Re[i] = 0
            Cd_corrected[i] = Cd
            continue
            
        # Calculate pressure ratio and check for critical flow condition
        x = dp_samples[i] / P_Pa
        
        # Auto-switch to critical flow if pressure ratio exceeds critical
        if x >= x_t:
            critical_flow_transitions += 1  # Count the transition
            # Apply critical flow calculation
            Cd_corrected[i] = Cd  # Start with nominal Cd
            
            # Critical flow calculation (same as critical flow branch)
            eqA[i] = calculate_choked_flow(fr_samples[i], P_Pa, Cd_corrected[i])
            critical_flow_transitions += 1  # Increment critical flow transition count
            continue
            
        # For each pressure sample, calculate upstream and downstream densities
        P2_Pa = P_Pa - dp_samples[i]
        try:
            rho_upstream = PropsSI("D", "T", T, "P", P_Pa, fluid)
            rho_downstream = PropsSI("D", "T", T, "P", P2_Pa, fluid)
            # Use average density for incompressible flow
            rho_avg = (rho_upstream + rho_downstream) / 2
            mu_sample = PropsSI("V", "T", T, "P", P_Pa, fluid)  # Use upstream viscosity
        except Exception:
            # Fallback to original density if CoolProp fails
            rho_avg = rho
            mu_sample = mu
        
        # Initial approximation of diameter
        eqA_approx = fr_samples[i] / (Cd * np.sqrt(2 * rho_avg * dp_samples[i]))
        eqD_approx = np.sqrt(4 * eqA_approx / math.pi) if eqA_approx > 0 else 0
        
        # Calculate Reynolds number
        velocity = fr_samples[i] / (rho_avg * eqA_approx) if eqA_approx > 0 else 0
        Re[i] = rho_avg * velocity * eqD_approx / mu_sample if mu_sample > 0 else 0
        
        # Apply Reynolds correction to Cd according to Crane TP-410 (2013 Ed.)
        # Reference: Flow of Fluids Through Valves, Fittings and Pipe, Crane TP-410
        # These corrections represent the deviation from ideal discharge coefficient
        # at lower Reynolds numbers, specifically for sharp-edged orifices
        if Re[i] < 100:
            # For extreme laminar flows (Re<100), modified Crane correlation
            # Cd drops significantly in deep laminar regime
            Cd_corrected_first_pass = Cd * (0.5 * np.sqrt(Re[i]/100))
        elif Re[i] < 1000:
            # Transition region correlation based on Crane TP-410 data
            Cd_corrected_first_pass = Cd * (0.9 - 0.4/(Re[i]/1000)**0.25)
        else:
            # For higher Reynolds numbers, correlation approaches ideal value
            # Per ASME MFC-3M-1989 and Crane TP-410 data
            Cd_corrected_first_pass = Cd * (0.9 - 0.2/(Re[i]/1000)**0.25)
            
        # Limit correction factor to prevent unrealistic values
        Cd_corrected_first_pass = max(0.1 * Cd, min(Cd, Cd_corrected_first_pass))
        
        # Second pass for convergence using the corrected Cd from first pass
        # This iterative approach improves accuracy per NASA-TM-2016-219078
        eqA_second_pass = fr_samples[i] / (Cd_corrected_first_pass * np.sqrt(2 * rho_avg * dp_samples[i]))
        eqD_second_pass = np.sqrt(4 * eqA_second_pass / math.pi) if eqA_second_pass > 0 else 0
        
        # Calculate Reynolds number for second pass
        velocity_second_pass = fr_samples[i] / (rho_avg * eqA_second_pass) if eqA_second_pass > 0 else 0
        Re[i] = rho_avg * velocity_second_pass * eqD_second_pass / mu_sample if mu_sample > 0 else 0
        
        # Apply enhanced Reynolds correction again with updated Re
        if Re[i] < 100:
            Cd_corrected[i] = Cd * (0.5 * np.sqrt(Re[i]/100))
        elif Re[i] < 1000:
            Cd_corrected[i] = Cd * (0.9 - 0.4/(Re[i]/1000)**0.25)
        else:
            Cd_corrected[i] = Cd * (0.9 - 0.2/(Re[i]/1000)**0.25)
            
        # Limit correction factor to prevent unrealistic values
        Cd_corrected[i] = max(0.1 * Cd, min(Cd, Cd_corrected[i]))
        
        # Calculate final area with twice-corrected Cd
        eqA[i] = fr_samples[i] / (Cd_corrected[i] * np.sqrt(2 * rho_avg * dp_samples[i]))
    
    # Add after the main loop to report auto-switching statistics
    if critical_flow_transitions > 0:
        critical_pct = (critical_flow_transitions / total_samples) * 100
        st.warning(f"⚠️ {critical_flow_transitions} samples ({critical_pct:.1f}%) exceeded the critical pressure ratio and were automatically calculated using critical flow equations.")

# Improved compressible flow model - changes to subsonic calculation
elif flow_model == "Compressible - Subsonic":
    # Using ISA-75.01.01 equations for control valves
    Y_values = np.zeros_like(fr_samples)
    
    # Theoretical critical pressure ratio (ideal gas)
    x_t_ideal = (2/(k+1))**(k/(k-1))
    
    for i in range(len(fr_samples)):
        # Guard against division by zero and extreme values
        if dp_samples[i] <= 0 or fr_samples[i] <= 0 or P_Pa <= 0 or rho <= 0:
            eqA[i] = 0
            Re[i] = 0
            Cd_corrected[i] = Cd
            Y_values[i] = 1.0
            continue
            
        # Calculate pressure ratio x and downstream pressure
        x = dp_samples[i] / P_Pa
        P2_Pa = P_Pa - dp_samples[i]
        
        # Calculate upstream density and viscosity for this specific pressure point
        try:
            rho_upstream = PropsSI("D", "T", T, "P", P_Pa, fluid)
            mu_upstream = PropsSI("V", "T", T, "P", P_Pa, fluid)
        except Exception:
            # Fallback to original values if CoolProp fails
            rho_upstream = rho
            mu_upstream = mu
            
        # Critical flow check - if pressure ratio exceeds critical, switch calculation
        if x >= x_t:
            critical_flow_transitions += 1  # Count the transition
            # Apply critical flow calculation
            Cd_corrected[i] = Cd  # Start with nominal Cd
            
            # Calculate Reynolds number for critical flow
            # Use sonic velocity for Reynolds calculation in critical flow
            sonic_velocity = np.sqrt(k * Z * R_specific * T)
            
            # Estimate area first for Reynolds calculation
            eqA_approx = calculate_choked_flow(fr_samples[i], P_Pa, Cd)
            eqD_approx = np.sqrt(4 * eqA_approx / math.pi) if eqA_approx > 0 else 0
            
            Re[i] = rho_upstream * sonic_velocity * eqD_approx / mu_upstream if mu_upstream > 0 and eqD_approx > 0 else 0
            
            # Apply Reynolds corrections
            if Re[i] < 10000:
                A_coef = 0.5
                B_coef = 0.25
                Cd_corrected[i] = Cd * max(0.3, min(1.0, (1.0 - A_coef * (Re[i]**(-B_coef)))))
            else:
                Cd_corrected[i] = Cd
                
            # Final critical flow calculation with corrected Cd
            eqA[i] = calculate_choked_flow(fr_samples[i], P_Pa, Cd_corrected[i])
            Y_values[i] = 0.0  # Y factor not applicable for choked flow
            critical_flow_transitions += 1  # Increment critical flow transition count
            continue
            
        # For subsonic compressible flow
        # Calculate Y-factor with proper pressure ratio term
        if P2_Pa > 0:  # Prevent division by zero
            pressure_ratio_term = (P2_Pa/P_Pa)**((k-1)/k)
            # Standard Y-factor formula from ISA-75.01.01-2012
            Y = 1.0 - (x/(3*geometry_factor*x_t)) * (1.0 - pressure_ratio_term)
            Y_values[i] = max(0.1, min(1.0, Y))  # Bound between 0.1 and 1.0 for stability
        else:
            Y_values[i] = 0.1  # Minimum bound for extreme cases
        
        # Initial approximation with proper density reference per ISA-75.01.01
        eqA_approx = fr_samples[i] / (Cd * Y_values[i] * np.sqrt(2 * rho_upstream * dp_samples[i]))
        eqD_approx = np.sqrt(4 * eqA_approx / math.pi) if eqA_approx > 0 else 0
        
        # Calculate Reynolds number
        velocity = fr_samples[i] / (rho_upstream * eqA_approx) if eqA_approx > 0 else 0
        Re[i] = rho_upstream * velocity * eqD_approx / mu_upstream if mu_upstream > 0 else 0
        
        # Enhanced Reynolds correction based on documented methods
        if Re[i] < 10000:
            # For non-fully turbulent flow per Crane TP-410 data for thin-plate orifices
            A_coef = 0.5
            B_coef = 0.25
            Cd_corrected[i] = Cd * max(0.3, min(1.0, (1.0 - A_coef * (Re[i]**(-B_coef)))))
        else:
            # Fully turbulent flow - minimal correction
            Cd_corrected[i] = Cd
        
        # Flow area with corrected Cd - use upstream density per ISA standard
        eqA[i] = fr_samples[i] / (Cd_corrected[i] * Y_values[i] * np.sqrt(2 * rho_upstream * dp_samples[i]))

    # Add after the main loop to report auto-switching statistics
    if critical_flow_transitions > 0:
        critical_pct = (critical_flow_transitions / total_samples) * 100
        st.warning(f"⚠️ {critical_flow_transitions} samples ({critical_pct:.1f}%) exceeded the critical pressure ratio and were automatically calculated using critical flow equations.")

# Improved critical flow model with proper Z-factor handling
elif flow_model == "Compressible - Critical Flow":
    # For critical/choked flow conditions
    for i in range(len(fr_samples)):
        # Guard against division by zero or invalid inputs
        if P_Pa <= 0 or fr_samples[i] <= 0 or Z <= 0 or T <= 0:
            eqA[i] = 0
            Re[i] = 0
            Cd_corrected[i] = Cd
            continue
            
        # Calculate per-sample fluid properties
        try:
            rho_upstream = PropsSI("D", "T", T, "P", P_Pa, fluid)
            mu_upstream = PropsSI("V", "T", T, "P", P_Pa, fluid)
        except Exception:
            # Fallback to original values if CoolProp fails
            rho_upstream = rho
            mu_upstream = mu
            
        # A = mdot / (Cd * P1 * choked_factor) * sqrt(Z*R*T)
        eqA_approx = calculate_choked_flow(fr_samples[i], P_Pa, Cd)
        eqD_approx = np.sqrt(4 * eqA_approx / math.pi) if eqA_approx > 0 else 0
        
        # Calculate Reynolds number – for choked flow use sonic velocity
        # Include Z-factor in sonic velocity calculation per gas dynamics principles
        sonic_velocity = np.sqrt(k * Z * R_specific * T)
        Re[i] = rho_upstream * sonic_velocity * eqD_approx / mu_upstream if mu_upstream > 0 and eqD_approx > 0 else 0
        
        # Enhanced Reynolds correction with documented basis
        if Re[i] < 10000:
            A_coef = 0.5
            B_coef = 0.25
            Cd_corrected[i] = Cd * max(0.3, min(1.0, (1.0 - A_coef * (Re[i]**(-B_coef)))))
        else:
            Cd_corrected[i] = Cd
        
        # Critical flow equation with corrected Cd
        eqA[i] = calculate_choked_flow(fr_samples[i], P_Pa, Cd_corrected[i])

# Calculate equivalent diameter
eqD = np.sqrt(4 * eqA / math.pi) * 1000  # Convert to mm for better readability

# Calculate safety-factored results
eqA_safe = eqA * safety_factor
eqD_safe = np.sqrt(4 * eqA_safe / math.pi) * 1000  # Convert to mm

# 6) Prepare results dataframe
df = pd.DataFrame({
    "Flow Rate": fr_samples,
    "ΔP (Pa)": dp_samples,
    "EqArea (m²)": eqA,
    "EqDiam (mm)": eqD,
    "EqArea_Safe (m²)": eqA_safe,
    "EqDiam_Safe (mm)": eqD_safe
})

# TAB 2: Results & Visualization (Moved content from old display_tab1 here)
with main_tabs[1]:
    st.markdown('<p class="sub-header">Calculated Results</p>', unsafe_allow_html=True)
    
    # Display units
    eq_area_unit = st.selectbox("Display area units", ["m²", "mm²", "in²"])
    eq_diam_unit = st.selectbox("Display diameter units", ["mm", "in", "m"])
    
    # Convert to display units
    if eq_area_unit == "m²":
        display_area = df["EqArea (m²)"]
        area_scale = 1.0
    elif eq_area_unit == "mm²":
        display_area = df["EqArea (m²)"] * 1e6
        area_scale = 1e6
    else:  # in²
        display_area = df["EqArea (m²)"] * 1550.0
        area_scale = 1550.0
        
    if eq_diam_unit == "mm":
        display_diam = df["EqDiam (mm)"]
        diam_scale = 1.0
    elif eq_diam_unit == "in":
        display_diam = df["EqDiam (mm)"] / 25.4
        diam_scale = 1/25.4
    else:  # m
        display_diam = df["EqDiam (mm)"] / 1000.0
        diam_scale = 1/1000.0
    
    # Calculate mean values for metrics display
    mean_area = np.mean(eqA) * area_scale
    mean_diam = np.mean(eqD) * diam_scale
    
    # N-3: Calculate conservative (minimum) Cd values for conservative sizing
    if len(Cd_corrected) > 1:
        min_cd = np.min(Cd_corrected)
        # Calculate Cd ratio for conservative sizing
        cd_ratio = np.mean(Cd_corrected) / min_cd
        
        # Conservative sizing using min Cd instead of mean
        # First calculate conservative area in base units (m²)
        conservative_area_m2 = np.mean(eqA) * cd_ratio
        
        # Calculate conservative diameter directly from the conservative area
        conservative_diam_mm = np.sqrt(4 * conservative_area_m2 / math.pi) * 1000
        
        # Convert to display units
        conservative_area = conservative_area_m2 * area_scale
        if eq_diam_unit == "mm":
            conservative_diam = conservative_diam_mm
        elif eq_diam_unit == "in":
            conservative_diam = conservative_diam_mm / 25.4
        else:  # m
            conservative_diam = conservative_diam_mm / 1000
    else:
        min_cd = np.mean(Cd_corrected)
        conservative_area = mean_area
        conservative_diam = mean_diam
    
    # N-6: Calculate uncertainty bands (95% confidence interval)
    if len(df) > 1:
        # Calculate standard deviation
        std_area = np.std(eqA) * area_scale
        std_diam = np.std(eqD) * diam_scale
        
        # Calculate 95% confidence interval (±1.96σ for normal distribution)
        ci_95_area = 1.96 * std_area
        ci_95_diam = 1.96 * std_diam
        
        # Calculate percentile-based bounds (more robust to non-normal distributions)
        p05_area = np.percentile(eqA, 5) * area_scale
        p95_area = np.percentile(eqA, 95) * area_scale
        p05_diam = np.percentile(eqD, 5) * diam_scale
        p95_diam = np.percentile(eqD, 95) * diam_scale
    
    # Results metrics
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.metric(
            label=f"Equivalent Flow Area (ESEOA)",
            value=f"{mean_area:.6f} {eq_area_unit}"
        )
        if len(df) > 1:
            # N-6: Display uncertainty with the results
            st.metric(
                label="Area Range",
                value=f"{np.min(eqA) * area_scale:.6f} - {np.max(eqA) * area_scale:.6f} {eq_area_unit}"
            )
            st.metric(
                label="Area (95% Confidence)",
                value=f"{mean_area:.6f} ± {ci_95_area:.6f} {eq_area_unit}"
            )
            # N-3: Show conservative sizing
            st.metric(
                label="Conservative Area (min Cd)",
                value=f"{conservative_area:.6f} {eq_area_unit}",
                delta=f"{conservative_area - mean_area:.6f} {eq_area_unit}"
            )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.metric(
            label=f"Equivalent Diameter (ESEOD)",
            value=f"{mean_diam:.3f} {eq_diam_unit}"
        )
        if len(df) > 1:
            # N-6: Display uncertainty with the results
            st.metric(
                label="Diameter Range",
                value=f"{np.min(eqD) * diam_scale:.3f} - {np.max(eqD) * diam_scale:.3f} {eq_diam_unit}"
            )
            st.metric(
                label="Diameter (95% Confidence)",
                value=f"{mean_diam:.3f} ± {ci_95_diam:.3f} {eq_diam_unit}"
            )
            # N-3: Show conservative sizing
            st.metric(
                label="Conservative Diam (min Cd)",
                value=f"{conservative_diam:.3f} {eq_diam_unit}",
                delta=f"{conservative_diam - mean_diam:.3f} {eq_diam_unit}"
            )
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Visualization
    if len(df) > 1:
        st.markdown('<p class="sub-header">Distribution Analysis</p>', unsafe_allow_html=True)
        
        # N-4: Use session state to remember chart choice
        if 'chart_type' not in st.session_state:
            st.session_state.chart_type = "Histogram"
            
        chart_type = st.radio(
            "Chart Type", 
            ["Histogram", "Scatter Plot", "Box Plot"], 
            horizontal=True,
            index=["Histogram", "Scatter Plot", "Box Plot"].index(st.session_state.chart_type)
        )
        
        # Update session state
        st.session_state.chart_type = chart_type
        
        if chart_type == "Histogram":
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=display_diam,
                name=f'ESEOD ({eq_diam_unit})',
                marker_color='#0078D7',
                opacity=0.7,
                nbinsx=30
            ))
            
            fig.update_layout(
                title=f"Distribution of Equivalent Diameter ({eq_diam_unit})",
                xaxis_title=f"Equivalent Diameter ({eq_diam_unit})",
                yaxis_title="Frequency",
                bargap=0.05,
                template="plotly_white"
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
        elif chart_type == "Scatter Plot":
            fig = px.scatter(
                x=df["ΔP (Pa)"]/dp_convert,
                y=display_diam,
                color=df["Flow Rate"]/flow_convert,
                labels={
                    "x": f"ΔP ({dp_unit})",
                    "y": f"ESEOD ({eq_diam_unit})",
                    "color": f"Flow Rate ({unit_label})"
                },
                title=f"ESEOD vs. Pressure Drop (colored by Flow Rate)"
            )
            
            fig.update_layout(template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
            
        else:  # Box Plot
            fig = go.Figure()
            fig.add_trace(go.Box(
                y=display_diam,
                name=f'ESEOD ({eq_diam_unit})',
                marker_color='#0078D7',
                boxpoints='outliers'
            ))
            
            fig.update_layout(
                title=f"Statistical Distribution of Equivalent Diameter",
                yaxis_title=f"ESEOD ({eq_diam_unit})",
                template="plotly_white"
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        # Extra statistics
        with st.expander("Detailed Statistics"):
            stat_df = pd.DataFrame({
                f"EqArea ({eq_area_unit})": display_area,
                f"EqDiam ({eq_diam_unit})": display_diam
            })
            st.write(stat_df.describe().T)
    else:
        st.info("Distribution analysis requires multiple samples. Your current calculation uses only one sample point.")
    
    # Valve selection guidance
    st.markdown('<p class="sub-header">Engineering Recommendations</p>', unsafe_allow_html=True)
    st.markdown('<div class="container">', unsafe_allow_html=True)
    
    # Round up to nearest standard sizes (example values, can be customized)
    if eq_diam_unit == "mm":
        std_sizes = np.array([1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 32, 40, 50, 65, 80, 100])
    elif eq_diam_unit == "in":
        std_sizes = np.array([1/16, 1/8, 1/4, 3/8, 1/2, 3/4, 1, 1.25, 1.5, 2, 2.5, 3, 4])
    else:  # m
        std_sizes = np.array([0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.008, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.065, 0.08, 0.1])
    
    # Find nearest standard size (rounding up) based on mean diameter with safety factor applied
    mean_diam_safe = np.mean(eqD_safe) * diam_scale
    recommended_size = std_sizes[std_sizes >= mean_diam_safe][0] if any(std_sizes >= mean_diam_safe) else std_sizes[-1]
    
    # Calculate recommended area correctly
    # Convert from display units back to mm for diameter calculation
    recommended_size_mm = recommended_size
    if eq_diam_unit == "in":
        recommended_size_mm = recommended_size * 25.4
    elif eq_diam_unit == "m":
        recommended_size_mm = recommended_size * 1000
        
    # Calculate area in mm² first
    recommended_area_mm2 = np.pi * (recommended_size_mm/2)**2
    
    # Then convert to desired area units
    if eq_area_unit == "mm²":
        recommended_area = recommended_area_mm2
    elif eq_area_unit == "in²":
        recommended_area = recommended_area_mm2 / 645.16  # mm² to in²
    else:  # m²
        recommended_area = recommended_area_mm2 / 1e6  # mm² to m²
    
    st.markdown(f"""
    ### Valve Selection Recommendation
    
    Based on your flow parameters (with {safety_factor}x safety factor applied), we recommend selecting a valve with:
    - **Minimum flow diameter: {recommended_size:.3f} {eq_diam_unit}**
    - **Minimum flow area: {recommended_area:.6f} {eq_area_unit}**
    - **Application type: {safety_application}**
    
    For space vehicle applications, safety factors account for:
    - Manufacturing tolerances
    - Flow coefficient variations
    - Operating condition changes
    - Degradation over mission life
    
    Remember that this calculation is based on the effective flow diameter. The actual valve 
    physical diameter may need to be larger depending on valve type and geometry.
    """)
    
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# TAB 3: Technical Analysis (Moved content from old display_tab2 here, then existing content)
with main_tabs[2]:
    st.markdown('<p class="sub-header">Technical Information & Analysis</p>', unsafe_allow_html=True) # Updated header slightly
    
    # Content from old display_tab2 (Technical Information)
    tech_col1_main, tech_col2_main = st.columns([2,1])
    
    with tech_col1_main:
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.subheader("Calculation Methodology")
        
        if flow_model == "Incompressible":
            st.latex(r'''A = \frac{\dot{m}}{C_d \sqrt{2 \rho \Delta P}}''')
            st.write("""
            Where:
            - A = Flow area (m²)
            - ṁ = Mass flow rate (kg/s)
            - Cd = Discharge coefficient (dimensionless)
            - ρ = Fluid density (kg/m³)
            - ΔP = Pressure drop (Pa)
            
            **Reference:** ASME MFC-3M standard for flow coefficient calculation
            with Reynolds number corrections per Crane TP-410 (2013 Ed.)
            """)
            
        elif flow_model == "Compressible - Subsonic":
            # Updated LaTeX formula to match actual code implementation
            st.latex(r'''A = \frac{\dot{m}}{C_d Y \sqrt{2 \rho_1 \Delta P}}''')
            st.latex(r'''Y = 1 - \frac{x}{3 F_g x_T} \left(1 - \left(\frac{P_2}{P_1}\right)^{\frac{k-1}{k}}\right) \quad \text{where} \quad x = \frac{\Delta P}{P_1}''')
            st.write("""
            Where:
            - A = Flow area (m²)
            - ṁ = Mass flow rate (kg/s)
            - Cd = Discharge coefficient (dimensionless)
            - Y = Expansion factor (dimensionless)
            - ρ₁ = Upstream fluid density (kg/m³)
            - ΔP = Pressure drop (Pa)
            - x = Pressure drop ratio (ΔP/P₁)
            - xT = Critical pressure drop ratio
            - Fg = Valve geometry factor
            - k = Specific heat ratio (Cp/Cv)
            
            **Reference:** ISA-75.01.01-2012 "Flow Equations for Sizing Control Valves"
            """)
            
        elif flow_model == "Compressible - Critical Flow":
            # Updated LaTeX formula to match actual code implementation
            st.latex(r'''A = \frac{\dot{m} \sqrt{Z \cdot R \cdot T}}{{C_d \cdot P_1 \cdot \sqrt{k} \cdot \left(\frac{2}{k+1}\right)^{\frac{k+1}{2(k-1)}}}}''')
            st.write("""
            Where:
            - A = Flow area (m²)
            - ṁ = Mass flow rate (kg/s)
            - Cd = Discharge coefficient (dimensionless)
            - P1 = Upstream pressure (Pa)
            - k = Specific heat ratio (Cp/Cv)
            - Z = Compressibility factor (dimensionless)
            - R = Gas constant for fluid (J/kg/K)
            - T = Upstream temperature (K)
            
            **Reference:** ISO 5167 and NESC Technical Bulletin 22-064 "Calculating Mass Flow Rate Through a Valve"
            """)
        
        st.markdown("""
        ### ESEOD Definition
        
        The Effective Square-Edged Orifice Diameter (ESEOD) represents the diameter of a square-edged 
        orifice that would produce the same flow rate under the same conditions. For space vehicle 
        applications, this parameter is critical for sizing relief and control valves correctly.
        """)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with tech_col2_main:
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.subheader("Input Summary")
        st.write(f"- **Fluid:** {fluid}")
        st.write(f"- **Temperature:** {T:.2f} K ({T_val} {T_unit})")
        st.write(f"- **Pressure:** {P_Pa/1000:.2f} kPa ({P_val} {P_unit})")
        
        if use_range:
            st.write(f"- **Flow Rate:** {fr_min}-{fr_max} {unit_label}")
        else:
            st.write(f"- **Flow Rate:** {fr_min} {unit_label}")
            
        if use_dp_range:
            st.write(f"- **ΔP:** {dp_min}-{dp_max} {dp_unit}")
        else:
            st.write(f"- **ΔP:** {dp_min} {dp_unit}")
            
        st.write(f"- **Flow Model:** {flow_model}")
        st.write(f"- **Discharge Coef:** {Cd}")
        
        st.caption("""
        Note: All calculations use SI units internally 
        with appropriate unit conversions applied.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---") # Separator before existing Technical Analysis sub-tabs
    
    tech_tabs = st.tabs(["Reynolds Effects", "Safety Analysis", "Flow Regime"])
    
    # Reynolds Effects Tab
    with tech_tabs[0]:
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.subheader("Reynolds Number Analysis")
        
        col1, col2 = st.columns([2,1])
        
        with col1:
            # Convert Reynolds numbers to scientific notation for display
            mean_re = np.mean(Re)
            min_re = np.min(Re)
            max_re = np.max(Re)
            
            # Categorize flow regime
            def flow_regime(re):
                if re < 2300:
                    return "Laminar flow"
                elif re < 4000:
                    return "Transitional flow"
                else:
                    return "Turbulent flow"
            
            mean_regime = flow_regime(mean_re)
            
            # Plot Reynolds number vs Cd correction
            if Re.size > 1: # Changed from np.size(Re)
                fig = go.Figure()
                
                fig.add_trace(go.Scatter(
                    x=Re, 
                    y=Cd_corrected,
                    mode='markers',
                    marker=dict(
                        size=8,
                        color=Re,
                        colorscale='Viridis',
                        showscale=True,
                        colorbar=dict(title="Reynolds Number")
                    ),
                    name='Cd vs Re'
                ))
                
                fig.update_layout(
                    title="Discharge Coefficient vs Reynolds Number",
                    xaxis_title="Reynolds Number",
                    yaxis_title="Corrected Discharge Coefficient (Cd)",
                    template="plotly_white",
                    xaxis_type="log"  # Logarithmic scale for Reynolds
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
                # Create histogram of Reynolds numbers
                fig = go.Figure()
                fig.add_trace(go.Histogram(
                    x=Re,
                    nbinsx=30,
                    marker_color='rgba(0, 120, 215, 0.7)',
                    name='Reynolds distribution'
                ))
                
                # Add vertical lines for flow regime boundaries
                fig.add_vline(x=2300, line_width=2, line_dash="dash", line_color="red",
                          annotation_text="Laminar", annotation_position="top right")
                fig.add_vline(x=4000, line_width=2, line_dash="dash", line_color="green",
                          annotation_text="Turbulent", annotation_position="top left")
                          
                fig.update_layout(
                    title="Reynolds Number Distribution with Flow Regimes",
                    xaxis_title="Reynolds Number",
                    yaxis_title="Count",
                    template="plotly_white"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Add explanation text
                if mean_re < 2300:
                    st.info("""
                    **Laminar Flow Detected**: At low Reynolds numbers, viscous forces dominate and can significantly
                    affect discharge coefficient. For cryogenic applications, this usually occurs during low-flow
                    conditions or with highly viscous fluids.
                    """)
                elif mean_re < 4000:
                    st.warning("""
                    **Transitional Flow Detected**: In this flow regime, flow behavior is less predictable and
                    discharge coefficients can vary significantly. Consider sizing with additional margin or
                    conducting detailed testing for critical applications.
                    """)
                else:
                    st.success("""
                    **Turbulent Flow Detected**: At high Reynolds numbers, flow patterns stabilize and discharge
                    coefficients become more consistent. This is the preferred operating regime for valves in
                    aerospace applications.
                    """)
        
        with col2:
            st.metric("Mean Reynolds Number", f"{mean_re:.2e}")
            st.metric("Flow Regime", mean_regime)
            
            if Re.size > 1: # Changed from np.size(Re)
                st.metric("Min Reynolds", f"{min_re:.2e}")
                st.metric("Max Reynolds", f"{max_re:.2e}")
            
            st.markdown("""
            ### Reynolds Effects
            
            Reynolds number affects the discharge coefficient (Cd) of valves:
            
            - **Re < 2,300**: Laminar flow - Cd decreases significantly
            - **2,300 < Re < 4,000**: Transitional - Cd increases rapidly
            - **Re > 4,000**: Turbulent - Cd stabilizes at typical values
            
            For aerospace applications, most systems operate in turbulent regime, 
            but startup, shutdown, and low-flow conditions may experience transitional
            or laminar flow.
            """)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Safety Analysis Tab
    with tech_tabs[1]:
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.subheader("Safety Factor Analysis")
        
        col1, col2 = st.columns([2,1])
        
        with col1:
            # Calculate safety factored results
            if len(df) > 1: # Changed from np.size(df) # Only if we have Monte Carlo results
                fig = go.Figure()
                
                # Create original and safety-factored distributions
                fig.add_trace(go.Histogram(
                    x=eqD,
                    name='Original Size',
                    opacity=0.7,
                    marker_color='blue',
                    nbinsx=30
                ))
                
                fig.add_trace(go.Histogram(
                    x=eqD_safe,
                    name=f'With {safety_factor}x Safety Factor',
                    opacity=0.5,
                    marker_color='red',
                    nbinsx=30
                ))
                
                fig.update_layout(
                    title=f"Effect of {safety_factor}x Safety Factor on Valve Size",
                    xaxis_title="Equivalent Diameter (mm)",
                    yaxis_title="Count",
                    barmode='overlay',
                    template="plotly_white"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Create a comparison bar chart of original vs safety factored diameter
                labels = ["Original Size", f"With {safety_factor}x Safety Factor"]
                values = [np.mean(eqD), np.mean(eqD_safe)]
                
                fig = go.Figure(data=[
                    go.Bar(
                        x=labels,
                        y=values,
                        marker_color=['rgba(0, 120, 215, 0.7)', 'rgba(215, 0, 0, 0.7)']
                    )
                ])
                
                fig.update_layout(
                    title="Diameter Comparison",
                    yaxis_title="Equivalent Diameter (mm)",
                    template="plotly_white"
                )
                
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.metric(
                label=f"Original ESEOD",
                value=f"{np.mean(eqD):.3f} mm"
            )
            st.metric(
                label=f"Safety Factored ESEOD",
                value=f"{np.mean(eqD_safe):.3f} mm",
                delta=f"{(np.mean(eqD_safe) - np.mean(eqD)):.3f} mm"
            )
            
            st.metric(
                label=f"Original EqA",
                value=f"{np.mean(eqA)*1e6:.2f} mm²"
            )
            st.metric(
                label=f"Safety Factored EqA",
                value=f"{np.mean(eqA_safe)*1e6:.2f} mm²",
                delta=f"{(np.mean(eqA_safe) - np.mean(eqA))*1e6:.2f} mm²"
            )
            
            st.markdown(f"""
            ### Safety Factor: {safety_factor}x
            
            **Application Type:** {safety_application}
            
            {SAFETY_FACTORS[safety_application]['description']}
            
            Area increases with the square of diameter, so even a modest
            safety factor on diameter results in a significant increase
            in flow capacity.
            """)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Flow Regime Tab  
    with tech_tabs[2]:
        st.markdown('<div class="container">', unsafe_allow_html=True)
        st.subheader("Flow Regime Analysis")
        
        # Add information about automatic critical flow calculation
        if critical_flow_transitions > 0:
            critical_pct = (critical_flow_transitions / total_samples) * 100
            st.warning(f"""
            **Flow Regime Transitions**: {critical_flow_transitions} out of {total_samples} samples ({critical_pct:.1f}%)
            exceeded the critical pressure ratio (xT = {custom_xt:.3f}) and were automatically calculated 
            using critical flow equations, regardless of the selected flow model.
            """)
        else:
            st.info(f"""
            **Auto-Switching Logic**: 
            This calculator automatically switches to critical flow calculation when the pressure ratio (x = ΔP/P₁) exceeds 
            the critical pressure ratio (xT = {custom_xt:.3f}), regardless of the selected flow model. This ensures accuracy at 
            all operating points.
            """)
        
        # Calculate Mach number for the flow (approximate)
        if flow_model.startswith("Compressible"):
            # Speed of sound in the fluid - now includes compressibility factor Z
            # Reference: Gas dynamics and real gas effects in aerospace applications
            c = np.sqrt(k * Z * R_specific * T)
            
            # Estimate velocity at orifice
            if eqA.size > 0 and np.mean(eqA) > 0: # Changed from np.size(eqA)
                # fr_samples is already mass flow rate (kg/s) at this point
                # Velocity = MassFlowRate / (Density * Area)
                velocity = fr_samples / (rho * eqA)
                    
                # Calculate Mach number
                mach = velocity / c
                
                col1, col2 = st.columns([2,1])
                
                with col1:
                    if mach.size > 1: # Changed from np.size(mach)
                        # Plot Mach number histogram
                        fig = go.Figure()
                        fig.add_trace(go.Histogram(
                            x=mach,
                            nbinsx=30,
                            marker_color='rgba(0, 120, 215, 0.7)',
                            name='Mach number distribution'
                        ))
                        
                        # Add vertical line for critical Mach number (Ma=1)
                        fig.add_vline(x=1.0, line_width=2, line_dash="dash", line_color="red",
                                    annotation_text="Sonic (Ma=1)", annotation_position="top right")
                                    
                        fig.update_layout(
                            title="Mach Number Distribution",
                            xaxis_title="Mach Number",
                            yaxis_title="Count",
                            template="plotly_white"
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # Plot Mach vs Flow rate
                        fig = px.scatter(
                            x=fr_samples/flow_convert,
                            y=mach,
                            color=dp_samples/dp_convert,
                            labels={
                                "x": f"Flow Rate ({unit_label})",
                                "y": "Mach Number",
                                "color": f"ΔP ({dp_unit})"
                            },
                            title="Mach Number vs. Flow Rate"
                        )
                        
                        fig.add_hline(y=1.0, line_width=2, line_dash="dash", line_color="red")
                        fig.update_layout(template="plotly_white")
                        st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    mean_mach = np.mean(mach)
                    max_mach = np.max(mach)
                    
                    st.metric("Mean Mach Number", f"{mean_mach:.3f}")
                    
                    if mach.size > 1: # Changed from np.size(mach)
                        st.metric("Maximum Mach Number", f"{max_mach:.3f}")
                    
                    if mean_mach < 0.3:
                        flow_type = "Subsonic (incompressible approximation valid)"
                        st.success(f"Flow Regime: {flow_type}")
                    elif mean_mach < 0.8:
                        flow_type = "Subsonic (compressible effects important)"
                        st.info(f"Flow Regime: {flow_type}")
                    elif mean_mach < 1.0:
                        flow_type = "Transonic (approaching choked flow)"
                        st.warning(f"Flow Regime: {flow_type}")
                    else:
                        flow_type = "Sonic/Supersonic (choked flow)"
                        st.error(f"Flow Regime: {flow_type}")
                    
                    # Recommendations based on Mach number
                    st.markdown("""
                    ### Flow Regime Recommendations
                    
                    - **Ma < 0.3**: Incompressible model adequate
                    - **0.3 < Ma < 0.8**: Use subsonic compressible model
                    - **Ma > 0.8**: Use critical flow model
                    - **Ma > 1.0**: Flow is choked, pressure recovery and expansion effects important
                    
                    For cryogenic applications, compressible effects are important even at lower Mach numbers
                    due to high pressure ratios and fluid property variations.
                    """)
                    
                    if flow_model == "Incompressible" and mean_mach > 0.3:
                        st.warning("""
                        ⚠️ **Model Mismatch**: Your flow conditions indicate compressible effects are important, 
                        but you're using the incompressible model. Consider switching to a compressible flow model.
                        """)
                    elif flow_model == "Compressible - Subsonic" and mean_mach > 0.8:
                        st.warning("""
                        ⚠️ **Model Mismatch**: Your flow conditions indicate critical/choked flow is likely, 
                        but you're using the subsonic model. Consider switching to the critical flow model.
                        """)
                    elif flow_model == "Compressible - Critical Flow" and mean_mach < 0.8:
                        st.warning("""
                        ⚠️ **Model Mismatch**: Your flow conditions indicate subsonic flow, 
                        but you're using the critical flow model. Consider switching to the subsonic model.
                        """)
            
            else:
                st.error("Unable to calculate flow velocity and Mach number with current parameters.")
        else:
            st.info("Mach number analysis is only available for compressible flow models.")
        
        st.markdown('</div>', unsafe_allow_html=True)

    # Add Technical Notes section after calculations for documentation
    with st.expander("Valve Sizing Technical Standards"):
        st.markdown("""
        ### Standards Implementation Details

        This calculator implements the following industry standards:

        **Incompressible Flow**
        - Based on ASME MFC-3M equations for flow coefficient
        - Reynolds number corrections follow Crane TP-410 (2013 Ed.) guidance for orifice coefficients
        - Valid for liquids and gases with Mach < 0.3

        **Compressible Subsonic Flow**
        - Based on ISA-75.01.01 (2012) Flow Equations for Sizing Control Valves
        - Expansion factor (Y) calculation includes specific heat ratio and valve geometry adjustments
        - Valid for 0.3 < Mach < 0.8 and pressure ratios below critical

        **Compressible Critical Flow**
        - Based on NASA SP-125 and NESC TB 22-064 for choked flow through orifices
        - Includes compressibility factor (Z) correction for real gas behavior
        - Valid for Mach ≥ 0.8 and pressure ratios at or above critical

        **Aerospace-Specific References**
        - NASA Technical Memorandum X-52097 "Valve Sizing for Cryogenic Applications"
        - NASA Technical Memorandum 2016-219078 "Fluid Flow Modeling Guidelines in Rocket Engine Systems"
        - AIAA S-142-2018 "Standard for Propellant Feed System Design and Analysis"
        - ASME Section VIII, Division 1 for relief device sizing
        
        **Limitations**
        - For very low Reynolds numbers (Re < 100), sizing results have increased uncertainty
        - Two-phase flow is not supported
        - For cryogenic applications near saturation, consult detailed CFD or test data
        """)

# TAB 4: Valve Comparison
with main_tabs[3]:
    st.markdown('<p class="sub-header">Valve Comparison Analysis</p>', unsafe_allow_html=True)
    
    # Create a reference valve from current calculation
    current_valve = {
        "name": "Current Valve",
        "type": valve_type,
        "size_mm": np.mean(eqD),
        "size_in": np.mean(eqD) / 25.4,
        "area_mm2": np.mean(eqA) * 1e6,
        "cd": np.mean(Cd_corrected),
        "re": np.mean(Re),
        "safe_size_mm": np.mean(eqD_safe),
        "safe_area_mm2": np.mean(eqA_safe) * 1e6
    }
    
    # Define common aerospace valve manufacturers and sizes
    # Note: These are representative sizes, actual compatibility would need verification
    VALVE_LIBRARY = {
        "Small Spacecraft": [
            {"name": "1/4\" Mini Valve", "size_mm": 6.35, "type": "Ball Valve"},
            {"name": "3/8\" Mini Valve", "size_mm": 9.53, "type": "Ball Valve"},
            {"name": "Small Poppet", "size_mm": 5.0, "type": "Poppet Valve"},
            {"name": "Small Relief", "size_mm": 8.0, "type": "Cryogenic Relief Valve"}
        ],
        "Medium Spacecraft": [
            {"name": "1/2\" Medium Valve", "size_mm": 12.7, "type": "Ball Valve"},
            {"name": "3/4\" Medium Valve", "size_mm": 19.05, "type": "Ball Valve"},
            {"name": "Medium Globe", "size_mm": 15.0, "type": "Globe Valve"},
            {"name": "Medium Relief", "size_mm": 12.0, "type": "Cryogenic Relief Valve"}
        ],
        "Upper Stage": [
            {"name": "1\" Flow Control", "size_mm": 25.4, "type": "Ball Valve"},
            {"name": "1.5\" Flow Control", "size_mm": 38.1, "type": "Butterfly Valve"},
            {"name": "Large Poppet", "size_mm": 25.0, "type": "Poppet Valve"},
            {"name": "High-Flow Relief", "size_mm": 32.0, "type": "Cryogenic Relief Valve"}
        ],
        "Main Propulsion": [
            {"name": "2\" Main Valve", "size_mm": 50.8, "type": "Ball Valve"},
            {"name": "3\" Main Valve", "size_mm": 76.2, "type": "Butterfly Valve"},
            {"name": "4\" Main Valve", "size_mm": 101.6, "type": "Butterfly Valve"},
            {"name": "Large Relief", "size_mm": 65.0, "type": "Cryogenic Relief Valve"}
        ]
    }
    
    # Options for adding custom valves for comparison
    st.markdown('<div class="container">', unsafe_allow_html=True)
    st.subheader("Valve Selection Analysis")
    
    st.write("""
    Compare your calculated valve size against standard space vehicle valve options or add custom valves to evaluate.
    This analysis helps determine if an off-the-shelf valve will meet your requirements or if a custom valve is needed.
    """)
    
    # Selection of valve categories to evaluate
    valve_categories = st.multiselect(
        "Select valve categories to evaluate",
        options=list(VALVE_LIBRARY.keys()),
        default=["Small Spacecraft", "Medium Spacecraft"]
    )
    
    # Option to add custom valves
    add_custom = st.checkbox("Add custom valve for comparison")
    
    custom_valves = []
    if add_custom:
        col1, col2 = st.columns(2)
        
        with col1:
            custom_name = st.text_input("Custom valve name", "My Custom Valve")
            custom_size_mm = st.number_input("Custom valve size (mm)", value=float(np.mean(eqD)), step=0.1)
            custom_type = st.selectbox("Custom valve type", list(AEROSPACE_VALVE_TYPES.keys()))
        
        with col2:
            custom_cd = st.slider("Custom valve Cd", 0.1, 1.0, 0.6, 0.01)
            # Calculate area from diameter
            custom_area_mm2 = np.pi * (custom_size_mm/2)**2
            st.metric("Custom valve area", f"{custom_area_mm2:.2f} mm²")
        
        custom_valves.append({
            "name": custom_name,
            "type": custom_type,
            "size_mm": custom_size_mm,
            "size_in": custom_size_mm / 25.4,
            "area_mm2": custom_area_mm2,
            "cd": custom_cd,
            "re": np.mean(Re),  # Use same Reynolds for comparison
            "safe_size_mm": custom_size_mm,  # No safety factor applied to custom valve
            "safe_area_mm2": custom_area_mm2
        })
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Comparison Analysis
    st.markdown('<div class="container">', unsafe_allow_html=True)
    st.subheader("Comparative Valve Analysis")
    
    # Build list of valves to compare
    valves_to_compare = [current_valve]
    
    # Add valves from selected categories
    for category in valve_categories:
        for valve in VALVE_LIBRARY[category]:
            valve_area_mm2 = np.pi * (valve["size_mm"]/2)**2
            
            # Get typical Cd for this valve type
            if valve["type"] in AEROSPACE_VALVE_TYPES:
                cd_min, cd_max = AEROSPACE_VALVE_TYPES[valve["type"]]["typical_cd"]
                valve_cd = (cd_min + cd_max) / 2
            else:
                valve_cd = 0.6  # Default value
            
            # Complete valve data
            complete_valve = {
                "name": f"{valve['name']} ({category})",
                "type": valve["type"],
                "size_mm": valve["size_mm"],
                "size_in": valve["size_mm"] / 25.4,
                "area_mm2": valve_area_mm2,
                "cd": valve_cd,
                "re": np.mean(Re),  # Use same Reynolds for comparison
                "safe_size_mm": valve["size_mm"],
                "safe_area_mm2": valve_area_mm2
            }
            valves_to_compare.append(complete_valve)
    
    # Add any custom valves
    valves_to_compare.extend(custom_valves)
    
    # Create comparison dataframe
    comparison_df = pd.DataFrame(valves_to_compare)
    
    # Calculate flow capacity percentage compared to required
    req_area = np.mean(eqA) * 1e6  # mm²
    comparison_df["capacity_pct"] = (comparison_df["area_mm2"] * comparison_df["cd"]) / (req_area * np.mean(Cd_corrected)) * 100
    
    # Calculate flow capacity vs safety factored requirement
    req_area_safe = np.mean(eqA_safe) * 1e6  # mm²
    comparison_df["safe_capacity_pct"] = (comparison_df["area_mm2"] * comparison_df["cd"]) / (req_area_safe * np.mean(Cd_corrected)) * 100
    
    # Determine if valve is suitable
    comparison_df["suitable"] = comparison_df["capacity_pct"] >= 100
    comparison_df["safe_suitable"] = comparison_df["safe_capacity_pct"] >= 100
    
    # Display comparison dataframe with colored status
    st.write("### Valve Size Comparison")
    
    # Format the dataframe for display
    display_df = comparison_df[["name", "type", "size_mm", "area_mm2", "cd", "capacity_pct", "safe_capacity_pct", "suitable", "safe_suitable"]]
    display_df.columns = ["Valve Name", "Type", "Size (mm)", "Area (mm²)", "Cd", "Flow Capacity %", f"Capacity with {safety_factor}x SF %", "Meets Req", "Meets Safe Req"]
    
    # Add styling to the dataframe
    def color_suitable(val):
        if val == True:
            return 'background-color: #c6efce; color: #006100'
        else:
            return 'background-color: #fec7ce; color: #9c0006'
    
    # Apply styling
    styled_df = display_df.style.map(color_suitable, subset=["Meets Req", "Meets Safe Req"])
    
    # Add background color for flow capacity
    def color_capacity(val):
        if val >= 100:
            return f'background-color: rgba(198, 239, 206, {min(val/200, 1)})'
        else:
            return f'background-color: rgba(254, 199, 206, {min((100-val)/100, 1)})'
    
    styled_df = styled_df.map(color_capacity, subset=["Flow Capacity %", f"Capacity with {safety_factor}x SF %"])
    
    # Round numeric columns
    styled_df = styled_df.format({
        "Size (mm)": "{:.2f}",
        "Area (mm²)": "{:.2f}",
        "Cd": "{:.2f}",
        "Flow Capacity %": "{:.1f}%",
        f"Capacity with {safety_factor}x SF %": "{:.1f}%"
    })
    
    st.dataframe(styled_df, use_container_width=True)
    
    # Visualization of valve comparison
    st.write("### Visual Comparison")
    
    # Bar chart of valve sizes with required size highlighted
    fig = go.Figure()
    
    # Add required size line
    fig.add_shape(
        type="line",
        x0=-0.5,
        y0=np.mean(eqD),
        x1=len(valves_to_compare)-0.5,
        y1=np.mean(eqD),
        line=dict(color="red", width=2, dash="dash"),
        name="Required Size"
    )
    
    # Add safety factored required size line
    fig.add_shape(
        type="line",
        x0=-0.5,
        y0=np.mean(eqD_safe),
        x1=len(valves_to_compare)-0.5,
        y1=np.mean(eqD_safe),
        line=dict(color="darkred", width=2, dash="dash"),
        name=f"Required Size with {safety_factor}x Safety Factor"
    )
    
    # Add valve size bars
    valve_colors = ['blue' if i == 0 else 
                   'green' if comparison_df['safe_suitable'][i] else 
                   'orange' if comparison_df['suitable'][i] else 
                   'red' for i in range(len(comparison_df))]
    
    fig.add_trace(go.Bar(
        x=comparison_df['name'],
        y=comparison_df['size_mm'],
        marker_color=valve_colors,
        text=comparison_df['size_mm'].round(1),
        textposition='auto',
    ))
    
    fig.add_trace(go.Scatter(
        x=[comparison_df['name'][0]],
        y=[np.mean(eqD)],
        mode="markers+text",
        marker=dict(symbol="star", size=12, color="red"),
        text=["Required"],
        textposition="top center",
        showlegend=False
    ))
    
    fig.add_trace(go.Scatter(
        x=[comparison_df['name'][0]],
        y=[np.mean(eqD_safe)],
        mode="markers+text",
        marker=dict(symbol="star", size=12, color="darkred"),
        text=[f"With {safety_factor}x SF"],
        textposition="bottom center",
        showlegend=False
    ))
    
    fig.update_layout(
        title="Valve Size Comparison",
        xaxis_title="Valve Option",
        yaxis_title="Size (mm)",
        template="plotly_white"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Capacity comparison (accounting for different Cd values)
    fig = go.Figure()
    
    # Add 100% line
    fig.add_shape(
        type="line",
        x0=-0.5,
        y0=100,
        x1=len(valves_to_compare)-0.5,
        y1=100,
        line=dict(color="green", width=2, dash="dash"),
    )
    
    fig.add_trace(go.Bar(
        x=comparison_df['name'],
        y=comparison_df['capacity_pct'],
        name="Base Requirement",
        marker_color='rgba(0, 120, 215, 0.7)',
        text=comparison_df['capacity_pct'].round(1),
    ))
    
    fig.add_trace(go.Bar(
        x=comparison_df['name'],
        y=comparison_df['safe_capacity_pct'],
        name=f"With {safety_factor}x Safety Factor",
        marker_color='rgba(215, 0, 0, 0.7)',
        text=comparison_df['safe_capacity_pct'].round(1),
        textposition='auto',
    ))
    
    fig.update_layout(
        title="Valve Flow Capacity Comparison",
        xaxis_title="Valve Option",
        yaxis_title="Capacity (%)",
        barmode='group',
        template="plotly_white",
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Recommendations
    st.write("### Recommendations")
    
    suitable_valves = comparison_df[comparison_df['suitable'] == True]
    safe_suitable_valves = comparison_df[comparison_df['safe_suitable'] == True]
    
    if len(safe_suitable_valves) > 0: # Changed from np.size
        st.success(f"""
        ✅ **{len(safe_suitable_valves)} valves** meet your requirements with the {safety_factor}x safety factor applied:
        {", ".join(safe_suitable_valves['name'].tolist())}
        """)
        
        # Find the smallest suitable valve with safety factor
        smallest_valve = safe_suitable_valves.loc[safe_suitable_valves['size_mm'].idxmin()]
        
        st.info(f"""
        💡 **Recommended Option**: {smallest_valve['name']}
        
        - Size: {smallest_valve['size_mm']:.2f} mm ({smallest_valve['size_in']:.3f} in)
        - Type: {smallest_valve['type']}
        - Flow Capacity: {smallest_valve['safe_capacity_pct']:.1f}% of required with safety factor
        
        This is the smallest valve that meets requirements with the safety factor applied.
        """)
    elif len(suitable_valves) > 0: # Changed from np.size
        st.warning(f"""
        ⚠️ **{len(suitable_valves)} valves** meet your base requirements but not with the {safety_factor}x safety factor applied:
        {", ".join(suitable_valves['name'].tolist())}
        """)
        
        # Find the smallest suitable valve
        smallest_valve = suitable_valves.loc[suitable_valves['size_mm'].idxmin()]
        
        st.info(f"""
        💡 **Potential Option**: {smallest_valve['name']} 
        
        - Size: {smallest_valve['size_mm']:.2f} mm ({smallest_valve['size_in']:.3f} in)
        - Type: {smallest_valve['type']}
        - Flow Capacity: {smallest_valve['capacity_pct']:.1f}% of base requirement
        
        Consider using a larger size or custom valve to meet safety factor requirements.
        """)
    else:
        st.error(f"""
        ❌ **No suitable valves found** that meet your flow requirements.
        
        Consider:
        1. Custom valve design
        2. Parallel valve configuration 
        3. System redesign to reduce flow requirements
        4. Increasing allowable pressure drop
        """)
    
    st.markdown('</div>', unsafe_allow_html=True)

# 7) Help and Documentation
with st.sidebar:
    with st.expander("About this Calculator"):
        st.markdown("""
        ### Space Vehicle Valve Sizing
        
        **Application Areas:**
        - Propellant systems
        - Pressurization systems
        - Cryogenic fluid management
        - Relief systems
        
        **When to use each flow model:**
        - **Incompressible** - For liquids or low-velocity gases
        - **Compressible Subsonic** - For gases below critical pressure ratio
        - **Compressible Critical** - For choked flow (common in high-pressure systems)
        
        **References:**
        - ASME MFC-3M Flow Coefficient Standard
        - ISA-75.01.01 Flow Equations
        - NASA NESC Technical Bulletins
        """)
        
    with st.expander("Validation & Verification"):
        st.write("This tool incorporates aerospace-grade calculations suitable for preliminary valve sizing.")
        st.warning("Final valve selection should be verified by test or detailed CFD analysis.")
        
    with st.expander("Model Selection Guide"):
        st.markdown("""
        ### How to Choose the Right Flow Model

        **Use Incompressible Flow model when:**
        - Working with liquids
        - Working with gases at low pressure drops (ΔP/P < 10%)
        - Mach number < 0.3

        **Use Compressible Subsonic model when:**
        - Working with gases at moderate pressure drops (10% < ΔP/P < critical ratio)
        - 0.3 < Mach number < 0.8
        - Operating below the critical pressure ratio

        **Use Compressible Critical Flow model when:**
        - Working with gases at high pressure drops (ΔP/P ≥ critical ratio)
        - Mach number ≥ 0.8
        - Flow is choked (velocity reaches sonic conditions at minimum area)
        - Pressure recovery is not important (e.g., vents, relief devices)
        """)

# 8) Export results options
col_export1, col_export2 = st.columns(2)

with col_export1:
    # Original CSV export option
    st.download_button(
        label="📥 Export Results to CSV",
        data=df.to_csv().encode('utf-8'),
        file_name=f'valve_sizing_results_{fluid}_{flow_model.replace(" ", "_")}.csv',
        mime='text/csv',
    )

with col_export2:
    # New Excel export option with multiple sheets
    if EXCEL_EXPORT_AVAILABLE:
        # Create Excel file in memory
        def create_excel_file():
            output = BytesIO()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create a writer to save the Excel file
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Create summary sheet
                summary_data = {
                    "Parameter": [
                        "Fluid",
                        "Temperature",
                        "Pressure",
                        "Flow Rate Type",
                        "Flow Rate Range" if use_range else "Flow Rate",
                        "ΔP Range" if use_dp_range else "ΔP",
                        "Flow Model",
                        "Discharge Coefficient",
                        "Date Generated",
                        "",  # Empty row for spacing
                        "RESULTS",
                        "Equivalent Flow Area (Mean)",
                        "Equivalent Flow Area (Min)",
                        "Equivalent Flow Area (Max)",
                        "Equivalent Diameter (Mean)",
                        "Equivalent Diameter (Min)",
                        "Equivalent Diameter (Max)",
                        "Recommended Valve Size"
                    ],
                    "Value": [
                        fluid,
                        f"{T_val} {T_unit} ({T:.2f} K)",
                        f"{P_val} {P_unit} ({P_Pa/1000:.2f} kPa)",
                        fr_type,
                        f"{fr_min}-{fr_max} {unit_label}" if use_range else f"{fr_min} {unit_label}",
                        f"{dp_min}-{dp_max} {dp_unit}" if use_dp_range else f"{dp_min} {dp_unit}",
                        flow_model,
                        Cd,
                        timestamp,
                        "",  # Empty row for spacing
                        "",  # Header for results
                        f"{mean_area:.6f} {eq_area_unit}",
                        f"{np.min(eqA) * area_scale:.6f} {eq_area_unit}" if len(df) > 1 else "N/A",
                        f"{np.max(eqA) * area_scale:.6f} {eq_area_unit}" if len(df) > 1 else "N/A",
                        f"{mean_diam:.3f} {eq_diam_unit}",
                        f"{np.min(eqD) * diam_scale:.3f} {eq_diam_unit}" if len(df) > 1 else "N/A",
                        f"{np.max(eqD) * diam_scale:.3f} {eq_diam_unit}" if len(df) > 1 else "N/A",
                        f"{recommended_size:.3f} {eq_diam_unit}"
                    ]
                }
                
                # Create the summary dataframe and save to Excel
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Add the detailed results
                df.to_excel(writer, sheet_name='Monte Carlo Results', index=False)
                
                # Add statistics sheet only if stat_df exists
                if stat_df is not None:
                    stat_summary = stat_df.describe()
                    stat_summary.to_excel(writer, sheet_name='Statistics')
                
                # If we created a chart, add chart data
                if len(df) > 1:
                    # Create a sheet with the data used in the last chart
                    if chart_type == "Histogram":
                        chart_data = pd.DataFrame({
                            f"ESEOD ({eq_diam_unit})": display_diam
                        })
                        chart_data.to_excel(writer, sheet_name='Chart Data', index=False)
                    elif chart_type == "Scatter Plot":
                        chart_data = pd.DataFrame({
                            f"ΔP ({dp_unit})": df["ΔP (Pa)"]/dp_convert,
                            f"ESEOD ({eq_diam_unit})": display_diam,
                            f"Flow Rate ({unit_label})": df["Flow Rate"]/flow_convert
                        })
                        chart_data.to_excel(writer, sheet_name='Chart Data', index=False)
                    elif chart_type == "Box Plot":
                        chart_data = pd.DataFrame({
                            f"ESEOD ({eq_diam_unit})": display_diam
                        })
                        chart_data.to_excel(writer, sheet_name='Chart Data', index=False)
            
            return output.getvalue()
        
        try:
            excel_data = create_excel_file()
            st.download_button(
                label="📊 Export to Excel Workbook",
                data=excel_data,
                file_name=f'valve_sizing_report_{fluid}_{flow_model.replace(" ", "_")}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
        except ModuleNotFoundError:
            st.error("Excel export failed: 'openpyxl' module not found. Please install it with `pip install openpyxl`")
            EXCEL_EXPORT_AVAILABLE = False
        except Exception as e:
            st.error(f"Excel export failed: {str(e)}")
    else:
        st.info("Excel export requires the 'openpyxl' package. Install with `pip install openpyxl` to enable this feature.")

# Add a note about required packages
with st.sidebar:
    st.markdown("---")
    if not EXCEL_EXPORT_AVAILABLE:
        st.warning("Excel export unavailable. Please install 'openpyxl'.")
        st.code("pip install openpyxl", language="bash")