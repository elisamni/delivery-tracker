from __future__ import annotations

import re
from urllib.parse import quote_plus


ACS_LOCATION_DIRECTORY: dict[str, str] = {
    "paphos mesogis ave": "53 Mesogis Ave, 8280 Paphos, Cyprus",
    "polis chrysochous": "11 Vasileos Stasioikou, 8820 Polis Chrysochous, Cyprus",
    "chloraka": "Chlorakas Avenue, 8220 Chloraka, Cyprus",
    "paphos courts": "4 N. Nikolaide & Kynira Str, 8010 Paphos, Cyprus",
    "aradippou": "127 Arch. Makariou III Ave, 7102 Aradippou, Cyprus",
    "artemidos": "24 Artemidos Ave, 6030 Larnaca, Cyprus",
    "xylofagou": "16 Eleutherias Str, 7520 Xylofagou, Cyprus",
    "ormidia": "21 Metochiou Str, 7530 Ormidia, Cyprus",
    "athienou": "29 Evagorou, 7600 Athienou, Cyprus",
    "kiti": "56 Arch. Makarios Str, 7550 Kiti, Cyprus",
    "choirokoitia": "41 Agias Paraskevis Str, 7741 Choirokoitia, Cyprus",
    "kornos": "102A Arch. Makariou Str, 7640 Kornos, Cyprus",
    "larnaka centre": "18 Arch. Kyprianos Str, 6016 Larnaca, Cyprus",
    "paralimni": "84 Stadiou Str, 5280 Paralimni, Cyprus",
    "liopetri": "5 April 1st Ave, 5320 Liopetri, Cyprus",
    "derynia": "4 Eleutherias Str, 5380 Derynia, Cyprus",
    "ayia napa": "1 Dionysiou Solomou Str, 5330 Ayia Napa, Cyprus",
    "tsireio": "41 Stelios Kyriakides Str, 3080 Limassol, Cyprus",
    "agios nicolaos": "3 Riga Feraiou Str, 3095 Limassol, Cyprus",
    "ayios nicolaos": "3 Riga Feraiou Str, 3095 Limassol, Cyprus",
    "omonoia": "35A Vasileos Pavlou Str, 3052 Limassol, Cyprus",
    "ypsonas": "38 Elia Kannaourou, 4180 Ypsonas, Cyprus",
    "kolonakiou": "17 Sp. Kyprianos Ave, 4043 Yermasoyia, Cyprus",
    "episkopi": "31 Arch. Makariou, 4620 Episkopi, Cyprus",
    "agros": "17 Stelios Chatzipetris Str, Agros, Cyprus",
    "tzamouda": "18 June 16th 1943, 3022 Limassol, Cyprus",
    "eleftherias square": "6A Con. Palaiologou, 1011 Nicosia, Cyprus",
    "michalakopoulou": "22 Michalacopoulou Str, 1075 Nicosia, Cyprus",
    "strovolos": "70 Athalassas Ave, 2012 Strovolos, Cyprus",
    "engomi": "34B October 28th Str, 2414 Engomi, Cyprus",
    "lakatamia": "40H Makariou Ave, 2324 Lakatamia, Cyprus",
    "pallouriotisa": "68A John Kennedy Ave, 1046 Pallouriotisa, Cyprus",
    "pera chorio nisou": "27C Makariou Ave, 2572 Pera Chorio Nisou, Cyprus",
    "astromeritis": "70A Grivas Digenis Ave, 2722 Astromeritis, Cyprus",
    "kakopetria galata": "15 Filippou Loizou, 2827 Galata, Cyprus",
    "kokkinotrimithia": "2 Gr. Auxentiou & Avlonos, 2660 Kokkinotrimithia, Cyprus",
    "latsia": "33 Arch. Makariou Ave, 2220 Latsia, Cyprus",
    "strovolos ind area": "14 Varkizas Str, 2033 Strovolos Industrial Area, Cyprus",
    "strakka": "351 Arch. Makariou III, 2313 Pano Lakatamia, Cyprus",
    "ayios dometios": "9 Prigkipos Karolou, 2373 Ayios Dometios, Cyprus",
    "agios dometios": "9 Prigkipos Karolou, 2373 Ayios Dometios, Cyprus",
    "pissouri": "57C Ampelonon, 4607 Pissouri, Cyprus",
    "palaichori": "22 Polykarpou Giorkatzi Ave, 2745 Palaichori, Cyprus",
    "arediou": "29A Griva Digeni, 2614 Arediou, Cyprus",
    "platy aglantzias": "143 Kyrinias Avenue, 2113 Aglantzia, Cyprus",
}


def resolve_pickup_location_url(carrier: str, status_raw: str | None) -> str | None:
    if carrier != "acs" or not status_raw:
        return None

    service_point = extract_acs_service_point(status_raw)
    if not service_point:
        return None

    normalized = _normalize_key(service_point)
    address = ACS_LOCATION_DIRECTORY.get(normalized)
    if not address:
        return None
    return build_google_maps_url(address)


def extract_acs_service_point(status_raw: str) -> str | None:
    patterns = (
        r"arrived at acs\s+(.+?)\s+open\b",
        r"arrived at acs\s+(.+?)\s+delivery\s+pin\b",
        r"arrived at acs\s+(.+)$",
        r"acs\s+(.+?)\s+open\b",
    )
    for pattern in patterns:
        match = re.search(pattern, status_raw, re.IGNORECASE)
        if match:
            return match.group(1).strip(" ,.-")
    return None


def build_google_maps_url(address: str) -> str:
    return f"https://maps.google.com/?q={quote_plus(address)}"


def _normalize_key(value: str) -> str:
    normalized = value.lower().replace("-", " ").replace("/", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
