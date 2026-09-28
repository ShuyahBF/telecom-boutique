"""
Pages du portail public (accessibles sans connexion).
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from catalogue.models import Categorie, Marque, Produit
from core.utils import normaliser_telephone
from maintenance.models import DossierMaintenance
from messagerie.models import Conversation, Message
from messagerie.services import notifier
from tiers.models import Client
from ventes.models import Commande, LigneCommande

from .forms import CommandeForm, ConseilForm, ReponseForm, SuiviCommandeForm, SuiviMaintenanceForm
from .panier import Panier


def _produits_visibles():
    """Produits affichables sur le site public (actifs et marqués visibles)."""
    return Produit.objects.filter(actif=True, visible_portail=True).select_related("categorie", "marque")


def _client_par_telephone(nom, telephone, email="") -> Client:
    """Retrouve le client par son téléphone, ou le crée s'il est nouveau."""
    client = Client.objects.filter(telephone=telephone).first()
    if client is None:
        client = Client.objects.create(nom=nom, telephone=telephone, email=email)
    elif email and not client.email:
        client.email = email  # on complète la fiche sans écraser les données existantes
        client.save(update_fields=["email"])
    return client


# ----------------------------------------------------------------------
#  Vitrine
# ----------------------------------------------------------------------
def accueil(request):
    return render(request, "portail/accueil.html", {
        "nouveautes": _produits_visibles().order_by("-date_creation")[:8],
        "categories": Categorie.objects.all(),
    })


def catalogue(request):
    """Liste des produits avec recherche, filtres et pagination (12 par page)."""
    produits = _produits_visibles()
    q = request.GET.get("q", "").strip()
    categorie = request.GET.get("categorie", "")
    marque = request.GET.get("marque", "")
    tri = request.GET.get("tri", "recent")

    if q:
        produits = produits.filter(Q(nom__icontains=q) | Q(description__icontains=q) | Q(reference__icontains=q))
    if categorie:
        produits = produits.filter(categorie__slug=categorie)
    if marque:
        produits = produits.filter(marque_id=marque)
    produits = produits.order_by({
        "prix_asc": "prix_vente", "prix_desc": "-prix_vente", "nom": "nom",
    }.get(tri, "-date_creation"))

    page = Paginator(produits, 12).get_page(request.GET.get("page"))
    # Paramètres de filtre conservés dans les liens de pagination
    filtres = request.GET.copy()
    filtres.pop("page", None)
    return render(request, "portail/catalogue.html", {
        "page": page, "q": q, "categorie": categorie, "marque": marque, "tri": tri,
        "categories": Categorie.objects.all(), "marques": Marque.objects.all(),
        "filtres": filtres.urlencode(),
    })


def produit(request, slug):
    p = get_object_or_404(_produits_visibles(), slug=slug)
    similaires = _produits_visibles().filter(categorie=p.categorie).exclude(pk=p.pk)[:4]
    return render(request, "portail/produit.html", {"produit": p, "similaires": similaires})


# ----------------------------------------------------------------------
#  Panier et commande
# ----------------------------------------------------------------------
@require_POST
def panier_ajouter(request, pk):
    p = get_object_or_404(_produits_visibles(), pk=pk)
    if not p.disponible:
        messages.error(request, f"« {p.nom} » est en rupture de stock.")
        return redirect(p.get_absolute_url())
    try:
        quantite = max(1, int(request.POST.get("quantite", 1)))
    except ValueError:
        quantite = 1
    Panier(request).ajouter(p, quantite)
    messages.success(request, f"« {p.nom} » ajouté au panier.")
    # "suivant" permet de rester sur la page d'origine ; on vérifie que c'est bien
    # une adresse de NOTRE site (protection contre les redirections malveillantes).
    suivant = request.POST.get("suivant", "")
    if suivant and url_has_allowed_host_and_scheme(suivant, allowed_hosts={request.get_host()}):
        return redirect(suivant)
    return redirect("portail:panier")


@require_POST
def panier_modifier(request, pk):
    p = get_object_or_404(Produit, pk=pk)
    try:
        quantite = int(request.POST.get("quantite", 0))
    except ValueError:
        quantite = 0
    Panier(request).ajouter(p, quantite, remplacer=True)
    return redirect("portail:panier")


@require_POST
def panier_retirer(request, pk):
    Panier(request).retirer(pk)
    return redirect("portail:panier")


def panier(request):
    pan = Panier(request)
    return render(request, "portail/panier.html", {"lignes": pan.lignes(), "total": pan.total})


