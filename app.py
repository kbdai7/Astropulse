
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

import streamlit as st

try:
    from pystac.validation import validate_dict
    PYSTAC_DISPONIBLE = True
except ImportError:
    validate_dict = None
    PYSTAC_DISPONIBLE = False


API_URL = "https://earth-search.aws.element84.com/v1/search"


# ==========================================
# 1. MOTEUR DE DETECTION ASTROPULSE
# ==========================================

def verifier_item(item):
    alertes = []

    if not isinstance(item, dict):
        return ["Objet invalide : un objet JSON est attendu."]

    if item.get("type") != "Feature":
        alertes.append("Type Feature incorrect.")

    if not isinstance(item.get("id"), str) or not item["id"].strip():
        alertes.append("Identifiant absent ou invalide.")

    version = item.get("stac_version")
    if not isinstance(version, str) or not version.strip():
        alertes.append("Version STAC absente ou invalide.")

    props = item.get("properties")
    if not isinstance(props, dict):
        alertes.append("Propriétés absentes ou invalides.")
        props = {}

    geometry = item.get("geometry")
    if "geometry" not in item:
        alertes.append("Champ geometry absent.")
    elif geometry is not None:
        if not isinstance(geometry, dict):
            alertes.append("Géométrie invalide.")
        elif geometry.get("type") not in (
            "Point", "MultiPoint", "LineString",
            "MultiLineString", "Polygon", "MultiPolygon",
            "GeometryCollection"
        ):
            alertes.append("Type de géométrie inconnu.")

    bbox = item.get("bbox")

    if bbox is not None:
        if not isinstance(bbox, list) or len(bbox) not in (4, 6):
            alertes.append("BBox absente ou format invalide.")
        elif not all(
            isinstance(v, (int, float)) and not isinstance(v, bool)
            for v in bbox
        ):
            alertes.append("BBox contenant des valeurs non numériques.")
        else:
            n = len(bbox) // 2

            if any(bbox[i] > bbox[i + n] for i in range(n)):
                alertes.append("BBox avec limites incohérentes.")

            if len(bbox) in (4, 6):
                if bbox[0] < -180 or bbox[n] > 180:
                    alertes.append("Longitude hors limites.")
                if bbox[1] < -90 or bbox[n + 1] > 90:
                    alertes.append("Latitude hors limites.")

    if geometry is None and bbox is not None:
        alertes.append(
            "Géométrie nulle avec BBox présente : vérifier la conformité STAC."
        )

    if not isinstance(item.get("links"), list):
        alertes.append("Liste links absente ou invalide.")

    if not isinstance(item.get("assets"), dict):
        alertes.append("Objet assets absent ou invalide.")

    date_item = props.get("datetime")
    date_debut = props.get("start_datetime")
    date_fin = props.get("end_datetime")

    if date_item is None and not (date_debut and date_fin):
        alertes.append("Date ou période temporelle manquante.")

    dates = {}

    for nom, valeur in (
        ("datetime", date_item),
        ("start_datetime", date_debut),
        ("end_datetime", date_fin),
    ):
        if valeur is None:
            continue

        if not isinstance(valeur, str):
            alertes.append(f"{nom} : format invalide.")
            continue

        try:
            dates[nom] = datetime.fromisoformat(
                valeur.replace("Z", "+00:00")
            )
        except ValueError:
            alertes.append(f"{nom} : date illisible.")

    if "start_datetime" in dates and "end_datetime" in dates:
        try:
            debut = dates["start_datetime"]
            fin = dates["end_datetime"]

            if debut.tzinfo is None and fin.tzinfo is not None:
                debut = debut.replace(tzinfo=timezone.utc)
            elif fin.tzinfo is None and debut.tzinfo is not None:
                fin = fin.replace(tzinfo=timezone.utc)

            if debut > fin:
                alertes.append("Début de période postérieur à la fin.")
        except TypeError:
            alertes.append("Période temporelle impossible à comparer.")

    return alertes


# ==========================================
# 2. VALIDATION STAC OFFICIELLE
# ==========================================

def valider_stac(item):
    if not PYSTAC_DISPONIBLE:
        return [
            "PySTAC indisponible : validation STAC non exécutée."
        ]

    try:
        from pystac.validation import validate_dict

        validate_dict(item)
        return []

    except Exception as erreur:
        message = " ".join(str(erreur).split())

        if not message:
            message = type(erreur).__name__

        return [f"Validation STAC : {message[:500]}"]


# ==========================================
# 3. FICHES ET TESTS AUTOMATIQUES
# ==========================================

