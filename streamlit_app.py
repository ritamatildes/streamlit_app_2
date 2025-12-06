
import streamlit as st
import requests
import urllib.parse
import csv
import io
import pandas as pd
import pydeck as pdk
from collections import Counter

# --- Set Background Color and Icons ---
page_bg_img = """
<style>
[data-testid="stAppViewContainer"] {
    background-color: #ffffff; /* white background */
}

/* Custom style for the main analysis button */
div.stButton > button {
    border: 2px solid #808080; /* grey */
    color: #808080; /* grey */
}

div.stButton > button:hover {
    border: 2px solid #808080; /* grey */
    color: white;
    background-color: #808080; /* grey */
}

/* Specific style for the smaller, nested icon button */
div[data-testid="stHorizontalBlock"] div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button {
    border: 1px solid #808080;
    color: #808080;
    background-color: transparent;
    padding: 1px 5px;
    font-size: 1em;
    line-height: 1.2;
    height: 30px; /* Make it shorter */
}

div[data-testid="stHorizontalBlock"] div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button:hover {
    border: 1px solid #808080;
    color: white;
    background-color: #808080;
}

</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css">
"""
st.markdown(page_bg_img, unsafe_allow_html=True)


# --- Core Logic Function ---
def get_analysis_for_address(address):
    # ... (rest of the function is unchanged, so it is omitted for brevity) ...
    safe_address = urllib.parse.quote(address)
    geocode_url = f"https://nominatim.openstreetmap.org/search?q={safe_address}&format=json"
    headers = {'User-Agent': 'MyStreamlitApp/1.0'}
    
    try:
        geocode_response = requests.get(geocode_url, headers=headers)
        geocode_response.raise_for_status()
        results = geocode_response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro de rede ao contactar o serviço de geocodificação: {e}", None, None, None, None, None, None, None, None, None, None

    if not results:
        return "Não foi possível encontrar as coordenadas para a morada indicada.", None, None, None, None, None, None, None, None, None, None

    first_result = results[0]
    input_lat = first_result.get('lat')
    input_lon = first_result.get('lon')

    if not input_lat or not input_lon:
        return "O serviço de geocodificação não retornou uma latitude ou longitude para esta morada.", None, None, None, None, None, None, None, None, None, None

    reverse_geocode_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={input_lat}&longitude={input_lon}&localityLanguage=pt"
    
    try:
        reverse_response = requests.get(reverse_geocode_url)
        reverse_response.raise_for_status()
        location_data = reverse_response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro de rede ao contactar o serviço de geocodificação inversa: {e}", None, input_lat, input_lon, None, None, None, None, None, None, None

    out_municipality = location_data.get('city')

    if not out_municipality:
        return "Não foi possível encontrar o concelho para a morada indicada.", None, input_lat, input_lon, None, None, None, None, None, None, None

    poi_locations = []
    out_pop = None
    out_cirac_desc = None
    out_poi_count = None
    poi_categories = None
    try:
        csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR0A79pNYNO4YD-jhyZ4baNjHsGZCsAyTgVlZgaoSGdKN_ehlS5fUnwmESyknqyy-Wf9-30OnjdCR3I/pub?gid=0&single=true&output=csv"
        csv_response = requests.get(csv_url)
        csv_response.raise_for_status()
        csv_text = csv_response.text
        csv_file = io.StringIO(csv_text)
        csv_reader = csv.reader(csv_file)
        for row in csv_reader:
            if len(row) > 2 and row[1] == out_municipality:
                out_pop = row[2]
                break

        out_cirac_cod = 3
        out_cirac_desc = "Risco moderado"

        radius = 500
        overpass_url = "https://overpass-api.de/api/interpreter"
        overpass_query = f'''[out:json];(node["amenity"](around:{radius},{input_lat},{input_lon});way["amenity"](around:{radius},{input_lat},{input_lon});relation["amenity"](around:{radius},{input_lat},{input_lon}););out center;'''
        poi_response = requests.post(overpass_url, data=overpass_query)
        poi_response.raise_for_status()
        poi_data = poi_response.json()
        
        poi_amenities = []
        unique_poi_coords = set()
        for el in poi_data.get('elements', []):
            tags = el.get('tags', {})
            name = tags.get('name')
            amenity = tags.get('amenity')
            if name and amenity:
                lat, lon = (None, None)
                if el['type'] == 'node':
                    lat, lon = el.get('lat'), el.get('lon')
                elif 'center' in el:
                    lat, lon = el['center'].get('lat'), el['center'].get('lon')
                
                if lat and lon and (lat, lon) not in unique_poi_coords:
                    poi_locations.append({'name': name, 'lat': lat, 'lon': lon})
                    poi_amenities.append(amenity.replace('_', ' ').capitalize())
                    unique_poi_coords.add((lat, lon))

        out_poi_count = len(poi_locations)
        if poi_amenities:
            poi_categories = Counter(poi_amenities)

    except requests.exceptions.RequestException as e:
        return f"Erro de rede ao obter dados (população ou POIs): {e}", None, input_lat, input_lon, None, out_municipality, out_pop, out_cirac_desc, out_poi_count, None, address

    final_class = None
    if out_pop and out_poi_count >= 0:
        numeric_population = int(out_pop.replace(",", ""))
        resid_poi = numeric_population / (out_poi_count + 1)
        
        POP_MIN, POP_MAX = 384, 545_796
        CIRAC_MIN, CIRAC_MAX = 1.0, 5.0
        RESID_POI_MIN, RESID_POI_MAX = 0.0, 2000.0

        def min_max_scale(x, xmin, xmax):
            if xmax == xmin: return 0.0
            val = (x - xmin) / (xmax - xmin)
            return max(0.0, min(1.0, val))

        pop_norm = min_max_scale(numeric_population, POP_MIN, POP_MAX)
        cirac_norm = min_max_scale(out_cirac_cod, CIRAC_MIN, CIRAC_MAX)
        resid_norm = min_max_scale(resid_poi, RESID_POI_MIN, RESID_POI_MAX)

        cirac_norm_inv = 1.0 - cirac_norm
        resid_norm_inv = 1.0 - resid_norm

        w_pop, w_cirac, w_poi = 0.4, 0.3, 0.3
        final_score = (w_pop * pop_norm + w_cirac * cirac_norm_inv + w_poi * resid_norm_inv)

        if final_score < 0.33: final_class = "REDUZIDO"
        elif final_score < 0.66: final_class = "MÉDIO"
        else: final_class = "ALTO"

    message = ""
    if final_class and out_pop and out_cirac_desc:
        try:
            pop_number = int(out_pop.replace(",", ""))
            out_pop_formatted = f"{pop_number:,}".replace(",", " ")
        except (ValueError, TypeError):
            out_pop_formatted = out_pop

        message = f'''<p>A morada analizada localiza-se no concelho ({out_municipality}) onde residem {out_pop_formatted} pessoas.</p>
<p>Apresenta um {out_cirac_desc} de inundação (CIRAC 2.0) e, num raio de 500m, existem {out_poi_count} POIs.</p>'''
    else:
        message = "Não foi possível concluir a análise. Um ou mais dados (população, POIs) não foram encontrados para este local."
        
    return message, final_class, input_lat, input_lon, poi_locations, out_municipality, out_pop, out_cirac_desc, out_poi_count, poi_categories, address

