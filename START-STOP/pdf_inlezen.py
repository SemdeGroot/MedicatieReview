import pdfplumber
with pdfplumber.open("START_STOP_Criteria.pdf") as pdf:
    first_page = pdf.pages[0].extract_text()
    print(first_page[:300])