"""Build the Argos installation and user guide PDF.

The PDF is intentionally generated from repository assets so screenshots and
operational instructions can be refreshed alongside the application.

Run from the repository root with::

    uv run --with reportlab scripts/build_user_guide.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets" / "guide"
OUTPUT = ROOT / "output" / "pdf" / "Guide_Argos_installation_utilisation_v1.2.pdf"

PAGE_W, PAGE_H = A4
MARGIN_X = 17 * mm
MARGIN_TOP = 17 * mm
MARGIN_BOTTOM = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_X

NAVY = colors.HexColor("#13263D")
BLUE = colors.HexColor("#2375B9")
PALE_BLUE = colors.HexColor("#EAF4FC")
CYAN = colors.HexColor("#4DA7D9")
INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#D8E2EC")
SOFT = colors.HexColor("#F5F8FB")
GREEN = colors.HexColor("#138A62")
PALE_GREEN = colors.HexColor("#EAF8F2")
AMBER = colors.HexColor("#B56A00")
PALE_AMBER = colors.HexColor("#FFF5DF")
RED = colors.HexColor("#B42318")
PALE_RED = colors.HexColor("#FFF0EE")
WHITE = colors.white


def register_fonts() -> None:
    base = Path("/System/Library/Fonts/Supplemental")
    choices = {
        "ArgosSans": base / "Arial.ttf",
        "ArgosSans-Bold": base / "Arial Bold.ttf",
        "ArgosSans-Italic": base / "Arial Italic.ttf",
    }
    for name, path in choices.items():
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
        else:
            fallback = {
                "ArgosSans": "Helvetica",
                "ArgosSans-Bold": "Helvetica-Bold",
                "ArgosSans-Italic": "Helvetica-Oblique",
            }[name]
            pdfmetrics.registerFont(pdfmetrics.Font(name, fallback, "WinAnsiEncoding"))


register_fonts()

styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="CoverKicker",
        fontName="ArgosSans-Bold",
        fontSize=10,
        leading=13,
        textColor=CYAN,
        spaceAfter=5 * mm,
        uppercase=True,
    )
)
styles.add(
    ParagraphStyle(
        name="CoverTitle",
        fontName="ArgosSans-Bold",
        fontSize=31,
        leading=34,
        textColor=WHITE,
        spaceAfter=5 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="CoverSubtitle",
        fontName="ArgosSans",
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#DDEBFA"),
        spaceAfter=6 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="PageTitle",
        fontName="ArgosSans-Bold",
        fontSize=22,
        leading=27,
        textColor=NAVY,
        spaceAfter=3 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="Lead",
        fontName="ArgosSans",
        fontSize=11,
        leading=16,
        textColor=MUTED,
        spaceAfter=5 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="H2x",
        fontName="ArgosSans-Bold",
        fontSize=14,
        leading=18,
        textColor=NAVY,
        spaceBefore=3 * mm,
        spaceAfter=2 * mm,
        keepWithNext=True,
    )
)
styles.add(
    ParagraphStyle(
        name="H3x",
        fontName="ArgosSans-Bold",
        fontSize=10.5,
        leading=14,
        textColor=BLUE,
        spaceBefore=2 * mm,
        spaceAfter=1.5 * mm,
        keepWithNext=True,
    )
)
styles.add(
    ParagraphStyle(
        name="Bodyx",
        fontName="ArgosSans",
        fontSize=9.6,
        leading=14,
        textColor=INK,
        spaceAfter=2.5 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="Smallx",
        fontName="ArgosSans",
        fontSize=8.2,
        leading=11.5,
        textColor=MUTED,
    )
)
styles.add(
    ParagraphStyle(
        name="CardTitle",
        fontName="ArgosSans-Bold",
        fontSize=10,
        leading=13,
        textColor=NAVY,
        spaceAfter=1.5 * mm,
    )
)
styles.add(
    ParagraphStyle(
        name="CardBody",
        fontName="ArgosSans",
        fontSize=8.8,
        leading=12.2,
        textColor=INK,
    )
)
styles.add(
    ParagraphStyle(
        name="GuideCode",
        fontName="Courier",
        fontSize=7.7,
        leading=10.4,
        textColor=colors.HexColor("#DDEBFA"),
    )
)
styles.add(
    ParagraphStyle(
        name="Caption",
        fontName="ArgosSans-Italic",
        fontSize=7.7,
        leading=10,
        textColor=MUTED,
        alignment=TA_CENTER,
    )
)


def safe(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def bullets(items: list[str], *, level: int = 0) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, styles["Bodyx"]), leftIndent=3 * mm) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=(5 + level * 3) * mm,
        bulletFontName="ArgosSans",
        bulletFontSize=6,
        bulletColor=BLUE,
        spaceAfter=2 * mm,
    )


def steps(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, styles["Bodyx"]), leftIndent=4 * mm) for item in items],
        bulletType="1",
        leftIndent=7 * mm,
        bulletFontName="ArgosSans-Bold",
        bulletFontSize=9,
        bulletColor=BLUE,
        spaceAfter=2 * mm,
    )


def callout(title: str, body: str, *, tone: str = "blue") -> Table:
    palette = {
        "blue": (PALE_BLUE, BLUE),
        "green": (PALE_GREEN, GREEN),
        "amber": (PALE_AMBER, AMBER),
        "red": (PALE_RED, RED),
    }
    background, accent = palette[tone]
    content = [
        Paragraph(title, ParagraphStyle("tmp-title", parent=styles["CardTitle"], textColor=accent)),
        Paragraph(body, styles["CardBody"]),
    ]
    table = Table([[content]], colWidths=[CONTENT_W])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.Color(accent.red, accent.green, accent.blue, alpha=0.35)),
                ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
            ]
        )
    )
    return table


def code_block(code: str) -> Table:
    table = Table([[Paragraph(safe(code), styles["GuideCode"])]], colWidths=[CONTENT_W])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("BOX", (0, 0), (-1, -1), 0.5, BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
            ]
        )
    )
    return table


def screenshot(filename: str, caption: str, *, max_h: float = 145 * mm) -> Table:
    path = ASSETS / filename
    if not path.exists():
        raise FileNotFoundError(f"Capture absente: {path}")
    image = Image(str(path))
    ratio = min(CONTENT_W / image.imageWidth, max_h / image.imageHeight)
    image.drawWidth = image.imageWidth * ratio
    image.drawHeight = image.imageHeight * ratio
    frame = Table(
        [[image], [Paragraph(caption, styles["Caption"])]],
        colWidths=[image.drawWidth],
        hAlign="CENTER",
    )
    frame.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, 0), 0.7, LINE),
                ("BACKGROUND", (0, 1), (-1, 1), SOFT),
                ("LEFTPADDING", (0, 0), (-1, -1), 1.8 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1.8 * mm),
                ("TOPPADDING", (0, 0), (-1, 0), 1.8 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 1.8 * mm),
                ("TOPPADDING", (0, 1), (-1, 1), 1.6 * mm),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 1.6 * mm),
            ]
        )
    )
    return frame


def cards(rows: list[tuple[str, str]], *, columns: int = 2) -> Table:
    cells = []
    for title, body in rows:
        cells.append([Paragraph(title, styles["CardTitle"]), Paragraph(body, styles["CardBody"])])
    matrix = [cells[i : i + columns] for i in range(0, len(cells), columns)]
    if len(matrix[-1]) < columns:
        matrix[-1].append("")
    table = Table(matrix, colWidths=[CONTENT_W / columns - 2 * mm] * columns, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 2 * mm, WHITE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.5 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5 * mm),
            ]
        )
    )
    return table


def page_title(title: str, lead: str) -> list:
    return [Paragraph(title, styles["PageTitle"]), Paragraph(lead, styles["Lead"])]


def draw_page(canvas, doc) -> None:
    canvas.saveState()
    if doc.page == 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canvas.setFillColor(BLUE)
        canvas.rect(0, 0, PAGE_W, 12 * mm, stroke=0, fill=1)
        canvas.setFillColor(CYAN)
        canvas.circle(PAGE_W - 19 * mm, PAGE_H - 20 * mm, 25 * mm, stroke=0, fill=1)
        canvas.setFillColor(NAVY)
        canvas.circle(PAGE_W - 18 * mm, PAGE_H - 19 * mm, 18 * mm, stroke=0, fill=1)
    else:
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_X, PAGE_H - 11 * mm, PAGE_W - MARGIN_X, PAGE_H - 11 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("ArgosSans", 7.5)
        canvas.drawString(MARGIN_X, PAGE_H - 8.3 * mm, "ARGOS - GUIDE UTILISATEUR")
        canvas.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 8.3 * mm, "Version 1.2.0 - Juillet 2026")
        canvas.setStrokeColor(LINE)
        canvas.line(MARGIN_X, 10 * mm, PAGE_W - MARGIN_X, 10 * mm)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN_X, 6.5 * mm, "Document interne - configuration locale")
        canvas.drawRightString(PAGE_W - MARGIN_X, 6.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_story() -> list:
    story: list = []

    # 1 - Couverture
    story += [
        Spacer(1, 26 * mm),
        Paragraph("VEILLE D'APPELS D'OFFRES", styles["CoverKicker"]),
        Paragraph("Argos", styles["CoverTitle"]),
        Paragraph("Guide d'installation et d'utilisation", styles["CoverTitle"]),
        Paragraph(
            "Version 1.2.0 - Edition mise à jour en juillet 2026<br/>"
            "BOAMP, EDF Portail fournisseurs et TED/JOUE",
            styles["CoverSubtitle"],
        ),
        Spacer(1, 4 * mm),
        screenshot(
            "01-accueil-argos.png",
            "Accueil de la version actuelle d'Argos",
            max_h=103 * mm,
        ),
        Spacer(1, 7 * mm),
        Paragraph(
            "Recherche multi-source  •  Filtrage IA  •  Historique local  •  Prompts réutilisables",
            ParagraphStyle(
                "cover-bottom",
                parent=styles["Bodyx"],
                textColor=colors.HexColor("#DDEBFA"),
                fontSize=9.3,
                alignment=TA_CENTER,
            ),
        ),
        PageBreak(),
    ]

    # 2 - Repères
    story += page_title(
        "Bien démarrer",
        "Ce guide couvre l'installation locale, la recherche d'appels d'offres, la bibliothèque de prompts et les comportements spécifiques à EDF.",
    )
    story += [
        Paragraph("Parcours express", styles["H2x"]),
        cards(
            [
                ("1. Installer", "Installer <b>uv</b>, synchroniser les dépendances puis préparer le fichier <b>.env</b>."),
                ("2. Lancer", "Démarrer l'interface avec <b>uv run backend/ui_app.py</b> et ouvrir l'adresse affichée."),
                ("3. Rechercher", "Décrire le besoin, choisir la période et les sources, puis ajuster les mots-clés proposés."),
                ("4. Exploiter", "Consulter les AO pertinents, les erreurs éventuelles et réutiliser les prompts sauvegardés."),
            ]
        ),
        Spacer(1, 4 * mm),
        Paragraph("Sommaire", styles["H2x"]),
        cards(
            [
                ("Pages 3-4", "Installation, configuration et lancement."),
                ("Pages 5-7", "Première recherche, résultats et erreurs non bloquantes."),
                ("Pages 8-9", "Tutoriel complet des prompts sauvegardés."),
                ("Pages 10-12", "EDF/CAPTCHA, données locales, dépannage et bonnes pratiques."),
            ]
        ),
        Spacer(1, 5 * mm),
        callout(
            "Principe à retenir",
            "Chaque source est indépendante. Si BOAMP, EDF ou TED rencontre une erreur, Argos poursuit avec les autres sources et affiche l'incident dans le détail de la recherche.",
            tone="green",
        ),
        Spacer(1, 4 * mm),
        Paragraph("Prérequis", styles["H2x"]),
        bullets(
            [
                "Python 3.13 ou une installation <b>uv</b> capable de fournir la version attendue.",
                "Accès au dépôt Argos et aux services réseau nécessaires (Azure OpenAI, BOAMP, TED et, si autorisé, EDF).",
                "Une clé et un déploiement Azure OpenAI valides.",
                "Les paramètres proxy de l'environnement Framatome/Fra lorsque le réseau les impose.",
            ]
        ),
        PageBreak(),
    ]

    # 3 - Installation
    story += page_title(
        "Installer Argos",
        "Les commandes suivantes sont à exécuter depuis un terminal. Sur Windows, PowerShell est recommandé.",
    )
    story += [
        Paragraph("1. Installer uv", styles["H2x"]),
        Paragraph("Windows (PowerShell)", styles["H3x"]),
        code_block("irm https://astral.sh/uv/install.ps1 | iex"),
        Spacer(1, 3 * mm),
        Paragraph("macOS / Linux", styles["H3x"]),
        code_block("curl -LsSf https://astral.sh/uv/install.sh | sh"),
        Spacer(1, 4 * mm),
        Paragraph("2. Récupérer le projet et installer les dépendances", styles["H2x"]),
        code_block("git clone <URL_DU_DEPOT>\ncd Argos\nuv sync"),
        Spacer(1, 4 * mm),
        callout(
            "En environnement corporate",
            "Le dépôt contient une configuration de dépendances adaptée au Nexus interne. Respecter les instructions de votre équipe pour le VPN, les certificats et le proxy Fra. Ne jamais désactiver la vérification TLS pour contourner un certificat manquant.",
            tone="blue",
        ),
        Spacer(1, 4 * mm),
        Paragraph("3. Créer le fichier .env", styles["H2x"]),
        Paragraph(
            "Copier <b>.env.example</b> vers <b>.env</b>, puis renseigner au minimum les variables Azure. Le fichier <b>.env</b> contient des secrets et ne doit jamais être versionné.",
            styles["Bodyx"],
        ),
        code_block(
            "AZURE_API_KEY=...\n"
            "AZURE_ENDPOINT=https://<ressource>.openai.azure.com\n"
            "DEPLOYMENT=<nom_du_deploiement>\n"
            "API_VERSION=2024-10-21\n"
            "ARGOS_EDF_CAPTCHA_MODE=fail"
        ),
        Spacer(1, 4 * mm),
        callout(
            "Configuration sûre par défaut",
            "Le mode EDF <b>fail</b> ne tente pas de résoudre ni de contourner un CAPTCHA. Si EDF exige un contrôle, la source est signalée indisponible pour cette exécution et la recherche continue.",
            tone="amber",
        ),
        PageBreak(),
    ]

    # 4 - Lancement et accueil
    story += page_title(
        "Lancer l'interface",
        "Depuis la racine du dépôt, démarrez NiceGUI. L'adresse locale est affichée dans le terminal, le plus souvent http://127.0.0.1:8080.",
    )
    story += [
        code_block("uv run backend/ui_app.py"),
        Spacer(1, 4 * mm),
        screenshot(
            "01-accueil-argos.png",
            "Accueil : formulaire de recherche, choix des sources, historique et panneau de détail.",
            max_h=157 * mm,
        ),
        Spacer(1, 4 * mm),
        cards(
            [
                ("Nouvelle recherche", "Le grand champ reçoit le besoin métier en langage naturel."),
                ("Période", "Les dates de publication bornent les résultats demandés aux sources."),
                ("Sources", "BOAMP, EDF et TED peuvent être activées ou désactivées séparément."),
                ("Historique", "Chaque exécution est stockée localement avec son statut et ses résultats."),
            ]
        ),
        PageBreak(),
    ]

    # 5 - Première recherche
    story += page_title(
        "Effectuer une première recherche",
        "Un prompt précis améliore à la fois la génération des mots-clés et le tri de pertinence des résultats.",
    )
    story += [
        Paragraph("Procédure", styles["H2x"]),
        steps(
            [
                "Décrire le besoin dans le champ principal : métier, prestations visées, zone et exclusions utiles.",
                "Choisir la date minimale et la date maximale de publication. Le raccourci <b>7 derniers jours</b> rétablit la période récente.",
                "Cocher une ou plusieurs sources : <b>BOAMP</b>, <b>EDF - Portail fournisseurs</b> et/ou <b>TED (JOUE)</b>.",
                "Cliquer sur <b>Rechercher</b>. Argos crée la recherche et ouvre l'assistant de mots-clés.",
                "Supprimer les groupes inutiles, ajouter des groupes si nécessaire, puis cliquer sur <b>Valider et lancer</b>.",
                "Laisser la recherche se terminer. Le statut et les compteurs se mettent à jour automatiquement.",
            ]
        ),
        Spacer(1, 4 * mm),
        Paragraph("Comment écrire un bon prompt", styles["H2x"]),
        code_block(
            "Contexte : bureau d'etudes specialise en maintenance industrielle.\n"
            "Recherche : prestations d'analyse vibratoire et maintenance predictive.\n"
            "Priorites : diagnostic, capteurs, traitement du signal, campagne d'essais.\n"
            "Exclusions : fourniture seule de materiel et travaux electriques lourds.\n"
            "Zone : France metropolitaine."
        ),
        Spacer(1, 4 * mm),
        callout(
            "Groupes de mots-clés",
            "Chaque groupe représente une combinaison de recherche. Pour ajouter plusieurs groupes, séparez-les par un point-virgule, par exemple : <b>moteur électrique, vibration ; analyse numérique, jumeau numérique</b>.",
            tone="blue",
        ),
        Spacer(1, 4 * mm),
        cards(
            [
                ("Trop peu de résultats", "Élargir la période, retirer une exclusion ou employer des synonymes plus généraux."),
                ("Trop de bruit", "Ajouter la prestation attendue, les technologies, le secteur ou des exclusions explicites."),
            ]
        ),
        PageBreak(),
    ]

    # 6 - Recherche non bloquante
    story += page_title(
        "Comprendre l'exécution multi-source",
        "Argos isole les collecteurs : l'échec d'une source n'annule ni les résultats déjà collectés ni le traitement des sources suivantes.",
    )
    story += [
        cards(
            [
                ("BOAMP", "Marchés publics français. Recherche paginée et filtrée sur la période choisie."),
                ("EDF", "Avis publics du portail fournisseurs EDF, sous réserve de la politique d'accès et d'une éventuelle session autorisée."),
                ("TED / JOUE", "Avis européens. Recherche paginée sur les publications du Journal officiel de l'Union européenne."),
                ("Tri IA", "Les annonces collectées sont comparées au besoin initial puis classées comme pertinentes ou non pertinentes."),
            ]
        ),
        Spacer(1, 5 * mm),
        Paragraph("En cas d'erreur", styles["H2x"]),
        steps(
            [
                "La source en erreur est arrêtée proprement pour la recherche en cours.",
                "Le message technique utile est enregistré avec la recherche.",
                "Les autres sources continuent normalement.",
                "Le détail de la recherche affiche une alerte rouge pour identifier la source concernée.",
            ]
        ),
        Spacer(1, 4 * mm),
        callout(
            "Ce que signifie une alerte source",
            "Une alerte ne signifie pas que toute la recherche a échoué. Vérifiez les cartes de résultats et les compteurs : les AO provenant des autres sources restent disponibles.",
            tone="green",
        ),
        Spacer(1, 5 * mm),
        Paragraph("Statuts principaux", styles["H2x"]),
        cards(
            [
                ("En cours", "Génération, collecte ou tri encore actif."),
                ("Terminé", "Le traitement est fini, avec ou sans alerte partielle de source."),
                ("Erreur", "Le traitement global n'a pas pu produire un résultat exploitable."),
                ("Compteurs", "<b>Trouvés</b> mesure la collecte ; <b>insérés</b> correspond aux AO enregistrés après dédoublonnage."),
            ]
        ),
        PageBreak(),
    ]

    # 7 - Résultats
    story += page_title(
        "Lire et exploiter les résultats",
        "Ouvrez une recherche depuis l'historique pour retrouver son prompt, ses paramètres, ses alertes et les appels d'offres associés.",
    )
    story += [
        screenshot(
            "03-detail-recherche.png",
            "Détail d'une recherche : paramètres, alerte EDF non bloquante et cartes d'appels d'offres.",
            max_h=161 * mm,
        ),
        Spacer(1, 4 * mm),
        cards(
            [
                ("Score", "Indique la proximité estimée entre l'annonce et le besoin initial."),
                ("Détails", "Ouvre les informations disponibles et le lien vers la publication source."),
                ("Tri", "La flèche permet d'inverser l'ordre des scores dans la vue pertinente."),
                ("Non pertinents", "Le menu à trois points donne accès aux AO écartés par le filtre IA."),
            ]
        ),
        PageBreak(),
    ]

    # 8 - Prompts sauvegardés
    story += page_title(
        "Prompts sauvegardés : créer et relancer",
        "La bibliothèque locale évite de ressaisir les recherches récurrentes. Elle est accessible par l'icône marque-page à droite du bouton Rechercher.",
    )
    story += [
        screenshot(
            "02-prompts-sauvegardes.png",
            "Bibliothèque : formulaire à gauche, prompts sauvegardés et actions à droite.",
            max_h=105 * mm,
        ),
        Spacer(1, 4 * mm),
        Paragraph("Sauvegarder un nouveau prompt", styles["H2x"]),
        steps(
            [
                "Facultatif : rédiger d'abord le prompt sur l'accueil. Il est automatiquement prérempli à l'ouverture de la bibliothèque.",
                "Cliquer sur l'icône <b>marque-page</b>.",
                "Saisir ou ajuster le texte dans la zone <b>Prompt</b>.",
                "Cliquer sur <b>Sauvegarder</b>. Un doublon exact n'est pas ajouté une seconde fois.",
            ]
        ),
        Paragraph("Relancer un prompt", styles["H2x"]),
        steps(
            [
                "Ouvrir la bibliothèque.",
                "Cliquer directement sur la grande carte du prompt souhaité, pas sur l'icône crayon.",
                "La fenêtre se ferme et l'assistant de mots-clés démarre avec ce prompt. Vérifier ensuite la période et les sources utilisées par l'écran courant avant validation.",
            ]
        ),
        callout(
            "Stockage local",
            "Les prompts sont enregistrés dans la même base SQLite locale qu'Argos. Ils ne sont pas envoyés à un service de synchronisation externe par la bibliothèque.",
            tone="blue",
        ),
        PageBreak(),
    ]

    # 9 - Edition prompts
    story += page_title(
        "Prompts sauvegardés : modifier et supprimer",
        "Chaque ligne propose un crayon pour modifier et une corbeille pour supprimer. La carte elle-même sert à lancer la recherche.",
    )
    story += [
        screenshot(
            "04-modifier-prompt.png",
            "Mode modification : le prompt sélectionné est chargé dans le formulaire de gauche.",
            max_h=105 * mm,
        ),
        Spacer(1, 4 * mm),
        Paragraph("Modifier", styles["H2x"]),
        steps(
            [
                "Cliquer sur le <b>crayon</b> du prompt à corriger.",
                "Modifier le texte dans le formulaire de gauche.",
                "Cliquer sur <b>Enregistrer</b>. La date de mise à jour est rafraîchie.",
                "Cliquer sur <b>Annuler</b> pour quitter le mode modification sans enregistrer.",
            ]
        ),
        Paragraph("Supprimer", styles["H2x"]),
        steps(
            [
                "Cliquer sur la <b>corbeille</b> du prompt concerné.",
                "Lire l'aperçu dans la fenêtre de confirmation.",
                "Cliquer sur <b>Supprimer</b>. Cette action retire le prompt de la bibliothèque locale mais ne supprime pas les recherches historiques déjà effectuées.",
            ]
        ),
        callout(
            "Organisation conseillée",
            "Conserver un prompt par besoin récurrent et mettre les variables changeantes (zone, technologie, exclusions) directement dans le texte. Des formulations distinctes sont plus faciles à relire qu'un prompt générique trop long.",
            tone="green",
        ),
        PageBreak(),
    ]

    # 10 - EDF / CAPTCHA
    story += page_title(
        "EDF : accès, CAPTCHA et autorisation",
        "Argos ne résout pas automatiquement un CAPTCHA et n'essaie pas de le contourner. La configuration par défaut privilégie la conformité et la continuité des autres sources.",
    )
    story += [
        callout(
            "Mode par défaut recommandé",
            "Avec <b>ARGOS_EDF_CAPTCHA_MODE=fail</b>, si EDF présente un CAPTCHA, la collecte EDF s'arrête, une alerte est enregistrée et BOAMP/TED continuent.",
            tone="green",
        ),
        Spacer(1, 4 * mm),
        Paragraph("Session prévalidée, uniquement après accord EDF", styles["H2x"]),
        Paragraph(
            "Si un administrateur EDF fournit une autorisation explicite et une session officiellement validée, Argos peut réutiliser le cookie de cette session. Ce mode ne casse pas le CAPTCHA : il réemploie une preuve de session légitime et temporaire.",
            styles["Bodyx"],
        ),
        code_block(
            "ARGOS_EDF_CAPTCHA_MODE=prevalidated_session\n"
            "ARGOS_EDF_SCRAPING_AUTHORIZED=true\n"
            "ARGOS_EDF_AUTHORIZED_SESSION_COOKIE=ASP.NET_SessionId=...; autre_cookie=..."
        ),
        Spacer(1, 4 * mm),
        callout(
            "Trois garde-fous obligatoires",
            "Le mode, l'autorisation booléenne et le cookie doivent être présents ensemble. Sans ces trois éléments, EDF reste désactivé. Le cookie est un secret : uniquement dans <b>.env</b>, jamais dans Git, les logs, une capture ou un ticket.",
            tone="amber",
        ),
        Spacer(1, 4 * mm),
        Paragraph("Politique robots.txt", styles["H2x"]),
        Paragraph(
            "Le portail EDF peut publier une politique interdisant la collecte automatisée. Argos respecte cette politique par défaut. La variable d'autorisation ne doit être activée qu'après validation explicite, documentée et toujours en vigueur de l'administrateur EDF compétent.",
            styles["Bodyx"],
        ),
        Paragraph("Renouvellement et diagnostic", styles["H2x"]),
        bullets(
            [
                "Une session expirée provoque une nouvelle alerte EDF sans bloquer les autres sources.",
                "Demander un nouveau cookie officiel ; ne pas automatiser la résolution du CAPTCHA.",
                "Limiter la diffusion de la session et la supprimer dès qu'elle n'est plus nécessaire.",
                "Conserver la configuration proxy Fra habituelle : le mode EDF n'autorise aucun contournement réseau.",
            ]
        ),
        PageBreak(),
    ]

    # 11 - Données et maintenance
    story += page_title(
        "Historique, données locales et mises à jour",
        "Argos conserve les recherches, les résultats et les prompts dans une base SQLite locale. Sauvegardez-la avant une opération de maintenance importante.",
    )
    story += [
        Paragraph("Historique", styles["H2x"]),
        bullets(
            [
                "Cliquer sur une ligne pour afficher le détail dans le panneau de droite ou ouvrir la page dédiée.",
                "Cocher plusieurs recherches puis utiliser <b>Supprimer</b> pour un nettoyage groupé.",
                "La suppression d'une recherche retire ses données associées de la base locale.",
                "Le bouton d'actualisation permet de relire l'état courant si une exécution vient de se terminer.",
            ]
        ),
        Paragraph("Emplacement de la base", styles["H2x"]),
        Paragraph(
            "Par défaut, Argos utilise sa base locale prévue par l'application. Pour une instance de test ou un emplacement maîtrisé, définir <b>ARGOS_DB_PATH</b> dans <b>.env</b>.",
            styles["Bodyx"],
        ),
        code_block("ARGOS_DB_PATH=/chemin/vers/argos.db"),
        Spacer(1, 4 * mm),
        callout(
            "Sauvegarde",
            "Arrêter Argos avant de copier la base. Conserver la copie dans un emplacement protégé : elle peut contenir des prompts métiers et des informations issues d'appels d'offres.",
            tone="blue",
        ),
        Spacer(1, 5 * mm),
        Paragraph("Mettre à jour le dépôt", styles["H2x"]),
        code_block("git pull\nuv sync\nuv run backend/ui_app.py"),
        Spacer(1, 4 * mm),
        Paragraph("Distribution Windows", styles["H2x"]),
        Paragraph(
            "Si vous utilisez l'exécutable packagé, suivez <b>RELEASE_WINDOWS.md</b> pour construire une version. La version affichée en haut de l'interface doit correspondre au package installé.",
            styles["Bodyx"],
        ),
        PageBreak(),
    ]

    # 12 - Dépannage
    story += page_title(
        "Dépannage et checklist",
        "Commencez par relire l'alerte affichée dans le détail. Elle distingue un problème global d'une source simplement indisponible.",
    )
    story += [
        cards(
            [
                ("L'interface ne démarre pas", "Exécuter <b>uv sync</b>, puis relancer via <b>uv run backend/ui_app.py</b>. Vérifier que le port n'est pas déjà occupé."),
                ("Erreur Azure", "Contrôler <b>AZURE_API_KEY</b>, <b>AZURE_ENDPOINT</b>, <b>DEPLOYMENT</b>, <b>API_VERSION</b> et le proxy."),
                ("Timeout IA", "Augmenter <b>AZURE_READ_TIMEOUT_S</b> ou réduire <b>PROMPT_GEN_MAX_TOKENS</b>."),
                ("Aucun résultat", "Élargir la période, simplifier les groupes de mots-clés et retirer les exclusions trop strictes."),
                ("Alerte EDF CAPTCHA", "Conserver le mode <b>fail</b>, ou renouveler la session uniquement via l'administrateur EDF autorisé."),
                ("Erreur d'une seule source", "Consulter les résultats des autres sources ; la recherche a pu se terminer correctement."),
            ]
        ),
        Spacer(1, 5 * mm),
        Paragraph("Checklist avant une recherche", styles["H2x"]),
        bullets(
            [
                "Le besoin décrit une prestation, un contexte, des priorités et des exclusions.",
                "La période de publication correspond à la veille souhaitée.",
                "Les sources pertinentes sont cochées.",
                "Les mots-clés générés ont été relus avant <b>Valider et lancer</b>.",
                "Après traitement, les alertes et les AO non pertinents ont été contrôlés.",
            ]
        ),
        Spacer(1, 4 * mm),
        Paragraph("Commandes de vérification", styles["H2x"]),
        code_block(
            "uv run python -m compileall backend\n"
            "uv run pytest\n"
            "uv run backend/ui_app.py"
        ),
        Spacer(1, 5 * mm),
        callout(
            "Support efficace",
            "Pour signaler un problème, joindre la version Argos, l'heure de la recherche, la source concernée et le message d'erreur. Retirer systématiquement les clés API, cookies, URLs sensibles et données confidentielles.",
            tone="green",
        ),
        Spacer(1, 8 * mm),
        HRFlowable(width="100%", thickness=0.7, color=LINE),
        Spacer(1, 5 * mm),
        Paragraph(
            "Argos 1.2.0 - Guide d'installation et d'utilisation - Edition juillet 2026",
            ParagraphStyle("end", parent=styles["Smallx"], alignment=TA_CENTER),
        ),
    ]

    return story


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=MARGIN_X,
        leftMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title="Guide Argos - Installation et utilisation",
        author="Equipe Argos",
        subject="Installation, recherche multi-source et gestion des prompts sauvegardés",
    )
    document.build(build_story(), onFirstPage=draw_page, onLaterPages=draw_page)
    print(f"Guide généré : {OUTPUT}")


if __name__ == "__main__":
    main()
