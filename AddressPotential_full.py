
import requests
import urllib.parse
import csv
import io
import warnings

def analyze_address():
    address = input("Por favor, introduza a morada para análise: ")

    safe_address = urllib.parse.quote(address)
    geocode_url = f"https://nominatim.openstreetmap.org/search?q={safe_address}&format=json"
    headers = {'User-Agent': 'AddressAnalysisScript/1.0'}

    try:
        print("A obter coordenadas...")
        geocode_response = requests.get(geocode_url, headers=headers)
        geocode_response.raise_for_status()
        results = geocode_response.json()

        if not results:
            print("Não foi possível encontrar as coordenadas para a morada indicada.")
            return

        first_result = results[0]
        input_lat = first_result.get('lat')
        input_lon = first_result.get('lon')

        print("A determinar o concelho...")
        reverse_geocode_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={input_lat}&longitude={input_lon}&localityLanguage=pt"
        reverse_response = requests.get(reverse_geocode_url)
        reverse_response.raise_for_status()
        location_data = reverse_response.json()
        out_municipality = location_data.get('city')
        
        if not out_municipality:
            print("Não foi possível encontrar o concelho para a morada indicada.")
            return

        print("A recolher dados de população, risco e pontos de interesse...")
        
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

        warnings.filterwarnings('ignore', message='Unverified HTTPS request')
        cirac_url = "https://segurmaps.apseguradores.pt/api/v2/extract?map_id=36"
        cirac_headers = {
            "Authorization": "Bearer 8e4b46eb-ce25-424b-83ee-2e21f52a476b",
            "content-type": "application/json",
            "accept": "application/json"
        }
        cirac_json_data = {"type": "Point", "coordinates": [float(input_lon), float(input_lat)]}
        
        cirac_response = requests.post(cirac_url, headers=cirac_headers, json=cirac_json_data, verify=False)
        cirac_response.raise_for_status()
        cirac_data = cirac_response.json()

        out_cirac_cod = None
        try:
            out_cirac_cod = cirac_data['geojson']['features'][0]['properties']['__extract__']['ridx']
        except (KeyError, IndexError):
            pass

        risk_map = {1: "Risco muito baixo", 2: "Risco baixo", 3: "Risco moderado", 4: "Risco elevado", 5: "Risco muito elevado"}
        out_cirac_desc = risk_map.get(out_cirac_cod, "desconhecido")

        radius = 500
        overpass_url = "https://overpass-api.de/api/interpreter"
        overpass_query = f'''[out:json];(node["amenity"](around:{radius},{input_lat},{input_lon});way["amenity"](around:{radius},{input_lat},{input_lon});relation["amenity"](around:{radius},{input_lat},{input_lon}););out center;'''
        poi_response = requests.post(overpass_url, data=overpass_query)
        poi_response.raise_for_status()
        poi_data = poi_response.json()
        points_of_interest = [el.get('tags', {}).get('name') for el in poi_data.get('elements', []) if el.get('tags', {}).get('name')]
        out_poi_count = len(points_of_interest)

        print("A calcular o potencial...")
        final_class = None
        if out_pop and out_poi_count > 0 and out_cirac_cod is not None:
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

        # --- This is where we add the new print statements for debugging ---
        print("\n--- DADOS INTERMÉDIOS ---")
        print(f"Concelho: {out_municipality}")
        print(f"População: {out_pop}")
        print(f"CIRAC: {out_cirac_cod} ({out_cirac_desc})")
        print(f"Pontos de Interesse: {out_poi_count}")
        print("-------------------------")

        print("\n--- RESULTADO DA ANÁLISE ---")
        if final_class and out_pop and out_cirac_desc:
            print(f"A morada que analisou ({address}) apresenta um potencial {final_class}:")
            print(f"- Concelho: {out_municipality}")
            print(f"- População residente: {out_pop} pessoas")
            print(f"- Risco de inundação: {out_cirac_desc} (nível {out_cirac_cod})")
            print(f"- Pontos de interesse (raio de 500m): {out_poi_count}")
        else:
            print("Não foi possível concluir a análise. Um ou mais dados não foram encontrados.")

    except requests.exceptions.RequestException as e:
        print(f"\nERRO: Ocorreu um problema de rede. {e}")
    except Exception as e:
        print(f"\nERRO: Ocorreu um erro inesperado. {e}")

if __name__ == "__main__":
    analyze_address()
