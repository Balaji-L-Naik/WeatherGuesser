import streamlit as st
import requests
import random
import pandas as pd

# ==========================================
# 0. CONFIGURATION & WAREHOUSE INITIALIZATION
# ==========================================
st.set_page_config(page_title="WeatherGuesser Pipeline", layout="wide")

# Initialize our in-memory "Data Warehouse" if it doesn't exist
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
    """Ingests a dynamic list of major world cities from a public raw dataset."""
    url = "https://raw.githubusercontent.com/lutangar/cities.json/master/cities.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()  # Returns raw nested JSON list
    except Exception as e:
        st.error(f"Ingestion failed for City Catalog: {e}")
    return []

def ingest_realtime_weather(lat, lon):
    """Executes a GET call to retrieve current weather metrics without auth keys."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()  # Returns raw weather JSON
        else:
            print(f"API Error: {response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"Ingestion failed for Weather API: {e}")
    return None

# ==========================================
# 2. PARSING & STAGING LAYER (Data Cleaning)
# ==========================================
def parse_and_stage_round(city_obj, weather_json):
    """Parses raw JSON responses and builds a clean, structured staging record."""
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
# 3. TRANSFORMATION & WAREHOUSING LAYER
# ==========================================
def execute_transformation_and_warehouse(staging_record, user_guess):
    """Applies business metrics (scoring/deltas) and commits row to warehouse."""
    actual = staging_record['Actual_Temp']
    delta = abs(actual - user_guess)
    
    # Core scoring transformation rule
    score = max(0, 100 - int(delta * 5))
    
    # Create the final enriched data row
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
    
    # Append/Commit to the data warehouse
    st.session_state['data_warehouse'] = pd.concat(
        [st.session_state['data_warehouse'], new_warehouse_row], 
        ignore_index=True
    )
    return score, actual

# ==========================================
# 4. CONSUMPTION LAYER (User Interface)
# ==========================================
st.title("🌍 WeatherGuesser: Data Pipeline Edition")
st.caption("A real-time API ingestion, processing, and visualization pipeline game.")

# Step A: Load dynamic city catalog data source
cities_catalog = ingest_global_cities()

if not cities_catalog:
    st.error("Failed to initialize pipeline data sources.")
    st.stop()

# Game controls logic
def start_new_round():
    random_city = random.choice(cities_catalog)
    raw_weather = ingest_realtime_weather(random_city['lat'], random_city['lng'])
    if raw_weather:
        st.session_state['current_round'] = parse_and_stage_round(random_city, raw_weather)
        st.session_state['round_submitted'] = False

if st.session_state['current_round'] is None:
    start_new_round()

# Render main gameplay screen
current = st.session_state['current_round']

if current:
    # Layout division for active gameplay and interactive hint map
    game_col, map_col = st.columns([1, 1])
    
    with game_col:
        st.subheader(f"Target Destination: {current['City']}, Country Code: {current['Country']}")
        st.info(f"Coordinates Staged: Latitude {current['Latitude']}, Longitude {current['Longitude']}")
        
        # User input collection
        guess = st.slider("Guess the current temperature in Celsius (°C):", min_value=-30, max_value=50, value=20)
        
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("Submit Guess to Pipeline", disabled=st.session_state.get('round_submitted', False)):
                st.session_state['round_submitted'] = True
                score, actual = execute_transformation_and_warehouse(current, guess)
                st.success(f"Pipeline Processed! Actual Temp: {actual}°C | Your Guess: {guess}°C")
                st.metric(label="Points Awarded", value=f"{score} / 100")
                
        with btn_col2:
            if st.button("Trigger Next Round / Ingestion"):
                start_new_round()
                st.rerun()

    with map_col:
        st.write("### 📍 Location Visual Hint")
        # Build a temporary mapping dataframe from our staged coordinates
        # Streamlit maps require explicit column labels named 'lat' and 'lon'
        map_hint_df = pd.DataFrame([{
            'lat': current['Latitude'],
            'lon': current['Longitude']
        }])
        # Display the map with a custom default zoom level
        st.map(map_hint_df, zoom=3, use_container_width=True)

# --- ANALYTICS DASHBOARD (Consumption Warehouse Views) ---
st.markdown("---")
st.subheader("📊 Analytics Dashboard (Data Warehouse Consumption)")

warehouse_df = st.session_state['data_warehouse']

if not warehouse_df.empty:
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Rounds Logged", len(warehouse_df))
    m2.metric("Average Pipeline Score", f"{warehouse_df['Score'].mean():.1f}")
    m3.metric("Average Error Delta", f"{warehouse_df['Error_Delta'].mean():.2f}°C")
    
    # Visual analysis using consumption tables
    st.write("### Historical Log (OLAP Table View)")
    st.dataframe(warehouse_df.sort_values(by='Timestamp', ascending=False), use_container_width=True)
    
    st.write("### Score Performance Over Time")
    st.line_chart(data=warehouse_df, x='Timestamp', y='Score', use_container_width=True)
else:
    st.info("The Data Warehouse is currently empty. Submit a guess above to populate the pipeline records.")