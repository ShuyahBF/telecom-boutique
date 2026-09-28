import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Case, Champ, ChoixImage } from "./communs";

// Champs de la fiche modifiables par le DG (PATCH /boutique).
// Le nom, le code marchand et le pays sont réservés à l'administrateur de la plateforme.
const CHAMPS = ["slogan", "adresse", "ville", "telephone", "email", "dg_nom", "ifu", "rccm", "cnss", "latitude", "longitude",
  "devise", "taux_tva_defaut", "prix_ttc", "validite_proforma_jours", "conditions_facture", "couleur", "paiement_mobile_money"];

// Transforme le texte saisi (« 12,3714 » ou « 12.3714 ») en nombre, ou null si vide / invalide
function versNombre(texte) {
  const t = String(texte ?? "").trim().replace(",", ".");
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

// Onglet « Ma boutique » : fiche d'identité, géolocalisation, réglages de facturation et logo.
export default function ParamBoutique() {
  const { boutique, setBoutique } = useAuth();
  const toast = useToast();

  // Copie modifiable de la fiche (initialisée avec les valeurs actuelles)
  const [fiche, setFiche] = useState(() => Object.fromEntries(CHAMPS.map((c) => [c, boutique[c] ?? ""])));
  const [envoi, setEnvoi] = useState(false);
  const [localisation, setLocalisation] = useState(false); // recherche GPS en cours
  const maj = (champ, valeur) => setFiche((f) => ({ ...f, [champ]: valeur }));

  // Coordonnées actuellement saisies (null si vides ou invalides)
  const lat = versNombre(fiche.latitude);
  const lng = versNombre(fiche.longitude);
  const coordonneesValides = lat !== null && lng !== null && Math.abs(lat) <= 90 && Math.abs(lng) <= 180;
  // Lien vers la carte OpenStreetMap centrée sur la boutique (s'ouvre dans un nouvel onglet)
  const lienCarte = coordonneesValides
    ? `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=18/${lat}/${lng}`
    : null;

  // Bouton « Utiliser ma position actuelle » : le navigateur demande l'autorisation,
  // puis renvoie la position GPS du téléphone / de l'ordinateur (à faire DANS la boutique)
  function utiliserMaPosition() {
    if (!navigator.geolocation) {
      toast.erreur("Votre navigateur ne sait pas donner votre position : saisissez-la à la main.");
      return;
    }
    setLocalisation(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // 6 décimales ≈ 10 cm de précision : largement suffisant
        maj("latitude", pos.coords.latitude.toFixed(6));
        maj("longitude", pos.coords.longitude.toFixed(6));
        setLocalisation(false);
        toast.succes("Position trouvée : pensez à enregistrer la fiche");
      },
      (err) => {
        setLocalisation(false);
        toast.erreur(err.code === 1
          ? "Accès à la position refusé : autorisez-le dans le navigateur ou saisissez les coordonnées."
          : "Position introuvable pour le moment : réessayez ou saisissez les coordonnées.");
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  }

  // Enregistrement de la fiche, puis mise à jour de la boutique en mémoire (menu, couleurs…)
  async function enregistrer(e) {
    e.preventDefault();
    // Coordonnées : les deux ou aucune, et dans les bornes (latitude ±90, longitude ±180)
    if ((String(fiche.latitude).trim() || String(fiche.longitude).trim()) && !coordonneesValides) {
      toast.erreur("Coordonnées invalides : latitude entre -90 et 90, longitude entre -180 et 180 (ex. 12.371400 et -1.519700).");
      return;
    }
    setEnvoi(true);
    try {
      const { data } = await apiClient.patch("/boutique", {
        ...fiche,
        email: fiche.email.trim(), // e-mail vide "" = effacer l'e-mail de contact
        // Coordonnées vides : non envoyées (null = « ne pas changer » pour le serveur)
        latitude: coordonneesValides ? lat : null,
        longitude: coordonneesValides ? lng : null,
        taux_tva_defaut: Number(fiche.taux_tva_defaut) || 0,
        validite_proforma_jours: Number(fiche.validite_proforma_jours) || 15,
      });
      setBoutique(data);
      setFiche(Object.fromEntries(CHAMPS.map((c) => [c, data[c] ?? ""])));
      // Modifier IFU, RCCM, CNSS ou nom du DG remet le dossier KYC « en attente » (revérification)
      const kycRelance = data.kyc?.statut === "EN_ATTENTE" && boutique.kyc?.statut !== "EN_ATTENTE";
      toast.succes(kycRelance ? "Fiche enregistrée. Informations légales modifiées : dossier KYC à revérifier." : "Fiche de la boutique enregistrée");
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez les champs (e-mail, couleur, taux de TVA…)"));
    } finally {
      setEnvoi(false);
    }
  }

  // Envoi du logo (multipart/form-data, champ « fichier »)
  async function envoyerLogo(fichier) {
    const f = new FormData();
    f.append("fichier", fichier);
    try {
      const { data } = await apiClient.post("/boutique/logo", f);
      setBoutique({ ...boutique, logo_url: data.logo_url });
      toast.succes("Logo enregistré");
    } catch (err) {
      toast.erreur(messageErreur(err, "Image refusée (JPEG, PNG ou WebP, 5 Mo maximum)"));
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <form onSubmit={enregistrer} className="space-y-5 lg:col-span-2">
        {/* Identité : nom et code marchand en lecture seule */}
        <div className="card grid gap-4 sm:grid-cols-2">
          <h2 className="font-bold sm:col-span-2">Identité</h2>
          <Champ label="Nom de la boutique" aide="Modifiable par l'administrateur de la plateforme."><input className="input bg-gray-50" value={boutique.nom} disabled /></Champ>
          <Champ label="ID boutique (code marchand)" aide="À taper par votre équipe pour se connecter. Modifiable par l'administrateur de la plateforme."><input className="input bg-gray-50 font-mono" value={boutique.code_marchand} disabled /></Champ>
          <Champ label="Pays" aide="Modifiable par l'administrateur de la plateforme."><input className="input bg-gray-50" value={boutique.pays || "—"} disabled /></Champ>
          <Champ label="Nom du DG (Directeur Général)" aide="Tel qu'il figure sur sa pièce d'identité."><input className="input" maxLength={120} value={fiche.dg_nom} onChange={(e) => maj("dg_nom", e.target.value)} /></Champ>
          <Champ label="Slogan" className="sm:col-span-2"><input className="input" maxLength={200} value={fiche.slogan} onChange={(e) => maj("slogan", e.target.value)} placeholder="ex. Le meilleur prix sur vos smartphones" /></Champ>
          <Champ label="Adresse" className="sm:col-span-2"><input className="input" maxLength={500} value={fiche.adresse} onChange={(e) => maj("adresse", e.target.value)} placeholder="ex. Avenue Kwame Nkrumah, en face de la pharmacie" /></Champ>
          <Champ label="Ville"><input className="input" maxLength={80} value={fiche.ville} onChange={(e) => maj("ville", e.target.value)} /></Champ>
          <Champ label="Téléphone"><input className="input" maxLength={30} value={fiche.telephone} onChange={(e) => maj("telephone", e.target.value)} /></Champ>
          <Champ label="E-mail de contact"><input className="input" type="email" value={fiche.email} onChange={(e) => maj("email", e.target.value)} /></Champ>
          <Champ label="Couleur de la boutique" aide="Utilisée sur votre vitrine en ligne.">
            <div className="flex items-center gap-3">
              <input type="color" className="h-11 w-16 cursor-pointer rounded-lg border border-gray-300 bg-white p-1" value={fiche.couleur || "#1e90ff"} onChange={(e) => maj("couleur", e.target.value)} />
              <span className="font-mono text-sm text-gray-600">{fiche.couleur}</span>
            </div>
          </Champ>
        </div>

        {/* Géolocalisation : permet aux clients de trouver la boutique (itinéraire) */}
        <div className="card grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <h2 className="font-bold">Géolocalisation</h2>
            <p className="text-sm text-gray-500">Position GPS de la boutique, utilisée pour l'itinéraire sur votre vitrine. Le plus simple : cliquez sur le bouton ci-dessous en étant dans la boutique.</p>
          </div>
          <Champ label="Latitude" aide="Entre -90 et 90 (ex. 12.371400)"><input className="input font-mono" inputMode="decimal" value={fiche.latitude} onChange={(e) => maj("latitude", e.target.value)} placeholder="12.371400" /></Champ>
          <Champ label="Longitude" aide="Entre -180 et 180 (ex. -1.519700)"><input className="input font-mono" inputMode="decimal" value={fiche.longitude} onChange={(e) => maj("longitude", e.target.value)} placeholder="-1.519700" /></Champ>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
            <button type="button" className="btn-outline btn-sm" onClick={utiliserMaPosition} disabled={localisation}>
              {localisation ? "Recherche de la position…" : "📍 Utiliser ma position actuelle"}
            </button>
            {lienCarte
              ? <a href={lienCarte} target="_blank" rel="noreferrer" className="text-sm font-semibold text-primary">🗺️ Voir sur la carte ↗</a>
              : <span className="text-sm text-gray-500">Aucune position enregistrée.</span>}
          </div>
        </div>

        {/* Mentions légales et facturation */}
        <div className="card grid gap-4 sm:grid-cols-2">
          <h2 className="font-bold sm:col-span-2">Informations légales et facturation</h2>
          <Champ label="IFU"><input className="input" maxLength={50} value={fiche.ifu} onChange={(e) => maj("ifu", e.target.value)} /></Champ>
          <Champ label="RCCM"><input className="input" maxLength={60} value={fiche.rccm} onChange={(e) => maj("rccm", e.target.value)} /></Champ>
          <Champ label="N° CNSS" aide="Numéro d'employeur à la Caisse nationale de sécurité sociale."><input className="input" maxLength={50} value={fiche.cnss} onChange={(e) => maj("cnss", e.target.value)} /></Champ>
          <p className="self-end text-xs text-gray-500">Modifier le nom du DG, l'IFU, le RCCM ou la CNSS remet votre dossier KYC « en attente de vérification ».</p>
          <Champ label="Devise"><input className="input" maxLength={10} value={fiche.devise} onChange={(e) => maj("devise", e.target.value)} /></Champ>
          <Champ label="Taux de TVA par défaut (%)"><input className="input" type="number" min={0} max={100} step="0.01" value={fiche.taux_tva_defaut} onChange={(e) => maj("taux_tva_defaut", e.target.value)} /></Champ>
          <Champ label="Validité des proformas (jours)"><input className="input" type="number" min={1} max={365} value={fiche.validite_proforma_jours} onChange={(e) => maj("validite_proforma_jours", e.target.value)} /></Champ>
          <div className="sm:col-span-2"><Case label="Prix du catalogue exprimés TTC" aide="Coché : les prix de vente saisis incluent la TVA. Décoché : ils sont hors taxes." checked={fiche.prix_ttc} onChange={(v) => maj("prix_ttc", v)} /></div>
          <div className="sm:col-span-2"><Case label="Paiement Mobile Money activé" aide="Les clients peuvent payer leurs commandes en ligne par Orange Money, Moov Money… Actif seulement une fois votre dossier d'identification (onglet KYC) validé par adLyn." checked={fiche.paiement_mobile_money} onChange={(v) => maj("paiement_mobile_money", v)} /></div>
          <Champ label="Mentions en pied de facture" className="sm:col-span-2"><textarea className="input" rows={3} maxLength={1000} value={fiche.conditions_facture} onChange={(e) => maj("conditions_facture", e.target.value)} /></Champ>
        </div>

        <button className="btn-primary w-full sm:w-auto" disabled={envoi}>{envoi ? "Enregistrement…" : "💾 Enregistrer la fiche"}</button>
      </form>

      {/* Logo */}
      <div className="card h-fit">
        <h2 className="mb-3 font-bold">Logo</h2>
        <ChoixImage image={boutique.logo_url} onEnvoyer={envoyerLogo} />
        <p className="mt-3 text-center text-xs text-gray-500">Affiché sur vos factures, votre vitrine et l'affiche QR code. Un format carré sur fond clair rend mieux.</p>
      </div>
    </div>
  );
}