# --- Streamlit App Interface ---
st.title("Análise de Potencial de Morada")

# Initialize session state
if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None
if 'show_poi_details' not in st.session_state:
    st.session_state.show_poi_details = False

def clear_state():
    st.session_state.analysis_result = None
    st.session_state.show_poi_details = False

# Input and button layout
col1, col2 = st.columns([3, 1])
with col1:
    address_input = st.text_input("Por favor, introduza a morada para análise:", "", on_change=clear_state)
with col2:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    analyze_button = st.button("Analisar Morada")

if analyze_button and address_input:
    with st.spinner("A analisar... Por favor, aguarde."):
        st.session_state.analysis_result = get_analysis_for_address(address_input)
        st.session_state.show_poi_details = False # Reset on new analysis
elif analyze_button and not address_input:
    st.warning("Por favor, introduza uma morada.")

# Display results if they exist in session state
if st.session_state.analysis_result:
    result_message, final_class, lat, lon, poi_locations, out_municipality, out_pop, out_cirac_desc, out_poi_count, poi_categories, analyzed_address = st.session_state.analysis_result

    if final_class:
        if final_class == "REDUZIDO": color = "#d4edda"
        elif final_class == "MÉDIO": color = "#fff3cd"
        else: color = "#f8d7da"

        st.markdown(f'<div style="background-color: {color}; color: black; padding: 10px; border-radius: 5px; text-align: center;"><span style="font-size: 1.5em;"><strong>POTENCIAL {final_class}</strong></span><br><span style="font-size: 1.2em;">{analyzed_address}</span></div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        res_col1, res_col2 = st.columns(2)
        with res_col1:
            st.markdown(f'<div style="background-color: {color}; color: black; padding: 10px; border-radius: 5px; font-size: 0.9em;">{result_message}</div>', unsafe_allow_html=True)
        
        with res_col2:
            st.markdown("##### Resumo dos Dados")
            try:
                pop_number = int(out_pop.replace(",", ""))
                out_pop_formatted = f"{pop_number:,}".replace(",", " ")
            except (ValueError, TypeError):
                out_pop_formatted = out_pop
            
            st.markdown(f"<p style='font-size:0.9em'><i class='fas fa-map-marked-alt'></i>&nbsp;&nbsp;<strong>Concelho:</strong> {out_municipality}</p>", unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:0.9em'><i class='fas fa-users'></i>&nbsp;&nbsp;<strong>População:</strong> {out_pop_formatted}</p>", unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:0.9em'><i class='fas fa-cloud-rain'></i>&nbsp;&nbsp;<strong>Risco de Inundação:</strong> {out_cirac_desc}</p>", unsafe_allow_html=True)

            if poi_categories:
                poi_col1, poi_col2 = st.columns([2,1])
                with poi_col1:
                    st.markdown(f"<p style='font-size:0.9em'><i class='fas fa-map-marker-alt'></i>&nbsp;&nbsp;<strong>Total de POIs (500m):</strong> {out_poi_count}</p>", unsafe_allow_html=True)
                with poi_col2:
                    if st.button("🔍"):
                        st.session_state.show_poi_details = not st.session_state.show_poi_details
            else:
                 st.markdown(f"<p style='font-size:0.9em'><i class='fas fa-map-marker-alt'></i>&nbsp;&nbsp;<strong>Total de POIs (500m):</strong> {out_poi_count}</p>", unsafe_allow_html=True)


            if st.session_state.show_poi_details and poi_categories:
                for category, count in sorted(poi_categories.items()):
                    st.markdown(f"<div style='font-size:0.8em; padding-left: 20px;'>- {category}: {count}</div>", unsafe_allow_html=True)

        if lat and lon:
            lat, lon = float(lat), float(lon)
            ICON_DATA = {
                "address": {"url": "https://maps.google.com/mapfiles/ms/icons/red-dot.png", "width": 128, "height": 128, "anchorY": 128},
                "poi": {"url": "https://maps.google.com/mapfiles/ms/icons/blue-dot.png", "width": 128, "height": 128, "anchorY": 128}
            }
            address_df = pd.DataFrame([{'name': 'Morada Analisada', 'lat': lat, 'lon': lon}])
            address_df["icon_data"] = [ICON_DATA["address"]]
            address_layer = pdk.Layer("IconLayer", data=address_df, get_icon="icon_data", get_position='[lon, lat]', get_size=4, size_scale=15, pickable=True)
            layers_to_render = [address_layer]

            if poi_locations:
                poi_df = pd.DataFrame(poi_locations)
                poi_df["icon_data"] = [ICON_DATA["poi"]] * len(poi_locations)
                poi_layer = pdk.Layer("IconLayer", data=poi_df, get_icon="icon_data", get_position='[lon, lat]', get_size=4, size_scale=10, pickable=True)
                layers_to_render.append(poi_layer)
            
            st.pydeck_chart(pdk.Deck(
                map_style="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
                initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=15, pitch=0, bearing=0),
                layers=layers_to_render,
                tooltip={"text": "{name}"}
            ))
    else:
        st.error(result_message)