def creer_item_test():
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": "ASTROPULSE-TEST-001",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [2.0, 6.0],
                [3.0, 6.0],
                [3.0, 7.0],
                [2.0, 7.0],
                [2.0, 6.0]
            ]]
        },
        "bbox": [2.0, 6.0, 3.0, 7.0],
        "properties": {
            "datetime": "2026-01-15T10:30:00Z"
        },
        "links": [],
        "assets": {}
    }


def executer_tests():
    tests = []

    def tester(nom, modification, attendu=None):
        item = creer_item_test()
        modification(item)
        alertes = verifier_item(item)

        if attendu is None:
            reussi = len(alertes) == 0
            attendu_txt = "Aucune alerte"
        else:
            reussi = any(attendu in a for a in alertes)
            attendu_txt = attendu

        tests.append({
            "Test": nom,
            "Détection attendue": attendu_txt,
            "Détectée ?": "OUI" if reussi else "NON",
            "Résultat": "RÉUSSI" if reussi else "ÉCHEC",
            "Alertes obtenues": "; ".join(alertes) or "Aucune"
        })

    tester("Fiche correcte", lambda i: None)

    tester(
        "Identifiant manquant",
        lambda i: i.update({"id": ""}),
        "Identifiant"
    )

    tester(
        "Type incorrect",
        lambda i: i.update({"type": "Image"}),
        "Type Feature"
    )

    tester(
        "Version manquante",
        lambda i: i.pop("stac_version"),
        "Version STAC"
    )

    tester(
        "Propriétés invalides",
        lambda i: i.update({"properties": None}),
        "Propriétés"
    )

    tester(
        "Géométrie absente",
        lambda i: i.pop("geometry"),
        "geometry absent"
    )

    tester(
        "BBox incohérente",
        lambda i: i.update({"bbox": [3.0, 6.0, 2.0, 7.0]}),
        "BBox avec limites"
    )

    tester(
        "Liens invalides",
        lambda i: i.update({"links": "invalides"}),
        "Liste links"
    )

    tester(
        "Assets invalides",
        lambda i: i.update({"assets": None}),
        "Objet assets"
    )

    tester(
        "Date manquante",
        lambda i: i["properties"].pop("datetime"),
        "Date ou période"
    )

    tester(
        "Date illisible",
        lambda i: i["properties"].update({
            "datetime": "date-invalide"
        }),
        "date illisible"
    )

    tester(
        "Période inversée",
        lambda i: i["properties"].update({
            "datetime": None,
            "start_datetime": "2026-12-31T00:00:00Z",
            "end_datetime": "2026-01-01T00:00:00Z"
        }),
        "postérieur à la fin"
    )

    tester(
        "Longitude hors limites",
        lambda i: i.update({"bbox": [200, 6, 210, 7]}),
        "Longitude hors limites"
    )

    return tests


# ==========================================
# 4. RECUPERATION DES DONNEES SATELLITAIRES
# ==========================================

