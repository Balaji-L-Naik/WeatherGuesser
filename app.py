import streamlit as st
import requests
import random
import pandas as pd

# ==========================================
# 0. CONFIGURATION & WAREHOUSE INITIALIZATION
# ==========================================
st.set_page_config(page_title="WeatherGuesser Pipeline", layout="wide")

# --- CUSTOM CSS FOR DARK NEON THEME & STARRY BACKGROUND ---
st.markdown("""
<style>
    /* Main app background: Dark base, light purple low-opacity overlay, and white dots */
    .stApp {
        background-color: #130b1c; /* Deep base color */
        background-image: 
            radial-gradient(rgba(255,255,255,0.15) 1px, transparent 1px),
            radial-gradient(rgba(255,255,255,0.15) 2px, transparent 2px),
            linear-gradient(rgba(167, 139, 250, 0.15), rgba(167, 139, 250, 0.15)); /* Light purple overlay */
        background-size: 100px 100px, 250px 250px, 100% 100%;
        background-position: 0 0, 50px 50px, 0 0;
        color: #e2e8f0;
        font-family: 'Inter', 'Segoe UI', sans-serif;
    }

    /* Primary Centered Heading (Matching reference specs) */
    h1 {
        color: #ffffff !important;
        font-weight: 700 !important;
        font-style: italic !important;
        text-align: center !important;
        font-size: 48px !important;
        line-height: 1.2 !important;
        margin-top: 1rem !important;
        margin-bottom: 2rem !important;
    }
    
    /* Secondary and Tertiary Headings */
    h2 { font-size: 36px !important; font-weight: 700 !important; color: #ffffff !important; }
    h3 { font-size: 24px !important; font-weight: 700 !important; color: #ffffff !important; }

    /* Subtext */
    .st-emotion-cache-10trblm {
        color: #94a3b8;
    }

    /* Neon Glow Buttons */
    div.stButton > button {
        background-color: transparent;
        color: #ffffff;
        border: 2px solid #8b5cf6; 
        border-radius: 8px;
        box-shadow: 0 0 10px #8b5cf6, inset 0 0 5px #8b5cf6;
        transition: all 0.3s ease;
        text-transform: uppercase;
        font-weight: bold;
        letter-spacing: 1px;
        padding: 0.5rem 1rem;
    }

    div.stButton > button:hover {
        background-color: #8b5cf6;
        box-shadow: 0 0 25px #8b5cf6, inset 0 0 10px #8b5cf6;
        border-color: #a78bfa;
        color: #ffffff;
    }

    /* Map Container Glow Contours */
    [data-testid="stDeckGlJsonChart"] {
        border-radius: 12px;
        border: 1px solid #38bdf8; 
        box-shadow: 0 0 20px rgba(56, 189, 248, 0.3);
    }
    
    /* Metrics Styling */
    [data-testid="stMetricValue"] {
        color: #38bdf8; 
        text-shadow: 0 0 10px rgba(56, 189, 248, 0.4);
    }
    
    /* DataFrame/Table adjustments for dark mode */
    [data-testid="stDataFrame"] {
        background-color: #111122;
        border-radius: 8px;
        border: 1px solid #1e1e3f;
    }
</style>
""", unsafe_allow_html=True)


if 'data_warehouse' not in st.session_state:
    st.session_state['data_warehouse'] = pd.DataFrame(columns=[
        'Timestamp', 'City', 'Country', 'Latitude', 'Longitude', 'Actual_Temp', 'Guessed_Temp', 'Error_Delta', 'Score'
    ])

if 'current_round' not in st.session_state:
    st.session_state['current_round'] = None

# ==========================================
# 1. INGESTION LAYER (API Extraction)
# ==========================================
@st.cache_data
def ingest_global_cities():
    url = "https://raw.githubusercontent.com/lutangar/cities.json/master/cities.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Ingestion failed for City Catalog: {e}")
    return []

