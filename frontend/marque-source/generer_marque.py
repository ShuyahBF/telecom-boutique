# Préparation des fichiers de la marque adLyn à partir des images fournies :
# détourage (fond blanc -> transparent), version claire pour fonds sombres,
# icônes aux tailles standard (favicon, iPhone, Android) et image de partage.
from PIL import Image
import numpy as np

SORTIE = "../public"  # script à lancer depuis frontend/marque-source
FOND = 254.0  # couleur du fond des images fournies (quasi blanc)

def detourer(im):
    """Fond blanc -> transparent (« color to alpha ») en gardant des bords lissés."""
    a = np.asarray(im.convert("RGB")).astype(float)
    mini = a.min(axis=2)
    alpha = np.clip((FOND - mini) / FOND, 0, 1)
    alpha = np.where(alpha < 0.06, 0, np.clip((alpha - 0.06) / 0.94 * 1.08, 0, 1))  # supprime le grain du fond
    sure = np.where(alpha > 0, alpha, 1)[..., None]
    rgb = np.clip((a - (1 - sure) * FOND) / sure, 0, 255)  # couleur « dé-mélangée » du blanc
    out = np.dstack([rgb, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")

def version_claire(im):
    """Bleu nuit du logo -> blanc (pour les bandeaux sombres) ; le bleu reste bleu."""
    a = np.asarray(im).astype(float)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    sombre = (b - r < 60) & (r + g + b < 300)  # pixels bleu nuit / gris foncé (pas le bleu vif)
    a[..., :3][sombre] = 255
    return Image.fromarray(a.astype(np.uint8), "RGBA")

def rogner(im, marge=0):
    boite = im.getbbox()
    im = im.crop(boite)
    if marge:
        fond = Image.new("RGBA", (im.width + 2 * marge, im.height + 2 * marge), (0, 0, 0, 0))
        fond.paste(im, (marge, marge)); im = fond
    return im

def carre(im, marge_ratio=0.08, fond=(0, 0, 0, 0)):
    cote = int(max(im.size) * (1 + 2 * marge_ratio))
    c = Image.new("RGBA", (cote, cote), fond)
    c.alpha_composite(im, ((cote - im.width) // 2, (cote - im.height) // 2))
    return c

logo_src = Image.open("logo-adlyn-original.webp").convert("RGB")
icone_src = Image.open("icone-adlyn-original.webp").convert("RGB")

# --- Logo horizontal (pictogramme + « adLyn »), sans slogan ---
logo = rogner(detourer(logo_src.crop((215, 330, 1790, 765))))
logo = logo.resize((900, round(900 * logo.height / logo.width)), Image.LANCZOS)
logo.save(f"{SORTIE}/marque/logo-adlyn.png", optimize=True)
version_claire(logo).save(f"{SORTIE}/marque/logo-adlyn-clair.png", optimize=True)

# --- Icône (téléphone + engrenage + anneau), sans le texte ---
ico = rogner(detourer(icone_src.crop((500, 250, 1570, 1260))))
ico_carre = carre(ico, 0.04)
ico_carre.resize((512, 512), Image.LANCZOS).save(f"{SORTIE}/marque/icone-adlyn.png", optimize=True)
version_claire(ico_carre).resize((512, 512), Image.LANCZOS).save(f"{SORTIE}/marque/icone-adlyn-clair.png", optimize=True)

# Favicon (onglet du navigateur) : 16, 32, 48 px dans un .ico + PNG 32/192/512
ico_carre.resize((256, 256), Image.LANCZOS).save(f"{SORTIE}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
ico_carre.resize((32, 32), Image.LANCZOS).save(f"{SORTIE}/favicon-32.png", optimize=True)
# Icônes d'écran d'accueil : fond blanc (iOS n'accepte pas la transparence)
blanc = carre(ico, 0.16, (255, 255, 255, 255))
blanc.resize((180, 180), Image.LANCZOS).convert("RGB").save(f"{SORTIE}/apple-touch-icon.png", optimize=True)
for t in (192, 512):
    blanc.resize((t, t), Image.LANCZOS).convert("RGB").save(f"{SORTIE}/icon-{t}.png", optimize=True)

# --- Image de partage (WhatsApp, Facebook…) 1200 x 630 : logo + slogan sur fond blanc ---
complet = rogner(detourer(logo_src.crop((215, 330, 1800, 870))))
og = Image.new("RGBA", (1200, 630), (255, 255, 255, 255))
l = complet.resize((1000, round(1000 * complet.height / complet.width)), Image.LANCZOS)
og.alpha_composite(l, ((1200 - l.width) // 2, (630 - l.height) // 2))
og.convert("RGB").save(f"{SORTIE}/og-adlyn.png", optimize=True)
print("logo", logo.size, "icône", ico_carre.size, "partage", og.size)
