"""Deterministic bilingual explanations; numbers and source records are untouched."""

IT = {
    "Current coverage or comparable personal baselines are incomplete.": "La copertura attuale o le baseline personali comparabili sono incomplete.",
    "No conservative adjustment rule fired.": "Nessuna regola prudenziale di adattamento è stata attivata.",
    "Recent observations are covered; no conservative adjustment rule fired.": "Le osservazioni recenti sono coperte; nessuna regola prudenziale di adattamento è stata attivata.",
    "HRV is below the personal reference and resting HR is elevated; reduce workload while collecting a symptom note.": "HRV sotto il riferimento personale e frequenza a riposo elevata: riduci il carico e registra eventuali sintomi.",
    "Recorded sleep was shorter than six hours; use a conservative volume adjustment.": "Il sonno registrato è inferiore a sei ore: usa un adattamento prudenziale del volume.",
    "A priority event is inside its configured taper window.": "Un evento prioritario rientra nel periodo di scarico configurato.",
    "You reported pain or feeling unwell; avoid escalating training and seek appropriate help if symptoms persist.": "Hai segnalato dolore o malessere: evita di aumentare l’allenamento e cerca assistenza appropriata se i sintomi persistono.",
    "Today is marked unavailable.": "Oggi non hai disponibilità per allenarti.",
    "Sync/import missing observations or record a subjective check-in.": "Sincronizza o importa le misurazioni mancanti, oppure registra un check-in soggettivo.",
    "Keep the planned focus with less volume.": "Mantieni l’obiettivo pianificato con meno volume.",
    "Choose an easy technical session or low-impact movement.": "Scegli una sessione tecnica facile o movimento a basso impatto.",
    "Preserve rest and reassess symptoms and availability.": "Mantieni il riposo e rivaluta sintomi e disponibilità.",
    "Record a symptom note and current evidence before returning to training.": "Registra i sintomi e le misurazioni attuali prima di tornare ad allenarti.",
    "New current observations, a symptom check-in or changed availability/event constraints can change this decision.": "Nuove misurazioni, un check-in sui sintomi o nuovi vincoli di disponibilità ed eventi possono cambiare questa decisione.",
    "Review a small session change before applying it.": "Rivedi una piccola modifica della sessione prima di applicarla.",
    "Record availability and choose an appropriately conservative session.": "Registra la disponibilità e scegli una sessione adeguatamente prudente.",
    "Conservative planning rules, not a diagnosis or performance/injury prediction.": "Regole di pianificazione prudenti: non una diagnosi o una previsione di prestazioni e infortuni.",
    "No proprietary readiness score is reconstructed.": "Nessun punteggio proprietario di readiness viene ricostruito.",
}


def translate_decision(output, locale):
    if locale != "it":
        return output
    for field in ("reasons", "limitations"):
        output[field] = [IT.get(s, s) for s in output[field]]
    for item in output["alternatives"]:
        item["reason"] = IT.get(item["reason"], item["reason"])
    for field in ("counterfactual", "next_step"):
        output[field] = IT.get(output[field], output[field])
    return output


NOTIFICATION_IT = {
    "Today's evidence is incomplete": "Le misurazioni di oggi sono incomplete",
    "The training decision is limited by missing or old measurements.": "Le misurazioni mancanti o datate limitano la decisione di allenamento.",
    "Review data coverage or record a check-in.": "Rivedi la copertura dei dati o registra un check-in.",
    "Sync or authorization failed; current evidence may be incomplete.": "Sincronizzazione o autorizzazione non riuscita: le misurazioni attuali possono essere incomplete.",
    "Reconnect the provider or run a scoped repair.": "Ricollega il servizio o avvia una riparazione mirata.",
    "A persistent change deserves a plan review": "Una variazione persistente richiede una revisione del piano",
    "Three recorded days show lower HRV and higher resting HR relative to comparable personal baselines.": "Tre giorni registrati mostrano HRV inferiore e frequenza a riposo superiore alle baseline personali comparabili.",
    "Review the conservative decision and record any symptoms.": "Rivedi la decisione prudenziale e registra eventuali sintomi.",
    "Priority event is approaching": "Un evento prioritario si avvicina",
    "Review the configured taper and preserve the session focus.": "Rivedi lo scarico configurato e mantieni l’obiettivo della sessione.",
    "Review today's decision and planned sessions.": "Rivedi la decisione di oggi e le sessioni pianificate.",
    "Equipment service is due": "È prevista la manutenzione dell’attrezzatura",
    "Recorded usage reached the configured service interval.": "L’utilizzo registrato ha raggiunto l’intervallo di manutenzione configurato.",
    "Inspect equipment and record completed service.": "Controlla l’attrezzatura e registra la manutenzione completata.",
}


def translate_notification(payload, locale):
    output = dict(payload)
    if locale == "it":
        for key in ("title", "why", "action"):
            value = output.get(key, "")
            output[key] = NOTIFICATION_IT.get(value, value)
        suffix = " needs attention"
        if output.get("title", "").endswith(suffix):
            output["title"] = output["title"][: -len(suffix)] + " richiede attenzione"
    return output
