
import streamlit as st
import requests
import urllib.parse
import csv
import io
import pandas as pd
import pydeck as pdk

# --- Set Background Color ---
page_bg_img = """
<style>
[data-testid="stAppViewContainer"] {
    background-color: #ffffff; /* white background */
}
</style>
"""
st.markdown(page_bg_img, unsafe_allow_html=True)


# --- Core Logic Function ---
def get_analysis_for_address(address):
    """
    This function takes an address and performs all the data gathering and analysis.
    It returns the final message, class, coordinates, POI locations, and summary data.
    """
    safe_address = urllib.parse.quote(address)
    geocode_url = f"https://nominatim.openstreetmap.org/search?q={safe_address}&format=json"
    headers = {'User-Agent': 'MyStreamlitApp/1.0'}
    
    try:
        geocode_response = requests.get(geocode_url, headers=headers)
        geocode_response.raise_for_status()
        results = geocode_response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro de rede ao contactar o serviço de geocodificação: {e}", None, None, None, None, None, None, None, None

    if not results:
        return "Não foi possível encontrar as coordenadas para a morada indicada.", None, None, None, None, None, None, None, None

    first_result = results[0]
    input_lat = first_result.get('lat')
    input_lon = first_result.get('lon')

    if not input_lat or not input_lon:
        return "O serviço de geocodificação não retornou uma latitude ou longitude para esta morada.", None, None, None, None, None, None, None, None

    reverse_geocode_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={input_lat}&longitude={input_lon}&localityLanguage=pt"
    
    try:
        reverse_response = requests.get(reverse_geocode_url)
        reverse_response.raise_for_status()
        location_data = reverse_response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro de rede ao contactar o serviço de geocodificação inversa: {e}", None, input_lat, input_lon, None, None, None, None, None

    out_municipality = location_data.get('city')

    if not out_municipality:
        return "Não foi possível encontrar o concelho para a morada indicada.", None, input_lat, input_lon, None, None, None, None, None

    # --- Data Gathering (Population, CIRAC, POIs) ---
    poi_locations = []
    out_pop = None
    out_cirac_desc = None
    out_poi_count = None
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
        overpass_query = f'''
        [out:json];
        (
          node["amenity"](around:{radius},{input_lat},{input_lon});
          way["amenity"](around:{radius},{input_lat},{input_lon});
          relation["amenity"](around:{radius},{input_lat},{input_lon});
        );
        out center;
        '''
        poi_response = requests.post(overpass_url, data=overpass_query)
        poi_response.raise_for_status()
        poi_data = poi_response.json()
        
        unique_poi_coords = set()
        for el in poi_data.get('elements', []):
            tags = el.get('tags', {})
            name = tags.get('name')
            if name:
                lat, lon = (None, None)
                if el['type'] == 'node':
                    lat, lon = el.get('lat'), el.get('lon')
                elif 'center' in el:
                    lat, lon = el['center'].get('lat'), el['center'].get('lon')
                
                if lat and lon and (lat, lon) not in unique_poi_coords:
                    poi_locations.append({'name': name, 'lat': lat, 'lon': lon})
                    unique_poi_coords.add((lat, lon))

        out_poi_count = len(poi_locations)

    except requests.exceptions.RequestException as e:
        return f"Erro de rede ao obter dados (população ou POIs): {e}", None, input_lat, input_lon, None, out_municipality, out_pop, out_cirac_desc, out_poi_count

    # --- Scoring ---
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

        if final_score < 0.33: final_class = "BAIXO"
        elif final_score < 0.66: final_class = "MÉDIO"
        else: final_class = "ALTO"

    # --- Return Final Message ---
    message = ""
    if final_class and out_pop and out_cirac_desc:
        message = f"A morada que analisou ({address}) apresenta um potencial **{final_class}**: neste concelho ({out_municipality}) residem {out_pop} pessoas, o risco de inundação é {out_cirac_desc} e, num raio de 500m, existem {out_poi_count} pontos de interesse."
    else:
        message = "Não foi possível concluir a análise. Um ou mais dados (população, POIs) não foram encontrados para este local."
    
    return message, final_class, input_lat, input_lon, poi_locations, out_municipality, out_pop, out_cirac_desc, out_poi_count

# --- Streamlit App Interface ---
st.title("Análise de Potencial de Morada")

address_input = st.text_input("Por favor, introduza a morada para análise:", "")

if st.button("Analisar Morada"):
    if address_input:
        with st.spinner("A analisar... Por favor, aguarde."):
            result_message, final_class, lat, lon, poi_locations, out_municipality, out_pop, out_cirac_desc, out_poi_count = get_analysis_for_address(address_input)

            if final_class:
                col1, col2 = st.columns(2)

                with col1:
                    if final_class == "BAIXO":
                        st.markdown(f'<div style="background-color: #d4edda; color: black; padding: 10px; border-radius: 5px;">{result_message}</div>', unsafe_allow_html=True)
                    elif final_class == "MÉDIO":
                        st.markdown(f'<div style="background-color: #fff3cd; color: black; padding: 10px; border-radius: 5px;">{result_message}</div>', unsafe_allow_html=True)
                    else: # ALTO
                        st.markdown(f'<div style="background-color: #f8d7da; color: black; padding: 10px; border-radius: 5px;">{result_message}</div>', unsafe_allow_html=True)
                
                with col2:
                    st.markdown("##### Resumo dos Dados")
                    st.markdown(f"**Concelho:** {out_municipality}")
                    st.markdown(f"**População:** {out_pop}")
                    st.markdown(f"**Risco de Inundação:** {out_cirac_desc}")
                    st.markdown(f"**Pontos de Interesse (500m):** {out_poi_count}")

                if lat and lon:
                    lat = float(lat)
                    lon = float(lon)
                    
                    address_df = pd.DataFrame([{'name': 'Morada Analisada', 'lat': lat, 'lon': lon}])

                    address_layer = pdk.Layer(
                        "ScatterplotLayer",
                        data=address_df,
                        get_position='[lon, lat]',
                        get_fill_color=[255, 0, 0], # Red
                        get_radius=25,
                        pickable=True
                    )
                    
                    layers_to_render = [address_layer]

                    if poi_locations:
                        poi_df = pd.DataFrame(poi_locations)
                        poi_layer = pdk.Layer(
                            "ScatterplotLayer",
                            data=poi_df,
                            get_position='[lon, lat]',
                            get_fill_color=[0, 0, 255], # Blue
                            get_radius=7,
                            pickable=True
                        )
                        layers_to_render.append(poi_layer)
                    
                    st.pydeck_chart(pdk.Deck(
                        map_style="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
                        initial_view_state=pdk.ViewState(
                            latitude=lat,
                            longitude=lon,
                            zoom=15,
                            pitch=0,
                            bearing=0
                        ),
                        layers=layers_to_render,
                        tooltip={"text": "{name}"}
                    ))
            else:
                st.markdown(f'<div style="background-color: #f8d7da; color: black; padding: 10px; border-radius: 5px;">{result_message}</div>', unsafe_allow_html=True)

    else:
        st.markdown(f'<div style="background-color: #f8d7da; color: black; padding: 10px; border-radius: 5px;">Por favor, introduza uma morada.</div>', unsafe_allow_html=True)
