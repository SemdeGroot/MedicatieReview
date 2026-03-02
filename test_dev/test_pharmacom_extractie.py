import sys
import time
from lxml import etree

def parse_pharmacom_html(file_path):
    # Start de timer
    start_time = time.perf_counter()
    
    parser = etree.HTMLParser(recover=True, encoding='utf-8')
    
    try:
        # Het laden en parsen van de boomstructuur
        tree = etree.parse(file_path, parser)
        
        # Headers ophalen
        header_row = tree.xpath('//tr[th[@class="headervalue"]]')
        if not header_row:
            return None, 0
            
        headers = [th.text.strip() if th.text else "Onbekend" for th in header_row[0].xpath('.//th')]
        
        # Data rijen ophalen
        data_rows = header_row[0].xpath('./following-sibling::tr')
        
        results = []
        for row in data_rows:
            cells = row.xpath('.//td')
            if len(cells) == len(headers):
                entry = {headers[i]: cells[i].text.strip() if cells[i].text else "" for i in range(len(headers))}
                results.append(entry)
        
        # Stop de timer
        end_time = time.perf_counter()
        duration = end_time - start_time
        
        return results, duration

    except Exception as e:
        print(f"Er is een fout opgetreden: {e}")
        return None, 0

if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "/media/semdegroot/Shared/Projects/MedicatieReview/raw_data/Extractie medicatiehistorie.html"
    
    print(f"Bezig met laden van: {input_file}...")
    data, duration = parse_pharmacom_html(input_file)
    
    if data:
        print("-" * 30)
        print(f"Klaar! {len(data)} regels verwerkt.")
        print(f"Totale parse-tijd: {duration:.4f} seconden")
        print("-" * 30)
        # Toon een klein voorbeeld
        print(f"Eerste item: {data[0] if data else 'N/A'}")
    else:
        print("Geen data kunnen parsen.")