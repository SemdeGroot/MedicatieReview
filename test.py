def test_token_split(gm_naam):
    """
    Test het splitsen van een geneesmiddelnaam in tokens en het maken van prefixes.
    """
    full_clean = gm_naam.strip()  # normaal zou je clean_name() gebruiken
    tokens = full_clean.split()
    n = len(tokens)

    print(f"Originele naam: '{gm_naam}'")
    print(f"Tokens ({n}): {tokens}")

    print("\nPrefixes die worden geprobeerd:")
    for k in range(1, n + 1):
        candidate = " ".join(tokens[:k])
        print(f"  Eerste {k} woorden: '{candidate}'")


# ---- TEST ----
test_token_split("Calci chew d3 kauwtablet 500/400ie")