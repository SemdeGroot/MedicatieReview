import json

def bereken_acb_score(medicatielijst, json_path="Anticholinerge_Score/acb.json"):
    """
    Berekent de totale ACB-score en geeft interpretatie.

    Args:
        medicatielijst (list of str): Lijst met geneesmiddelennamen
        json_path (str): Pad naar JSON met ACB-scores

    Returns:
        tuple: (totale ACB-score, interpretatie string)
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    scores = data["scores"]
    totaal = 0
    medicatielijst_norm = [m.lower() for m in medicatielijst]

    for level, middelen in scores.items():
        for middel in middelen:
            if middel.lower() in medicatielijst_norm:
                totaal += int(level)

    # Interpretatie op basis van score
    if totaal == 0:
        interpretatie = "Geen anticholinerge belasting (score = 0)."
    elif totaal == 1:
        interpretatie = "Lichte anticholinerge belasting (score = 1)."
    elif totaal == 2:
        interpretatie = "Matige anticholinerge belasting (score = 2)."
    else:
        interpretatie = "Hoge anticholinerge belasting (score ≥ 3)."

    return totaal, interpretatie


if __name__ == "__main__":
    medicatielijst = ["codeïne", "paroxetine", "diazepam", "clemastine", "digoxine"]
    score, interpretatie = bereken_acb_score(medicatielijst)
    print(f"Totale ACB-score: {score}")
    print(interpretatie)