def ingest_realtime_weather(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"API Error: {response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"Ingestion failed for Weather API: {e}")
    return None

# ==========================================
# 2. PARSING & STAGING LAYER
# ==========================================
def parse_and_stage_round(city_obj, weather_json):
    try:
        actual_temp = weather_json['current']['temperature_2m']
        staging_record = {
            'City': city_obj.get('name'),
            'Country': city_obj.get('country'),
            'Latitude': float(city_obj.get('lat')),
            'Longitude': float(city_obj.get('lng')),
            'Actual_Temp': float(actual_temp)
        }
        return staging_record
    except KeyError as e:
        st.error(f"Parsing error - schema key missing: {e}")
        return None

# ==========================================
# 3. TRANSFORMATION & WAREHOUSING
# ==========================================
def execute_transformation_and_warehouse(staging_record, user_guess):
    actual = staging_record['Actual_Temp']
    delta = abs(actual - user_guess)
    score = max(0, 100 - int(delta * 5))
    
    new_warehouse_row = pd.DataFrame([{
        'Timestamp': pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        'City': staging_record['City'],
        'Country': staging_record['Country'],
        'Latitude': staging_record['Latitude'],
        'Longitude': staging_record['Longitude'],
        'Actual_Temp': actual,
        'Guessed_Temp': user_guess,
        'Error_Delta': delta,
        'Score': score
    }])
    
    st.session_state['data_warehouse'] = pd.concat(
        [st.session_state['data_warehouse'], new_warehouse_row], 
        ignore_index=True
    )
    return score, actual

# ==========================================
# 4. CONSUMPTION LAYER (User Interface)
# ==========================================

# Custom Centered Title HTML
st.markdown("<h1>WeatherGuesser</h1>", unsafe_allow_html=True)

cities_catalog = ingest_global_cities()

if not cities_catalog:
    st.error("Failed to initialize pipeline data sources.")
    st.stop()

def start_new_round():
    random_city = random.choice(cities_catalog)
    raw_weather = ingest_realtime_weather(random_city['lat'], random_city['lng'])
    if raw_weather:
        st.session_state['current_round'] = parse_and_stage_round(random_city, raw_weather)
        st.session_state['round_submitted'] = False

if st.session_state['current_round'] is None:
    start_new_round()

current = st.session_state['current_round']

if current:
    game_col, map_col = st.columns([1, 1])
    
    with game_col:
        st.subheader(f"Target Destination: {current['City']}, {current['Country']}")
        st.info(f"Coordinates Staged: Latitude {current['Latitude']}, Longitude {current['Longitude']}")
        
        guess = st.slider("Guess the current temperature in Celsius:", min_value=-30, max_value=50, value=20)
        
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("Submit Guess", disabled=st.session_state.get('round_submitted', False)):
                st.session_state['round_submitted'] = True
                score, actual = execute_transformation_and_warehouse(current, guess)
                st.success(f"Pipeline Processed! Actual Temp: {actual}°C | Your Guess: {guess}°C")
                st.metric(label="Points Awarded", value=f"{score} / 100")
                
        with btn_col2:
            if st.button("Trigger Next Round"):
                start_new_round()
                st.rerun()

    with map_col:
        st.write("### Location Visual Hint")
        map_hint_df = pd.DataFrame([{
            'lat': current['Latitude'],
            'lon': current['Longitude']
        }])
        st.map(map_hint_df, zoom=3, use_container_width=True)

# --- ANALYTICS DASHBOARD ---
st.markdown("---")
st.subheader("Analytics Dashboard (Data Warehouse Consumption)")

warehouse_df = st.session_state['data_warehouse']

if not warehouse_df.empty:
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Rounds Logged", len(warehouse_df))
    m2.metric("Average Pipeline Score", f"{warehouse_df['Score'].mean():.1f}")
    m3.metric("Average Error Delta", f"{warehouse_df['Error_Delta'].mean():.2f}°C")
    
    st.write("### Historical Log (OLAP Table View)")
    st.dataframe(warehouse_df.sort_values(by='Timestamp', ascending=False), use_container_width=True)
    
    st.write("### Score Performance Over Time")
    st.line_chart(data=warehouse_df, x='Timestamp', y='Score', use_container_width=True)
else:
    st.info("The Data Warehouse is currently empty. Submit a guess above to populate the pipeline records.")