def commander(request):
    """Formulaire de commande : crée le client (si nouveau), la commande et ses lignes."""
    pan = Panier(request)
    lignes = pan.lignes()
    if not lignes:
        messages.info(request, "Votre panier est vide.")
        return redirect("portail:catalogue")

    form = CommandeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            client = _client_par_telephone(d["nom"], d["telephone"], d["email"])
            commande = Commande.objects.create(
                client=client, mode_livraison=d["mode_livraison"],
                adresse_livraison=d["adresse_livraison"], message_client=d["message_client"],
            )
            for l in lignes:
                LigneCommande.objects.create(
                    commande=commande, produit=l["produit"], quantite=l["quantite"],
                    prix_unitaire=l["produit"].prix_vente,
                )
        pan.vider()
        # Notifications : confirmation au client + alerte à l'équipe
        notifier("CMD_RECUE", client, {"commande": commande})  # ignoré si le client n'a pas d'e-mail
        notifier("EQUIPE_CMD", None, {"commande": commande, "client": client})
        # On mémorise le n° en session pour afficher la page de confirmation
        request.session["derniere_commande"] = commande.numero
        return redirect("portail:commande_confirmee")
    return render(request, "portail/commander.html", {"form": form, "lignes": lignes, "total": pan.total})


def commande_confirmee(request):
    numero = request.session.get("derniere_commande")
    commande = Commande.objects.filter(numero=numero).first() if numero else None
    if not commande:
        return redirect("portail:accueil")
    return render(request, "portail/commande_confirmee.html", {"commande": commande})


# ----------------------------------------------------------------------
#  Suivi (commande / maintenance) sans compte client
# ----------------------------------------------------------------------
def suivi_commande(request):
    """Le client saisit son n° de commande + son téléphone (les deux doivent correspondre)."""
    form = SuiviCommandeForm(request.GET or None)
    commande = None
    if request.GET and form.is_valid():
        commande = (
            Commande.objects.select_related("client").prefetch_related("lignes__produit")
            .filter(numero__iexact=form.cleaned_data["numero"].strip(),
                    client__telephone=form.cleaned_data["telephone"])
            .first()
        )
        if not commande:
            messages.error(request, "Aucune commande ne correspond à ce numéro et ce téléphone.")
    return render(request, "portail/suivi_commande.html", {"form": form, "commande": commande})


def suivi_maintenance(request):
    """
    Le client saisit son n° de dossier + (son téléphone OU le code de suivi
    du bon de dépôt). Le lien reçu par e-mail pré-remplit ces deux champs.
    """
    # Le lien e-mail transmet "code" : on le recopie dans le champ du formulaire
    donnees = request.GET.copy()
    if "code" in donnees and "telephone" not in donnees:
        donnees["telephone"] = donnees["code"]
    form = SuiviMaintenanceForm(donnees or None)
    dossier = None
    if donnees and form.is_valid():
        secret = form.cleaned_data["telephone"].strip()
        dossier = (
            DossierMaintenance.objects.select_related("client").prefetch_related("historique")
            .filter(numero__iexact=form.cleaned_data["numero"].strip())
            .filter(Q(client__telephone=normaliser_telephone(secret)) | Q(code_suivi__iexact=secret))
            .first()
        )
        if not dossier:
            messages.error(request, "Aucun dossier ne correspond à ces informations.")
    return render(request, "portail/suivi_maintenance.html", {
        "form": form, "dossier": dossier, "etapes": DossierMaintenance.ETAPES,
    })


# ----------------------------------------------------------------------
#  Demandes de conseil (messagerie client <-> équipe)
# ----------------------------------------------------------------------
def conseil(request):
    initial = {}
    if request.GET.get("produit"):
        initial["produit"] = request.GET["produit"]
    form = ConseilForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            conv = Conversation.objects.create(
                client=Client.objects.filter(telephone=d["telephone"]).first(),
                nom=d["nom"], telephone=d["telephone"], email=d["email"],
                sujet=d["sujet"], produit=d["produit"],
            )
            msg = Message.objects.create(conversation=conv, auteur_type="CLIENT", texte=d["texte"])
        notifier("EQUIPE_CONSEIL", None, {"conversation": conv, "message": msg})
        messages.success(request, "Votre question a été transmise. Conservez l'adresse de cette page pour suivre la réponse.")
        return redirect(conv.get_absolute_url())
    return render(request, "portail/conseil.html", {"form": form})


def conversation(request, jeton):
    """Fil de discussion privé : accessible uniquement avec le lien secret (jeton)."""
    conv = get_object_or_404(Conversation, jeton=jeton)
    form = ReponseForm(request.POST or None)
    if request.method == "POST" and form.is_valid() and conv.statut != "CLOS":
        msg = Message.objects.create(conversation=conv, auteur_type="CLIENT", texte=form.cleaned_data["texte"])
        conv.statut = "ATTENTE"
        conv.date_maj = timezone.now()
        conv.save(update_fields=["statut", "date_maj"])
        notifier("EQUIPE_CONSEIL", None, {"conversation": conv, "message": msg})
        return redirect(conv.get_absolute_url())
    return render(request, "portail/conversation.html", {"conv": conv, "form": form})
