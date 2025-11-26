import streamlit as st
import requests
import urllib.parse
import csv
import io

# --- Core Logic Function ---
# We wrap all our previous logic in a single function.
# This makes the code clean and easy for Streamlit to use.
def get_analysis_for_address(address):
    """
    This function takes an address and performs all the data gathering and analysis.
    It returns the final friendly message or an error string.
    """
    safe_address = urllib.parse.quote(address)
    geocode_url = f"https://nominatim.openstreetmap.org/search?q={safe_address}&format=json"
    headers = {'User-Agent': 'MyStreamlitApp/1.0'}
    
    try:
        geocode_response = requests.get(geocode_url, headers=headers)
        geocode_response.raise_for_status() # This will raise an error for bad responses (4xx or 5xx)
        results = geocode_response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro de rede ao contactar o serviço de geocodificação: {e}"

    if not results:
        return "Não foi possível encontrar as coordenadas para a morada indicada."

    first_result = results[0]
    input_lat = first_result.get('lat')
    input_lon = first_result.get('lon')

    reverse_geocode_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={input_lat}&longitude={input_lon}&localityLanguage=pt"
    
    try:
        reverse_response = requests.get(reverse_geocode_url)
        reverse_response.raise_for_status()
        location_data = reverse_response.json()
    except requests.exceptions.RequestException as e:
        return f"Erro de rede ao contactar o serviço de geocodificação inversa: {e}"

    out_municipality = location_data.get('city')

    if not out_municipality:
        return "Não foi possível encontrar o concelho para a morada indicada."

    # --- Data Gathering (Population, CIRAC, POIs) ---
    try:
        csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR0A79pNYNO4YD-jhyZ4baNjHsGZCsAyTgVlZgaoSGdKN_ehlS5fUnwmESyknqyy-Wf9-30OnjdCR3I/pub?gid=0&single=true&output=csv"
        csv_response = requests.get(csv_url)
        csv_response.raise_for_status()
        csv_text = csv_response.text
        csv_file = io.StringIO(csv_text)
        csv_reader = csv.reader(csv_file)
        out_pop = None
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
        points_of_interest = [el.get('tags', {}).get('name') for el in poi_data.get('elements', []) if el.get('tags', {}).get('name')]
        out_poi_count = len(points_of_interest)

    except requests.exceptions.RequestException as e:
        return f"Erro de rede ao obter dados (população ou POIs): {e}"

    # --- Scoring ---
    final_class = None
    if out_pop and out_poi_count > 0:
        numeric_population = int(out_pop.replace(",", ""))
        resid_poi = numeric_population / out_poi_count
        
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
    if final_class and out_pop and out_cirac_desc:
        return f"A morada que analisou ({address}) apresenta um potencial **{final_class}**: neste concelho ({out_municipality}) residem {out_pop} pessoas, o risco de inundação é {out_cirac_desc} e, num raio de 500m, existem {out_poi_count} pontos de interesse."
    else:
        return "Não foi possível concluir a análise. Um ou mais dados (população, POIs) não foram encontrados para este local."


# --- Streamlit App Interface ---

st.title("Análise de Potencial de Morada")

# The text_input function creates a text box in the web app
address_input = st.text_input("Por favor, introduza a morada para análise:", "")

# The button function creates a button. The code inside this "if" statement
# will only run when the user clicks the button.
if st.button("Analisar Morada"):
    if address_input:
        # We show a spinner while the analysis is running
        with st.spinner("A analisar... Por favor, aguarde."):
            result_message = get_analysis_for_address(address_input)
            # The success function displays the message in a green box
            st.success(result_message)
    else:
        # The warning function displays a message in a yellow box
        st.warning("Por favor, introduza uma morada.")
