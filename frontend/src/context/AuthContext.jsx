import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiClient, BOUTIQUE_ACTIVE_KEY, memoriserIdBoutique } from "@/lib/api";

// Session du personnel : utilisateur connecté + sa boutique.
// La session vit dans un cookie HttpOnly (30 jours) : à l'ouverture du site,
// /auth/me suffit à retrouver l'utilisateur, sans rien retaper.
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [boutique, setBoutique] = useState(null);
  const [chargement, setChargement] = useState(true);

  // Relit la session (utilisateur + boutique) depuis l'API
  const rafraichir = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/auth/me");
      setUser(data.user);
      // Super-admin : boutique consultée = celle choisie dans /plateforme
      if (data.user.role === "super_admin") {
        const id = localStorage.getItem(BOUTIQUE_ACTIVE_KEY);
        setBoutique(id ? (await apiClient.get("/boutique")).data : null);
      } else {
        setBoutique(data.boutique);
      }
    } catch {
      // Pas de session (ou session expirée) : il faudra se connecter
      setUser(null);
      setBoutique(null);
    } finally {
      setChargement(false);
    }
  }, []);

  useEffect(() => {
    rafraichir();
  }, [rafraichir]);

  /** Connexion : ID boutique (vide pour le super-admin) + e-mail OU téléphone + mot de passe.
   *  Le serveur pose le cookie de session ; on retient seulement l'ID boutique. */
  async function connexion(codeBoutique, identifiant, password) {
    const { data } = await apiClient.post("/auth/login", { code_boutique: codeBoutique || null, identifiant, password });
    memoriserIdBoutique(codeBoutique);
    localStorage.removeItem(BOUTIQUE_ACTIVE_KEY);
    setUser(data.user);
    setBoutique(data.boutique);
    return data.user;
  }

  /** Déconnexion : le serveur efface le cookie de session */
  async function deconnexion() {
    try {
      await apiClient.post("/auth/logout");
    } catch { /* déjà déconnecté ou serveur injoignable : on nettoie quand même */ }
    localStorage.removeItem(BOUTIQUE_ACTIVE_KEY);
    setUser(null);
    setBoutique(null);
  }

  /** Changement de mot de passe (obligatoire après un mot de passe provisoire) */
  async function changerMotDePasse(ancien, nouveau) {
    await apiClient.post("/auth/mot-de-passe", { ancien, nouveau });
    setUser((u) => (u ? { ...u, doit_changer_mot_de_passe: false } : u));
  }

  /** Super-admin : choisir la boutique à consulter dans le back-office */
  async function choisirBoutique(id) {
    if (id) localStorage.setItem(BOUTIQUE_ACTIVE_KEY, id);
    else localStorage.removeItem(BOUTIQUE_ACTIVE_KEY);
    await rafraichir();
  }

  return (
    <AuthContext.Provider value={{ user, boutique, setBoutique, chargement, connexion, deconnexion, rafraichir, choisirBoutique, changerMotDePasse }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

/** Vrai si l'utilisateur a l'un des rôles donnés (le super-admin a tous les droits). */
export function aLeRole(user, ...roles) {
  return !!user && (user.role === "super_admin" || roles.includes(user.role));
}

/**
 * Vrai si l'utilisateur a la permission demandée. La liste des permissions
 * de chaque rôle est définie UNE seule fois côté serveur (table PERMISSIONS
 * de backend/auth.py) et renvoyée à la connexion dans user.permissions.
 * Exemples : peut(user, "facturation"), peut(user, "catalogue.edition").
 */
export function peut(user, permission) {
  return !!user && (user.role === "super_admin" || (user.permissions || []).includes(permission));
}
