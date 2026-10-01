import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import ChampMotDePasse from "@/components/ChampMotDePasse";

// Page « Mon compte » (tout membre du personnel connecté) : ses identifiants
// de connexion (e-mail et/ou téléphone) et son mot de passe.
//   - Ajouter / changer : mot de passe actuel + nouvelle valeur -> un code est
//     envoyé À LA NOUVELLE VALEUR (WhatsApp ou SMS pour un numéro, e-mail pour
//     une adresse) -> saisie du code.
//   - Vérifier : même chose avec la valeur actuelle (prouve qu'elle est à vous).
//   - Retirer : possible seulement si l'AUTRE identifiant existe et est vérifié.
const TYPES = {
  email: { libelle: "E-mail", icone: "✉️", saisie: "vous@exemple.com", type: "email", canal: "par e-mail" },
  telephone: { libelle: "Téléphone (WhatsApp)", icone: "📱", saisie: "70 12 34 56 ou +226 70 12 34 56", type: "tel", canal: "par WhatsApp (ou SMS)" },
};

export default function MonCompte() {
  const { user, chargement, rafraichir } = useAuth();
  const navigate = useNavigate();
  // Fenêtre ouverte : { action: "changer" | "retirer", type, etape: "saisie" | "code", valeur, motDePasse, code, info }
  const [fenetre, setFenetre] = useState(null);
  const [erreur, setErreur] = useState("");
  const [succes, setSucces] = useState("");
  const [envoi, setEnvoi] = useState(false);

  if (chargement) return <Chargement plein />;
  if (!user) return <Navigate to="/connexion" replace />;
  const accueil = user.role === "super_admin" ? "/plateforme" : "/gestion";

  function ouvrir(action, type, valeur = "") {
    setErreur("");
    setSucces("");
    setFenetre({ action, type, etape: "saisie", valeur, motDePasse: "", code: "", info: "" });
  }
  const maj = (champs) => setFenetre((f) => ({ ...f, ...champs }));

  // Appel à l'API avec gestion commune de l'attente et des erreurs
  async function appel(fonction) {
    setErreur("");
    setEnvoi(true);
    try {
      await fonction();
    } catch (err) {
      setErreur(messageErreur(err, "Opération impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  // Étape 1 : envoi du code à la nouvelle valeur
  const demanderCode = (e) => {
    e.preventDefault();
    return appel(async () => {
      const { data } = await apiClient.post("/auth/identifiant/demande", { type: fenetre.type, valeur: fenetre.valeur, mot_de_passe: fenetre.motDePasse });
      maj({ etape: "code", info: data.message, motDePasse: "" });
    });
  };

  // Étape 2 : confirmation par le code reçu
  const confirmerCode = (e) => {
    e.preventDefault();
    return appel(async () => {
      await apiClient.post("/auth/identifiant/confirmer", { type: fenetre.type, code: fenetre.code });
      await rafraichir();
      setFenetre(null);
      setSucces(`${TYPES[fenetre.type].libelle} enregistré et vérifié. Vous pouvez l'utiliser pour vous connecter.`);
    });
  };

  // Retrait d'un identifiant (mot de passe exigé)
  const retirer = (e) => {
    e.preventDefault();
    return appel(async () => {
      await apiClient.post("/auth/identifiant/retirer", { type: fenetre.type, mot_de_passe: fenetre.motDePasse });
      await rafraichir();
      setFenetre(null);
      setSucces(`${TYPES[fenetre.type].libelle} retiré de votre compte.`);
    });
  };

  // Une carte par identifiant
  const carte = (type) => {
    const t = TYPES[type];
    const autre = type === "email" ? "telephone" : "email";
    const valeur = user[type];
    const verifie = !!user[`${type}_verifie`];
    const retirable = valeur && user[autre] && user[`${autre}_verifie`];
    return (
      <div key={type} className="rounded-xl border border-gray-200 p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-gray-600">{t.icone} {t.libelle}</p>
          {valeur && (verifie
            ? <span className="badge bg-green-100 text-green-800">✓ vérifié</span>
            : <span className="badge bg-amber-100 text-amber-800">non vérifié</span>)}
        </div>
        <p className="mt-1 break-all font-mono">{valeur || <span className="font-sans text-gray-400">Aucun</span>}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="btn-outline btn-sm" onClick={() => ouvrir("changer", type)}>{valeur ? "Changer" : "Ajouter"}</button>
          {valeur && !verifie && <button type="button" className="btn-outline btn-sm" onClick={() => ouvrir("changer", type, valeur)}>Vérifier</button>}
          {retirable && <button type="button" className="btn-outline btn-sm text-red-600" onClick={() => ouvrir("retirer", type)}>Retirer</button>}
        </div>
      </div>
    );
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary to-primary-dark p-4">
      <div className="w-full max-w-md space-y-4 rounded-3xl bg-white p-8 shadow-xl">
        <div className="text-center">
          <p className="text-3xl">👤</p>
          <h1 className="mt-1 text-xl font-extrabold">Mon compte</h1>
          <p className="text-sm text-gray-500">{user.nom}</p>
        </div>

        {user.role === "super_admin" ? (
          <p className="rounded-lg bg-gray-50 p-3 text-sm text-gray-600">
            Compte administrateur : son e-mail de connexion est fixé par la configuration du serveur (SUPER_ADMIN_EMAIL).
          </p>
        ) : (
          <>
            <p className="text-sm text-gray-600">
              Vous pouvez vous connecter avec votre <b>e-mail</b> ou votre <b>numéro de téléphone</b>. En cas d'oubli
              du mot de passe, le code de réinitialisation est envoyé en priorité par <b>WhatsApp</b>.
            </p>
            {carte("telephone")}
            {carte("email")}
          </>
        )}
        {succes && <p className="rounded-lg bg-green-50 p-2 text-sm text-green-800">{succes}</p>}

        <Link to="/mot-de-passe" className="btn-outline block w-full text-center">🔑 Changer mon mot de passe</Link>
        <div className="text-center text-sm">
          <button type="button" className="text-primary" onClick={() => navigate(accueil)}>← Retour</button>
        </div>
      </div>

      {/* Fenêtre : ajouter / changer / vérifier, puis code */}
      <Modal ouvert={fenetre?.action === "changer"} titre={fenetre ? `${TYPES[fenetre.type].libelle} de connexion` : ""} onFermer={() => setFenetre(null)}>
        {fenetre?.action === "changer" && fenetre.etape === "saisie" && (
          <form onSubmit={demanderCode} className="space-y-3">
            <label className="block"><span className="label">{fenetre.type === "email" ? "Adresse e-mail" : "Numéro de téléphone"}</span>
              <input className="input" type={TYPES[fenetre.type].type} required placeholder={TYPES[fenetre.type].saisie}
                value={fenetre.valeur} onChange={(e) => maj({ valeur: e.target.value })} /></label>
            <label className="block"><span className="label">Votre mot de passe actuel</span>
              <ChampMotDePasse required autoComplete="current-password"
                value={fenetre.motDePasse} onChange={(e) => maj({ motDePasse: e.target.value })} /></label>
            <p className="text-xs text-gray-500">Un code à 6 chiffres sera envoyé {TYPES[fenetre.type].canal} à cette nouvelle valeur pour vérifier qu'elle est bien à vous.</p>
            {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
            <button className="btn-primary w-full" disabled={envoi}>{envoi ? "Envoi du code…" : "Recevoir le code"}</button>
          </form>
        )}
        {fenetre?.action === "changer" && fenetre.etape === "code" && (
          <form onSubmit={confirmerCode} className="space-y-3">
            <p className="rounded-lg bg-blue-50 p-2 text-sm text-blue-800">{fenetre.info}</p>
            <label className="block"><span className="label">Code reçu (6 chiffres)</span>
              <ChampMotDePasse className="input text-center font-mono text-2xl tracking-[0.5em]" required inputMode="numeric" autoComplete="one-time-code"
                maxLength={6} value={fenetre.code} onChange={(e) => maj({ code: e.target.value.replace(/\D/g, "").slice(0, 6) })} /></label>
            {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
            <button className="btn-primary w-full" disabled={envoi || fenetre.code.length !== 6}>{envoi ? "Vérification…" : "Confirmer"}</button>
            <button type="button" className="w-full text-sm text-gray-500" onClick={() => maj({ etape: "saisie", code: "" })}>← Modifier la valeur ou renvoyer un code</button>
          </form>
        )}
      </Modal>

      {/* Fenêtre : retrait d'un identifiant */}
      <Modal ouvert={fenetre?.action === "retirer"} titre={fenetre ? `Retirer : ${TYPES[fenetre.type].libelle}` : ""} onFermer={() => setFenetre(null)}>
        {fenetre?.action === "retirer" && (
          <form onSubmit={retirer} className="space-y-3">
            <p className="text-sm text-gray-600">Vous ne pourrez plus vous connecter avec <b>{user[fenetre.type]}</b>. Votre autre identifiant (vérifié) reste valable.</p>
            <label className="block"><span className="label">Votre mot de passe actuel</span>
              <ChampMotDePasse required autoComplete="current-password"
                value={fenetre.motDePasse} onChange={(e) => maj({ motDePasse: e.target.value })} /></label>
            {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
            <button className="btn-primary w-full bg-red-600 hover:bg-red-700" disabled={envoi}>{envoi ? "Retrait…" : "Retirer"}</button>
          </form>
        )}
      </Modal>
    </div>
  );
}