def recuperer_donnees(limite, bbox):
    requete = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "limit": limite
    }

    demande = urllib.request.Request(
        API_URL,
        data=json.dumps(requete).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(demande, timeout=45) as reponse:
        resultat = json.loads(reponse.read().decode("utf-8"))

    features = resultat.get("features", [])

    if not isinstance(features, list):
        raise ValueError("La réponse du catalogue est inattendue.")

    return features


# ==========================================
# 5. INTERFACE ASTROPULSE
# ==========================================

st.set_page_config(
    page_title="AstroPulse",
    page_icon="🛰️",
    layout="wide"
)

st.title("AstroPulse")
st.caption("Analyse de la qualité des métadonnées satellitaires")

if PYSTAC_DISPONIBLE:
    st.success("PySTAC détecté : validation officielle disponible.")
else:
    st.warning(
        "PySTAC n'est pas disponible dans cet environnement. "
        "Les contrôles personnalisés restent utilisables."
    )

onglet_analyse, onglet_tests = st.tabs([
    "Analyse satellitaire",
    "Banc de tests"
])


# ==========================================
# 6. BANC DE TESTS
# ==========================================

with onglet_tests:
    st.subheader("Tests du moteur AstroPulse")
    st.write(
        "Chaque test vérifie une anomalie connue dans une fiche "
        "de test. Ces tests évaluent nos contrôles personnalisés."
    )

    if st.button("Exécuter les tests", type="primary"):
        st.session_state["tests"] = executer_tests()

    if "tests" in st.session_state:
        tests = st.session_state["tests"]

        reussis = sum(
            t["Résultat"] == "RÉUSSI" for t in tests
        )
        total = len(tests)

        col1, col2, col3 = st.columns(3)
        col1.metric("Tests réussis", f"{reussis}/{total}")
        col2.metric("Tests échoués", total - reussis)
        col3.metric(
            "Réussite",
            f"{100 * reussis / total:.0f}%" if total else "0%"
        )

        st.dataframe(
            tests,
            width="stretch",
            hide_index=True
        )

        st.download_button(
            "Télécharger les résultats des tests",
            data=json.dumps(tests, indent=2, ensure_ascii=False),
            file_name="astropulse_tests.json",
            mime="application/json"
        )


# ==========================================
# 7. ANALYSE DE DONNEES REELLES
# ==========================================

with onglet_analyse:
    st.write(
        "Analyse des métadonnées provenant du catalogue public "
        "Earth Search."
    )

    with st.sidebar:
        st.header("Paramètres")
        nombre = st.slider("Nombre de fiches", 1, 20, 5)

        bbox_texte = st.text_input(
            "Zone : ouest, sud, est, nord",
            value="2, 6, 3, 7"
        )

    if st.button("Lancer l'analyse", type="primary"):
        try:
            valeurs = [
                float(v.strip()) for v in bbox_texte.split(",")
            ]

            if len(valeurs) != 4:
                st.error("Saisis exactement quatre coordonnées.")
                st.stop()

            ouest, sud, est, nord = valeurs

            if not (-180 <= ouest <= 180 and -180 <= est <= 180):
                st.error("Les longitudes doivent être entre -180 et 180.")
                st.stop()

            if not (-90 <= sud <= 90 and -90 <= nord <= 90):
                st.error("Les latitudes doivent être entre -90 et 90.")
                st.stop()

            if ouest >= est or sud >= nord:
                st.error("Les limites géographiques sont incohérentes.")
                st.stop()

            with st.spinner("Récupération des données satellitaires..."):
                items = recuperer_donnees(nombre, valeurs)

        except ValueError:
            st.error("Coordonnées invalides. Exemple : 2, 6, 3, 7.")
            st.stop()
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError
        ) as erreur:
            st.error(f"Récupération impossible : {erreur}")
            st.stop()

        if not items:
            st.warning("Aucune fiche trouvée pour cette zone.")
        else:
            resultats = []

            with st.spinner("Analyse des métadonnées..."):
                for item in items:
                    alertes = verifier_item(item)
                    erreurs_stac = valider_stac(item)

                    resultats.append({
                        "Identifiant": (
                            item.get("id", "Absent")
                            if isinstance(item, dict)
                            else "Objet invalide"
                        ),
                        "Alertes personnalisées": len(alertes),
                        "Erreurs STAC": len(erreurs_stac),
                        "Résultat": (
                            "À examiner"
                            if alertes or erreurs_stac
                            else "Aucune anomalie détectée"
                        ),
                        "Alertes AstroPulse": "; ".join(alertes) or "Aucune",
                        "Validation STAC": (
                            "; ".join(erreurs_stac) or "Aucune erreur signalée"
                        )
                    })

            total_alertes = sum(
                r["Alertes personnalisées"] for r in resultats
            )
            total_stac = sum(
                r["Erreurs STAC"] for r in resultats
            )
            fiches_a_examiner = sum(
                r["Résultat"] == "À examiner" for r in resultats
            )

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Fiches analysées", len(resultats))
            col2.metric("Alertes AstroPulse", total_alertes)
            col3.metric("Erreurs STAC", total_stac)
            col4.metric("Fiches à examiner", fiches_a_examiner)

            st.dataframe(
                resultats,
                width="stretch",
                hide_index=True
            )

            rapport = {
                "outil": "AstroPulse",
                "version": "0.8",
                "date_utc": datetime.now(timezone.utc).isoformat(),
                "source": API_URL,
                "fiches_analysees": len(resultats),
                "alertes_personnalisees": total_alertes,
                "erreurs_stac": total_stac,
                "resultats": resultats,
                "limite": (
                    "Les contrôles personnalisés ne remplacent pas "
                    "une validation complète de toutes les extensions STAC. "
                    "Une absence d'erreur ne garantit pas l'exactitude "
                    "scientifique des données."
                )
            }

            st.download_button(
                "Télécharger le rapport JSON",
                data=json.dumps(
                    rapport, indent=2, ensure_ascii=False
                ),
                file_name="astropulse_rapport.json",
                mime="application/json"
            )

            st.info(
                "Une absence d'alerte ne prouve pas que la fiche "
                "est entièrement correcte."
            )