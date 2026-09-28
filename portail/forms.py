"""Formulaires du portail public (saisis par les visiteurs, donc tous validés)."""

from django import forms

from catalogue.models import Produit
from core.utils import normaliser_telephone
from ventes.models import Commande


class TelephoneField(forms.CharField):
    """Champ téléphone : normalisé automatiquement et contrôlé (au moins 8 chiffres)."""

    def clean(self, value):
        value = normaliser_telephone(super().clean(value))
        if len(value.lstrip("+")) < 8:
            raise forms.ValidationError("Numéro de téléphone invalide.")
        return value


class CommandeForm(forms.Form):
    nom = forms.CharField(label="Nom complet", max_length=150)
    telephone = TelephoneField(label="Téléphone", max_length=30)
    email = forms.EmailField(label="E-mail (facultatif, pour recevoir le suivi)", required=False)
    mode_livraison = forms.ChoiceField(
        label="Mode de réception", choices=Commande.LIVRAISON_CHOIX, widget=forms.RadioSelect,
        initial="RETRAIT",
    )
    adresse_livraison = forms.CharField(label="Adresse de livraison", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    message_client = forms.CharField(label="Message (facultatif)", widget=forms.Textarea(attrs={"rows": 2}), required=False)

    def clean(self):
        donnees = super().clean()
        if donnees.get("mode_livraison") == "LIVRAISON" and not donnees.get("adresse_livraison"):
            self.add_error("adresse_livraison", "Indiquez l'adresse de livraison.")
        return donnees


class SuiviCommandeForm(forms.Form):
    numero = forms.CharField(label="N° de commande", max_length=30, widget=forms.TextInput(attrs={"placeholder": "CMD-2026-00001"}))
    telephone = TelephoneField(label="Téléphone utilisé pour la commande", max_length=30)


class SuiviMaintenanceForm(forms.Form):
    numero = forms.CharField(label="N° de dossier", max_length=30, widget=forms.TextInput(attrs={"placeholder": "MNT-2026-00001"}))
    telephone = forms.CharField(
        label="Téléphone OU code de suivi (inscrit sur votre bon de dépôt)", max_length=30,
    )


class ConseilForm(forms.Form):
    nom = forms.CharField(label="Votre nom", max_length=150)
    telephone = TelephoneField(label="Téléphone", max_length=30)
    email = forms.EmailField(label="E-mail (pour être averti de la réponse)", required=False)
    produit = forms.ModelChoiceField(
        label="Produit concerné (facultatif)", required=False,
        queryset=Produit.objects.filter(actif=True, visible_portail=True),
    )
    sujet = forms.CharField(label="Sujet", max_length=200)
    texte = forms.CharField(label="Votre question", widget=forms.Textarea(attrs={"rows": 5}))


class ReponseForm(forms.Form):
    texte = forms.CharField(label="Votre message", widget=forms.Textarea(attrs={"rows": 3}))
