import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiClient, BOUTIQUE_ACTIVE_KEY, TOKEN_KEY } from "@/lib/api";

// Session du personnel : utilisateur connecté + sa boutique.
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [boutique, setBoutique] = useState(null);
  const [chargement, setChargement] = useState(true);

  // Relit la session (utilisateur + boutique) depuis l'API
  const rafraichir = useCallback(async () => {
    if (!localStorage.getItem(TOKEN_KEY)) {
      setUser(null);
      setBoutique(null);
      setChargement(false);
      return;
    }
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
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
      setBoutique(null);
    } finally {
      setChargement(false);
    }
  }, []);

  useEffect(() => {
    rafraichir();
  }, [rafraichir]);

  async function connexion(email, password) {
    const { data } = await apiClient.post("/auth/login", { email, password });
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.removeItem(BOUTIQUE_ACTIVE_KEY);
    setUser(data.user);
    setBoutique(data.boutique);
    return data.user;
  }

  function deconnexion() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(BOUTIQUE_ACTIVE_KEY);
    setUser(null);
    setBoutique(null);
  }

  /** Super-admin : choisir la boutique à consulter dans le back-office */
  async function choisirBoutique(id) {
    if (id) localStorage.setItem(BOUTIQUE_ACTIVE_KEY, id);
    else localStorage.removeItem(BOUTIQUE_ACTIVE_KEY);
    await rafraichir();
  }

  return (
    <AuthContext.Provider value={{ user, boutique, setBoutique, chargement, connexion, deconnexion, rafraichir, choisirBoutique }}>
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
