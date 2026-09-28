"""Écrans d'administration de la messagerie (paramétrage + conversations)."""

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .models import Conversation, JournalEnvoi, Message, ModeleMessage, ParametresMessagerie
from .services import assurer_modeles_par_defaut, envoyer_email


class ParametresForm(forms.ModelForm):
    # Le mot de passe SMTP s'affiche masqué (●●●) ; laissé vide = inchangé
    smtp_mot_de_passe = forms.CharField(
        label="Mot de passe SMTP", required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Laisser vide pour conserver le mot de passe actuel.",
    )
    email_test = forms.EmailField(
        label="Envoyer un e-mail de test à", required=False,
        help_text="Facultatif : renseignez une adresse pour vérifier les réglages à l'enregistrement.",
    )

    class Meta:
        model = ParametresMessagerie
        fields = "__all__"

    def clean_smtp_mot_de_passe(self):
        mdp = self.cleaned_data.get("smtp_mot_de_passe")
        return mdp or (self.instance.smtp_mot_de_passe if self.instance.pk else "")


@admin.register(ParametresMessagerie)
class ParametresMessagerieAdmin(admin.ModelAdmin):
    form = ParametresForm
    fieldsets = (
        ("Activation", {"fields": ("email_actif", "url_site", "email_equipe")}),
        ("Serveur d'envoi (SMTP)", {"fields": (
            "smtp_hote", "smtp_port", "smtp_utilisateur", "smtp_mot_de_passe", "smtp_tls", "smtp_ssl",
        )}),
        ("Expéditeur", {"fields": ("expediteur_nom", "expediteur_email")}),
        ("Test", {"fields": ("email_test",)}),
    )

    # Fiche unique : pas de bouton « Ajouter » ni « Supprimer »
    def has_add_permission(self, request):
        return not ParametresMessagerie.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Un clic sur « Paramètres de messagerie » ouvre directement la fiche unique
        obj = ParametresMessagerie.get()
        return redirect(reverse("admin:messagerie_parametresmessagerie_change", args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        adresse = form.cleaned_data.get("email_test")
        if adresse:
            j = envoyer_email(adresse, "Test de messagerie", "Les réglages de messagerie fonctionnent.", "TEST")
            niveau = messages.SUCCESS if j.statut == "ENVOYE" else messages.WARNING
            detail = f" — {j.erreur}" if j.erreur else ""
            self.message_user(request, f"E-mail de test : {j.get_statut_display()}{detail}", niveau)


@admin.register(ModeleMessage)
class ModeleMessageAdmin(admin.ModelAdmin):
    list_display = ("code", "sujet", "actif")
    list_editable = ("actif",)

    def changelist_view(self, request, extra_context=None):
        # Crée les modèles par défaut à la première visite de la liste
        assurer_modeles_par_defaut()
        return super().changelist_view(request, extra_context)


@admin.register(JournalEnvoi)
class JournalEnvoiAdmin(admin.ModelAdmin):
    list_display = ("date", "code", "destinataire", "sujet", "statut")
    list_filter = ("statut", "code")
    search_fields = ("destinataire", "sujet")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class MessageInline(admin.StackedInline):
    """Fil de discussion ; la ligne vide en bas sert à écrire une RÉPONSE de l'équipe."""

    model = Message
    extra = 1
    fields = ("auteur_type", "texte", "date")
    readonly_fields = ("auteur_type", "date")

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("sujet", "nom", "telephone", "statut", "non_lus", "date_maj")
    list_filter = ("statut",)
    search_fields = ("sujet", "nom", "telephone", "email")
    readonly_fields = ("date_creation", "date_maj")
    inlines = [MessageInline]

    @admin.display(description="Non lus")
    def non_lus(self, obj):
        return obj.nb_non_lus or ""

    def change_view(self, request, object_id, form_url="", extra_context=None):
        # Ouvrir la conversation = marquer les messages du client comme lus
        Message.objects.filter(conversation_id=object_id, auteur_type="CLIENT").update(lu=True)
        return super().change_view(request, object_id, form_url, extra_context)

    def save_formset(self, request, form, formset, change):
        """Les messages saisis ici sont des réponses de l'équipe : on notifie le client."""
        from .services import notifier

        nouveaux = formset.save(commit=False)
        for msg in nouveaux:
            msg.auteur_type = "EQUIPE"
            msg.auteur = request.user
            msg.lu = True
            msg.save()
            conv = msg.conversation
            conv.statut = "REPONDU"
            conv.date_maj = timezone.now()
            conv.save(update_fields=["statut", "date_maj"])
            if conv.email:
                notifier("CONSEIL_REPONSE", conv.email, {"conversation": conv, "message": msg})
        formset.save_m2m()
